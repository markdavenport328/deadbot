// The classic shell: the original default page, a start view and then one page
// per question. It is still the default; the other shells are chosen with
// ?shell=<name> (see ../../shells.ts).
import { type FormEvent, type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { type AskFocus, type ExperienceResponse } from "../../types";
import { loadRequestedStreamEvents, loadRequestedVisualFixture, requestedStreamFixture, requestedVisualFixture } from "../../visual-fixture-loader";
import { askRequestBody } from "../../core/ask-request";
import { clearStoredNotebook, readStoredNotebook, storeNotebook } from "../../core/research-notebook";
import { ASK_ERROR, askPlain, askStreaming, createThreadId, replayStreamEvents } from "../../core/ask-client";
import { applyPageEvent, groupsOfResponse, type Draft } from "../../core/page-draft";
import { currentPath, takeQuestionFromUrl, useAskFromPage } from "../../core/site-nav";
import { renderInline } from "../../cards/inline";
import { ComposedPage } from "../../cards/PageGroups";
import { NowPlayingBar } from "../../player/NowPlayingBar";
import { PHONE_QUERY, useMediaQuery } from "../../core/media-query";
import { StartLibrary } from "./StartLibrary";

// The dock's send: an arrow up, the direction the question travels.
function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-6 6m6-6l6 6" />
    </svg>
  );
}

// Reload after a deploy, checked only when a tab comes back into view and at
// most every few minutes. A timer would keep every forgotten background tab
// calling the server around the clock.
const VERSION_CHECK_INTERVAL_MS = 5 * 60_000;

let lastVersionCheck = 0;

async function refreshIfServerChanged(): Promise<void> {
  const now = Date.now();
  if (now - lastVersionCheck < VERSION_CHECK_INTERVAL_MS) return;
  lastVersionCheck = now;
  const result = await fetch("/api/version", { cache: "no-store" });
  if (!result.ok) return;
  const health = await result.json() as { git_commit?: string };
  const current = health.git_commit;
  if (!current || current === "unknown") return;
  const storageKey = "deadbot-server-version";
  const previous = sessionStorage.getItem(storageKey);
  sessionStorage.setItem(storageKey, current);
  if (previous && previous !== current) window.location.reload();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function ClassicApp() {
  // A named `?fixture=` response is available only in Vite development. It
  // gives visual reviewers the actual app chrome and renderers without a live
  // model request or a testing-only control in the visitor experience.
  const visualFixture = requestedVisualFixture;
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<ExperienceResponse | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeThreadId, setActiveThreadId] = useState(createThreadId);
  // What this conversation's research has found so far, signed by the
  // server. It goes back with each follow-up and is replaced by each answer.
  const [notebook, setNotebook] = useState<string | null>(readStoredNotebook);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingStartsFresh, setPendingStartsFresh] = useState(false);
  // What Deadbot is doing right now, one line per tool call, newest last.
  const [progress, setProgress] = useState<string[]>([]);
  // The final answer's text as it streams in, replaced wholesale per event.
  const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null);
  // How many progress lines existed when the answer started, so the chat can
  // show only the statuses that arrived after the answer, not the whole run.
  const [answerProgressStart, setAnswerProgressStart] = useState<number | null>(null);
  const threadContainer = useRef<HTMLElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const conversationPaneRef = useRef<HTMLElement>(null);
  // Phone layout: the ask box and player sit in a dock fixed at the foot of
  // the screen instead of in the rail and the answer pane.
  const isPhone = useMediaQuery(PHONE_QUERY);
  const dockRef = useRef<HTMLDivElement>(null);
  const dockTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [composerFocused, setComposerFocused] = useState(false);
  // Callbacks passed into askStreaming close over stale render state, so track
  // whether the answer has already started in a ref.
  const answerStartedRef = useRef(false);
  // Set right before a successful response lands, so the focus/live-region
  // effect below knows this render is the one to act on rather than firing on
  // every unrelated response change (a `?fixture=` load, for instance).
  const askJustCompletedRef = useRef(false);

  // The start screen is the whole content area until a question is asked (or
  // one is already in flight, or already answered). It drives both the empty
  // layout and the initial animation phase below.
  const atStart = !response && !loading && !pendingQuestion;

  // The ask transition's state machine. Emil Kowalski's rules: transform and
  // opacity only, never ease-in. "start" is the still, rail-less home screen;
  // "leaving" fades the lead and library while the composer stays put;
  // "opening" snaps the rail and content pane off-canvas with no transition
  // the instant the real layout replaces the start screen; "arriving" turns
  // the transitions on for one frame later so the browser animates from that
  // off-canvas position back to rest; "settled" is the ordinary, resting page.
  const [phase, setPhase] = useState<"start" | "leaving" | "opening" | "arriving" | "settled">(atStart ? "start" : "settled");
  // A visually hidden status line, announced once per answer instead of on
  // every render (finding 3).
  const [answerReadyMessage, setAnswerReadyMessage] = useState<string | null>(null);

  useEffect(() => {
    const thread = threadContainer.current;
    if (!thread) return;
    // Keep streaming updates inside the conversation's scroll area. Scrolling
    // an end sentinel into view can move the entire page away from the guide.
    thread.scrollTo({
      top: thread.scrollHeight,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"
    });
  }, [loading, pendingQuestion, response, progress, streamingAnswer]);

  // The page keeps room under the dock: its measured height becomes a CSS
  // variable the shell pads by. Nothing to measure means no padding.
  useLayoutEffect(() => {
    const root = document.documentElement;
    const dock = dockRef.current;
    if (!dock) {
      root.style.setProperty("--dock-h", "0px");
      return;
    }
    const measure = () => root.style.setProperty("--dock-h", `${dock.getBoundingClientRect().height}px`);
    measure();
    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(measure);
    observer.observe(dock);
    return () => observer.disconnect();
  }, [isPhone, atStart]);

  // On iOS the keyboard covers a fixed footer rather than shrinking the page,
  // so the dock follows the visual viewport: the gap between the layout
  // viewport's bottom and the visual one's is how far the dock lifts.
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    if (!isPhone || !viewport) {
      root.style.setProperty("--kb", "0px");
      return;
    }
    const update = () => {
      const covered = Math.max(0, window.innerHeight - (viewport.height + viewport.offsetTop));
      root.style.setProperty("--kb", `${Math.round(covered)}px`);
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      root.style.setProperty("--kb", "0px");
    };
  }, [isPhone]);

  // The dock's ask box is one line tall and grows with what is typed; the
  // stylesheet caps it at a few lines, after which it scrolls inside.
  useLayoutEffect(() => {
    const field = dockTextareaRef.current;
    if (!field) return;
    // Empty, the field is its one row; a wrapped placeholder must not grow it.
    field.style.height = "";
    if (question.trim()) {
      field.style.height = "auto";
      field.style.height = `${field.scrollHeight}px`;
    }
  }, [question, isPhone, atStart]);

  useEffect(() => {
    if (visualFixture || requestedStreamFixture) return;
    void refreshIfServerChanged();
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshIfServerChanged();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [visualFixture]);

  useEffect(() => {
    if (!visualFixture) return;
    void loadRequestedVisualFixture().then((fixture) => {
      if (fixture) setResponse(fixture);
    });
  }, [visualFixture]);

  // Once the app switches out of the start screen ("opening"), measure the
  // rail's actual width and hand it to the content pane as a CSS variable, so
  // the content pane's opening translateX matches the rail exactly even if
  // the rail isn't the 310px the grid track defaults to. Two nested rAFs
  // force a reflow at the off-canvas position before "arriving" turns the
  // transitions on, so the browser animates from there rather than skipping
  // straight to rest.
  const innerFrameRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (phase !== "opening") return;
    const rail = conversationPaneRef.current;
    const workspace = workspaceRef.current;
    if (rail && workspace) {
      workspace.style.setProperty("--rail-w", `${rail.getBoundingClientRect().width}px`);
    }
    const outer = requestAnimationFrame(() => {
      const inner = requestAnimationFrame(() => setPhase("arriving"));
      innerFrameRef.current = inner;
    });
    return () => {
      cancelAnimationFrame(outer);
      if (innerFrameRef.current !== null) cancelAnimationFrame(innerFrameRef.current);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== "arriving") return;
    const timer = window.setTimeout(() => setPhase("settled"), 1300);
    return () => window.clearTimeout(timer);
  }, [phase]);

  // Move focus to the answer heading once a response actually lands from an
  // ask (never on a `?fixture=` load, which never sets the ref). The page has
  // usually streamed in and the visitor may already be reading further down,
  // so focus moves without scrolling them back to the top.
  useEffect(() => {
    if (!response || !askJustCompletedRef.current) return;
    askJustCompletedRef.current = false;
    document.getElementById("answer-title")?.focus({ preventScroll: true });
  }, [response]);

  // The dev `?stream=` fixture replays a canned event sequence through the
  // same dispatch the network path uses, so progressive rendering can be
  // reviewed without a model. It no longer starts itself on mount: askQuestion
  // triggers it, the same way it triggers a real request, so the start screen
  // and the ask transition are both exercised by simply asking a question.
  async function replayStreamFixture(): Promise<void> {
    const events = await loadRequestedStreamEvents();
    if (!events) return;
    let statusCount = 0;
    await replayStreamEvents(events, {
      onStatus: (status) => {
        statusCount += 1;
        setProgress((lines) => [...lines, status]);
      },
      onLead: (text) => {
        if (!answerStartedRef.current) {
          answerStartedRef.current = true;
          setAnswerProgressStart(statusCount);
        }
        setStreamingAnswer(text);
      },
      onPage: (pageEvent) => setDraft((current) => applyPageEvent(current, pageEvent)),
      onResponse: (nextResponse) => {
        setResponse(nextResponse);
        setAnswerReadyMessage(`Answer ready: ${nextResponse.headline ?? nextResponse.lead}`);
        askJustCompletedRef.current = true;
        setLoading(false);
        setPendingQuestion(null);
        setPendingStartsFresh(false);
        setProgress([]);
        setStreamingAnswer(null);
        setAnswerProgressStart(null);
        setDraft(null);
      }
    });
  }

  async function askQuestion(nextQuestion?: string, { fresh = false, focus }: { fresh?: boolean; focus?: AskFocus } = {}) {
    if (visualFixture) return;
    const trimmed = (nextQuestion ?? question).trim();
    if (!trimmed || loading) return;

    const cameFromStart = phase === "start";
    if (cameFromStart) {
      setPhase("leaving");
      await delay(180);
    }

    const requestThreadId = fresh ? createThreadId() : activeThreadId;
    const conversation = fresh ? [] : response?.conversation ?? [];
    // The notebook belongs to the answer on screen; with none showing (a
    // reload, the start page) the question starts its own research.
    const sentNotebook = fresh || !response ? null : notebook;
    if (fresh) {
      setActiveThreadId(requestThreadId);
      setResponse(null);
      setNotebook(null);
      clearStoredNotebook();
    }
    setPendingQuestion(trimmed);
    setPendingStartsFresh(fresh);
    setQuestion("");
    setLoading(true);
    setError(null);
    setProgress([]);
    setStreamingAnswer(null);
    setDraft(null);
    setAnswerReadyMessage(null);
    answerStartedRef.current = false;
    if (cameFromStart) setPhase("opening");
    if (isPhone && !cameFromStart) {
      // The conversation is at the top of the one-column page; the ask box is
      // at the foot. Return to where the answer will appear.
      window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    }

    if (import.meta.env.DEV && requestedStreamFixture) {
      await replayStreamFixture();
      return;
    }

    const body = askRequestBody({ question: trimmed, threadId: requestThreadId, conversation, focus, notebook: sentNotebook });
    try {
      let statusCount = 0;
      const streamed = await askStreaming(body, {
        onStatus: (status) => {
          statusCount += 1;
          setProgress((lines) => [...lines, status]);
        },
        onLead: (text) => {
          if (!answerStartedRef.current) {
            answerStartedRef.current = true;
            setAnswerProgressStart(statusCount);
          }
          setStreamingAnswer(text);
        },
        onPage: (event) => setDraft((current) => applyPageEvent(current, event))
      });
      const finalResponse = streamed ?? await askPlain(body);
      // An answer without a notebook means the server could not use ours
      // (or has none to give); the stale token goes rather than lingering.
      setNotebook(finalResponse.notebook ?? null);
      storeNotebook(finalResponse.notebook);
      setResponse(finalResponse);
      setAnswerReadyMessage(`Answer ready: ${finalResponse.headline ?? finalResponse.lead}`);
      askJustCompletedRef.current = true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : ASK_ERROR);
      if (cameFromStart) setPhase("start");
    } finally {
      setLoading(false);
      setPendingQuestion(null);
      setPendingStartsFresh(false);
      setProgress([]);
      setStreamingAnswer(null);
      setAnswerProgressStart(null);
      setDraft(null);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await askQuestion();
  }

  function chooseFollowUp(prompt: string, focus?: AskFocus) {
    void askQuestion(prompt, { focus });
  }

  useAskFromPage((prompt) => void askQuestion(prompt, { fresh: true }));

  // A link can carry the opening question (`/?q=…`); it is asked as soon as
  // the home screen is up, the same as if the visitor had typed it.
  useEffect(() => {
    if (visualFixture || currentPath() !== "/") return;
    const linked = takeQuestionFromUrl();
    if (linked) void askQuestion(linked, { fresh: true });
    // Read once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startNewChat() {
    if (loading) return;
    setActiveThreadId(createThreadId());
    setNotebook(null);
    clearStoredNotebook();
    setResponse(null);
    setError(null);
    setQuestion("");
    setAnswerReadyMessage(null);
    setPhase("start");
  }

  const visibleConversation = pendingQuestion
    ? [
        ...(pendingStartsFresh ? [] : response?.conversation ?? []),
        { role: "user" as const, text: pendingQuestion }
      ]
    : response?.conversation ?? [];

  // Statuses that arrived after the chat answer started, so the chat can show
  // Deadbot is still composing the page instead of just a blinking cursor.
  const postAnswerLines = answerProgressStart !== null ? progress.slice(answerProgressStart) : [];
  const postAnswerStatus = postAnswerLines.length > 0 ? postAnswerLines[postAnswerLines.length - 1] : null;

  // The last four progress lines for a working display, falling back to a
  // single placeholder line before the first tool call reports in.
  const workingLines = progress.length > 0 ? progress.slice(-4) : ["Looking through the library…"];

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void askQuestion();
  }

  // Shared by the rail and the start screen, which never render at the same
  // time (the rail is visually collapsed while atStart), but each needs its
  // own element id.
  function renderComposer(variant: "rail" | "start" | "dock") {
    const dock = variant === "dock";
    return (
      <form className={variant === "start" ? "composer start-composer" : dock ? "composer dock-composer" : "composer"} onSubmit={submit}>
        <div className="question-field">
          <textarea
            id={`question-${variant}`}
            ref={dock ? dockTextareaRef : undefined}
            aria-label="Question"
            rows={dock ? 1 : 3}
            placeholder={dock ? "Ask about a song, show, or recording" : "Ask about a song, show, source, or recording"}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={submitOnEnter}
            onFocus={dock ? () => setComposerFocused(true) : undefined}
            onBlur={dock ? () => setComposerFocused(false) : undefined}
            disabled={loading}
          />
          {dock ? (
            <button type="submit" className="dock-send" disabled={loading || !question.trim()} aria-label={loading ? "Looking…" : "Explore"} aria-busy={loading}>
              <SendIcon />
            </button>
          ) : (
            <button type="submit" disabled={loading || !question.trim()}>{loading ? "Looking…" : "Explore"}</button>
          )}
        </div>
        {variant === "rail" && response && !loading && (
          <a className="view-answer-link" href="#answer-title">View answer <span aria-hidden="true">↓</span></a>
        )}
      </form>
    );
  }

  const workspaceClassName = [
    "workspace",
    atStart ? "start" : null,
    phase === "opening" ? "opening" : null,
    phase === "arriving" ? "arriving" : null
  ].filter(Boolean).join(" ");

  return (
    <main className="app-shell">
      <p role="status" className="sr-only">{answerReadyMessage}</p>
      <div className={workspaceClassName} ref={workspaceRef}>
        <aside className="conversation-pane" aria-label="Conversation" ref={conversationPaneRef}>
          <header className="masthead">
            <div className="masthead-row">
              <a className="wordmark" href="/">Deadbot</a>
              <button type="button" className="new-chat-button" onClick={startNewChat} disabled={loading}>
                New chat
              </button>
            </div>
            <p>Grateful Dead knowledge, listening, and context</p>
          </header>

          <section className="thread" aria-label="Deadbot conversation" ref={threadContainer}>
            <div className="thread-messages" aria-live="polite">
              {visibleConversation.map((turn, index) => (
                <article className={`message ${turn.role}`} key={`${turn.role}-${index}`}>
                  <div>{renderInline(turn.text)}</div>
                </article>
              ))}
              {loading && (
                <article className="message assistant pending">
                  {streamingAnswer ? (
                    <div className="streaming-answer">
                      {renderInline(streamingAnswer)}
                      {postAnswerStatus ? (
                        <p className="post-answer-status">{postAnswerStatus}…</p>
                      ) : (
                        <span className="cursor" aria-hidden="true" />
                      )}
                    </div>
                  ) : progress.length === 0 ? (
                    <div>Looking through the library…</div>
                  ) : (
                    <ol className="progress-lines" aria-label="What Deadbot is doing">
                      {progress.slice(-4).map((status, index, lines) => (
                        <li key={`${index}-${status}`} className={index === lines.length - 1 ? "current" : undefined}>
                          {status}{index === lines.length - 1 ? "…" : ""}
                        </li>
                      ))}
                    </ol>
                  )}
                </article>
              )}
            </div>

            {error && !atStart && <p className="error" role="alert">{error}</p>}

            {isPhone ? (
              response && !loading && (
                <a className="view-answer-link" href="#answer-title">View answer <span aria-hidden="true">↓</span></a>
              )
            ) : (
              renderComposer("rail")
            )}
          </section>
        </aside>

        <section className="content-pane" aria-label="Deadbot guide">
          <div className="content-body">
          {atStart ? (
            <div className={`start-screen${phase === "leaving" ? " leaving" : ""}`}>
              <StartLibrary onAsk={(prompt) => void askQuestion(prompt, { fresh: true })} disabled={loading}>
                {renderComposer("start")}
                {error && <p className="error" role="alert">{error}</p>}
              </StartLibrary>
            </div>
          ) : loading && draft ? (
            <ComposedPage
              title={draft.headline}
              groups={draft.groups}
              sources={[]}
              composing
              onFollowUp={chooseFollowUp}
            />
          ) : loading ? (
            <div className="content-working">
              <p className="eyebrow">Working</p>
              <h1>{pendingQuestion}</h1>
              <ol className="progress-lines" aria-hidden="true">
                {workingLines.map((line, index, lines) => (
                  <li key={`${index}-${line}`} className={index === lines.length - 1 ? "current" : undefined}>
                    {line}{index === lines.length - 1 && progress.length > 0 ? "…" : ""}
                  </li>
                ))}
              </ol>
            </div>
          ) : response ? (
            <ComposedPage
              title={response.headline ?? null}
              groups={groupsOfResponse(response)}
              sources={response.sources}
              composing={false}
              onFollowUp={chooseFollowUp}
            />
          ) : null}
          </div>
          {!isPhone && <NowPlayingBar />}
        </section>
      </div>
      {isPhone && !atStart && (
        <div className="mobile-dock" ref={dockRef}>
          <NowPlayingBar collapsible forceCollapsed={composerFocused} />
          {renderComposer("dock")}
        </div>
      )}
    </main>
  );
}
