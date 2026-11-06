import { memo, useMemo, useState, type ReactNode } from "react";
import type { FollowUp } from "./ask-request";
import { groupsOfResponse, type RenderGroup } from "./page-draft";
import type { ExperienceResponse, SourceReference } from "./types";
import { WORKSPACE_TABS, openingTab, readTab, routeGroups, tabsWithContent, type WorkspaceTab } from "./tab-routing";
import { visible, type Entry, type EntryView, type ExplorationState, type Pending } from "./exploration-state";
import { WorkspaceTabs, type TabState } from "./WorkspaceTabs";

// How the shell renders a page's pieces. App.tsx supplies them, so the
// workspace shares the old shell's group, unit and sources renderers.
export type PageParts = {
  groups(groups: RenderGroup[], sources: SourceReference[], composing: boolean, onFollowUp: FollowUp): ReactNode;
  sources(groups: RenderGroup[], sources: SourceReference[]): ReactNode;
  inline(text: string): ReactNode;
};

// One exploration's page as the pane draws it: a finished response, or the
// draft while it streams. The same shape either way, so the pane (and every
// disclosure and chart pick inside it) carries straight from draft to final.
export type PaneContent = {
  title: string;
  answer: string | null;
  lead: string | null;
  groups: RenderGroup[];
  sources: SourceReference[];
};

// A finished response never changes, so its pane content is built once and
// stays the same object: the pane skips re-rendering while a later request
// streams in beside it.
const finishedContent = new WeakMap<ExperienceResponse, PaneContent>();

export function contentOf(response: ExperienceResponse): PaneContent {
  let content = finishedContent.get(response);
  if (!content) {
    content = { title: response.title, answer: response.answer, lead: response.body_lead ?? null, groups: groupsOfResponse(response), sources: response.sources };
    finishedContent.set(response, content);
  }
  return content;
}

export function draftContent(pending: Pending): PaneContent {
  return {
    title: pending.draft?.title || pending.question,
    answer: pending.answer,
    lead: pending.draft?.lead ?? null,
    groups: pending.draft?.groups ?? [],
    sources: []
  };
}

export function activeTabOf(view: EntryView, initial: WorkspaceTab | null, groups: RenderGroup[]): WorkspaceTab {
  return view.tab ?? openingTab(initial, routeGroups(groups));
}

export function entryTab(entry: Entry): WorkspaceTab {
  return activeTabOf(entry.view, readTab((entry.response as { initial_tab?: unknown }).initial_tab), contentOf(entry.response).groups);
}

// The pane on screen and the view state that belongs to it, or null for the
// start view. Tab clicks and scroll positions are saved into that view.
export function shownPane(state: ExplorationState): { id: string; tab: WorkspaceTab | null; view: EntryView; draft: boolean } | null {
  const shown = visible(state);
  switch (shown.kind) {
    case "start":
      return null;
    case "working":
      return { id: shown.pending.requestId, tab: null, view: shown.pending.view, draft: false };
    case "draft":
      return { id: shown.pending.requestId, tab: activeTabOf(shown.pending.view, shown.pending.initialTab, shown.pending.draft?.groups ?? []), view: shown.pending.view, draft: true };
    case "failed":
      return shown.entry ? { id: shown.entry.id, tab: entryTab(shown.entry), view: shown.entry.view, draft: false } : null;
    case "held":
    case "entry":
      return { id: shown.entry.id, tab: entryTab(shown.entry), view: shown.entry.view, draft: false };
  }
}

const WAITING: Record<WorkspaceTab, string> = {
  listen: "Finding recordings",
  charts: "Drawing the picture",
  read: "Writing the answer"
};

// A tab is marked new when content arrives there while the visitor is
// elsewhere and has not looked at it yet during this request.
export function tabStates(content: Set<WorkspaceTab>, active: WorkspaceTab, streaming: boolean, seen: ReadonlySet<WorkspaceTab> = new Set()): Record<WorkspaceTab, TabState> {
  const states = {} as Record<WorkspaceTab, TabState>;
  for (const { id } of WORKSPACE_TABS) {
    if (content.has(id)) states[id] = streaming && id !== active && !seen.has(id) ? "new" : "ready";
    else states[id] = streaming ? "preparing" : "unused";
  }
  return states;
}

// One exploration: its heading, the tab bar and all three panels, mounted
// together so switching tabs never rebuilds a card. Before anything has
// arrived it shows what Deadbot is doing instead.
export const ExplorationPane = memo(function ExplorationPane({
  paneId,
  content,
  activeTab,
  statuses,
  streaming,
  hidden,
  previous,
  parts,
  onSelectTab,
  onInteract,
  onFollowUp
}: {
  paneId: string;
  content: PaneContent;
  activeTab: WorkspaceTab;
  statuses: string[] | null;
  streaming: boolean;
  hidden: boolean;
  previous: boolean;
  parts: PageParts;
  onSelectTab(tab: WorkspaceTab): void;
  // Present only on the page being written right now: the first touch there
  // means the visitor has taken over, and later arrivals leave their view alone.
  onInteract?: () => void;
  onFollowUp: FollowUp;
}) {
  const routed = useMemo(() => routeGroups(content.groups), [content.groups]);
  const filled = useMemo(() => tabsWithContent(routed, content.answer), [routed, content.answer]);
  const titleId = `${paneId}-title`;
  // Tabs the visitor has looked at in this pane; their "new" mark stays off.
  const [seen, setSeen] = useState<ReadonlySet<WorkspaceTab>>(() => new Set([activeTab]));
  if (!statuses && !seen.has(activeTab)) setSeen(new Set(seen).add(activeTab));
  const className = ["exploration-pane", previous ? "previous" : null].filter(Boolean).join(" ");

  if (statuses) {
    const lines = statuses.length > 0 ? statuses.slice(-4) : ["Looking through the library…"];
    return (
      <article className={`${className} content-working`} hidden={hidden} aria-labelledby={titleId}>
        <p className="eyebrow">Working</p>
        <h1 id={titleId} tabIndex={-1}>{content.title}</h1>
        <ol className="progress-lines" aria-hidden="true">
          {lines.map((line, index) => (
            <li key={`${index}-${line}`} className={index === lines.length - 1 ? "current" : undefined}>
              {line}{index === lines.length - 1 && statuses.length > 0 ? "…" : ""}
            </li>
          ))}
        </ol>
      </article>
    );
  }

  const states = tabStates(filled, activeTab, streaming, seen);
  const panel = (tab: WorkspaceTab) => {
    if (!filled.has(tab)) return streaming ? <p className="workspace-waiting">{WAITING[tab]}…</p> : null;
    const groups = parts.groups(routed[tab], content.sources, streaming, onFollowUp);
    if (tab !== "read") return groups;
    return (
      <>
        {content.answer && content.answer.trim() && <p className="workspace-answer">{parts.inline(content.answer)}</p>}
        {content.lead && <p className="answer-lead">{parts.inline(content.lead)}</p>}
        {groups}
        {!streaming && parts.sources(content.groups, content.sources)}
      </>
    );
  };

  return (
    <article
      className={className}
      hidden={hidden}
      aria-labelledby={titleId}
      onPointerDown={onInteract}
      onKeyDown={onInteract}
      onWheel={onInteract}
      onTouchMove={onInteract}
    >
      {previous && <p className="previous-label">Previous result</p>}
      <div className="content-heading">
        <h1 id={titleId} tabIndex={-1}>{content.title}</h1>
      </div>
      <WorkspaceTabs active={activeTab} states={states} onSelect={onSelectTab} idPrefix={paneId} />
      {WORKSPACE_TABS.map(({ id }) => (
        <div
          key={id}
          role="tabpanel"
          id={`${paneId}-panel-${id}`}
          aria-labelledby={`${paneId}-tab-${id}`}
          className="workspace-panel"
          hidden={id !== activeTab}
        >
          {panel(id)}
        </div>
      ))}
    </article>
  );
});
