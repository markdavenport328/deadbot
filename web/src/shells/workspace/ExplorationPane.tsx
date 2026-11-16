import { memo } from "react";
import type { FollowUp } from "../../core/ask-request";
import { groupsOfResponse, type RenderGroup } from "../../core/page-draft";
import type { ExperienceResponse, SourceReference } from "../../types";
import { visible, type EntryView, type ExplorationState, type Pending } from "../../core/exploration-state";
import { RichText } from "../../cards/text";
import { PageGroups, SourcesFooter } from "../../cards/PageGroups";

// One exploration's page as the pane draws it: a finished response, or the
// draft while it streams. The same shape either way, so the pane (and every
// disclosure and chart pick inside it) carries straight from draft to final.
export type PaneContent = {
  // The visitor's question, shown while Deadbot is still working.
  question: string;
  // The model's optional line above the lead, then the lead itself, at the
  // top of the page.
  headline: string | null;
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
    content = { question: "", headline: response.headline ?? null, lead: response.lead, groups: groupsOfResponse(response), sources: response.sources };
    finishedContent.set(response, content);
  }
  return content;
}

export function draftContent(pending: Pending): PaneContent {
  return {
    question: pending.question,
    headline: pending.draft?.headline ?? null,
    // The lead streams ahead of the page head; the head's copy replaces it once it lands.
    lead: pending.draft?.lead ?? pending.lead,
    groups: pending.draft?.groups ?? [],
    sources: []
  };
}

// The pane on screen and the view state that belongs to it, or null for the
// start view. The scroll position is saved into that view.
export function shownPane(state: ExplorationState): { id: string; view: EntryView; draft: boolean } | null {
  const shown = visible(state);
  switch (shown.kind) {
    case "start":
      return null;
    case "working":
      return { id: shown.pending.requestId, view: shown.pending.view, draft: false };
    case "draft":
      return { id: shown.pending.requestId, view: shown.pending.view, draft: true };
    case "failed":
      return shown.entry ? { id: shown.entry.id, view: shown.entry.view, draft: false } : null;
    case "held":
    case "entry":
      return { id: shown.entry.id, view: shown.entry.view, draft: false };
  }
}

// One exploration: its headline and lead, then every section in one column
// in the order the model wrote them, then the sources. Before anything has
// arrived it shows what Deadbot is doing instead.
export const ExplorationPane = memo(function ExplorationPane({
  paneId,
  content,
  statuses,
  streaming,
  hidden,
  previous,
  onInteract,
  onFollowUp
}: {
  paneId: string;
  content: PaneContent;
  statuses: string[] | null;
  streaming: boolean;
  hidden: boolean;
  previous: boolean;
  // Present only on the page being written right now: the first touch there
  // means the visitor has taken over, and later arrivals leave their view alone.
  onInteract?: () => void;
  onFollowUp: FollowUp;
}) {
  const titleId = `${paneId}-title`;
  const className = ["exploration-pane", previous ? "previous" : null].filter(Boolean).join(" ");

  if (statuses) {
    const lines = statuses.length > 0 ? statuses.slice(-4) : ["Looking through the library…"];
    return (
      <article className={`${className} content-working`} hidden={hidden} aria-labelledby={titleId}>
        <p className="eyebrow">Working</p>
        <h1 id={titleId} tabIndex={-1}>{content.question}</h1>
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

  const filled = content.groups.some((group) => group.blocks.length > 0);

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
      {content.headline && (
        <div className="content-heading">
          <h1 id={titleId} tabIndex={-1}>{content.headline}</h1>
        </div>
      )}
      {content.lead && content.lead.trim() && (
        <RichText className="answer-lead" text={content.lead} id={content.headline ? undefined : titleId} tabIndex={content.headline ? undefined : -1} />
      )}
      <div className="workspace-panel">
        {filled
          ? <PageGroups groups={content.groups} sources={content.sources} composing={streaming} onFollowUp={onFollowUp} />
          : streaming && <p className="workspace-waiting">Writing the answer…</p>}
        {!streaming && <SourcesFooter groups={content.groups} sources={content.sources} />}
      </div>
    </article>
  );
});
