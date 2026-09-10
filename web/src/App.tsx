import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import type { AlbumUnitBlock, ExperienceBlock, ExperienceGroup, ExperienceResponse, ShowUnitBlock, SourceReference } from "./types";
import type { PageEvent, StreamEvent } from "./stream-events";
import { loadRequestedStreamEvents, loadRequestedVisualFixture, requestedStreamFixture, requestedVisualFixture } from "./visual-fixture-loader";

type SetlistSections = ShowUnitBlock["sets"];
type ListenActions = ShowUnitBlock["listen"];
type UnitSources = ShowUnitBlock["sources"];

function formatShowDate(iso: string | null | undefined): string {
  if (!iso) return "Undated";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  return `${Number(month)}/${Number(day)}/${year.slice(2)}`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

// A card's identity row wants a reading date ("March 29, 1990"), not the
// short numeric form the rest of the page uses.
function formatShowDateLong(iso: string | null | undefined): string {
  if (!iso) return "Undated";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  const monthName = MONTH_NAMES[Number(month) - 1];
  if (!monthName) return iso;
  return `${monthName} ${Number(day)}, ${year}`;
}

// A release date is sometimes only a year. Prefer the full reading date and
// fall back to the year alone rather than showing nothing.
function formatReleaseDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return formatShowDateLong(iso);
  const year = /^(\d{4})/.exec(iso);
  return year ? year[1] : iso;
}

// "studio" becomes "Studio album"; a release type that already reads as an
// album ("live album") is not doubled up.
function formatReleaseType(releaseType: string): string {
  const words = releaseType.split(/[\s-]+/).filter(Boolean);
  const capitalized = words.map((word, index) => (index === 0 ? capitalize(word) : word)).join(" ");
  return /album/i.test(releaseType) ? capitalized : `${capitalized} album`;
}

const suggestions = [
  "What are the best versions of Franklin's Tower?",
  "What shows did Branford play on?",
  "What was the live legacy of American Beauty?"
];

function createThreadId(): string {
  return `web-${crypto.randomUUID()}`;
}

async function refreshIfServerChanged(): Promise<void> {
  const result = await fetch("/api/health", { cache: "no-store" });
  if (!result.ok) return;
  const health = await result.json() as { git_commit?: string };
  const current = health.git_commit;
  if (!current || current === "unknown") return;
  const storageKey = "deadbot-server-version";
  const previous = sessionStorage.getItem(storageKey);
  sessionStorage.setItem(storageKey, current);
  if (previous && previous !== current) window.location.reload();
}

function sourceFor(sources: SourceReference[], sourceId: string): SourceReference | undefined {
  return sources.find((source) => source.source_id === sourceId);
}

function dedupeSources(sources: SourceReference[]): SourceReference[] {
  const seen = new Set<string>();
  const result: SourceReference[] = [];
  for (const source of sources) {
    const key = `${source.label}|${source.url ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(source);
  }
  return result;
}

function ExternalLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children}
    </a>
  );
}

// Listening links open supplied recordings externally; they do not start playback.
function listeningDestination(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "the recording site";
  }
}

function ListeningLabel({ title, url, className = "" }: { title: string; url?: string | null; className?: string }) {
  if (!url) return <span className={`listening-label ${className}`.trim()}>{title}</span>;
  const destination = listeningDestination(url);
  const actionLabel = `${destination.includes("youtube") ? "Watch" : "Listen to"} ${title} on ${destination} (opens in a new tab)`;
  return (
    <a
      className={`listening-label song-link ${className}`.trim()}
      href={url}
      target="_blank"
      rel="noreferrer"
      aria-label={actionLabel}
      title={actionLabel}
    >
      <span className="play-mark" aria-hidden="true">▶</span>
      <span>{title}</span>
    </a>
  );
}

function venueFirstShowLabel(showDate?: string | null, venueName?: string | null, existingLabel?: string | null): string {
  const date = formatShowDate(showDate);
  const venue = venueName || existingLabel?.replace(/^\d{4}-\d{2}-\d{2} — /, "") || "";
  if (venue && date) return `${venue} (${date})`;
  return venue || date || existingLabel || "Unknown show";
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

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(inlineLink)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(...renderEmphasis(text.slice(last, index), `t${last}`));
    nodes.push(<ExternalLink key={`${index}-${match[2]}`} href={match[2]}>{renderEmphasis(match[1], `l${index}`)}</ExternalLink>);
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(...renderEmphasis(text.slice(last), `t${last}`));
  return nodes;
}

function Eyebrow({ label, title }: { label?: string | null; title?: string | null }) {
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
function AskChip({ prompt, onFollowUp }: { prompt: string; onFollowUp: (prompt: string) => void }) {
  return (
    <button type="button" className="ask-chip" onClick={() => onFollowUp(prompt)}>
      {prompt}
    </button>
  );
}

// Topic chips: the model writes a short label and the full question it stands
// for. The chip shows the label; pressing it sends the model's question.
type FollowUpTopic = { label: string; question: string };

function TopicChips({ topics, onFollowUp }: { topics?: FollowUpTopic[] | null; onFollowUp: (prompt: string) => void }) {
  const items = (topics ?? []).filter((topic) => topic.label.trim() && topic.question.trim());
  if (items.length === 0) return null;
  return (
    <div className="topics">
      {items.map((topic) => (
        <button type="button" className="ask-chip" key={topic.label} onClick={() => onFollowUp(topic.question)} title={topic.question}>
          {topic.label}
        </button>
      ))}
    </div>
  );
}

function MoreAbout({ topics, onFollowUp }: { topics?: FollowUpTopic[] | null; onFollowUp: (prompt: string) => void }) {
  if ((topics ?? []).length === 0) return null;
  return (
    <div className="ask-block">
      <span className="k">More about</span>
      <TopicChips topics={topics} onFollowUp={onFollowUp} />
    </div>
  );
}

function MediaEmbed({ block }: { block: Extract<ExperienceBlock, { type: "media_link" }> }) {
  if (block.embed_kind === "youtube" && block.embed_id) {
    return (
      <iframe
        className="media-frame"
        src={`https://www.youtube-nocookie.com/embed/${block.embed_id}`}
        title={block.title}
        loading="lazy"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
      />
    );
  }
  if (block.embed_kind === "spotify" && block.embed_id) {
    return (
      <iframe
        className="spotify-frame"
        src={`https://open.spotify.com/embed/${block.embed_id}`}
        title={block.title}
        loading="lazy"
        allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
      />
    );
  }
  return null;
}

type GlyphKind = "spotify" | "wave" | "disc" | "play";

// A leading destination glyph replaces the trailing arrow: gold, 14px, and
// chosen by where the link actually goes rather than by a generic convention.
function Glyph({ kind }: { kind: GlyphKind }) {
  if (kind === "wave") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
          <path d="M3 12v1M7 8v8M11 5v14M15 8v8M19 10v4M23 12v1" />
        </g>
      </svg>
    );
  }
  if (kind === "disc") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth={2}>
          <circle cx={12} cy={12} r={9} />
          <circle cx={12} cy={12} r={2.2} fill="currentColor" />
        </g>
      </svg>
    );
  }
  const path = kind === "spotify"
    ? "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.59 14.42a.62.62 0 0 1-.86.21c-2.35-1.44-5.31-1.76-8.79-.97a.62.62 0 0 1-.28-1.22c3.81-.87 7.08-.5 9.72 1.12.3.18.39.57.21.86zm1.22-2.72a.78.78 0 0 1-1.07.26c-2.69-1.65-6.79-2.13-9.97-1.17a.78.78 0 1 1-.45-1.49c3.63-1.1 8.15-.57 11.24 1.33.36.22.48.7.25 1.07zm.1-2.84c-3.22-1.91-8.54-2.09-11.62-1.16a.94.94 0 1 1-.54-1.79c3.53-1.07 9.4-.87 13.11 1.34a.94.94 0 0 1-.95 1.61z"
    : "M7 4.5v15l12-7.5z";
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d={path} />
    </svg>
  );
}

function glyphForAction(url: string, isOfficial: boolean): GlyphKind {
  let host = "";
  try {
    host = new URL(url).hostname.replace(/^www\./, "");
  } catch {
    host = "";
  }
  if (host === "open.spotify.com") return "spotify";
  if (host === "youtube.com" || host === "youtu.be") return "play";
  if (host === "archive.org" || host === "relisten.net") return "wave";
  return isOfficial ? "disc" : "wave";
}

// The primary action is the first official listening path, or simply the
// first when none is marked official. It renders filled; the rest are
// outlined, and none carries a trailing arrow now that a glyph leads instead.
function ListenActionList({ actions }: { actions: ListenActions }) {
  if (actions.length === 0) return null;
  const officialIndex = actions.findIndex((action) => action.is_official);
  const primaryIndex = officialIndex >= 0 ? officialIndex : 0;
  return (
    <ul className="listen-actions" aria-label="Listen">
      {actions.map((action, index) => (
        <li key={action.url}>
          <a
            className={index === primaryIndex ? "listen-action primary" : "listen-action"}
            href={action.url}
            target="_blank"
            rel="noreferrer"
            aria-label={`${action.label} on ${listeningDestination(action.url)} (opens in a new tab)`}
            title={`Opens ${listeningDestination(action.url)} in a new tab`}
          >
            <Glyph kind={glyphForAction(action.url, action.is_official)} />
            <span className="listen-action-label">{action.label}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

// "Listen for" is a sentence, not a labeled row: cream links in muted body
// text, shown whenever a unit has highlighted songs or tracks.
function ListenFor({ items: allItems }: { items: { key: string; title: string; url?: string | null }[] }) {
  // A song highlighted twice in one show (a reprise) is named once here; the
  // setlist still stars both.
  const seen = new Set<string>();
  const items = allItems.filter((item) => {
    const key = item.title.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (items.length === 0) return null;
  return (
    <p className="listen-for">
      Listen for{" "}
      {items.map((item, index) => (
        <span key={item.key}>
          {index > 0 && <span className="sep">·</span>}
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Listen to ${item.title} (opens in a new tab)`}
              title={`Opens ${listeningDestination(item.url)} in a new tab`}
            >
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </span>
      ))}
    </p>
  );
}

// One header row per card: the type on the left, a tabular-numeral fact on
// the right. Both are the same small-caps label style.
function IdRow({ type, when }: { type: ReactNode; when?: ReactNode }) {
  return (
    <div className="id-row">
      <span className="k type">{type}</span>
      {when ? <span className="k when">{when}</span> : null}
    </div>
  );
}

// The meta line under a card's h2: parts joined by a quiet middot, blank
// parts dropped so a card missing one fact doesn't leave a stray separator.
function Meta({ parts }: { parts: ReactNode[] }) {
  const visible = parts.filter((part) => part !== null && part !== undefined && part !== "");
  if (visible.length === 0) return null;
  return (
    <p className="meta">
      {visible.map((part, index) => (
        <span key={index}>
          {index > 0 && <span className="sep">·</span>}
          {part}
        </span>
      ))}
    </p>
  );
}

// A plain "Title · detail" row, used for recordings, on-record albums, and
// credits inside the drawer. Title links out when a url is given.
function PlainList({ items }: { items: { key: string; title: string; url?: string | null; detail?: string | null }[] }) {
  return (
    <ul className="plain">
      {items.map((item) => (
        <li key={item.key}>
          {item.url ? (
            <ExternalLink className="plain-title" href={item.url}>{item.title}</ExternalLink>
          ) : (
            <span className="plain-title">{item.title}</span>
          )}
          {item.detail ? <span>{item.detail}</span> : null}
        </li>
      ))}
    </ul>
  );
}

// A "Name · instruments" grid, used for lineups and album personnel.
function PeopleList({ people }: { people: { key: string; name: string; detail: string; guest?: boolean }[] }) {
  return (
    <ul className="people">
      {people.map((person) => (
        <li key={person.key}>
          {person.name}
          <span>{[person.detail, person.guest ? "guest" : null].filter(Boolean).join(" · ")}</span>
        </li>
      ))}
    </ul>
  );
}

// The setlist panel: one column per set, numbering continuing across sets
// (Set 2 starts at 9 when Set 1 has 8 songs), no play triangles, highlighted
// songs starred.
function SetlistPanel({ sets }: { sets: SetlistSections }) {
  let runningCount = 0;
  return (
    <div className="setlist-panel">
      {sets.map((set) => {
        const start = runningCount + 1;
        runningCount += set.songs.length;
        return (
          <div key={set.label}>
            <span className="k">{set.label}</span>
            <ol className="song-list" start={start}>
              {set.songs.map((song, index) => (
                <li key={song.performance_id} value={start + index} className={song.highlighted ? "hi" : undefined}>
                  {song.listen_url ? (
                    <a
                      href={song.listen_url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Listen to ${song.title} (opens in a new tab)`}
                      title={`Opens ${listeningDestination(song.listen_url)} in a new tab`}
                    >
                      {song.title}
                    </a>
                  ) : (
                    <span>{song.title}</span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </div>
  );
}

// The album tracklist: the same numbered-link styling as the setlist, one
// column, no set grouping.
function TrackList({ tracks }: { tracks: AlbumUnitBlock["tracks"] }) {
  return (
    <ol className="song-list">
      {tracks.map((track) => (
        <li key={track.track_number} value={track.track_number} className={track.highlighted ? "hi" : undefined}>
          {track.listen_url ? (
            <a
              href={track.listen_url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Listen to ${track.title} (opens in a new tab)`}
              title={`Opens ${listeningDestination(track.listen_url)} in a new tab`}
            >
              {track.title}
            </a>
          ) : (
            <span>{track.title}</span>
          )}
        </li>
      ))}
    </ol>
  );
}

// The "Go deeper" footer block: each source's title set in the serif as a
// cited headline, with publication and note sharing one muted line beneath.
function GoDeeper({ sources }: { sources: UnitSources }) {
  if (sources.length === 0) return null;
  return (
    <div className="reading">
      <span className="k">Go deeper</span>
      {sources.map((source) => (
        <div className="reading-source" key={source.url}>
          <p className="reading-title">
            <ExternalLink href={source.url}>{source.label}</ExternalLink>
          </p>
          {(source.source_name || source.note) && (
            <p className="reading-pub">
              {source.source_name && <span className="pub">{source.source_name}</span>}
              {source.source_name && source.note ? " · " : ""}
              {source.note}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

type DrawerTab = { id: string; label: string; count?: number; content: ReactNode };

// The tabbed drawer that replaced the stacked <details> facets. A disclosure
// decides once, when it first appears, whether to start open (the same
// reasoning as the old Facet component): later renders must not snap it open
// or closed beneath the reader.
function Drawer({ tabs, initialOpen }: { tabs: DrawerTab[]; initialOpen: string | null }) {
  const [open, setOpen] = useState(initialOpen);
  const baseId = useId();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  if (tabs.length === 0) return null;

  function focusTabAt(index: number) {
    const target = tabs[(index + tabs.length) % tabs.length];
    tabRefs.current[target.id]?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTabAt(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTabAt(index - 1);
    }
  }

  return (
    <div className="drawer">
      <div className="tabs" role="tablist">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${baseId}-tab-${tab.id}`}
            aria-selected={open === tab.id}
            aria-controls={`${baseId}-panel-${tab.id}`}
            className="tab k"
            ref={(element) => { tabRefs.current[tab.id] = element; }}
            onClick={() => setOpen((current) => (current === tab.id ? null : tab.id))}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            {tab.label}
            {tab.count !== undefined && <span className="n">{tab.count}</span>}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${baseId}-panel-${tab.id}`}
          aria-labelledby={`${baseId}-tab-${tab.id}`}
          className="panel"
          hidden={open !== tab.id}
        >
          {open === tab.id ? tab.content : null}
        </div>
      ))}
    </div>
  );
}

function UnitSourceList({ sources }: { sources: UnitSources }) {
  if (sources.length === 0) return null;
  return (
    <ul className="unit-sources" aria-label="Sources for this item">
      {sources.map((source) => (
        <li key={source.url}>
          {source.note && <p className="unit-source-note">{source.note}</p>}
          <ExternalLink href={source.url}>{source.label}</ExternalLink>
          {source.source_name && <span className="unit-source-name"> · {source.source_name}</span>}
        </li>
      ))}
    </ul>
  );
}

type UnitBlock = Extract<ExperienceBlock, { type: "show_unit" | "performance_unit" | "album_unit" | "song_overview" }>;

function isUnit(block: ExperienceBlock): block is UnitBlock {
  return block.type === "show_unit" || block.type === "performance_unit" || block.type === "album_unit" || block.type === "song_overview";
}

function unitIdentity(block: UnitBlock): { title: string; url?: string | null } {
  switch (block.type) {
    case "show_unit":
      return { title: block.venue_name ? `${block.venue_name} (${formatShowDate(block.show_date)})` : formatShowDate(block.show_date), url: block.listen[0]?.url };
    case "performance_unit":
      return { title: `${block.song_title}, ${venueFirstShowLabel(block.show_date, block.venue_name, block.show_label)}`, url: block.listen[0]?.url };
    case "album_unit":
      return { title: block.release_date ? `${block.title} (${block.release_date.slice(0, 4)})` : block.title, url: block.listen[0]?.url };
    case "song_overview":
      return { title: block.title, url: block.representative_performances[0]?.listen_url };
  }
}

// A mention is one line: the object, the model's note, a way to hear it.
function MentionRow({ block }: { block: UnitBlock }) {
  const identity = unitIdentity(block);
  return (
    <li className={`mention emphasis-mention ${block.type}`}>
      <ListeningLabel title={identity.title} url={identity.url} className="list-item-label" />
      {block.note && <span className="mention-note">{renderInline(block.note)}</span>}
    </li>
  );
}

function CriteriaTable({ criteria, judgments }: { criteria: string[]; judgments: string[] }) {
  if (criteria.length === 0) return null;
  return (
    <dl className="criteria">
      {criteria.map((criterion, index) => (
        <div key={criterion}>
          <dt>{criterion}</dt>
          <dd>{judgments[index] ? renderInline(judgments[index]) : null}</dd>
        </div>
      ))}
    </dl>
  );
}

// A disclosure decides once, when it first appears, whether to start open.
// Later renders leave it alone, so a page that finishes composing does not
// snap its facets open beneath the reader.
function unitKey(block: UnitBlock): string {
  switch (block.type) {
    case "show_unit": return block.show_id;
    case "performance_unit": return block.performance_id;
    case "album_unit": return block.release_id;
    case "song_overview": return block.song_id;
  }
}

// Units are keyed by identity, so a block that streamed in stays the same
// element when the final response replaces the draft; other blocks and mention
// lists are keyed by position. A repeated identity gets a numbered suffix.
function chunkMentions(blocks: (ExperienceBlock | undefined)[]) {
  const out: Array<{ kind: "mentions"; key: string; blocks: UnitBlock[] } | { kind: "block"; key: string; block: ExperienceBlock }> = [];
  const seen = new Map<string, number>();
  const uniqueKey = (base: string) => {
    const times = seen.get(base) ?? 0;
    seen.set(base, times + 1);
    return times === 0 ? base : `${base}-${times}`;
  };
  for (const block of blocks) {
    if (!block) continue;
    if (isUnit(block) && block.emphasis === "mention") {
      const last = out[out.length - 1];
      if (last && last.kind === "mentions") last.blocks.push(block);
      else out.push({ kind: "mentions", key: uniqueKey(`mentions-${out.length}`), blocks: [block] });
    } else {
      const base = isUnit(block) ? `${block.type}-${unitKey(block)}` : `${block.type}-${out.length}`;
      out.push({ kind: "block", key: uniqueKey(base), block });
    }
  }
  return out;
}

type RenderGroup = { title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[]; blocks: ExperienceBlock[] };
type Draft = { title: string; lead: string | null; groups: RenderGroup[] };

function emptyGroup(): RenderGroup {
  return { title: null, lead: null, presentation: "collection", criteria: [], blocks: [] };
}

// The draft page grows in reading order. A block for a group we have not
// heard of yet gets a provisional group; group_close fills the heading in.
function applyPageEvent(draft: Draft | null, event: PageEvent): Draft | null {
  if (event.type === "page_reset") return null;
  if (event.type === "page_head") return { title: event.title, lead: event.lead, groups: draft?.groups ?? [] };
  const current: Draft = draft ?? { title: "", lead: null, groups: [] };
  const groups = current.groups.slice();
  const index = event.type === "block" ? event.group_index : event.index;
  if (!Number.isInteger(index) || index < 0) return draft;
  while (groups.length <= index) groups.push(emptyGroup());
  if (event.type === "block") {
    groups[index] = { ...groups[index], blocks: [...groups[index].blocks, event.block] };
  } else {
    groups[index] = { ...groups[index], title: event.title, lead: event.lead, presentation: event.presentation, criteria: event.criteria };
  }
  return { ...current, groups };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

type StreamHandlers = {
  onStatus: (status: string) => void;
  onAnswer: (text: string) => void;
  onPage: (event: PageEvent) => void;
  onResponse: (response: ExperienceResponse) => void;
};

// Shared between the network reader and the fixture replay: turn one parsed
// event into the matching handler call. Error throws; everything else is
// handed to the caller's handlers, including the response, which the network
// reader captures and the replay applies immediately.
const PAGE_EVENT_TYPES = new Set(["page_head", "group_open", "group_close", "block", "page_reset"]);

function dispatchStreamEvent(event: StreamEvent, handlers: StreamHandlers): void {
  if (event.type === "status") handlers.onStatus(event.text);
  else if (event.type === "answer") handlers.onAnswer(event.text);
  else if (event.type === "response") handlers.onResponse(event.response);
  else if (event.type === "error") throw new Error(event.detail ?? "Deadbot could not answer just now.");
  else if (PAGE_EVENT_TYPES.has(event.type)) handlers.onPage(event);
}

function groupsOfResponse(response: ExperienceResponse): RenderGroup[] {
  return response.groups.map((group) => ({
    title: group.title ?? null,
    lead: group.lead ?? null,
    presentation: group.presentation,
    criteria: group.criteria ?? [],
    blocks: group.block_indexes.map((index) => response.blocks[index]).filter((block): block is ExperienceBlock => Boolean(block)),
  }));
}

function ShowUnit({
  unit,
  criteria,
  soleUnit,
  onFollowUp
}: {
  unit: ShowUnitBlock;
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: (prompt: string) => void;
}) {
  const shows = (facet: ShowUnitBlock["visible_facets"][number]) => unit.visible_facets.includes(facet);
  const openFacets = unit.emphasis === "primary" && soleUnit;
  const dateLong = formatShowDateLong(unit.show_date);
  const highlights = unit.sets.flatMap((set) => set.songs.filter((song) => song.highlighted));
  const totalSongs = unit.sets.reduce((count, set) => count + set.songs.length, 0);

  // The guest joins the meta line: who was there, not a separate labeled row.
  const guestsNode = shows("guests") && unit.guests.length > 0 ? (
    <>
      with{" "}
      {unit.guests.map((guest, index) => (
        <span key={`${guest.person_id}-${index}`}>
          {index > 0 ? ", " : ""}
          <strong>{guest.name}</strong>, {guest.instruments.join(", ")}
        </span>
      ))}
    </>
  ) : null;

  const tabs: DrawerTab[] = [];
  if (shows("setlist") && unit.setlist_disclosure !== "hidden" && unit.sets.length > 0) {
    tabs.push({ id: "setlist", label: "Setlist", count: totalSongs, content: <SetlistPanel sets={unit.sets} /> });
  }
  if (shows("lineup") && unit.lineup.length > 0) {
    tabs.push({
      id: "lineup",
      label: "Lineup",
      count: unit.lineup.length,
      content: (
        <PeopleList
          people={unit.lineup.map((person) => ({
            key: `${person.person_id}-${person.role}`,
            name: person.name,
            detail: person.instruments.join(", "),
            guest: person.role === "guest"
          }))}
        />
      )
    });
  }
  if (shows("recordings") && unit.recordings.length > 0) {
    tabs.push({
      id: "recordings",
      label: "Recordings",
      count: unit.recordings.length,
      content: (
        <PlainList
          items={unit.recordings.map((recording) => ({
            key: recording.recording_id,
            title: recording.title,
            url: recording.url,
            detail: [recording.source_type, recording.archive_identifier].filter(Boolean).join(" · ")
          }))}
        />
      )
    });
  }
  // The model writes the headline (the place or the legend); the venue is the
  // fallback. When the headline is not the venue, the full venue joins the meta line.
  const modelHeadline = unit.title?.trim() || "";
  const headline = modelHeadline || unit.venue_name || dateLong;
  const venueInMeta = modelHeadline && unit.venue_name && modelHeadline.toLowerCase() !== unit.venue_name.toLowerCase() ? unit.venue_name : null;
  const wantsSetlistOpen = unit.setlist_disclosure === "expanded" || openFacets;
  const initialOpen = wantsSetlistOpen && tabs.some((tab) => tab.id === "setlist") ? "setlist" : null;

  return (
    <article className={`card show-unit emphasis-${unit.emphasis}`}>
      <IdRow type="Show" when={dateLong} />
      <h2>{headline}</h2>
      <Meta parts={[venueInMeta, unit.location, guestsNode]} />
      {unit.note && <p className="unit-note">{renderInline(unit.note)}</p>}
      <CriteriaTable criteria={criteria} judgments={unit.judgments} />
      {shows("listen") && <ListenActionList actions={unit.listen} />}
      {highlights.length > 0 && (
        <ListenFor items={highlights.map((song) => ({ key: song.performance_id, title: song.title, url: song.listen_url }))} />
      )}
      {shows("setlist") && unit.setlist_disclosure !== "hidden" && unit.sets.length === 0 && unit.setlist_note && (
        <p className="coverage-note">{unit.setlist_note}</p>
      )}
      <Drawer tabs={tabs} initialOpen={initialOpen} />
      {((shows("sources") && unit.sources.length > 0) || (unit.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          {shows("sources") && <GoDeeper sources={unit.sources} />}
          <MoreAbout topics={unit.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </article>
  );
}

function capitalize(text: string): string {
  return text.length > 0 ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

type PersonnelGroup = {
  person_id: string;
  name: string;
  instruments: string[];
  extraRole: string | null;
};

function groupPersonnel(personnel: AlbumUnitBlock["personnel"]): PersonnelGroup[] {
  const groups = new Map<string, PersonnelGroup>();
  for (const credit of personnel) {
    let group = groups.get(credit.person_id);
    if (!group) {
      group = { person_id: credit.person_id, name: credit.name, instruments: [], extraRole: null };
      groups.set(credit.person_id, group);
    }
    if (credit.instrument && !group.instruments.includes(credit.instrument)) {
      group.instruments.push(credit.instrument);
    }
    if (credit.role && credit.role !== "performer" && !group.extraRole) {
      group.extraRole = credit.role;
    }
  }
  return [...groups.values()];
}

function AlbumUnit({
  block,
  criteria,
  soleUnit,
  onFollowUp
}: {
  block: AlbumUnitBlock;
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: (prompt: string) => void;
}) {
  const openFacets = block.emphasis === "primary" && soleUnit;
  const highlightedTracks = block.tracks.filter((track) => track.highlighted);
  const personnel = groupPersonnel(block.personnel);
  const typeLabel = block.artist_name && block.artist_name !== "Grateful Dead" ? `Album · ${block.artist_name}` : "Album";
  const releaseLong = formatReleaseDate(block.release_date);

  const tabs: DrawerTab[] = [];
  if (block.tracks.length > 0) {
    tabs.push({ id: "tracks", label: "Tracklist", count: block.tracks.length, content: <TrackList tracks={block.tracks} /> });
  }
  if (personnel.length > 0) {
    tabs.push({
      id: "personnel",
      label: "Personnel",
      count: personnel.length,
      content: (
        <PeopleList
          people={personnel.map((person) => ({
            key: person.person_id,
            name: person.name,
            detail: [person.instruments.join(", "), person.extraRole ? capitalize(person.extraRole) : null].filter(Boolean).join(" · ")
          }))}
        />
      )
    });
  }
  const initialOpen = openFacets && tabs.some((tab) => tab.id === "tracks") ? "tracks" : null;

  return (
    <article className={`card album-unit emphasis-${block.emphasis}`}>
      <IdRow type={typeLabel} when={releaseLong ? `Released ${releaseLong}` : null} />
      <h2>{block.title}</h2>
      <Meta parts={[formatReleaseType(block.release_type)]} />
      {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      <ListenActionList actions={block.listen} />
      {highlightedTracks.length > 0 && (
        <ListenFor items={highlightedTracks.map((track) => ({ key: String(track.track_number), title: track.title, url: track.listen_url }))} />
      )}
      <Drawer tabs={tabs} initialOpen={initialOpen} />
      {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          <GoDeeper sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </article>
  );
}

type PerformanceUnitBlockT = Extract<ExperienceBlock, { type: "performance_unit" }>;

function PerformanceUnit({
  block,
  criteria,
  onFollowUp
}: {
  block: PerformanceUnitBlockT;
  criteria: string[];
  onFollowUp: (prompt: string) => void;
}) {
  const rightParts = [block.set_label, block.position_in_set ? `Song ${block.position_in_set}` : null].filter(Boolean) as string[];
  return (
    <article className={`card performance-unit emphasis-${block.emphasis}`}>
      <IdRow type="Performance" when={rightParts.length > 0 ? rightParts.join(" · ") : null} />
      <h2>{block.song_title}</h2>
      <Meta parts={[block.venue_name, formatShowDateLong(block.show_date), block.location]} />
      {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      {(block.previous || block.next) && (() => {
        // Three consecutive setlist lines with this performance lit, numbered
        // from its position when the set position is known.
        const parsed = block.position_in_set ? Number(block.position_in_set) : NaN;
        const here = Number.isFinite(parsed) && parsed > 0 ? parsed : null;
        const setName = block.set_label || "the set";
        const rows: { key: string; n: number | null; title: string; here?: boolean; edge?: boolean }[] = [
          block.previous
            ? { key: "prev", n: here ? here - 1 : null, title: block.previous.title }
            : { key: "prev", n: null, title: `Opens ${setName}`, edge: true },
          { key: "here", n: here, title: block.song_title, here: true },
          block.next
            ? { key: "next", n: here ? here + 1 : null, title: block.next.title }
            : { key: "next", n: null, title: `Closes ${setName}`, edge: true }
        ];
        return (
          <ol className="set-excerpt" aria-label="Where this sits in the set">
            {rows.map((row) => (
              <li key={row.key} className={row.here ? "here" : row.edge ? "edge" : undefined}>
                <span className="n" aria-hidden="true">{row.n ?? ""}</span>
                <span>{row.title}</span>
              </li>
            ))}
          </ol>
        );
      })()}
      <ListenActionList actions={block.listen} />
      {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          <GoDeeper sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </article>
  );
}

type SongOverviewBlockT = Extract<ExperienceBlock, { type: "song_overview" }>;

function SongOverviewUnit({
  block,
  criteria,
  soleUnit,
  onFollowUp
}: {
  block: SongOverviewBlockT;
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: (prompt: string) => void;
}) {
  const openFacets = block.emphasis === "primary" && soleUnit;
  const showsFacet = (facet: SongOverviewBlockT["visible_facets"][number]) => block.visible_facets.includes(facet);

  const tabs: DrawerTab[] = [];
  if (showsFacet("history") && block.history) {
    const history = block.history;
    const byYear = history.by_year ?? [];
    tabs.push({
      id: "history",
      label: "History",
      content: (
        <div>
          <p className="subtitle">{history.known_count} performance{history.known_count === 1 ? "" : "s"}</p>
          <div className="endpoints">
            <div>
              <span className="k">First</span>
              <ListeningLabel title={history.first.show_label} url={history.first.listen_url} className="list-item-label" />
            </div>
            <div>
              <span className="k">Last</span>
              <ListeningLabel title={history.last.show_label} url={history.last.listen_url} className="list-item-label" />
            </div>
          </div>
          {byYear.length > 1 && (
            <ol className="comparison-track" aria-label="One performance per year">
              {byYear.map((item) => (
                <li className="comparison-stop" key={item.performance_id}>
                  <p className="comparison-year">{item.year}</p>
                  <ListeningLabel title={item.show_label} url={item.listen_url} className="list-item-label" />
                </li>
              ))}
            </ol>
          )}
        </div>
      )
    });
  }
  if (showsFacet("albums") && block.albums.length > 0) {
    tabs.push({
      id: "record",
      label: "On record",
      count: block.albums.length,
      content: (
        <PlainList
          items={block.albums.map((album) => ({
            key: album.release_id,
            title: album.title,
            detail: [album.release_type, album.release_date?.slice(0, 4)].filter(Boolean).join(" · ")
          }))}
        />
      )
    });
  }
  if (showsFacet("credits") && block.credits.length > 0) {
    tabs.push({
      id: "credits",
      label: "Credits",
      count: block.credits.length,
      content: (
        <PlainList items={block.credits.map((credit) => ({ key: `${credit.person_id}-${credit.role}`, title: credit.name, detail: credit.role }))} />
      )
    });
  }
  const initialOpen = openFacets && tabs.length > 0 ? tabs[0].id : null;
  const representatives = showsFacet("representatives") ? block.representative_performances : [];

  return (
    <article className={`card song-overview emphasis-${block.emphasis}`}>
      <IdRow type="Song" when={`${block.known_performance_count} performance${block.known_performance_count === 1 ? "" : "s"}`} />
      <h2>{block.title}</h2>
      <Meta parts={[block.original_artist ? `Originally by ${block.original_artist}` : null]} />
      {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      {representatives.length > 0 && (
        <section className="song-representatives">
          <ul>
            {representatives.map((performance) => (
              <li key={performance.performance_id}>
                <ListeningLabel
                  title={venueFirstShowLabel(performance.show_date, null, performance.show_label)}
                  url={performance.listen_url}
                  className="list-item-label"
                />
                {performance.set_label && <span>{performance.set_label}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <Drawer tabs={tabs} initialOpen={initialOpen} />
      {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          <GoDeeper sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </article>
  );
}

function Block({
  block,
  sources,
  criteria,
  soleUnit,
  onFollowUp
}: {
  block: ExperienceBlock;
  sources: SourceReference[];
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: (prompt: string) => void;
}) {
  switch (block.type) {
    case "show_unit":
      return <ShowUnit unit={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} />;
    case "performance_unit":
      return <PerformanceUnit block={block} criteria={criteria} onFollowUp={onFollowUp} />;
    case "era_unit":
      return (
        <section className="era-unit">
          <header className="unit-heading">
            <div>
              {block.span && <Eyebrow label={block.span} title={block.title} />}
              <h2>{block.title}</h2>
            </div>
          </header>
          {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
          <ul className="era-performances">
            {block.performances.map((performance) => (
              <li key={performance.performance_id}>
                <ListeningLabel
                  title={venueFirstShowLabel(performance.show_date, null, performance.show_label)}
                  url={performance.listen?.url}
                  className="list-item-label"
                />
                <span>{[performance.song_title, performance.set_label].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ul>
          <UnitSourceList sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </section>
      );
    case "album_unit":
      return <AlbumUnit block={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} />;
    case "entity_card": {
      return (
        <article className="typography-block entity-block">
          <Eyebrow label={block.entity_type} title={block.title} />
          <h2>{block.title}</h2>
          {block.subtitle && <p className="subtitle">{block.subtitle}</p>}
          {block.details.length > 0 && (
            <ul className="details">
              {block.details.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>
          )}
          {block.follow_up && <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />}
        </article>
      );
    }
    case "show_selection":
      return (
        <section className="typography-block show-selection">
          <Eyebrow label={block.selection_type} title={block.title} />
          <h2>{block.title}</h2>
          <p className="subtitle">Selected by {block.selector_name}</p>
          <ol className="show-selection-list">
            {block.items.map((item) => (
              <li key={item.show_id}>
                <span className="list-item-label">{formatShowDate(item.show_date)} · {item.venue_name}</span>
                {item.location && <span>{item.location}</span>}
              </li>
            ))}
          </ol>
          <p className="coverage-note">{block.coverage_note}</p>
        </section>
      );
    case "guest_appearance_list":
      return (
        <section className="typography-block guest-appearance-list">
          <Eyebrow label="Guest appearances" title={block.person_name} />
          <h2>{block.person_name}</h2>
          <p className="subtitle">
            {block.known_show_count} show{block.known_show_count === 1 ? "" : "s"}
          </p>
          <ol>
            {block.items.map((item) => (
              <li key={item.show_id}>
                <strong className="list-item-label">{formatShowDate(item.show_date)}{item.venue_name ? ` · ${item.venue_name}` : ""}</strong>
                <span>{[item.location, item.instruments.join(", "), item.participation_scope].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ol>
        </section>
      );
    case "equipment_list":
      return (
        <section className="typography-block equipment-list">
          <Eyebrow label="Equipment" title={block.title} />
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={`${item.equipment_id}-${item.usage_context}-${item.evidence}`}>
                <strong className="inline-label">{item.name}</strong>
                <span>{[item.manufacturer, item.model].filter(Boolean).join(" · ")}</span>
                <span>{item.usage_context}{item.claim_type === "show" ? " · specific show evidence" : " · dated range evidence"}</span>
                <ExternalLink href={item.source_url}>Source note</ExternalLink>
              </li>
            ))}
          </ul>
        </section>
      );
    case "song_overview":
      return <SongOverviewUnit block={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} />;
    case "resource_list":
      return (
        <section className="typography-block resource-list">
          <Eyebrow label="Sources" title={block.title} />
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={item.resource_id}>
                <ExternalLink href={item.url}>{item.title}</ExternalLink>
                <span>{item.resource_type} · {item.source_name}</span>
                {item.context_note && <p>{item.context_note}</p>}
              </li>
            ))}
          </ul>
        </section>
      );
    case "credit_list":
      return (
        <section className="typography-block credit-list">
          <Eyebrow label="Composition" title={block.title} />
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={`${item.person_id}-${item.role}`}>
                <strong className="inline-label">{item.name}</strong>
                <span>{item.role}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "media_link":
      return (
        <section className="card media-card">
          <Eyebrow label={`${block.provider}${block.is_official ? " · official" : ""}`} title={block.title} />
          <h2>{block.title}</h2>
          <MediaEmbed block={block} />
          <ExternalLink href={block.url}>Open on {block.provider}</ExternalLink>
        </section>
      );
    case "coverage":
      return (
        <aside className="typography-block coverage-block">
          <Eyebrow label="Library coverage" title={block.title} />
          <h2>{block.title}</h2>
          <p>{block.message}</p>
        </aside>
      );
    case "arrangement": {
      const source = sourceFor(sources, block.source_id);
      return (
        <section className="typography-block arrangement-block">
          <Eyebrow label="Source-specific arrangement" title={block.title} />
          <h2>{block.title}</h2>
          <dl className="arrangement-facts">
            {block.key_signature && <div><dt>Documented key</dt><dd>{block.key_signature}</dd></div>}
            <div><dt>Scope</dt><dd>{block.arrangement_scope.replaceAll("-", " ")}</dd></div>
            {block.capo && <div><dt>Capo</dt><dd>{block.capo}</dd></div>}
            {block.tuning && <div><dt>Tuning</dt><dd>{block.tuning}</dd></div>}
          </dl>
          {block.notes && <p className="arrangement-note">{block.notes}</p>}
          {block.progressions.length > 0 && (
            <ul className="chords">
              {block.progressions.map((progression, index) => <li key={`${index}-${progression}`}>{progression}</li>)}
            </ul>
          )}
          {source?.url && <ExternalLink href={source.url}>Open the source</ExternalLink>}
        </section>
      );
    }
    case "arrangement_search":
      return (
        <section className="typography-block arrangement-search">
          <Eyebrow label="Musician’s reference" title={block.title} />
          <h2>{block.title}</h2>
          <p className="arrangement-note">{block.coverage_note}</p>
          <ul>
            {block.items.map((item) => (
              <li key={item.arrangement_id}>
                <strong className="inline-label">{item.title}</strong>
                <span>{item.arrangement_scope.replaceAll("-", " ")} · key of {item.key_signature}</span>
                <ExternalLink href={item.url}>{item.resource_title}</ExternalLink>
                <span>{item.source_name}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "editorial":
      if (block.presentation === "narrative") return (
        <section className="typography-block narrative-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <h2>{block.title}</h2>}
          {block.paragraphs.map((paragraph, index) => <p key={index}>{renderInline(paragraph)}</p>)}
        </section>
      );
      if (block.presentation === "fact_grid") return (
        <section className="typography-block fact-grid-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <h2>{block.title}</h2>}
          <dl>
            {block.items.map((item, index) => (
              <div key={`${item.marker ?? item.title}-${index}`}>
                {item.marker ? <dt>{item.marker}</dt> : <dt className="fact-subject">{renderInline(item.title)}</dt>}
                {item.marker && <dd className="fact-subject">{renderInline(item.title)}</dd>}
                {item.value && (
                  <dd className={item.value.trim().length <= 20 ? "fact-value display" : "fact-value"}>
                    {renderInline(item.value)}
                  </dd>
                )}
                {item.detail && <dd className="fact-detail">{renderInline(item.detail)}</dd>}
                {item.link && <dd className="fact-link"><ExternalLink href={item.link.url}>{item.link.label}</ExternalLink></dd>}
                {(item.follow_ups ?? []).length > 0 && <dd className="fact-ask"><TopicChips topics={item.follow_ups} onFollowUp={onFollowUp} /></dd>}
              </div>
            ))}
          </dl>
        </section>
      );
      return (
        <section className="typography-block timeline-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <h2>{block.title}</h2>}
          <ol>
            {block.items.map((item, index) => (
              <li key={`${item.marker ?? item.title}-${index}`}>
                {item.marker && <span className="timeline-marker">{item.marker}</span>}
                <strong>{renderInline(item.title)}</strong>
                {item.detail && <span>{renderInline(item.detail)}</span>}
                {item.link && <ExternalLink href={item.link.url}>{item.link.label}</ExternalLink>}
                {(item.follow_ups ?? []).length > 0 && <span className="timeline-ask"><TopicChips topics={item.follow_ups} onFollowUp={onFollowUp} /></span>}
              </li>
            ))}
          </ol>
        </section>
      );
    case "provenance_note":
      return <aside className="typography-block provenance-note">{block.text}</aside>;
    case "gap_state":
      return <aside className="typography-block gap-state">{block.message}</aside>;
  }
}

function ComposedPage({
  title,
  lead,
  groups,
  sources,
  composing,
  onFollowUp
}: {
  title: string;
  lead: string | null;
  groups: RenderGroup[];
  sources: SourceReference[];
  composing: boolean;
  onFollowUp: (prompt: string) => void;
}) {
  // A primary unit's facets start open only when it is the page's sole unit;
  // typography blocks (era_unit, editorial, and the rest) do not count.
  const unitCount = groups.reduce((count, group) => count + group.blocks.filter(isUnit).length, 0);
  return (
    <>
      <div className="content-heading">
        <h1 id="answer-title" tabIndex={-1}>{title}</h1>
      </div>
      {lead && <p className="answer-lead">{renderInline(lead)}</p>}
      {groups.map((group, groupIndex) => (
        <section className={`experience-group group-${group.presentation}`} key={groupIndex}>
          {(group.title || group.lead) && (
            group.presentation === "argument" ? (
              <header className="group-heading claim">
                {group.title && <h2>{group.title}</h2>}
                {group.lead && <p className="claim-text">{renderInline(group.lead)}</p>}
              </header>
            ) : (
              <header className="group-heading">
                {group.title && <h2>{group.title}</h2>}
                {group.lead && <p>{renderInline(group.lead)}</p>}
              </header>
            )
          )}
          <div className="block-grid group-blocks">
            {chunkMentions(group.blocks).map((entry) =>
              entry.kind === "mentions" ? (
                <ul className="mention-list" key={entry.key}>
                  {entry.blocks.map((block) => <MentionRow key={`${block.type}-${unitKey(block)}`} block={block} />)}
                </ul>
              ) : (
                <Block
                  key={entry.key}
                  block={entry.block}
                  sources={sources}
                  criteria={group.presentation === "comparison" ? group.criteria : []}
                  soleUnit={composing ? false : unitCount === 1}
                  onFollowUp={onFollowUp}
                />
              )
            )}
          </div>
        </section>
      ))}
      {composing && <p className="composing-note">Composing the page…</p>}
      {!composing && sources.length > 0 && (
        <footer className="sources-footer">
          <p className="sources-footer-label">Sources</p>
          <ul>
            {dedupeSources(sources).map((source) => (
              <li key={`${source.label}-${source.url ?? source.source_id}`}>
                <span className="source-kind-chip">
                  {source.kind === "canonical" ? "Canonical" : "External source"}
                </span>
                {source.url ? (
                  <ExternalLink href={source.url}>{source.label}</ExternalLink>
                ) : (
                  <span>{source.label}</span>
                )}
              </li>
            ))}
          </ul>
        </footer>
      )}
    </>
  );
}

export default function App() {
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
  // Callbacks passed into askStreaming close over stale render state, so track
  // whether the answer has already started in a ref.
  const answerStartedRef = useRef(false);

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

  useEffect(() => {
    if (visualFixture || requestedStreamFixture) return;
    void refreshIfServerChanged();
    const check = window.setInterval(() => void refreshIfServerChanged(), 60_000);
    return () => window.clearInterval(check);
  }, [visualFixture]);

  useEffect(() => {
    if (!visualFixture) return;
    void loadRequestedVisualFixture().then((fixture) => {
      if (fixture) setResponse(fixture);
    });
  }, [visualFixture]);

  // A named `?stream=` fixture replays as a timed event sequence through the
  // same dispatch the network path uses, so progressive rendering can be
  // reviewed without a model. Development only, like `?fixture=`.
  useEffect(() => {
    if (!import.meta.env.DEV || !requestedStreamFixture) return;
    let cancelled = false;
    void loadRequestedStreamEvents().then(async (events) => {
      if (!events || cancelled) return;
      const responseEvent = events.find((event): event is Extract<StreamEvent, { type: "response" }> => event.type === "response");
      const firstTurn = responseEvent?.response.conversation.find((turn) => turn.role === "user")?.text ?? null;
      setPendingQuestion(firstTurn);
      setPendingStartsFresh(true);
      setLoading(true);
      setError(null);
      setProgress([]);
      setStreamingAnswer(null);
      setDraft(null);
      answerStartedRef.current = false;
      let statusCount = 0;
      for (const event of events) {
        if (cancelled) return;
        await delay(event.type === "block" ? 600 : event.type === "answer" ? 40 : 300);
        if (cancelled) return;
        dispatchStreamEvent(event, {
          onStatus: (status) => {
            statusCount += 1;
            setProgress((lines) => [...lines, status]);
          },
          onAnswer: (text) => {
            if (!answerStartedRef.current) {
              answerStartedRef.current = true;
              setAnswerProgressStart(statusCount);
            }
            setStreamingAnswer(text);
          },
          onPage: (pageEvent) => setDraft((current) => applyPageEvent(current, pageEvent)),
          onResponse: (nextResponse) => {
            setResponse(nextResponse);
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
    });
    return () => { cancelled = true; };
  }, []);

  async function askQuestion(nextQuestion?: string, { fresh = false }: { fresh?: boolean } = {}) {
    if (visualFixture || requestedStreamFixture) return;
    const trimmed = (nextQuestion ?? question).trim();
    if (!trimmed || loading) return;
    const requestThreadId = fresh ? createThreadId() : activeThreadId;
    const conversation = fresh ? [] : response?.conversation ?? [];
    if (fresh) {
      setActiveThreadId(requestThreadId);
      setResponse(null);
    }
    setPendingQuestion(trimmed);
    setPendingStartsFresh(fresh);
    setQuestion("");
    setLoading(true);
    setError(null);
    setProgress([]);
    setStreamingAnswer(null);
    setDraft(null);
    answerStartedRef.current = false;
    const body = JSON.stringify({ question: trimmed, thread_id: requestThreadId, conversation });
    try {
      let statusCount = 0;
      const streamed = await askStreaming(body, {
        onStatus: (status) => {
          statusCount += 1;
          setProgress((lines) => [...lines, status]);
        },
        onAnswer: (text) => {
          if (!answerStartedRef.current) {
            answerStartedRef.current = true;
            setAnswerProgressStart(statusCount);
          }
          setStreamingAnswer(text);
        },
        onPage: (event) => setDraft((current) => applyPageEvent(current, event))
      });
      setResponse(streamed ?? await askPlain(body));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Deadbot could not answer just now.");
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

  // The streaming endpoint sends one JSON object per line: statuses while the
  // agent works, page events as the page is composed, then the response. A
  // null return means the stream was not available and the caller should
  // fall back to the plain request.
  async function askStreaming(
    body: string,
    handlers: {
      onStatus: (status: string) => void;
      onAnswer: (text: string) => void;
      onPage: (event: PageEvent) => void;
    }
  ): Promise<ExperienceResponse | null> {
    const result = await fetch("/api/experience/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body
    });
    if (result.status === 404 || result.status === 405) return null;
    if (!result.ok) {
      const detail = await result.json().catch(() => null) as { detail?: string } | null;
      throw new Error(detail?.detail ?? "Deadbot could not answer just now.");
    }
    if (!result.body) return null;
    const reader = result.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer: ExperienceResponse | null = null;
    const consume = (line: string) => {
      if (!line.trim()) return;
      const event = JSON.parse(line) as StreamEvent;
      dispatchStreamEvent(event, {
        onStatus: handlers.onStatus,
        onAnswer: handlers.onAnswer,
        onPage: handlers.onPage,
        onResponse: (response) => { answer = response; }
      });
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        consume(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf("\n");
      }
    }
    consume(buffer);
    return answer;
  }

  async function askPlain(body: string): Promise<ExperienceResponse> {
    const result = await fetch("/api/experience", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body
    });
    if (!result.ok) {
      const detail = await result.json().catch(() => null) as { detail?: string } | null;
      throw new Error(detail?.detail ?? "Deadbot could not answer just now.");
    }
    return await result.json() as ExperienceResponse;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await askQuestion();
  }

  function chooseFollowUp(prompt: string) {
    void askQuestion(prompt);
  }

  function startNewChat() {
    if (loading) return;
    setActiveThreadId(createThreadId());
    setResponse(null);
    setError(null);
    setQuestion("");
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

  return (
    <main className="app-shell">
      <div className="workspace">
        <aside className="conversation-pane" aria-label="Conversation">
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
                <article className="message assistant pending" aria-live="polite">
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

            {error && <p className="error" role="alert">{error}</p>}

            <form className="composer" onSubmit={submit}>
              <div className="question-field">
                <textarea
                  id="question"
                  aria-label="Question"
                  rows={3}
                  placeholder="Ask about a song, show, source, or recording"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={submitOnEnter}
                  disabled={loading}
                />
                <button type="submit" disabled={loading || !question.trim()}>{loading ? "Looking…" : "Ask"}</button>
              </div>
              {response && !loading && (
                <a className="view-answer-link" href="#answer-title">View answer <span aria-hidden="true">↓</span></a>
              )}
            </form>
          </section>
        </aside>

        <section className="content-pane" aria-live={loading && draft ? "off" : "polite"} aria-label="Deadbot guide">
          {loading && draft ? (
            <ComposedPage
              title={draft.title || pendingQuestion || ""}
              lead={draft.lead}
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
              title={response.title}
              lead={response.body_lead ?? null}
              groups={groupsOfResponse(response)}
              sources={response.sources}
              composing={false}
              onFollowUp={chooseFollowUp}
            />
          ) : (
            <div className="content-empty">
              <p className="eyebrow">Starting points</p>
              <div className="starting-points">
                {suggestions.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => void askQuestion(suggestion, { fresh: true })} disabled={loading}>
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
