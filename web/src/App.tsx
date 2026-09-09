import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
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
      <span className="ask-label">Ask</span>
      <span>{prompt}</span>
    </button>
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

function ListenActionList({ actions }: { actions: ListenActions }) {
  if (actions.length === 0) return null;
  return (
    <ul className="listen-actions" aria-label="Listen">
      {actions.map((action) => (
        <li key={action.url}>
          <a
            className={action.is_official ? "listen-action official" : "listen-action"}
            href={action.url}
            target="_blank"
            rel="noreferrer"
            aria-label={`${action.label} on ${listeningDestination(action.url)} (opens in a new tab)`}
            title={`Opens ${listeningDestination(action.url)} in a new tab`}
          >
            <span className="listen-action-label">{action.label}</span>
            <span aria-hidden="true">↗</span>
          </a>
        </li>
      ))}
    </ul>
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

function unitKey(block: UnitBlock): string {
  switch (block.type) {
    case "show_unit": return block.show_id;
    case "performance_unit": return block.performance_id;
    case "album_unit": return block.release_id;
    case "song_overview": return block.song_id;
  }
}

function chunkMentions(blocks: (ExperienceBlock | undefined)[]) {
  const out: Array<{ kind: "mentions"; blocks: UnitBlock[] } | { kind: "block"; block: ExperienceBlock }> = [];
  for (const block of blocks) {
    if (!block) continue;
    if (isUnit(block) && block.emphasis === "mention") {
      const last = out[out.length - 1];
      if (last && last.kind === "mentions") last.blocks.push(block);
      else out.push({ kind: "mentions", blocks: [block] });
    } else {
      out.push({ kind: "block", block });
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

function SetlistSectionList({ sets }: { sets: SetlistSections }) {
  return (
    <div className="setlist-sections">
      {sets.map((set) => (
        <div className="setlist-section" key={set.label}>
          <p className="fact-label">{set.label}</p>
          <ol>
            {set.songs.map((song) => (
              <li key={song.performance_id} className={song.highlighted ? "setlist-song highlighted" : "setlist-song"}>
                <ListeningLabel title={song.title} url={song.listen_url} />
                {song.highlighted && <span className="highlight-mark" title="A performance worth your attention" aria-label="Highlighted">★</span>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
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
  const highlights = unit.sets.flatMap((set) => set.songs.filter((song) => song.highlighted));
  const shows = (facet: ShowUnitBlock["visible_facets"][number]) => unit.visible_facets.includes(facet);
  const compact = unit.emphasis === "supporting";
  const openFacets = unit.emphasis === "primary" && soleUnit;
  return (
    <article className={`card show-unit emphasis-${unit.emphasis}`}>
      <header className="unit-heading">
        <div>
          {unit.title && <Eyebrow label={unit.title} />}
          <h2>{unit.venue_name || formatShowDate(unit.show_date)}{unit.venue_name && <span className="subtitle"> ({formatShowDate(unit.show_date)})</span>}</h2>
          {unit.location && <p className="subtitle">{unit.location}</p>}
        </div>
      </header>
      {unit.note && <p className="unit-note">{renderInline(unit.note)}</p>}
      <CriteriaTable criteria={criteria} judgments={unit.judgments} />
      {shows("guests") && unit.guests.length > 0 && (
        <p className="unit-guests">
          <span className="fact-label">With </span>
          {unit.guests.map((guest, index) => (
            <span key={`${guest.person_id}-${index}`}>
              {index > 0 ? ", " : ""}
              <strong>{guest.name}</strong> ({guest.instruments.join(", ")})
            </span>
          ))}
        </p>
      )}
      {shows("listen") && <ListenActionList actions={unit.listen} />}
      {unit.setlist_disclosure === "collapsed" && highlights.length > 0 && (
        <div className="unit-highlights">
          <p className="fact-label">Listen for</p>
          <ul>
            {highlights.map((song) => (
              <li key={song.performance_id}>
                <ListeningLabel title={song.title} url={song.listen_url} className="list-item-label" />
              </li>
            ))}
          </ul>
        </div>
      )}
      {shows("setlist") && unit.setlist_disclosure !== "hidden" && (unit.sets.length > 0 ? (
        unit.setlist_disclosure === "collapsed" || compact ? (
          <details className="unit-setlist">
            <summary>Setlist</summary>
            <SetlistSectionList sets={unit.sets} />
          </details>
        ) : (
          <div className="unit-setlist">
            <p className="fact-label">Setlist</p>
            <SetlistSectionList sets={unit.sets} />
          </div>
        )
      ) : unit.setlist_note ? (
        <p className="coverage-note">{unit.setlist_note}</p>
      ) : null)}
      {shows("lineup") && unit.lineup.length > 0 && (
        <details className="unit-facet unit-setlist" open={openFacets}>
          <summary>Lineup</summary>
          <ul className="facet-list">
            {unit.lineup.map((person) => (
              <li key={`${person.person_id}-${person.role}`}>
                <strong>{person.name}</strong>
                <span>{person.instruments.join(", ")}{person.role === "guest" ? " · Guest" : ""}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {shows("recordings") && unit.recordings.length > 0 && (
        <details className="unit-facet unit-setlist" open={openFacets}>
          <summary>Recordings</summary>
          <ul className="facet-list">
            {unit.recordings.map((recording) => (
              <li key={recording.recording_id}>
                <ExternalLink href={recording.url}>{recording.title}</ExternalLink>
                <span>{recording.source_type}{recording.archive_identifier ? ` · ${recording.archive_identifier}` : ""}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {shows("sources") && <UnitSourceList sources={unit.sources} />}
      {unit.follow_up && (
        <p className="unit-follow-up">
          <AskChip prompt={unit.follow_up} onFollowUp={onFollowUp} />
        </p>
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
  const year = block.release_date?.slice(0, 4);
  const highlightedTracks = block.tracks.filter((track) => track.highlighted);
  const personnel = groupPersonnel(block.personnel);
  const compact = block.emphasis === "supporting";
  const openFacets = block.emphasis === "primary" && soleUnit;
  return (
    <article className={`card album-unit emphasis-${block.emphasis}`}>
      <header className="unit-heading">
        <div>
          {block.artist_name && block.artist_name !== "Grateful Dead" && <Eyebrow label={block.artist_name} title={block.title} />}
          <h2>
            {block.title}
            {year ? <span className="subtitle"> ({year})</span> : null}
          </h2>
        </div>
      </header>
      {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      <ListenActionList actions={block.listen} />
      {highlightedTracks.length > 0 && (
        <div className="unit-highlights">
          <p className="fact-label">Listen for</p>
          <ul>
            {highlightedTracks.map((track) => (
              <li key={track.track_number}>
                <ListeningLabel title={track.title} url={track.listen_url} className="list-item-label" />
              </li>
            ))}
          </ul>
        </div>
      )}
      {(block.tracks.length > 0 || personnel.length > 0) && (
      <div className="album-body">
        {block.tracks.length > 0 && (() => {
          const trackList = (
            <ol className="album-tracks">
              {block.tracks.map((track) => (
                <li
                  key={track.track_number}
                  className={track.highlighted ? "album-track highlighted" : "album-track"}
                  value={track.track_number}
                >
                  <ListeningLabel title={track.title} url={track.listen_url} />
                  {track.highlighted && <span className="highlight-mark" aria-label="Highlighted track">★</span>}
                </li>
              ))}
            </ol>
          );
          return (
            <details className={compact ? "unit-facet unit-setlist" : "album-tracks-section unit-setlist"} open={compact ? undefined : openFacets}>
              <summary>Tracklist</summary>
              {trackList}
            </details>
          );
        })()}
        {personnel.length > 0 && (
          <details className={compact ? "unit-facet unit-setlist" : "album-credits unit-setlist"} open={compact ? undefined : openFacets}>
            <summary>Personnel and credits</summary>
            <ul className="album-personnel">
              {personnel.map((person) => (
                <li key={person.person_id}>
                  <strong>{person.name}</strong>
                  <span>
                    {person.instruments.join(", ")}
                    {person.extraRole ? ` · ${capitalize(person.extraRole)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
      )}
      <UnitSourceList sources={block.sources} />
      {block.follow_up && (
        <p className="unit-follow-up">
          <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />
        </p>
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
      return (
        <article className={`card performance-unit emphasis-${block.emphasis}`}>
          <header className="unit-heading">
            <div>
              <p className="eyebrow">{block.song_title}</p>
              <h2>{venueFirstShowLabel(block.show_date, block.venue_name, block.show_label)}</h2>
              <p className="subtitle">
                {[block.location, block.set_label, block.position_in_set ? `#${block.position_in_set}` : null].filter(Boolean).join(" · ")}
              </p>
            </div>
          </header>
          {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
          <CriteriaTable criteria={criteria} judgments={block.judgments} />
          {(block.previous || block.next) && (
            <div className="set-thread" aria-label="Adjacent songs in the set">
              <div>
                <p className="fact-label">Before</p>
                {block.previous ? <span className="list-item-label">{block.previous.title}</span> : <span className="thread-boundary">Set opener</span>}
              </div>
              <div className="current-performance" aria-label="Current performance">{block.song_title}</div>
              <div>
                <p className="fact-label">After</p>
                {block.next ? <span className="list-item-label">{block.next.title}</span> : <span className="thread-boundary">Set closer</span>}
              </div>
            </div>
          )}
          <ListenActionList actions={block.listen} />
          <UnitSourceList sources={block.sources} />
          {block.follow_up && (
            <p className="unit-follow-up">
              <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />
            </p>
          )}
        </article>
      );
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
          {block.follow_up && (
            <p className="unit-follow-up">
              <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />
            </p>
          )}
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
            {block.known_show_count} documented show{block.known_show_count === 1 ? "" : "s"}
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
    case "song_overview": {
      const compact = block.emphasis === "supporting";
      const openFacets = block.emphasis === "primary" && soleUnit;
      return (
        <article className={`card song-overview emphasis-${block.emphasis}`}>
          <header className="unit-heading">
            <div>
              <p className="eyebrow">Song</p>
              <h2>{block.title}</h2>
              {block.original_artist && <p className="subtitle">Originally by {block.original_artist}</p>}
            </div>
          </header>
          {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
          <CriteriaTable criteria={criteria} judgments={block.judgments} />
          {block.visible_facets.map((facet) => {
            switch (facet) {
              case "representatives":
                return block.representative_performances.length > 0 ? (
                  <section className="song-representatives" key="representatives">
                    <p className="fact-label">Representative performances</p>
                    <ul>
                      {block.representative_performances.map((performance) => (
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
                ) : null;
              case "credits":
                return block.credits.length > 0 ? (
                  <details className={compact ? "unit-facet unit-setlist" : "song-credits unit-setlist"} key="credits" open={compact ? undefined : openFacets}>
                    <summary>Credits</summary>
                    <ul>
                      {block.credits.map((credit) => (
                        <li key={`${credit.person_id}-${credit.role}`}>
                          <strong className="inline-label">{credit.name}</strong>
                          <span>{credit.role}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null;
              case "albums": {
                if (block.albums.length === 0) return null;
                const albumsList = (
                  <ul className="song-albums">
                    {block.albums.map((album) => (
                      <li key={album.release_id}>
                        <strong>{album.title}</strong>
                        <span>{[album.release_type, album.release_date?.slice(0, 4)].filter(Boolean).join(" · ")}</span>
                      </li>
                    ))}
                  </ul>
                );
                return (
                  <details className={compact ? "unit-facet unit-setlist" : "song-albums-section unit-setlist"} key="albums" open={compact ? undefined : openFacets}>
                    <summary>On record</summary>
                    {albumsList}
                  </details>
                );
              }
              case "history": {
                const history = block.history;
                if (!history) return null;
                const byYear = history.by_year ?? [];
                const historyBody = (
                  <>
                    <p className="subtitle">{history.known_count} documented performance{history.known_count === 1 ? "" : "s"}</p>
                    <div className="performance-endpoints">
                      <div className="performance-endpoint"><p className="fact-label">First</p><ListeningLabel title={history.first.show_label} url={history.first.listen_url} className="list-item-label" /></div>
                      <div className="performance-endpoint"><p className="fact-label">Last</p><ListeningLabel title={history.last.show_label} url={history.last.listen_url} className="list-item-label" /></div>
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
                  </>
                );
                return (
                  <details className={compact ? "unit-facet unit-setlist" : "song-history unit-setlist"} key="history" open={compact ? undefined : openFacets}>
                    <summary>Performance history</summary>
                    {historyBody}
                  </details>
                );
              }
              default:
                return null;
            }
          })}
          <UnitSourceList sources={block.sources} />
          {block.follow_up && (
            <p className="unit-follow-up">
              <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />
            </p>
          )}
        </article>
      );
    }
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
                <span>{item.arrangement_scope.replaceAll("-", " ")} · documented key {item.key_signature}</span>
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
                {item.follow_up && <dd className="fact-ask"><AskChip prompt={item.follow_up} onFollowUp={onFollowUp} /></dd>}
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
                {item.follow_up && <span className="timeline-ask"><AskChip prompt={item.follow_up} onFollowUp={onFollowUp} /></span>}
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
            {chunkMentions(group.blocks).map((entry, position) =>
              entry.kind === "mentions" ? (
                <ul className="mention-list" key={`mentions-${groupIndex}-${position}`}>
                  {entry.blocks.map((block) => <MentionRow key={`${block.type}-${unitKey(block)}`} block={block} />)}
                </ul>
              ) : (
                <Block
                  key={`${entry.block.type}-${position}`}
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
              <div className="question-row">
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
                <button type="submit" disabled={loading || !question.trim()}>{loading ? "Looking…" : "Send"}</button>
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
