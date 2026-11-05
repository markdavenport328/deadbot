import { useEffect, useId, useLayoutEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { AskFocus, ExperienceResponse } from "./types";
import type { PageEvent } from "./stream-events";
import { ASK_ERROR, askPlain, askStreaming, createThreadId, isAbort, replayStreamEvents, type StreamHandlers } from "./ask-client";
import { askRequestBody, type FollowUp } from "./ask-request";
import { storeNotebook } from "./research-notebook";
import { loadRequestedStreamEvents, requestedStreamFixture } from "./visual-fixture-loader";
import { WORKSPACE_TABS, readTab, routeGroups, tabsWithContent, type WorkspaceTab } from "./tab-routing";
import {
  explorationReducer, initialExploration, isAsking, requestContext, visible,
  type ExplorationState, type Pending, type RequestSource
} from "./exploration-state";
import { ExplorationHistory } from "./ExplorationHistory";
import { ExplorationPane, activeTabOf, contentOf, draftContent, entryTab, shownPane, type PageParts } from "./ExplorationPane";
import { useCloseSiteMenu, useMenuSlot } from "./menu-slot";
import "./WorkspaceShell.css";

export type { PageParts } from "./ExplorationPane";

type AskOptions = { source: RequestSource; focus?: AskFocus | null; fresh: boolean };

type Actions = {
  ask(question: string, options: AskOptions): boolean;
  navigate(index: number): void;
  stop(): void;
  retry(): void;
  newChat(): void;
  selectTab(tab: WorkspaceTab): void;
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

// History in the phone's site menu: choosing a row or New chat also closes
// the menu, so the visitor lands on what they picked.
function MenuHistory({ state, actions, headingId }: { state: ExplorationState; actions: Actions; headingId: string }) {
  const close = useCloseSiteMenu();
  return (
    <div className="workspace-shell workspace-menu-history">
      <ExplorationHistory
        state={state}
        headingId={headingId}
        onNavigate={(index) => { actions.navigate(index); close(); }}
        onStop={actions.stop}
        onRetry={() => { actions.retry(); close(); }}
        onNewChat={() => { actions.newChat(); close(); }}
      />
    </div>
  );
}

// The workspace: every answer is one exploration with Listen, Charts and
// Read tabs; earlier explorations stay mounted (hidden) so going back costs
// no request and keeps what the visitor opened; the player plays on through
// all of it because nothing here owns it.
export function WorkspaceShell({ parts, startView, player, phonePlayer, isPhone, linkedQuestion, registerAskFromPage }: {
  parts: PageParts;
  startView(ask: (question: string) => void): ReactNode; // the home screen's lead and starting points
  player: ReactNode;
  phonePlayer: ReactNode;
  isPhone: boolean;
  linkedQuestion: string | null;
  registerAskFromPage(handler: (question: string) => void): void;
}) {
  const [state, dispatch] = useReducer(explorationReducer, initialExploration);
  const stateRef = useRef(state);
  stateRef.current = state;
  const controller = useRef<AbortController | null>(null);
  const requestRef = useRef<string | null>(null);
  // The request the visitor has started using (clicked, scrolled, typed in);
  // it keeps its view when it completes instead of taking focus.
  const interactedRef = useRef<string | null>(null);
  const focusPaneRef = useRef<string | null>(null);
  const announcedRef = useRef<{ requestId: string; tabs: Set<WorkspaceTab> } | null>(null);
  const lastShownRef = useRef<{ id: string; tab: WorkspaceTab | null } | null>(null);
  const [question, setQuestion] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const railHeadingId = useId();
  const menuHeadingId = useId();
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

  // The scroll position of the tab on screen goes into its view before the
  // visitor moves away from it.
  function saveScroll() {
    const current = shownPane(stateRef.current);
    if (!current?.tab) return;
    dispatch({ type: "view", patch: { scroll: { ...current.view.scroll, [current.tab]: window.scrollY } } });
  }

  function complete(requestId: string, response: ExperienceResponse) {
    dispatch({ type: "complete", requestId, response });
    storeNotebook(response.notebook ?? null);
    setAnnouncement(`Ready: ${response.title}`);
    if (interactedRef.current !== requestId) focusPaneRef.current = requestId;
  }

  async function run(requestId: string, body: string, signal: AbortSignal) {
    const handlers: Omit<StreamHandlers, "onResponse"> = {
      onStatus: (text) => dispatch({ type: "status", requestId, text }),
      onAnswer: (text) => dispatch({ type: "answer", requestId, text }),
      onPage: (event: PageEvent) => {
        // The model's opening tab rides on its own event or on page_head.
        const raw = event as { type: string; tab?: unknown; initial_tab?: unknown };
        const opening = raw.type === "page_tab" ? readTab(raw.tab) : raw.type === "page_head" ? readTab(raw.initial_tab) : null;
        if (opening) dispatch({ type: "initialTab", requestId, tab: opening });
        dispatch({ type: "page", requestId, event });
      }
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

  function selectTab(tab: WorkspaceTab) {
    const current = shownPane(stateRef.current);
    if (!current) return;
    const scroll = current.tab ? { ...current.view.scroll, [current.tab]: window.scrollY } : current.view.scroll;
    // Only a tab chosen on the page being written takes it over; a tab on the
    // held previous page is just reading.
    if (current.draft) interactedRef.current = stateRef.current.pending?.requestId ?? null;
    dispatch({ type: "view", patch: { tab, scroll }, interacted: current.draft });
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
  const latest = useRef({ ask, navigate, stop, retry, newChat, selectTab, interact });
  latest.current = { ask, navigate, stop, retry, newChat, selectTab, interact };
  const actions = useMemo<Actions>(() => ({
    ask: (text, options) => latest.current.ask(text, options),
    navigate: (index) => latest.current.navigate(index),
    stop: () => latest.current.stop(),
    retry: () => latest.current.retry(),
    newChat: () => latest.current.newChat(),
    selectTab: (tab) => latest.current.selectTab(tab),
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

  // History sits in the site menu on a phone, where there is no rail.
  const menuHistory = useMemo(
    () => (isPhone ? <MenuHistory state={state} actions={actions} headingId={menuHeadingId} /> : null),
    [isPhone, state, actions, menuHeadingId]
  );
  useMenuSlot(menuHistory);

  // Announce each tab the first time it gets something during a request.
  useEffect(() => {
    const pending = state.pending;
    if (!pending || pending.error !== null) return;
    if (announcedRef.current?.requestId !== pending.requestId) announcedRef.current = { requestId: pending.requestId, tabs: new Set() };
    const announced = announcedRef.current.tabs;
    const filled = tabsWithContent(routeGroups(pending.draft?.groups ?? []), pending.answer);
    const arrived = WORKSPACE_TABS.filter(({ id }) => filled.has(id) && !announced.has(id));
    if (arrived.length === 0) return;
    arrived.forEach(({ id }) => announced.add(id));
    setAnnouncement(arrived.map(({ label }) => `${label} ready`).join(". "));
  }, [state.pending]);

  // A finished page takes focus (without scrolling) unless the visitor had
  // already started using it.
  useEffect(() => {
    const id = focusPaneRef.current;
    if (!id) return;
    focusPaneRef.current = null;
    document.getElementById(`${id}-title`)?.focus({ preventScroll: true });
  }, [state.entries]);

  // Each tab keeps its own scroll position. A pane seen for the first time
  // starts at the top; a tab seen for the first time keeps the tab bar in view.
  const shownId = pane?.id ?? null;
  const shownTab = pane?.tab ?? null;
  useLayoutEffect(() => {
    const last = lastShownRef.current;
    lastShownRef.current = shownId ? { id: shownId, tab: shownTab } : null;
    const current = shownPane(stateRef.current);
    if (!current || !shownId || (last && last.id === shownId && last.tab === shownTab)) return;
    const saved = shownTab ? current.view.scroll[shownTab] : undefined;
    if (saved !== undefined) window.scrollTo(0, saved);
    else if (!last || last.id !== shownId) window.scrollTo(0, 0);
    else {
      const panel = document.getElementById(`${shownId}-panel-${shownTab}`);
      const bar = panel?.parentElement?.querySelector<HTMLElement>("[role=tablist]");
      if (!panel || !bar) return;
      const target = Math.max(0, window.scrollY + panel.getBoundingClientRect().top - bar.getBoundingClientRect().height);
      if (target < window.scrollY) window.scrollTo(0, target);
    }
  }, [shownId, shownTab]);

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

  function send() {
    if (actions.ask(question, { source: "typed", fresh: false })) setQuestion("");
  }

  function sendOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    send();
  }

  function composer(dock: boolean) {
    return (
      <form className={dock ? "composer dock-composer" : "composer"} onSubmit={(event) => { event.preventDefault(); send(); }}>
        <div className="question-field">
          <textarea
            id={dock ? "question-dock" : "question-rail"}
            ref={dock ? dockTextareaRef : undefined}
            aria-label="Question"
            rows={dock ? 1 : 3}
            placeholder={dock ? "Ask about a song, show, or recording" : "Ask about a song, show, source, or recording"}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={sendOnEnter}
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
      activeTab={entryTab(entry)}
      statuses={null}
      streaming={false}
      hidden={entry.id !== shownId}
      previous={entry.id === heldId}
      parts={parts}
      onSelectTab={actions.selectTab}
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
        activeTab={activeTabOf(pending.view, pending.initialTab, content.groups)}
        statuses={shown.kind === "draft" ? null : pending.statuses}
        streaming
        hidden={pending.requestId !== shownId}
        previous={false}
        parts={parts}
        onSelectTab={actions.selectTab}
        onInteract={shown.kind === "draft" && !pending.interacted ? actions.interact : undefined}
        onFollowUp={actions.followUp}
      />
    );
  }

  const showStart = shown.kind === "start" || (shown.kind === "failed" && !shown.entry);

  return (
    <main className={isPhone ? "app-shell workspace-shell phone" : "app-shell workspace-shell"}>
      <p role="status" className="sr-only">{announcement}</p>
      <div className="workspace-grid">
        {!isPhone && (
          <aside className="workspace-rail" aria-label="Explorations">
            <header className="masthead">
              <a className="wordmark" href="/">Deadbot</a>
              <p>Grateful Dead knowledge, listening, and context</p>
            </header>
            <ExplorationHistory
              state={state}
              headingId={railHeadingId}
              onNavigate={actions.navigate}
              onStop={actions.stop}
              onRetry={actions.retry}
              onNewChat={actions.newChat}
            />
            {composer(false)}
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
            {showStart && <div className="start-screen">{startView(startAsk)}</div>}
            {panes}
          </div>
          {!isPhone && player}
        </section>
      </div>
      {isPhone && (
        <div className="mobile-dock" ref={dockRef}>
          {phonePlayer}
          {composer(true)}
        </div>
      )}
    </main>
  );
}

