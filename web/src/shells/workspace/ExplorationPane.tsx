import { memo, useEffect, useState } from "react";
import type { FollowUp } from "../../core/ask-request";
import { groupsOfResponse, type RenderGroup } from "../../core/page-draft";
import type { ExperienceResponse, SourceReference } from "../../types";
import type { Pending } from "../../core/exploration-state";
import { pageHref } from "../../core/site-nav";
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

// The page's address, copied for sharing: one quiet line at the page's foot.
// A follow-up's link names the question its thread began with and then its
// own (see core/site-nav.ts).
function CopyLink({ question, followUp }: { question: string; followUp: string | null }) {
  const [result, setResult] = useState<"copied" | "failed" | null>(null);
  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(() => setResult(null), 4000);
    return () => window.clearTimeout(timer);
  }, [result]);
  async function copy() {
    const link = new URL(pageHref({ question, followUp }), window.location.origin).toString();
    try {
      await navigator.clipboard.writeText(link);
      setResult("copied");
    } catch {
      setResult("failed");
    }
  }
  return (
    <p className="page-foot">
      <button type="button" className="quiet-action" onClick={() => void copy()}>Copy link</button>
      <span role="status">{result === "copied" ? "Link copied" : result === "failed" ? "Couldn’t copy. The address bar has this page’s link." : ""}</span>
    </p>
  );
}

// A page that could not be drawn: its title and the model's lead, plainly,
// and a way to ask for it again.
export function PaneFallback({ paneId, hidden, title, lead, question, onAskAgain }: {
  paneId: string;
  hidden: boolean;
  title: string;
  lead: string | null;
  // The question to ask again; null while the page is still being written.
  question: string | null;
  onAskAgain(question: string): void;
}) {
  const titleId = `${paneId}-title`;
  return (
    <article className="exploration-pane" hidden={hidden} aria-labelledby={titleId}>
      <div className="content-heading">
        <h1 id={titleId} tabIndex={-1}>{title}</h1>
      </div>
      {lead && lead.trim() && <p className="answer-lead">{lead}</p>}
      <p className="workspace-waiting">The rest of this page could not be shown.</p>
      {question && <p><button type="button" className="ask-chip" onClick={() => onAskAgain(question)}>Ask it again</button></p>}
    </article>
  );
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
  linkQuestion = null,
  linkFollowUp = null,
  onInteract,
  onFollowUp
}: {
  paneId: string;
  content: PaneContent;
  statuses: string[] | null;
  streaming: boolean;
  hidden: boolean;
  previous: boolean;
  // A finished page's address, for Copy link.
  linkQuestion?: string | null;
  linkFollowUp?: string | null;
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
        {!streaming && linkQuestion && <CopyLink question={linkQuestion} followUp={linkFollowUp} />}
      </div>
    </article>
  );
});
