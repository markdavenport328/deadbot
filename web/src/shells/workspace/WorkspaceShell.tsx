import { useEffect, useId, useLayoutEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import type { AskFocus, ExperienceResponse } from "../../types";
import type { PageEvent } from "../../core/stream-events";
import { ASK_ERROR, askPlain, askStreaming, createThreadId, isAbort, replayStreamEvents, type StreamHandlers } from "../../core/ask-client";
import { askRequestBody, type FollowUp } from "../../core/ask-request";
import { storeNotebook } from "../../core/research-notebook";
import { loadRequestedStreamEvents, requestedStreamFixture } from "../../visual-fixture-loader";
import {
  explorationReducer, initialExploration, isAsking, requestContext, visible,
  type ExplorationState, type Pending, type RequestSource
} from "../../core/exploration-state";
import { ExplorationHistory } from "./ExplorationHistory";
import { StartLibrary } from "../classic/StartLibrary";
import { ExplorationPane, contentOf, draftContent, shownPane } from "./ExplorationPane";
import { loadHistory, saveHistory } from "../../core/history-store";
import { PanelToggle, PenIcon, useRememberedOpen } from "../../core/side-panel";
import { RESUME_URL } from "../../SiteMenu";
import { followInSite, usePath } from "../../core/site-nav";
import type { Entry } from "../../core/exploration-state";
import "./WorkspaceShell.css";

type AskOptions = { source: RequestSource; focus?: AskFocus | null; fresh: boolean };

type Actions = {
  ask(question: string, options: AskOptions): boolean;
  navigate(index: number): void;
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

// The site menu's two links, at the top of the rail on a desktop, above New chat.
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
// top-left corner. Escape or a tap outside closes it and focus returns to
// the button; choosing a row or New chat also closes it, so the visitor
// lands on what they picked.
function HistoryDrawer({ open, onOpen, onClose, children }: { open: boolean; onOpen(): void; onClose(): void; children: ReactNode }) {
  const toggleRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const wasOpen = useRef(false);
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
      <button ref={toggleRef} type="button" className="history-drawer-toggle" aria-label="Your explorations" aria-expanded={open} aria-controls="history-drawer" onClick={onOpen}>
        <HistoryIcon />
      </button>
      {open && <div className="history-drawer-scrim" onClick={onClose} aria-hidden="true" />}
      <aside ref={drawerRef} id="history-drawer" className={open ? "history-drawer open" : "history-drawer"} aria-label="Your explorations" hidden={!open}>
        {children}
      </aside>
    </>
  );
}

// The workspace: every answer is one exploration with Listen, Charts and
// Read tabs; earlier explorations stay mounted (hidden) so going back costs
// no request and keeps what the visitor opened; the player plays on through
// all of it because nothing here owns it.
export function WorkspaceShell({ player, queueRail = null, phonePlayer, isPhone, linkedQuestion, registerAskFromPage }: {
  player: ReactNode;
  queueRail?: ReactNode; // the queue's right rail on a wide desktop; it renders nothing until tracks are queued
  phonePlayer(composerFocused: boolean): ReactNode; // the player folds while the dock's ask box has focus
  isPhone: boolean;
  linkedQuestion: string | null;
  registerAskFromPage(handler: (question: string) => void): void;
}) {
  // Explorations saved in this browser come back on arrival.
  const [state, dispatch] = useReducer(explorationReducer, undefined, () => loadHistory() ?? initialExploration);
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
  const railHeadingId = useId();
  const drawerHeadingId = useId();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [railOpen, setRailOpen] = useRememberedOpen("deadbot.rail.history");
  const [cleared, setCleared] = useState<{ entries: Entry[]; cursor: number } | null>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const dockTextareaRef = useRef<HTMLTextAreaElement>(null);

  const asking = isAsking(state);
  const shown = visible(state);
  const pane = shownPane(state);

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
    dispatch({ type: "complete", requestId, response });
    storeNotebook(response.notebook ?? null);
    setAnnouncement(`Ready: ${response.headline ?? response.lead}`);
    if (interactedRef.current !== requestId) focusPaneRef.current = requestId;
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
  function ask(text: string, { source, focus = null, fresh }: AskOptions, from: ExplorationState = stateRef.current): boolean {
    const trimmed = text.trim();
    if (!trimmed || requestRef.current || isAsking(from)) return false;
    const requestId = crypto.randomUUID();
    const context = requestContext(from, fresh);
    const threadId = context.threadId ?? createThreadId();
    const abort = new AbortController();
    controller.current = abort;
    requestRef.current = requestId;
    storeNotebook(context.notebook);
    dispatch({ type: "submit", requestId, question: trimmed, source, focus, fresh, threadId });
    const body = askRequestBody({ question: trimmed, threadId, conversation: context.conversation, focus: focus ?? undefined, notebook: context.notebook });
    void run(requestId, body, abort.signal);
    return true;
  }

  function navigate(index: number) {
    saveScroll();
    dropRequest();
    const next = explorationReducer(stateRef.current, { type: "navigate", index });
    dispatch({ type: "navigate", index });
    storeNotebook(requestContext(next, false).notebook);
  }

  // Stopping or dismissing puts back the notebook of the page left on screen.
  function settle(action: { type: "cancel" } | { type: "dismiss" }) {
    if (action.type === "cancel") dropRequest();
    const next = explorationReducer(stateRef.current, action);
    dispatch(action);
    storeNotebook(requestContext(next, false).notebook);
  }

  function stop() {
    settle({ type: "cancel" });
  }

  // Retry sends the same question from the same place: dismiss the failure,
  // step back to the page it grew from if the visitor has moved, ask again.
  function retry() {
    const failed = stateRef.current.pending;
    if (!failed || failed.error === null) return;
    let next = explorationReducer(stateRef.current, { type: "dismiss" });
    dispatch({ type: "dismiss" });
    if (failed.baseEntryId) {
      const index = next.entries.findIndex((entry) => entry.id === failed.baseEntryId);
      if (index >= 0 && index !== next.cursor) {
        next = explorationReducer(next, { type: "navigate", index });
        dispatch({ type: "navigate", index });
      }
    }
    ask(failed.question, { source: failed.source, focus: failed.focus, fresh: failed.baseEntryId === null }, next);
  }

  function newChat() {
    if (isAsking(stateRef.current)) return;
    saveScroll();
    dispatch({ type: "newChat" });
    storeNotebook(null);
  }

  function interact() {
    const current = stateRef.current;
    const pending = current.pending;
    if (!pending || pending.interacted || visible(current).kind !== "draft") return;
    interactedRef.current = pending.requestId;
    dispatch({ type: "view", patch: {}, interacted: true });
  }

  // Panes and the menu get one stable set of callbacks that always reach the
  // latest render's functions, so a streaming token does not re-render every
  // earlier exploration.
  const latest = useRef({ ask, navigate, stop, retry, newChat, interact });
  latest.current = { ask, navigate, stop, retry, newChat, interact };
  const actions = useMemo<Actions>(() => ({
    ask: (text, options) => latest.current.ask(text, options),
    navigate: (index) => latest.current.navigate(index),
    stop: () => latest.current.stop(),
    retry: () => latest.current.retry(),
    newChat: () => latest.current.newChat(),
    interact: () => latest.current.interact(),
    followUp: (text, focus) => { latest.current.ask(text, { source: "chip", focus: focus ?? null, fresh: false }); }
  }), []);
  const startAsk = useMemo(() => (text: string) => { actions.ask(text, { source: "chip", fresh: true }); }, [actions]);

  registerAskFromPage((text) => { actions.ask(text, { source: "chip", fresh: true }); });

  // A question in the link is asked once, on arrival, as a fresh start.
  useEffect(() => {
    if (linkedQuestion) actions.ask(linkedQuestion, { source: "typed", fresh: true });
    // Read once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // On a desktop the rail carries the site's links, so the corner menu steps aside.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("workspace-desktop", !isPhone);
    return () => root.classList.remove("workspace-desktop");
  }, [isPhone]);

  // The page shown on arrival from saved history gets its research notebook back.
  useEffect(() => {
    storeNotebook(requestContext(stateRef.current, false).notebook);
  }, []);

  // Every change to the history is saved in this browser.
  useEffect(() => {
    saveHistory(state);
  }, [state.entries, state.cursor, state.startView]);

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
    storeNotebook(null);
    setAnnouncement("History cleared. Undo is available for ten seconds.");
  }

  function undoClear() {
    if (!cleared) return;
    const next = explorationReducer(stateRef.current, { type: "restore", ...cleared });
    dispatch({ type: "restore", ...cleared });
    setCleared(null);
    storeNotebook(requestContext(next, false).notebook);
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
  // already started using it.
  useEffect(() => {
    const id = focusPaneRef.current;
    if (!id) return;
    focusPaneRef.current = null;
    document.getElementById(`${id}-title`)?.focus({ preventScroll: true });
  }, [state.entries]);

  // Each page keeps its scroll position: a page seen before returns to where
  // the visitor left it, and a new one starts at the top.
  const shownId = pane?.id ?? null;
  useLayoutEffect(() => {
    const last = lastShownRef.current;
    lastShownRef.current = shownId;
    const current = shownPane(stateRef.current);
    if (!current || !shownId || last === shownId) return;
    window.scrollTo(0, current.view.scroll ?? 0);
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
  // it). Either way it grows with the question.
  function composer(dock: boolean) {
    return (
      <form className={dock ? "composer dock-composer" : "composer pane-composer"} onSubmit={(event) => { event.preventDefault(); send(); }}>
        <div className="question-field">
          <textarea
            id={dock ? "question-dock" : "question-pane"}
            ref={dockTextareaRef}
            aria-label="Question"
            rows={dock ? 1 : 2}
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
  const panes = entries.map((entry) => (
    <ExplorationPane
      key={entry.id}
      paneId={entry.id}
      content={contentOf(entry.response)}
      statuses={null}
      streaming={false}
      hidden={entry.id !== shownId}
      previous={entry.id === heldId}
      onFollowUp={actions.followUp}
    />
  ));
  // The request in flight is keyed by its id, which becomes its entry's id,
  // so React keeps the same pane (and whatever the visitor opened in it) from
  // draft to final.
  if (pending && pending.error === null) {
    const content = draftContent(pending);
    panes.push(
      <ExplorationPane
        key={pending.requestId}
        paneId={pending.requestId}
        content={content}
        statuses={shown.kind === "draft" ? null : pending.statuses}
        streaming
        hidden={pending.requestId !== shownId}
        previous={false}
          onInteract={shown.kind === "draft" && !pending.interacted ? actions.interact : undefined}
        onFollowUp={actions.followUp}
      />
    );
  }

  const showStart = shown.kind === "start" || (shown.kind === "failed" && !shown.entry);

  return (
    <main className={["app-shell", "workspace-shell", isPhone ? "phone" : null, !isPhone && !railOpen ? "history-collapsed" : null].filter(Boolean).join(" ")}>
      <p role="status" className="sr-only">{announcement}</p>
      {isPhone && (
        <HistoryDrawer open={drawerOpen} onOpen={() => setDrawerOpen(true)} onClose={() => setDrawerOpen(false)}>
          <ExplorationHistory
            state={state}
            headingId={drawerHeadingId}
            onNavigate={(index) => { actions.navigate(index); setDrawerOpen(false); }}
            onStop={actions.stop}
            onRetry={() => { actions.retry(); setDrawerOpen(false); }}
            onNewChat={() => { actions.newChat(); setDrawerOpen(false); }}
            onClear={clearHistory}
            onUndo={undoClear}
            cleared={cleared !== null}
          />
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
              {railOpen && <p>Grateful Dead knowledge, listening, and context</p>}
            </header>
            {railOpen && <RailLinks />}
            {railOpen ? <ExplorationHistory
              state={state}
              headingId={railHeadingId}
              onNavigate={actions.navigate}
              onStop={actions.stop}
              onRetry={actions.retry}
              onNewChat={actions.newChat}
              onClear={clearHistory}
              onUndo={undoClear}
              cleared={cleared !== null}
            /> : (
              <button type="button" className="history-new icon-only" disabled={asking} onClick={actions.newChat} aria-label="New chat" data-tip="New chat">
                <PenIcon />
              </button>
            )}
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
            {showStart && <div className="start-screen"><StartLibrary onAsk={startAsk} disabled={false} /></div>}
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

