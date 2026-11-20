import { useEffect, useId, useLayoutEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import type { AskFocus, ExperienceResponse } from "../../types";
import type { PageEvent } from "../../core/stream-events";
import { ASK_ERROR, MAX_QUESTION_LENGTH, askPlain, askStreaming, createThreadId, isAbort, replayStreamEvents, type StreamHandlers } from "../../core/ask-client";
import { askRequestBody, type FollowUp } from "../../core/ask-request";
import { loadRequestedStreamEvents, loadRequestedVisualFixture, requestedStreamFixture, requestedVisualFixture } from "../../visual-fixture-loader";
import { useReloadOnDeploy } from "../../core/server-version";
import {
  addressOf, explorationReducer, initialExploration, isAsking, openingFor, pendingHasContent, requestContext, shownPane, threadStart, visible,
  type ExplorationState, type Opening, type Pending, type RequestSource
} from "../../core/exploration-state";
import { ExplorationHistory } from "./ExplorationHistory";
import { StartLibrary } from "./StartLibrary";
import { ExplorationPane, PaneFallback, contentOf, draftContent } from "./ExplorationPane";
import { loadHistory, saveHistory } from "../../core/history-store";
import { ErrorBoundary } from "../../core/error-boundary";
import { PanelToggle, PenIcon, useRememberedOpen } from "../../core/side-panel";
import { RESUME_URL } from "../../SiteMenu";
import { atPage, currentPath, followInSite, navigate as goToPath, readPageAddress, useBackCloses, usePath, writePage } from "../../core/site-nav";
import type { Entry } from "../../core/exploration-state";
import "./WorkspaceShell.css";

// `record` says what the browser's history does with the new page: a new
// step for something the visitor asked, or the current step rewritten when
// the question came from the address they arrived at.
type AskOptions = { source: RequestSource; focus?: AskFocus | null; fresh: boolean; record?: "push" | "replace" };

type Actions = {
  ask(question: string, options: AskOptions): boolean;
  navigate(index: number): void;
  showPending(): void;
  stop(): void;
  retry(): void;
  newChat(): void;
  interact(): void;
  followUp: FollowUp;
};

function lastStatus(pending: Pending): string {
  return pending.statuses.length > 0 ? `${pending.statuses[pending.statuses.length - 1]}…` : "Looking through the library…";
}

// The dock's send: an arrow up, the direction the question travels.
function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-6 6m6-6l6 6" />
    </svg>
  );
}

const UNDO_CLEAR_SECONDS = 10;

// The site menu's two links, at the foot of the rail on a desktop, under the history.
function RailLinks() {
  const path = usePath();
  return (
    <nav className="rail-links" aria-label="Site">
      <a href="/about" aria-current={path === "/about" ? "page" : undefined} onClick={(event) => followInSite(event, "/about")}>About Deadbot</a>
      <a href={RESUME_URL} target="_blank" rel="noopener">
        About Mark Davenport<span aria-hidden="true"> ↗</span><span className="visually-hidden"> (opens in a new tab)</span>
      </a>
    </nav>
  );
}

// The history mark for the phone's drawer button: a clock face turning back.
function HistoryIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" d="M3.5 12a8.5 8.5 0 1 0 2.5-6M3.5 4v4h4M12 7.5V12l3 2" />
    </svg>
  );
}

// History on a phone: a drawer from the left, opened by the button in the
// top-left corner. Escape, the Back button or a tap outside closes it and
// focus returns to the button; choosing a row or New chat also closes it, so
// the visitor lands on what they picked. `news` marks the button while an
// answer is being written, or waits unread, behind the page on screen.
function HistoryDrawer({ open, news, onOpen, onClose, children }: { open: boolean; news: boolean; onOpen(): void; onClose(): void; children: ReactNode }) {
  const toggleRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const wasOpen = useRef(false);
  useBackCloses("history", open, onClose);
  useEffect(() => {
    if (open) {
      drawerRef.current?.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
      const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") onClose(); };
      document.addEventListener("keydown", onKey);
      wasOpen.current = true;
      return () => document.removeEventListener("keydown", onKey);
    }
    if (wasOpen.current) toggleRef.current?.focus();
    wasOpen.current = false;
  }, [open, onClose]);
  return (
    <>
      <button ref={toggleRef} type="button" className={news ? "history-drawer-toggle has-news" : "history-drawer-toggle"} aria-label="Your explorations" aria-expanded={open} aria-controls="history-drawer" onClick={onOpen}>
        <HistoryIcon />
        {news && <span className="visually-hidden"> (one is new)</span>}
      </button>
      {open && <div className="history-drawer-scrim" onClick={onClose} aria-hidden="true" />}
      <aside ref={drawerRef} id="history-drawer" className={open ? "history-drawer open" : "history-drawer"} aria-label="Your explorations" hidden={!open}>
        {children}
      </aside>
    </>
  );
}

// What the visitor arrives to: the explorations saved in this browser, opened
// at the page the address names. A development `?fixture=` page shows on its
// own and leaves the saved history alone.
function arrive(fixtureMode: boolean): { state: ExplorationState; opening: Opening | null } {
  if (fixtureMode) return { state: initialExploration, opening: null };
  const saved = loadHistory() ?? initialExploration;
  if (currentPath() !== "/") return { state: saved, opening: null };
  const address = readPageAddress();
  // No question in the address: back to the place they left.
  if (!address.question) return { state: saved, opening: null };
  const opening = openingFor(saved, address);
  if (opening.kind === "entry") return { state: explorationReducer(saved, { type: "navigate", index: opening.index }), opening };
  if (opening.kind === "ask") return { state: { ...saved, startView: true }, opening };
  return { state: saved, opening: null };
}

function typingInAField(): boolean {
  const active = document.activeElement;
  return active instanceof HTMLElement && (active.tagName === "TEXTAREA" || active.tagName === "INPUT" || active.isContentEditable === true);
}

// The workspace: every answer is one exploration in one column; earlier
// explorations stay mounted (hidden) so going back costs no request and keeps
// what the visitor opened; a request in flight carries on while they look at
// another page; the player plays on through all of it because nothing here
// owns it.
export function WorkspaceShell({ player, queueRail = null, phonePlayer, isPhone, registerAskFromPage }: {
  player: ReactNode;
  queueRail?: ReactNode; // the queue's right rail on a wide desktop; it renders nothing until tracks are queued
  phonePlayer(composerFocused: boolean): ReactNode; // the player folds while the dock's ask box has focus
  isPhone: boolean;
  registerAskFromPage(handler: (question: string) => void): void;
}) {
  const fixtureMode = Boolean(requestedVisualFixture);
  const arrival = useRef<{ state: ExplorationState; opening: Opening | null } | null>(null);
  if (!arrival.current) arrival.current = arrive(fixtureMode);
  const [state, dispatch] = useReducer(explorationReducer, arrival.current.state);
  const stateRef = useRef(state);
  stateRef.current = state;
  const controller = useRef<AbortController | null>(null);
  const requestRef = useRef<string | null>(null);
  // The request the visitor has started using (clicked, scrolled, typed in);
  // it keeps its view when it completes instead of taking focus.
  const interactedRef = useRef<string | null>(null);
  const focusPaneRef = useRef<string | null>(null);
  const lastShownRef = useRef<string | null>(null);
  const [question, setQuestion] = useState("");
  const [dockFocused, setDockFocused] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  // A follow-up named in the link the visitor opened, which this browser does
  // not have: offered on the page its thread began with, never asked unasked.
  const [offer, setOffer] = useState<string | null>(null);
  const railHeadingId = useId();
  const drawerHeadingId = useId();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [railOpen, setRailOpen] = useRememberedOpen("deadbot.rail.history");
  const [cleared, setCleared] = useState<{ entries: Entry[]; cursor: number } | null>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const dockTextareaRef = useRef<HTMLTextAreaElement>(null);
  const path = usePath();

  const asking = isAsking(state);
  const shown = visible(state);
  const pane = shownPane(state);
  const address = addressOf(state);

  function dropRequest() {
    controller.current?.abort();
    controller.current = null;
    requestRef.current = null;
  }

  // The scroll position of the page on screen goes into its view before the
  // visitor moves away from it.
  function saveScroll() {
    if (!shownPane(stateRef.current)) return;
    dispatch({ type: "view", patch: { scroll: window.scrollY } });
  }

  function complete(requestId: string, response: ExperienceResponse) {
    const pending = stateRef.current.pending;
    const watching = pending?.requestId === requestId && pending.watching;
    dispatch({ type: "complete", requestId, response });
    setAnnouncement(`Ready: ${response.headline ?? response.lead}`);
    // A page that finished behind another one waits in the history; it does
    // not take focus from the page the visitor is reading.
    if (watching && interactedRef.current !== requestId) focusPaneRef.current = requestId;
  }

  async function run(requestId: string, body: string, signal: AbortSignal) {
    const handlers: Omit<StreamHandlers, "onResponse"> = {
      onStatus: (text) => dispatch({ type: "status", requestId, text }),
      onLead: (text) => dispatch({ type: "lead", requestId, text }),
      onPage: (event: PageEvent) => dispatch({ type: "page", requestId, event })
    };
    try {
      const result: { response: ExperienceResponse | null } = { response: null };
      const fixture = import.meta.env.DEV && requestedStreamFixture ? await loadRequestedStreamEvents() : null;
      if (fixture) await replayStreamEvents(fixture, { ...handlers, onResponse: (response) => { result.response = response; } }, signal);
      else result.response = (await askStreaming(body, handlers, signal)) ?? await askPlain(body, signal);
      if (signal.aborted || requestRef.current !== requestId) return;
      if (!result.response) throw new Error(ASK_ERROR);
      complete(requestId, result.response);
    } catch (error) {
      if (isAbort(error) || signal.aborted || requestRef.current !== requestId) return;
      dispatch({ type: "fail", requestId, message: error instanceof Error ? error.message : ASK_ERROR });
    } finally {
      if (requestRef.current === requestId) {
        requestRef.current = null;
        controller.current = null;
      }
    }
  }

  // One request at a time: while one runs, asking does nothing. `from` is the
  // state the question is asked from, for a retry that has just moved back.
  function ask(text: string, { source, focus = null, fresh, record = "push" }: AskOptions, from: ExplorationState = stateRef.current): boolean {
    const trimmed = text.trim();
    if (!trimmed || requestRef.current || isAsking(from)) return false;
    const requestId = crypto.randomUUID();
    const context = requestContext(from, fresh);
    const threadId = context.threadId ?? createThreadId();
    const abort = new AbortController();
    controller.current = abort;
    requestRef.current = requestId;
    const submit = { type: "submit", requestId, question: trimmed, source, focus, fresh, threadId } as const;
    dispatch(submit);
    setOffer(null);
    if (!fixtureMode) {
      const next = addressOf(explorationReducer(from, submit));
      writePage(record, next.page, next);
    }
    const body = askRequestBody({ question: trimmed, threadId, conversation: context.conversation, focus: focus ?? undefined, notebook: context.notebook });
    void run(requestId, body, abort.signal);
    return true;
  }

  // Opening another page is a step in the browser's history. The request in
  // flight, if there is one, carries on behind it.
  function navigate(index: number, record = true) {
    saveScroll();
    dispatch({ type: "navigate", index });
    setOffer(null);
    if (record && !fixtureMode) {
      const next = addressOf(explorationReducer(stateRef.current, { type: "navigate", index }));
      writePage("push", next.page, next);
    }
  }

  // Back to the page being written (or the one that did not finish).
  function showPending(record = true) {
    if (!stateRef.current.pending) return;
    saveScroll();
    dispatch({ type: "watch" });
    setOffer(null);
    if (record && !fixtureMode) {
      const next = addressOf(explorationReducer(stateRef.current, { type: "watch" }));
      writePage("push", next.page, next);
    }
  }

  function settle(action: { type: "cancel" } | { type: "dismiss" }) {
    if (action.type === "cancel") dropRequest();
    dispatch(action);
  }

  function stop() {
    settle({ type: "cancel" });
  }

  // Retry sends the same question from the same place: dismiss the failure,
  // step back to where it was asked from if the visitor has moved, ask again.
  function retry() {
    const failed = stateRef.current.pending;
    if (!failed || failed.error === null) return;
    let next = explorationReducer(stateRef.current, { type: "dismiss" });
    dispatch({ type: "dismiss" });
    if (failed.baseEntryId) {
      const index = next.entries.findIndex((entry) => entry.id === failed.baseEntryId);
      if (index >= 0 && (index !== next.cursor || next.startView)) {
        next = explorationReducer(next, { type: "navigate", index });
        dispatch({ type: "navigate", index });
      }
    }
    // Still on the failed page: the new attempt takes its place in the browser's history.
    ask(failed.question, { source: failed.source, focus: failed.focus, fresh: failed.baseEntryId === null, record: failed.watching ? "replace" : "push" }, next);
  }

  function startView(record = true) {
    saveScroll();
    dispatch({ type: "newChat" });
    setOffer(null);
    if (record && !fixtureMode) writePage("push", null, { question: null, followUp: null });
  }

  function newChat() {
    if (isAsking(stateRef.current)) return;
    startView();
  }

  function interact() {
    const current = stateRef.current;
    const pending = current.pending;
    if (!pending || pending.interacted || visible(current).kind !== "draft") return;
    interactedRef.current = pending.requestId;
    dispatch({ type: "view", patch: {}, interacted: true });
  }

  // The browser moved (Back, Forward): show the page its address names. A
  // page this browser no longer has is asked for again, as a link would be.
  function openAddress() {
    if (fixtureMode || currentPath() !== "/") return;
    const current = stateRef.current;
    const here = addressOf(current);
    // The same page: a drawer's own step, or a return from About.
    if (atPage(here.page, here)) return;
    const opening = openingFor(current, readPageAddress());
    if (opening.kind === "pending") showPending(false);
    else if (opening.kind === "entry") {
      navigate(opening.index, false);
      setOffer(opening.offer);
    } else if (opening.kind === "start") startView(false);
    else if (ask(opening.question, { source: "typed", fresh: true, record: "replace" })) setOffer(opening.offer);
    else startView(false);
  }

  // Panes and the menu get one stable set of callbacks that always reach the
  // latest render's functions, so a streaming token does not re-render every
  // earlier exploration.
  const latest = useRef({ ask, navigate, showPending, stop, retry, newChat, interact, openAddress });
  latest.current = { ask, navigate, showPending, stop, retry, newChat, interact, openAddress };
  const actions = useMemo<Actions>(() => ({
    ask: (text, options) => latest.current.ask(text, options),
    navigate: (index) => latest.current.navigate(index),
    showPending: () => latest.current.showPending(),
    stop: () => latest.current.stop(),
    retry: () => latest.current.retry(),
    newChat: () => latest.current.newChat(),
    interact: () => latest.current.interact(),
    followUp: (text, focus) => { latest.current.ask(text, { source: "chip", focus: focus ?? null, fresh: false }); }
  }), []);
  const startAsk = useMemo(() => (text: string) => { actions.ask(text, { source: "chip", fresh: true }); }, [actions]);
  const askAgain = useMemo(() => (text: string) => { actions.ask(text, { source: "typed", fresh: true }); }, [actions]);

  // A question from another page (About's examples, the queue's "Go to this
  // show"): asked fresh, and the app comes forward either way.
  registerAskFromPage((text) => {
    if (!actions.ask(text, { source: "chip", fresh: true }) && currentPath() !== "/") goToPath("/");
  });

  // The address the visitor arrived at: a question this browser has no page
  // for is asked once, as a fresh start; a follow-up it names is offered.
  useEffect(() => {
    const opening = arrival.current?.opening;
    if (!opening) return;
    if (opening.kind === "ask") actions.ask(opening.question, { source: "typed", fresh: true, record: "replace" });
    if (opening.kind === "ask" || opening.kind === "entry") setOffer(opening.offer);
    // Read once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Back and Forward move between the pages the visitor has opened. Each
  // page keeps its own scroll position, so the browser's is switched off.
  useEffect(() => {
    if (fixtureMode) return;
    const onPop = () => latest.current.openAddress();
    window.addEventListener("popstate", onPop);
    const before = window.history.scrollRestoration;
    try {
      window.history.scrollRestoration = "manual";
    } catch {
      // Not supported: the page-by-page scroll below still applies.
    }
    return () => {
      window.removeEventListener("popstate", onPop);
      try {
        window.history.scrollRestoration = before;
      } catch {
        // As above.
      }
    };
  }, [fixtureMode]);

  // The address bar always names the page on screen. A move the visitor made
  // has already written it; anything else (an answer stopped, the history
  // cleared, a return from About) rewrites the current step.
  useEffect(() => {
    if (fixtureMode || path !== "/") return;
    const here = { question: address.question, followUp: address.followUp };
    if (!atPage(address.page, here)) writePage("replace", address.page, here);
  }, [fixtureMode, path, address.page, address.question, address.followUp]);

  // The tab is named for the page on screen.
  useEffect(() => {
    document.title = path === "/about" ? "About Deadbot" : address.title ? `${address.title} · Deadbot` : "Deadbot";
  }, [path, address.title]);

  // On a desktop the rail carries the site's links, so the corner menu steps aside.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("workspace-desktop", !isPhone);
    return () => root.classList.remove("workspace-desktop");
  }, [isPhone]);

  // Every change to the history is saved in this browser.
  useEffect(() => {
    if (!fixtureMode) saveHistory(state);
  }, [state.entries, state.cursor, state.startView]);

  // A development `?fixture=` page opens as the one page in the rail.
  useEffect(() => {
    if (!fixtureMode) return;
    void loadRequestedVisualFixture().then((response) => {
      if (!response) return;
      const entry: Entry = {
        id: `fixture-${requestedVisualFixture}`, parentId: null, root: true, request: response.headline ?? requestedVisualFixture ?? "Fixture",
        source: "typed", focus: null, threadId: createThreadId(), response, view: { scroll: null }
      };
      dispatch({ type: "restore", entries: [entry], cursor: 0 });
    });
  }, []);

  // A new deploy reloads the page when the tab comes back into view, unless
  // an answer is being written.
  useReloadOnDeploy(!fixtureMode && !requestedStreamFixture, () => isAsking(stateRef.current));

  // Undo is offered for ten seconds after Clear.
  useEffect(() => {
    if (!cleared) return;
    const timer = window.setTimeout(() => setCleared(null), UNDO_CLEAR_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [cleared]);

  function clearHistory() {
    if (isAsking(stateRef.current)) return;
    saveScroll();
    setCleared({ entries: stateRef.current.entries, cursor: stateRef.current.cursor });
    dispatch({ type: "clear" });
    setOffer(null);
    setAnnouncement("History cleared. Undo is available for ten seconds.");
  }

  function undoClear() {
    if (!cleared) return;
    dispatch({ type: "restore", ...cleared });
    setCleared(null);
    setAnnouncement("History restored");
  }

  // Announce once when the page being written first has something to read.
  const announcedRef = useRef<string | null>(null);
  useEffect(() => {
    const pending = state.pending;
    if (!pending || pending.error !== null || announcedRef.current === pending.requestId) return;
    if (!(pending.draft?.groups ?? []).some((group) => group.blocks.length > 0)) return;
    announcedRef.current = pending.requestId;
    setAnnouncement("The page is filling in");
  }, [state.pending]);

  // A finished page takes focus (without scrolling) unless the visitor had
  // already started using it, or is in the ask box: someone typing their
  // next question keeps their place in it.
  useEffect(() => {
    const id = focusPaneRef.current;
    if (!id) return;
    focusPaneRef.current = null;
    if (typingInAField()) return;
    document.getElementById(`${id}-title`)?.focus({ preventScroll: true });
  }, [state.entries]);

  // Each page keeps its scroll position: a page seen before returns to where
  // the visitor left it, and a new one, the start view included, starts at
  // the top.
  const shownId = pane?.id ?? null;
  useLayoutEffect(() => {
    const last = lastShownRef.current;
    lastShownRef.current = shownId;
    if (last === shownId) return;
    window.scrollTo(0, shownPane(stateRef.current)?.view.scroll ?? 0);
  }, [shownId]);

  // The page keeps room under the dock (the phone's player and ask box, or the
  // desktop's full-width player): its measured height becomes a CSS variable
  // the shell pads by and the pane's ask box sits on. Nothing to measure means
  // no padding.
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
  }, [isPhone]);

  // On iOS the keyboard covers a fixed footer rather than shrinking the page,
  // so the dock follows the visual viewport.
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

  // The dock's ask box is one line tall and grows with what is typed.
  useLayoutEffect(() => {
    const field = dockTextareaRef.current;
    if (!field) return;
    field.style.height = "";
    if (question.trim()) {
      field.style.height = "auto";
      field.style.height = `${field.scrollHeight}px`;
    }
  }, [question, isPhone]);

  // The wordmark goes to the start view in the app; a reload would lose every
  // exploration. A modified click still opens a new tab as a link should.
  function goHome(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    actions.newChat();
  }

  function send() {
    if (actions.ask(question, { source: "typed", fresh: false })) setQuestion("");
  }

  function sendOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    send();
  }

  // One ask box: in the phone's dock (one line, a round send), or held at the
  // foot of the answer pane on a desktop (two lines, the blue Explore inside
  // it). Either way it grows with the question, up to the length the server takes.
  function composer(dock: boolean) {
    return (
      <form className={dock ? "composer dock-composer" : "composer pane-composer"} onSubmit={(event) => { event.preventDefault(); send(); }}>
        <div className="question-field">
          <textarea
            id={dock ? "question-dock" : "question-pane"}
            ref={dockTextareaRef}
            aria-label="Question"
            rows={dock ? 1 : 2}
            maxLength={MAX_QUESTION_LENGTH}
            placeholder={dock ? "Ask about a song, show, or recording" : "Ask about a song, show, source, or recording"}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={sendOnEnter}
            onFocus={dock ? () => setDockFocused(true) : undefined}
            onBlur={dock ? () => setDockFocused(false) : undefined}
          />
          {dock ? (
            <button type="submit" className="dock-send" disabled={asking || !question.trim()} aria-label="Explore" aria-busy={asking}>
              <SendIcon />
            </button>
          ) : (
            <button type="submit" disabled={asking || !question.trim()} aria-busy={asking}>Explore</button>
          )}
        </div>
      </form>
    );
  }

  const { pending, entries } = state;
  const heldId = shown.kind === "held" ? shown.entry.id : null;
  const panes = entries.map((entry, index) => {
    const start = threadStart(entries, index);
    return (
      <ErrorBoundary
        key={entry.id}
        name={`the page for “${entry.request}”`}
        resetKey={entry.response}
        fallback={<PaneFallback paneId={entry.id} hidden={entry.id !== shownId} title={entry.response.headline ?? entry.request} lead={entry.response.lead} question={entry.request} onAskAgain={askAgain} />}
      >
        <ExplorationPane
          paneId={entry.id}
          content={contentOf(entry.response)}
          statuses={null}
          streaming={false}
          hidden={entry.id !== shownId}
          previous={entry.id === heldId}
          linkQuestion={entries[start].request}
          linkFollowUp={start === index ? null : entry.request}
          onFollowUp={actions.followUp}
        />
      </ErrorBoundary>
    );
  });
  // The request in flight is keyed by its id, which becomes its entry's id,
  // so React keeps the same pane (and whatever the visitor opened in it) from
  // draft to final. One that failed keeps the draft it had written.
  const drafted = pending ? pendingHasContent(pending) : false;
  if (pending && (pending.error === null || drafted)) {
    const content = draftContent(pending);
    panes.push(
      <ErrorBoundary
        key={pending.requestId}
        name={`the page for “${pending.question}”`}
        resetKey={pending.draft}
        fallback={<PaneFallback paneId={pending.requestId} hidden={pending.requestId !== shownId} title={content.headline ?? pending.question} lead={content.lead} question={null} onAskAgain={askAgain} />}
      >
        <ExplorationPane
          paneId={pending.requestId}
          content={content}
          statuses={drafted ? null : pending.statuses}
          streaming={pending.error === null}
          hidden={pending.requestId !== shownId}
          previous={false}
          onInteract={shown.kind === "draft" && !pending.interacted ? actions.interact : undefined}
          onFollowUp={actions.followUp}
        />
      </ErrorBoundary>
    );
  }

  const showStart = shown.kind === "start" || (shown.kind === "failed" && !shown.entry && !drafted);
  const news = Boolean(pending && !pending.watching) || entries.some((entry) => entry.unseen);
  const history = (headingId: string, inDrawer: boolean) => (
    <ExplorationHistory
      state={state}
      headingId={headingId}
      onNavigate={inDrawer ? (index) => { actions.navigate(index); setDrawerOpen(false); } : actions.navigate}
      onShowPending={inDrawer ? () => { actions.showPending(); setDrawerOpen(false); } : actions.showPending}
      onStop={actions.stop}
      onRetry={inDrawer ? () => { actions.retry(); setDrawerOpen(false); } : actions.retry}
      onNewChat={inDrawer ? () => { actions.newChat(); setDrawerOpen(false); } : actions.newChat}
      onClear={clearHistory}
      onUndo={undoClear}
      cleared={cleared !== null}
    />
  );

  return (
    <main className={["app-shell", "workspace-shell", isPhone ? "phone" : null, !isPhone && !railOpen ? "history-collapsed" : null].filter(Boolean).join(" ")}>
      <p role="status" className="sr-only">{announcement}</p>
      {isPhone && (
        <HistoryDrawer open={drawerOpen} news={news} onOpen={() => setDrawerOpen(true)} onClose={() => setDrawerOpen(false)}>
          {history(drawerHeadingId, true)}
        </HistoryDrawer>
      )}
      <div className="workspace-grid">
        {!isPhone && (
          <aside className="workspace-rail" aria-label="Explorations">
            <header className="masthead">
              <div className="masthead-bar">
                {railOpen && <a className="wordmark" href="/" onClick={goHome}>Deadbot</a>}
                <PanelToggle side="left" open={railOpen} label="sidebar" onToggle={() => setRailOpen(!railOpen)} />
              </div>
              {railOpen && <p className="tagline">Grateful Dead knowledge, listening, and context</p>}
            </header>
            {railOpen ? history(railHeadingId, false) : (
              <button type="button" className="history-new icon-only" disabled={asking} onClick={actions.newChat} aria-label="New chat" data-tip="New chat">
                <PenIcon />
              </button>
            )}
            {railOpen && <RailLinks />}
          </aside>
        )}
        <section className="content-pane workspace-main" aria-label="Deadbot guide">
          <div className="content-body">
            {shown.kind === "held" && (
              <div className="workspace-banner" role="status">
                <p>Working on “{shown.pending.question}”</p>
                <p className="banner-status">{lastStatus(shown.pending)}</p>
                <button type="button" onClick={actions.stop}>Stop</button>
              </div>
            )}
            {shown.kind === "failed" && (
              <div className="error workspace-alert" role="alert">
                <p>Deadbot couldn't finish “{shown.pending.question}”.</p>
                {shown.pending.error && <p className="alert-detail">{shown.pending.error}</p>}
                <div className="alert-actions">
                  <button type="button" onClick={actions.retry}>Retry</button>
                  <button type="button" onClick={() => settle({ type: "dismiss" })}>Dismiss</button>
                </div>
              </div>
            )}
            {offer && shown.kind === "entry" && (
              <div className="workspace-banner link-offer">
                <p>This link went on to ask “{offer}”</p>
                <div className="alert-actions">
                  <button type="button" onClick={() => actions.followUp(offer)} disabled={asking}>Ask it</button>
                  <button type="button" onClick={() => setOffer(null)}>Dismiss</button>
                </div>
              </div>
            )}
            {showStart && <div className="start-screen"><StartLibrary onAsk={startAsk} /></div>}
            {panes}
          </div>
          {!isPhone && composer(false)}
        </section>
        {queueRail}
      </div>
      {!isPhone && (
        <div className="player-dock" ref={dockRef}>
          <div className="player-dock-inner">{player}</div>
        </div>
      )}
      {isPhone && (
        <div className="mobile-dock" ref={dockRef}>
          {phonePlayer(dockFocused)}
          {composer(true)}
        </div>
      )}
    </main>
  );
}
