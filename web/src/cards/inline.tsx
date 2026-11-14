import { type ReactNode } from "react";
import { type FollowUp } from "../core/ask-request";
import { ListenControl, archiveTrack } from "./listen-control";

// A reading link: sources, articles, charts. A URL that is itself an audio
// track still plays in-page, so no path to a raw archive file leaves the page.
export function ExternalLink({ href, children, className, label }: { href: string; children: ReactNode; className?: string; label?: string }) {
  if (archiveTrack(href)) {
    const words = label ?? (typeof children === "string" ? children : "Play this track");
    return <ListenControl url={href} label={words} className={className} queueable={false}>{children}</ListenControl>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children}
    </a>
  );
}

const inlineLink = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

const inlineEmphasis = /(\*\*|__)(.+?)\1|(\*|_)(?=\S)(.+?)(?<=\S)\3/g;

// Bold and italic markers the model writes, so *Without a Net* reads as a
// title rather than as asterisks.
function renderEmphasis(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(inlineEmphasis)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    if (match[2] !== undefined) nodes.push(<strong key={`${keyPrefix}-${index}`}>{match[2]}</strong>);
    else nodes.push(<em key={`${keyPrefix}-${index}`}>{match[4]}</em>);
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

// The same words without their emphasis markers, for an accessible name.
export function plainText(text: string): string {
  return text.replace(inlineEmphasis, (_match, _bold, boldText, _italic, italicText) => boldText ?? italicText ?? "");
}

export function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(inlineLink)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(...renderEmphasis(text.slice(last, index), `t${last}`));
    nodes.push(<ExternalLink key={`${index}-${match[2]}`} href={match[2]} label={plainText(match[1])}>{renderEmphasis(match[1], `l${index}`)}</ExternalLink>);
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(...renderEmphasis(text.slice(last), `t${last}`));
  return nodes;
}

export function Eyebrow({ label, title }: { label?: string | null; title?: string | null }) {
  if (!label) return null;
  if (title) {
    const normalizedLabel = label.trim().toLowerCase();
    const normalizedTitle = title.trim().toLowerCase();
    if (normalizedTitle === normalizedLabel || normalizedTitle.startsWith(`${normalizedLabel}:`)) return null;
  }
  return <p className="eyebrow">{label}</p>;
}

// The one control that speaks to the thread. Only questions the composer
// wrote reach here, labeled as what they are, so a page carries a few of them
// and each reads as a next question rather than as navigation.
export function AskChip({ prompt, onFollowUp }: { prompt: string; onFollowUp: FollowUp }) {
  return (
    <button type="button" className="ask-chip" onClick={() => onFollowUp(prompt)}>
      {prompt}
    </button>
  );
}
