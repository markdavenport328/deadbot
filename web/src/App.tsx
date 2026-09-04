import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
import type { ExperienceBlock, ExperienceResponse, ShowUnitBlock, SourceReference } from "./types";

type SetlistSections = ShowUnitBlock["sets"];
type ListenActions = ShowUnitBlock["listen"];
type UnitSources = ShowUnitBlock["sources"];

// Roles are the composer's interpretive relationships; these labels are how
// the page names them. The composer never chooses styling.
const roleLabels: Record<string, string> = {
  anchor: "Start here",
  supporting: "Supporting",
  contrast: "Contrast",
  turning_point: "Turning point",
  outlier: "Outlier",
  culmination: "Culmination",
  overlooked: "Overlooked",
  representative: "Representative"
};

const organizationLabels: Record<string, string> = {
  chronological: "In order",
  curated: "A selection",
  comparative: "Side by side"
};

function formatShowDate(iso: string | null | undefined): string {
  if (!iso) return "Undated";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  return `${Number(month)}/${Number(day)}/${year.slice(2)}`;
}

const suggestions = [
  "Was Branford on the whole 1991-09-10 Madison Square Garden show, and where should I listen for him?",
  "What are the chords to Sugaree?",
  "What did they play after Dark Star on 1972-08-27?"
];

const modeLabels: Record<ExperienceResponse["mode"], string> = {
  quick_fact: "Answer",
  performance: "Performance guide",
  show: "Show guide",
  listening: "Listening guide",
  comparison: "Comparison",
  research: "Research desk",
  musician: "Musician’s reference",
  gap: "Library note"
};

const regionLabels: Partial<Record<"primary" | "supporting" | "context" | "media", string>> = {
  supporting: "Keep exploring",
  context: "Details and context",
  media: "Listen and watch"
};

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

// A song or performance label that plays its recording when the library has
// one, and is plain text otherwise. The ▶ is the only cue that a link plays.
function PlayableLabel({ title, url, className = "" }: { title: string; url?: string | null; className?: string }) {
  if (!url) return <span className={className}>{title}</span>;
  return (
    <a className={`song-link ${className}`.trim()} href={url} target="_blank" rel="noreferrer" title={`Play ${title}`}>
      <span className="play-mark" aria-hidden="true">▶</span> {title}
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

function RoleChip({ role }: { role?: string | null }) {
  if (!role) return null;
  return <span className={`role-chip role-${role}`}>{roleLabels[role] ?? role.replaceAll("_", " ")}</span>;
}

function ListenActionList({ actions }: { actions: ListenActions }) {
  if (actions.length === 0) return null;
  return (
    <ul className="listen-actions" aria-label="Listen">
      {actions.map((action) => (
        <li key={action.url}>
          <a className={action.is_official ? "listen-action official" : "listen-action"} href={action.url} target="_blank" rel="noreferrer">
            <span aria-hidden="true">▶</span> {action.label}
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

function SetlistSectionList({ sets }: { sets: SetlistSections }) {
  return (
    <div className="setlist-sections">
      {sets.map((set) => (
        <div className="setlist-section" key={set.label}>
          <p className="fact-label">{set.label}</p>
          <ol>
            {set.songs.map((song) => (
              <li key={song.performance_id} className={song.highlighted ? "setlist-song highlighted" : "setlist-song"}>
                <PlayableLabel title={song.title} url={song.listen_url} />
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
  onFollowUp,
  collapsed = false
}: {
  unit: ShowUnitBlock;
  onFollowUp: (prompt: string) => void;
  collapsed?: boolean;
}) {
  const highlights = unit.sets.flatMap((set) => set.songs.filter((song) => song.highlighted));
  return (
    <article className={`card show-unit${unit.role ? ` role-${unit.role}` : ""}`}>
      <header className="unit-heading">
        <div>
          {unit.title && <Eyebrow label={unit.title} />}
          <h2>
            <time dateTime={unit.show_date}>{formatShowDate(unit.show_date)}</time>
            {unit.venue_name ? ` · ${unit.venue_name}` : ""}
          </h2>
          {unit.location && <p className="subtitle">{unit.location}</p>}
        </div>
        <RoleChip role={unit.role} />
      </header>
      {unit.note && <p className="unit-note">{renderInline(unit.note)}</p>}
      {unit.guests.length > 0 && (
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
      {collapsed && highlights.length > 0 && (
        <div className="unit-highlights">
          <p className="fact-label">Listen for</p>
          <ul>
            {highlights.map((song) => (
              <li key={song.performance_id}>
                <PlayableLabel title={song.title} url={song.listen_url} className="list-item-label" />
              </li>
            ))}
          </ul>
        </div>
      )}
      {unit.sets.length > 0 ? (
        collapsed ? (
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
      ) : null}
      <ListenActionList actions={unit.listen} />
      <UnitSourceList sources={unit.sources} />
      {unit.follow_up && (
        <p className="unit-follow-up">
          <AskChip prompt={unit.follow_up} onFollowUp={onFollowUp} />
        </p>
      )}
    </article>
  );
}

function Block({
  block,
  sources,
  onFollowUp
}: {
  block: ExperienceBlock;
  sources: SourceReference[];
  onFollowUp: (prompt: string) => void;
}) {
  switch (block.type) {
    case "show_unit":
      return <ShowUnit unit={block} onFollowUp={onFollowUp} />;
    case "show_explorer":
      return (
        <section className="show-explorer">
          <Eyebrow label={organizationLabels[block.organization] ?? block.organization} title={block.title} />
          <h2>{block.title}</h2>
          <div className="explorer-units">
            {block.items.map((unit) => (
              <ShowUnit
                key={unit.show_id}
                unit={unit}
                onFollowUp={onFollowUp}
                collapsed={block.items.length > 1 && unit.role !== "anchor"}
              />
            ))}
          </div>
        </section>
      );
    case "performance_unit":
      return (
        <article className={`card performance-unit${block.role ? ` role-${block.role}` : ""}`}>
          <header className="unit-heading">
            <div>
              <p className="eyebrow">{block.song_title}</p>
              <h2>
                <time dateTime={block.show_date ?? undefined}>{formatShowDate(block.show_date)}</time>
                {block.venue_name ? ` · ${block.venue_name}` : ""}
              </h2>
              <p className="subtitle">
                {[block.location, block.set_label, block.position_in_set ? `#${block.position_in_set}` : null].filter(Boolean).join(" · ")}
              </p>
            </div>
            <RoleChip role={block.role} />
          </header>
          {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
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
        <section className={`card era-unit${block.role ? ` role-${block.role}` : ""}`}>
          <header className="unit-heading">
            <div>
              {block.span && <Eyebrow label={block.span} title={block.title} />}
              <h2>{block.title}</h2>
            </div>
            <RoleChip role={block.role} />
          </header>
          {block.note && <p className="unit-note">{renderInline(block.note)}</p>}
          <ul className="era-performances">
            {block.performances.map((performance) => (
              <li key={performance.performance_id}>
                <PlayableLabel
                  title={`${formatShowDate(performance.show_date)} · ${performance.show_label.replace(/^\d{4}-\d{2}-\d{2} — /, "")}`}
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
    case "show_setlist":
      return (
        <section className="card show-setlist">
          <Eyebrow label="Setlist" title={block.title} />
          <h2>{block.title}</h2>
          <SetlistSectionList sets={block.sets} />
        </section>
      );
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
    case "recording_list":
      return (
        <section className="card recording-list">
          <Eyebrow label="Listening" title={block.title} />
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={item.recording_id}>
                <ExternalLink href={item.url}>{item.title}</ExternalLink>
                <span>{item.source_type}{item.archive_identifier ? ` · ${item.archive_identifier}` : ""}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "performer_list":
      return (
        <section className="typography-block performer-list">
          <Eyebrow label="Lineup" title={block.title} />
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={`${item.person_id}-${item.role}`}>
                <strong className="inline-label">{item.name}</strong>
                <span className="performer-role">{item.role === "guest" ? "Guest" : "Performer"}</span>
                <span>{item.instruments.join(", ")}</span>
              </li>
            ))}
          </ul>
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
    case "song_overview":
      return (
        <section className="typography-block song-overview">
          <Eyebrow label="Song facts" title={block.title} />
          <h2>{block.title}</h2>
          <dl className="song-facts">
            {block.original_artist && (
              <div>
                <dt>Original artist</dt>
                <dd>{block.original_artist}</dd>
              </div>
            )}
            <div>
              <dt>Known performances</dt>
              <dd>{block.known_performance_count}</dd>
            </div>
          </dl>
          {block.credits.length > 0 && (
            <div className="song-credits">
              <p className="fact-label">Credits</p>
              <ul>
                {block.credits.map((credit) => (
                  <li key={`${credit.person_id}-${credit.role}`}>
                    <strong className="inline-label">{credit.name}</strong>
                    <span>{credit.role}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      );
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
    case "performance_list":
      return (
        <section className="typography-block performance-list">
          <Eyebrow label="Canonical performance evidence" title={block.title} />
          <h2>{block.title}</h2>
          <p className="subtitle">{block.known_count} known performance{block.known_count === 1 ? "" : "s"}</p>
          <ul>
            {block.items.map((item) => (
              <li key={item.performance_id}>
                <PlayableLabel title={item.show_label} url={item.listen_url} className="list-item-label" />
                {(item.set_label || item.position_in_set) && <span>{item.set_label}{item.position_in_set ? ` · #${item.position_in_set}` : ""}</span>}
              </li>
            ))}
          </ul>
        </section>
      );
    case "performance_extremes": {
      const endpoint = (label: string, item: typeof block.first) => (
        <div className="performance-endpoint" key={label}>
          <p className="fact-label">{label}</p>
          <PlayableLabel title={item.show_label} url={item.listen_url} className="list-item-label" />
          {(item.set_label || item.position_in_set) && (
            <span>{item.set_label}{item.position_in_set ? ` · #${item.position_in_set}` : ""}</span>
          )}
        </div>
      );
      return (
        <section className="typography-block performance-extremes">
          <Eyebrow label="Performance history" title={block.title} />
          <h2>{block.title}</h2>
          <div className="performance-endpoints">
            {endpoint("First", block.first)}
            {endpoint("Last", block.last)}
          </div>
        </section>
      );
    }
    case "comparison_strip":
      return (
        <section className="typography-block comparison-strip">
          <Eyebrow label="Performance history" title={block.title} />
          <h2>{block.title}</h2>
          <p className="subtitle">
            {block.known_count} known performance{block.known_count === 1 ? "" : "s"} · one representative per year
          </p>
          <ol className="comparison-track" aria-label="Selected performances by year">
            {block.items.map((item) => (
              <li className="comparison-stop" key={item.performance_id}>
                <p className="comparison-year">{item.year}</p>
                <PlayableLabel title={item.show_label} url={item.listen_url} className="list-item-label" />
                {(item.set_label || item.position_in_set) && (
                  <span className="comparison-placement">
                    {item.set_label}{item.position_in_set ? ` · #${item.position_in_set}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ol>
          <p className="coverage-note">{block.coverage_note}</p>
        </section>
      );
    case "performance_spine":
      return (
        <section className="typography-block performance-spine">
          <Eyebrow label="Performance context" title={block.title} />
          <h2>{block.title}</h2>
          <p className="subtitle">{block.show_label}{block.set_label ? ` · ${block.set_label}` : ""}{block.position_in_set ? ` · #${block.position_in_set}` : ""}</p>
          <div className="set-thread" aria-label="Adjacent songs in the set">
            <div>
              <p className="fact-label">Before</p>
              {block.previous ? <span className="list-item-label">{block.previous.title}</span> : <span className="thread-boundary">Set opener</span>}
            </div>
            <div className="current-performance" aria-label="Current performance">This performance</div>
            <div>
              <p className="fact-label">After</p>
              {block.next ? <span className="list-item-label">{block.next.title}</span> : <span className="thread-boundary">Set closer</span>}
            </div>
          </div>
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
                <dt>{item.marker ?? item.title}</dt>
                <dd>{renderInline(item.value ?? item.title)}</dd>
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

export default function App() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<ExperienceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeThreadId, setActiveThreadId] = useState(createThreadId);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingStartsFresh, setPendingStartsFresh] = useState(false);
  // What Deadbot is doing right now, one line per tool call, newest last.
  const [progress, setProgress] = useState<string[]>([]);
  const threadEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [loading, pendingQuestion, response, progress]);

  useEffect(() => {
    void refreshIfServerChanged();
    const check = window.setInterval(() => void refreshIfServerChanged(), 60_000);
    return () => window.clearInterval(check);
  }, []);

  async function askQuestion(nextQuestion?: string, { fresh = false }: { fresh?: boolean } = {}) {
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
    const body = JSON.stringify({ question: trimmed, thread_id: requestThreadId, conversation });
    try {
      const streamed = await askStreaming(body, (status) => setProgress((lines) => [...lines, status]));
      setResponse(streamed ?? await askPlain(body));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Deadbot could not answer just now.");
    } finally {
      setLoading(false);
      setPendingQuestion(null);
      setPendingStartsFresh(false);
      setProgress([]);
    }
  }

  // The streaming endpoint sends one JSON object per line: statuses while the
  // agent works, then the response. A null return means the stream was not
  // available and the caller should fall back to the plain request.
  async function askStreaming(body: string, onStatus: (status: string) => void): Promise<ExperienceResponse | null> {
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
      const event = JSON.parse(line) as { type: string; text?: string; response?: ExperienceResponse; detail?: string };
      if (event.type === "status" && event.text) onStatus(event.text);
      else if (event.type === "response" && event.response) answer = event.response;
      else if (event.type === "error") throw new Error(event.detail ?? "Deadbot could not answer just now.");
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

          <section className="thread" aria-label="Deadbot conversation">
            <div className="thread-messages" aria-live="polite">
              {visibleConversation.map((turn, index) => (
                <article className={`message ${turn.role}`} key={`${turn.role}-${index}`}>
                  <p>{turn.role === "user" ? "You" : "Deadbot"}</p>
                  <div>{renderInline(turn.text)}</div>
                </article>
              ))}
              {loading && (
                <article className="message assistant pending" aria-live="polite">
                  <p>Deadbot</p>
                  {progress.length === 0 ? (
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
            </form>
            <div ref={threadEnd} />
          </section>
        </aside>

        <section className="content-pane" aria-live="polite" aria-label="Deadbot guide">
          {response ? (
            <>
              <div className="content-heading">
                <p className="eyebrow">{modeLabels[response.mode]}</p>
                <h1>{response.title}</h1>
              </div>
              {response.body_lead && <p className="answer-lead">{renderInline(response.body_lead)}</p>}
              {response.layout.map((section, sectionIndex) => (
                <section className={`layout-section ${section.region}`} key={`${section.region}-${sectionIndex}`}>
                  {regionLabels[section.region] && <p className="region-label">{regionLabels[section.region]}</p>}
                  <div className="block-grid">
                    {section.block_indexes.map((index) => {
                      const block = response.blocks[index];
                      return block ? (
                        <Block
                          key={`${block.type}-${index}`}
                          block={block}
                          sources={response.sources}
                          onFollowUp={chooseFollowUp}
                        />
                      ) : null;
                    })}
                  </div>
                </section>
              ))}
              {response.sources.length > 0 && (
                <footer className="sources-footer">
                  <p className="sources-footer-label">Sources</p>
                  <ul>
                    {dedupeSources(response.sources).map((source) => (
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
