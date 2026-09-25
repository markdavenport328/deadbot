import { type ComponentProps, type FormEvent, type KeyboardEvent, type ReactNode, createContext, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { AlbumUnitBlock, ExperienceBlock, ExperienceGroup, ExperienceResponse, ShowUnitBlock, SourceReference } from "./types";
import type { PageEvent, StreamEvent } from "./stream-events";
import { loadRequestedStreamEvents, loadRequestedVisualFixture, requestedStreamFixture, requestedVisualFixture } from "./visual-fixture-loader";
import { PlayerProvider, usePlayer, formatClockTime, formatSeekValueText, type PlayerTrack } from "./player";
import { CardPlayButton, ClampText, ListenLinks, ListeningHero, PullQuote, Rosettes, splitListen, toTrack, type InPagePlay } from "./listening";

type SetlistSections = ShowUnitBlock["sets"];
type SetlistSongType = SetlistSections[number]["songs"][number];
type ListenActions = ShowUnitBlock["listen"];
type UnitSources = ShowUnitBlock["sources"];

// The show-level facts a setlist row or a recording's listen action needs to
// build a PlayerTrack: date/venue for the now-playing bar's meta line, and
// the one Internet Archive item behind this show's tracks (once per show,
// not repeated per song) for the tape link and thumbnail.
type ShowMeta = {
  showDate?: string | null;
  venueName?: string | null;
  recordingDetailsUrl?: string | null;
  thumbnailUrl?: string | null;
};

function thumbnailForIdentifier(identifier?: string | null): string | null {
  return identifier ? `https://archive.org/services/img/${identifier}` : null;
}

function toPlayerTrack(song: SetlistSongType, meta: ShowMeta): PlayerTrack | null {
  if (!song.audio_url) return null;
  return {
    id: song.performance_id,
    title: song.title,
    audioUrl: song.audio_url,
    durationSeconds: song.duration_seconds ?? null,
    showDate: meta.showDate ?? null,
    venueName: meta.venueName ?? null,
    recordingDetailsUrl: meta.recordingDetailsUrl ?? null,
    thumbnailUrl: meta.thumbnailUrl ?? null
  };
}

function PlayPauseIcon({ playing }: { playing: boolean }) {
  if (playing) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="6" y="5" width="4.5" height="14" fill="currentColor" />
        <rect x="13.5" y="5" width="4.5" height="14" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M7 4.5v15l12-7.5z" />
    </svg>
  );
}

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

// Catalog counts shown on the home screen. These are read from the canonical
// CSVs, not the live database, so they cost the page nothing to display.
// tests/test_home_stats.py fails when an import moves them; recompute with:
//   python scripts/home_stats.py
const stats = [
  { count: "2,358", noun: "shows" },
  { count: "436", noun: "songs" },
  { count: "39,774", noun: "performances" },
  { count: "17,977", noun: "recordings" },
  { count: "139", noun: "guests" }
];

const startingPoints = [
  {
    category: "Shows",
    questions: [
      "Why is Cornell '77 so famous?",
      "What was the deal with Veneta '72?",
      "Cornell vs. Buffalo '77"
    ]
  },
  {
    category: "Songs",
    questions: [
      "How did Eyes of the World evolve?",
      "Where should I start with Dark Star?",
      "Early vs. late Shakedown"
    ]
  },
  {
    category: "Performances",
    questions: [
      "Find me an overlooked Sugaree",
      "What's the best Scarlet > Fire of 1977?",
      "Find me a great 1973 Playing in the Band"
    ]
  },
  {
    category: "Recordings",
    questions: [
      "What shows did Reckoning draw from?",
      "Best soundboard of Cornell '77?",
      "Which official releases cover 1972?"
    ]
  },
  {
    category: "Guests",
    questions: [
      "What shows did Branford play?",
      "Best songs with Santana",
      "Which guests changed the music most?"
    ]
  }
];

function createThreadId(): string {
  return `web-${crypto.randomUUID()}`;
}

// Reload after a deploy, checked only when a tab comes back into view and at
// most every few minutes. A timer would keep every forgotten background tab
// calling the server around the clock.
const VERSION_CHECK_INTERVAL_MS = 5 * 60_000;
let lastVersionCheck = 0;

async function refreshIfServerChanged(): Promise<void> {
  const now = Date.now();
  if (now - lastVersionCheck < VERSION_CHECK_INTERVAL_MS) return;
  lastVersionCheck = now;
  const result = await fetch("/api/version", { cache: "no-store" });
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

// Cards inside a titled group must not sit at the same heading level as the
// group's own <h2>. ComposedPage sets this to "h3" for the duration of a
// titled group's blocks; every card-level heading renders through here so it
// follows without each renderer knowing which level applies.
const HeadingContext = createContext<"h2" | "h3">("h2");

function CardHeading(props: ComponentProps<"h2">) {
  const Tag = useContext(HeadingContext);
  return <Tag {...props} />;
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

// Listen actions on a card that has no in-page play of its own (a record, a
// media link): quiet text links, the first carrying the small gold play mark
// because it is the card's way to hear it.
function ListenActionList({ actions }: { actions: ListenActions }) {
  return <ListenLinks actions={actions} plays={actions.map(() => null)} leadsListening />;
}

// A card's header: its one in-page play, round and gold, beside the title and
// identity line. Without an in-page play the header is the title alone.
function CardHead({ primary, children }: { primary: { play: InPagePlay; label: string } | null; children: ReactNode }) {
  if (!primary) return <>{children}</>;
  return (
    <div className="card-head">
      <CardPlayButton play={primary.play} label={primary.label} />
      <div className="card-head-text">{children}</div>
    </div>
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

// One playable setlist row: a 44px round play button at left, the title
// (still a listening link when the library has one), and a right-aligned
// duration. Segue rows carry a muted " >" and a thin connector down to the
// next row's button; the current track's row gets a faint gold wash and a
// progress line along its bottom edge.
function SetlistRow({
  song,
  track,
  isCurrent,
  isPlaying,
  isLoading,
  isError,
  position,
  duration,
  onPlay
}: {
  song: SetlistSongType;
  track: PlayerTrack | null;
  isCurrent: boolean;
  isPlaying: boolean;
  isLoading: boolean;
  isError: boolean;
  position: number;
  duration: number;
  onPlay: () => void;
}) {
  const className = [
    song.highlighted ? "hi" : null,
    isCurrent ? "current" : null,
    song.segue_into_next ? "segue" : null,
    isError ? "errored" : null
  ]
    .filter(Boolean)
    .join(" ");
  const progressPct = isCurrent && duration > 0 ? Math.min(100, (position / duration) * 100) : 0;
  const playLabel = !track ? `No recording for ${song.title}` : isError ? `Retry ${song.title}` : `${isCurrent && isPlaying ? "Pause" : "Play"} ${song.title}`;
  return (
    <li className={className || undefined} role="listitem">
      <div className="row-play-cell">
        <button
          type="button"
          className={`row-play${isCurrent ? " current" : ""}${track ? "" : " disabled"}${isError ? " errored" : ""}`}
          onClick={() => {
            if (isLoading) return;
            onPlay();
          }}
          disabled={!track}
          aria-busy={isLoading}
          aria-label={playLabel}
        >
          <PlayPauseIcon playing={isCurrent && isPlaying} />
        </button>
      </div>
      <span className="row-title">
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
        {song.segue_into_next && (
          <span className="segue-mark" aria-hidden="true">
            {" "}
            &gt;
          </span>
        )}
      </span>
      <span className="row-duration">{track || song.duration_seconds ? formatClockTime(song.duration_seconds) : "—"}</span>
      {isCurrent && <span className="row-progress" style={{ width: `${progressPct}%` }} aria-hidden="true" />}
    </li>
  );
}

// The setlist panel: one column per set, numbering continuing across sets
// (Set 2 starts at 9 when Set 1 has 8 songs). Clicking a row's play button
// plays that track and queues the rest of that set (its own playable songs,
// in order) after it.
function SetlistPanel({ sets, showMeta }: { sets: SetlistSections; showMeta: ShowMeta }) {
  const player = usePlayer();
  let runningCount = 0;
  return (
    <div className="setlist-panel">
      {sets.map((set) => {
        const start = runningCount + 1;
        runningCount += set.songs.length;
        const setTracks = set.songs.map((song) => toPlayerTrack(song, showMeta));
        return (
          <div key={set.label}>
            <span className="k">{set.label}</span>
            <ol className="setlist-rows" start={start} role="list">
              {set.songs.map((song, index) => {
                const track = setTracks[index];
                const isCurrent = Boolean(track && player.currentTrack?.id === track.id);
                return (
                  <SetlistRow
                    key={song.performance_id}
                    song={song}
                    track={track}
                    isCurrent={isCurrent}
                    isPlaying={isCurrent && player.status === "playing"}
                    isLoading={isCurrent && player.status === "loading"}
                    isError={isCurrent && player.status === "error"}
                    position={player.position}
                    duration={player.duration}
                    onPlay={() => {
                      if (!track) return;
                      if (isCurrent) {
                        if (player.status === "playing") player.pause();
                        else if (player.status === "error") player.retry();
                        else player.toggle();
                        return;
                      }
                      const queue = setTracks.slice(index).filter((item): item is PlayerTrack => item !== null);
                      player.play(track, queue);
                    }}
                  />
                );
              })}
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
      <div className="tabs">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            type="button"
            id={`${baseId}-tab-${tab.id}`}
            aria-expanded={open === tab.id}
            aria-controls={`${baseId}-panel-${tab.id}`}
            className="tab"
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
          id={`${baseId}-panel-${tab.id}`}
          className="panel"
          hidden={open !== tab.id}
        >
          {open === tab.id ? tab.content : null}
        </div>
      ))}
    </div>
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

// Judgments on a comparison's shared terms, as sentences: the criterion is a
// run-in lead, not a stacked label row. Each sentence clamps on its own.
function CriteriaTable({ criteria, judgments }: { criteria: string[]; judgments: string[] }) {
  if (criteria.length === 0) return null;
  const rows = criteria.map((criterion, index) => ({ criterion, judgment: (judgments[index] ?? "").trim() })).filter((row) => row.judgment);
  if (rows.length === 0) return null;
  return (
    <div className="criteria">
      {rows.map(({ criterion, judgment }) => (
        <ClampText key={criterion} className="judgment">
          <strong className="lead-in">{/[.:?!]$/.test(criterion.trim()) ? criterion.trim() : `${criterion.trim()}.`}</strong> {renderInline(judgment)}
        </ClampText>
      ))}
    </div>
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

// The roles, show count and years line under a roster name; blank parts dropped.
function rosterDetail(item: Extract<ExperienceBlock, { type: "person_roster" }>["items"][number]): string {
  const years = item.first_year && item.last_year
    ? item.first_year === item.last_year ? item.first_year : `${item.first_year}–${item.last_year.slice(2)}`
    : null;
  return [(item.roles ?? []).join(", "), item.show_count > 0 ? countLabel(item.show_count, "show") : null, years].filter(Boolean).join(" · ");
}

// The heading a block prints for itself, when it has one. A group whose only
// block repeats the group's own heading would stutter; the block keeps its
// heading and the group's is dropped.
function blockHeading(block: ExperienceBlock): string | null {
  if (block.type === "guest_appearance_list") return block.person_name;
  if ("title" in block && typeof block.title === "string") return block.title;
  return null;
}

function sameHeading(a: string | null, b: string | null): boolean {
  return !!a && !!b && a.trim().toLowerCase() === b.trim().toLowerCase();
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
  else if (event.type === "error") throw new Error(event.detail ?? "Deadbot could not answer just now. Try again, or rephrase the question.");
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
  const showMeta: ShowMeta = {
    showDate: unit.show_date,
    venueName: unit.venue_name,
    recordingDetailsUrl: unit.recording_details_url,
    thumbnailUrl: thumbnailForIdentifier(unit.recording_identifier)
  };
  const playableQueue = useMemo(
    () => unit.sets.flatMap((set) => set.songs.map((song) => toPlayerTrack(song, showMeta)).filter((track): track is PlayerTrack => track !== null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [unit.sets, unit.show_date, unit.venue_name, unit.recording_details_url, unit.recording_identifier]
  );

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
    tabs.push({ id: "setlist", label: "Setlist", count: totalSongs, content: <SetlistPanel sets={unit.sets} showMeta={showMeta} /> });
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
  // Two authors share the top of the card. The library names the show: type,
  // date, venue and place, in one identity zone. When the model wrote a
  // headline, it opens the overview beneath that zone with its note as the
  // text; without one, the venue is the headline as before.
  const modelHeadline = unit.title?.trim() || "";
  const identityName = unit.venue_name || dateLong;
  const listen = splitListen(shows("listen") ? unit.listen : [], playableQueue);
  const primary = listen.primary ? { play: listen.primary.play, label: listen.primary.action.label } : null;
  const wantsSetlistOpen = unit.setlist_disclosure === "expanded" || openFacets;
  const initialOpen = wantsSetlistOpen && tabs.some((tab) => tab.id === "setlist") ? "setlist" : null;

  return (
    <article className={`card show-unit emphasis-${unit.emphasis}`}>
      {modelHeadline ? (
        <>
          <IdRow type="Show" />
          <CardHead primary={primary}>
            <div className="identity">
              <p className="identity-name">
                <span>{unit.venue_name || dateLong}</span>
                {unit.venue_name ? <span>{dateLong}</span> : null}
              </p>
              <Meta parts={[unit.location, guestsNode]} />
            </div>
            <CardHeading className="overview">{modelHeadline}</CardHeading>
          </CardHead>
        </>
      ) : (
        <>
          <IdRow type="Show" when={dateLong} />
          <CardHead primary={primary}>
            <CardHeading>{identityName}</CardHeading>
            <Meta parts={[unit.location, guestsNode]} />
          </CardHead>
        </>
      )}
      {unit.note && <ClampText className="unit-note">{renderInline(unit.note)}</ClampText>}
      <CriteriaTable criteria={criteria} judgments={unit.judgments} />
      <ListenLinks actions={listen.restActions} plays={listen.restPlays} leadsListening={!primary} />
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

function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
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
  // Two authors share the top of the card, as on the show card. The library
  // names the record: type, then its title, kind and release date in one
  // identity zone. When the model wrote a headline of its own, it opens the
  // overview beneath that zone; otherwise the record's title is the headline.
  const recordName = block.release_title?.trim() || block.title;
  const modelHeadline = block.title.trim() && !sameHeading(block.title, recordName) ? block.title.trim() : "";
  const kindLine = formatReleaseType(block.release_type);

  return (
    <article className={`card album-unit emphasis-${block.emphasis}`}>
      {modelHeadline ? (
        <>
          <IdRow type={typeLabel} />
          <div className="identity">
            <p className="identity-name">{recordName}</p>
            <Meta parts={[kindLine, releaseLong ? `Released ${releaseLong}` : null]} />
          </div>
          <CardHeading className="overview">{modelHeadline}</CardHeading>
        </>
      ) : (
        <>
          <IdRow type={typeLabel} when={releaseLong ? `Released ${releaseLong}` : null} />
          <CardHeading>{recordName}</CardHeading>
          <Meta parts={[kindLine]} />
        </>
      )}
      {block.note && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
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
  // The card's performance is the current track: its title, venue and date
  // name it in the now-playing bar. The show's tape, when the card carries
  // it, queues after it and plays for a full-show action.
  const showQueue = useMemo(
    () => (block.show_tracks ?? []).map((track) => toTrack(track, { showDate: block.show_date, venueName: block.venue_name })),
    [block.show_tracks, block.show_date, block.venue_name]
  );
  const standalone = (url: string): PlayerTrack =>
    toTrack({ performance_id: block.performance_id, title: block.song_title, audio_url: url }, { showDate: block.show_date, venueName: block.venue_name });
  const listen = splitListen(block.listen, showQueue, standalone);
  const primary = listen.primary ? { play: listen.primary.play, label: listen.primary.action.label } : null;
  return (
    <article className={`card performance-unit emphasis-${block.emphasis}`}>
      <IdRow type="Performance" when={rightParts.length > 0 ? rightParts.join(" · ") : null} />
      <CardHead primary={primary}>
        <CardHeading>{block.song_title}</CardHeading>
        <Meta parts={[block.venue_name, formatShowDateLong(block.show_date), block.location]} />
      </CardHead>
      {block.note && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
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
        // Each leg is a stop with its trailing arrow, so a narrow card wraps
        // between legs and every line but the last ends on an arrow.
        return (
          <p className="set-excerpt" aria-label="Where this sits in the set">
            {rows.map((row, index) => (
              <span key={row.key} className="leg">
                <span className={row.here ? "stop here" : row.edge ? "stop edge" : "stop"}>
                  {row.n !== null && <span className="n">{row.n}</span>}
                  {row.title}
                </span>
                {index < rows.length - 1 && <span className="arrow" aria-hidden="true">→</span>}
              </span>
            ))}
          </p>
        );
      })()}
      <ListenLinks actions={listen.restActions} plays={listen.restPlays} leadsListening={!primary} />
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

// A show label arrives as "1970-06-07 — Fillmore West". The venue is the name;
// the date is written out beneath it.
function splitShowLabel(label: string, showDate?: string | null): { venue: string; date: string | null } {
  const parts = label.split(/\s+[—–-]\s+/);
  const venue = parts.length > 1 ? parts.slice(1).join(" — ") : label;
  const date = showDate ? formatShowDateLong(showDate) : parts.length > 1 ? parts[0] : null;
  return { venue, date };
}

type HistoryStop = { performance_id: string; show_label: string; show_date?: string | null; listen_url?: string | null; set_label?: string | null };

function HistoryStop({ stop, label }: { stop: HistoryStop; label: ReactNode }) {
  const { venue, date } = splitShowLabel(stop.show_label, stop.show_date);
  return (
    <li>
      <span className="history-year">{label}</span>
      <ListeningLabel title={venue} url={stop.listen_url} className="entry-title" />
      <span className="entry-detail">{[date, stop.set_label].filter(Boolean).join(" · ")}</span>
    </li>
  );
}

// The song's performance history: where it began and ended, then one
// performance a year across a horizontal strip.
function HistoryPanel({ history }: { history: NonNullable<SongOverviewBlockT["history"]> }) {
  const byYear = history.by_year ?? [];
  return (
    <div className="history">
      <ol className="history-span">
        <HistoryStop stop={history.first} label="First" />
        <HistoryStop stop={history.last} label="Last" />
      </ol>
      {byYear.length > 1 && (
        <ol className="history-years" aria-label="One performance a year">
          {byYear.map((item) => <HistoryStop key={item.performance_id} stop={item} label={item.year} />)}
        </ol>
      )}
    </div>
  );
}

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
    tabs.push({
      id: "history",
      label: "History",
      content: <HistoryPanel history={history} />
    });
  }
  if (showsFacet("albums") && block.albums.length > 0) {
    tabs.push({
      id: "record",
      label: "On record",
      count: block.albums.length,
      content: (
        <ul className="entry-list two-up records">
          {block.albums.map((album) => {
            const detail = [capitalize(album.release_type), album.release_date?.slice(0, 4)].filter(Boolean).join(" · ");
            return (
              <li key={album.release_id}>
                {album.listen_url ? (
                  <a
                    className="entry-title record-link"
                    href={album.listen_url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`Listen to ${album.title} on ${listeningDestination(album.listen_url)} (opens in a new tab)`}
                    title={`Opens ${listeningDestination(album.listen_url)} in a new tab`}
                  >
                    <Glyph kind={glyphForAction(album.listen_url, true)} />
                    {album.title}
                  </a>
                ) : (
                  <span className="entry-title">{album.title}</span>
                )}
                <span className="entry-detail">{detail}</span>
              </li>
            );
          })}
        </ul>
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
      <CardHeading>{block.title}</CardHeading>
      <Meta parts={[block.original_artist ? `Originally by ${block.original_artist}` : null]} />
      {block.note && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
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
          <IdRow type="Era" when={block.span} />
          <CardHeading>{block.title}</CardHeading>
          {block.note && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
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
          {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
            <footer className="unit-footer">
              <GoDeeper sources={block.sources} />
              <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
            </footer>
          )}
        </section>
      );
    case "album_unit":
      return <AlbumUnit block={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} />;
    case "entity_card": {
      const typeLabel = block.entity_type === "song" ? "Song" : block.entity_type === "show" ? "Show" : "Performance";
      return (
        <article className="typography-block entity-block">
          <IdRow type={typeLabel} />
          <CardHeading>{block.title}</CardHeading>
          {block.subtitle && <p className="meta">{block.subtitle}</p>}
          {block.details.length > 0 && (
            <ul className="details">
              {block.details.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>
          )}
          {block.follow_up && (
            <footer className="unit-footer">
              <div className="ask-block">
                <span className="k">Ask</span>
                <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />
              </div>
            </footer>
          )}
        </article>
      );
    }
    case "show_selection":
      return (
        <section className="typography-block show-selection">
          <IdRow type={block.selection_type} when={countLabel(block.items.length, "show")} />
          <CardHeading>{block.title}</CardHeading>
          <p className="meta">Selected by {block.selector_name}</p>
          <ol className="entry-list two-up">
            {block.items.map((item) => (
              <li key={item.show_id}>
                <span className="entry-title">{item.venue_name}</span>
                <span className="entry-detail">{[formatShowDateLong(item.show_date), item.location].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ol>
          <p className="coverage-note">{block.coverage_note}</p>
        </section>
      );
    case "guest_appearance_list":
      return (
        <section className="typography-block guest-appearance-list">
          <IdRow type="Guest appearances" when={countLabel(block.known_show_count, "show")} />
          <CardHeading>{block.person_name}</CardHeading>
          <ol className="entry-list two-up">
            {block.items.map((item) => (
              <li key={item.show_id}>
                <span className="entry-title">{item.venue_name || formatShowDateLong(item.show_date)}</span>
                <span className="entry-detail">
                  {[item.venue_name ? formatShowDateLong(item.show_date) : null, item.location, item.instruments.join(", "), item.participation_scope].filter(Boolean).join(" · ")}
                </span>
                {item.songs && item.songs.length > 0 && (
                  <span className="entry-detail">{item.songs.map((song) => song.song_title).join(", ")}</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      );
    case "person_roster":
      return (
        <section className="typography-block person-roster">
          <IdRow type="Roster" when={countLabel(block.items.length, "name")} />
          <CardHeading>{block.title}</CardHeading>
          {block.lead && <p className="unit-note">{renderInline(block.lead)}</p>}
          <ul className="people roster">
            {block.items.map((item) => (
              <li key={item.person_id}>
                {item.name}
                <span>{rosterDetail(item)}</span>
                {item.note && <em className="roster-note">{renderInline(item.note)}</em>}
              </li>
            ))}
          </ul>
        </section>
      );
    case "equipment_list":
      return (
        <section className="typography-block equipment-list">
          <IdRow type="Equipment" when={countLabel(block.items.length, "item")} />
          <CardHeading>{block.title}</CardHeading>
          <ul className="entry-list two-up">
            {block.items.map((item) => (
              <li key={`${item.equipment_id}-${item.usage_context}-${item.evidence}`}>
                <span className="entry-title">{item.name}</span>
                <span className="entry-detail">{[item.manufacturer, item.model].filter(Boolean).join(" ")}</span>
                <span className="entry-detail">
                  {item.usage_context} · {item.claim_type === "show" ? "seen at this show" : "dated to this period"} · {item.evidence}
                </span>
                <ExternalLink className="entry-link" href={item.source_url}>Source note</ExternalLink>
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
          <IdRow type="Go deeper" when={countLabel(block.items.length, "source")} />
          <CardHeading>{block.title}</CardHeading>
          <div className="reading">
            {block.items.map((item) => (
              <div className="reading-source" key={item.resource_id}>
                <p className="reading-title"><ExternalLink href={item.url}>{item.title}</ExternalLink></p>
                <p className="reading-pub">
                  <span className="pub">{item.source_name}</span> · {item.resource_type}{item.context_note ? ` · ${item.context_note}` : ""}
                </p>
              </div>
            ))}
          </div>
        </section>
      );
    case "credit_list":
      return (
        <section className="typography-block credit-list">
          <IdRow type="Composition" />
          <CardHeading>{block.title}</CardHeading>
          <PeopleList people={block.items.map((item) => ({ key: `${item.person_id}-${item.role}`, name: item.name, detail: item.role }))} />
        </section>
      );
    case "media_link":
      return (
        <section className="card media-card">
          <IdRow type={block.provider} when={block.is_official ? "Official release" : null} />
          <CardHeading>{block.title}</CardHeading>
          <MediaEmbed block={block} />
          <ListenActionList actions={[{ label: `Open on ${block.provider}`, provider: block.provider, url: block.url, is_official: block.is_official }]} />
        </section>
      );
    case "coverage":
      return (
        <aside className="typography-block aside-block coverage-block">
          <span className="k">Library coverage</span>
          <p className="aside-title">{block.title}</p>
          <p>{block.message}</p>
        </aside>
      );
    case "arrangement": {
      const source = sourceFor(sources, block.source_id);
      return (
        <section className="typography-block arrangement-block">
          <IdRow type="Arrangement" when={block.key_signature ? `Key of ${block.key_signature}` : null} />
          <CardHeading>{block.title}</CardHeading>
          <Meta parts={[capitalize(block.arrangement_scope.replaceAll("-", " ")), block.capo ? `Capo ${block.capo}` : null, block.tuning ? `${block.tuning} tuning` : null]} />
          {block.notes && <p className="unit-note">{block.notes}</p>}
          {block.progressions.length > 0 && (
            <ul className="chords">
              {block.progressions.map((progression, index) => <li key={`${index}-${progression}`}>{progression}</li>)}
            </ul>
          )}
          {source?.url && (
            <div className="reading">
              <p className="reading-pub"><ExternalLink href={source.url}>Open the source</ExternalLink></p>
            </div>
          )}
        </section>
      );
    }
    case "arrangement_search":
      return (
        <section className="typography-block arrangement-search">
          <IdRow type="Musician’s reference" when={`Key of ${block.key_signature}`} />
          <CardHeading>{block.title}</CardHeading>
          <p className="meta">{block.coverage_note}</p>
          <ul className="entry-list">
            {block.items.map((item) => (
              <li key={item.arrangement_id}>
                <span className="entry-title">{item.title}</span>
                <span className="entry-detail">{capitalize(item.arrangement_scope.replaceAll("-", " "))} · key of {item.key_signature}</span>
                <ExternalLink className="entry-link" href={item.url}>{item.resource_title} · {item.source_name}</ExternalLink>
              </li>
            ))}
          </ul>
        </section>
      );
    case "editorial":
      if (block.presentation === "narrative") return (
        <section className="typography-block narrative-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <CardHeading>{block.title}</CardHeading>}
          {block.paragraphs.map((paragraph, index) => <p key={index}>{renderInline(paragraph)}</p>)}
        </section>
      );
      if (block.presentation === "fact_grid") return (
        <section className="typography-block fact-grid-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <CardHeading>{block.title}</CardHeading>}
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
          {block.title && <CardHeading>{block.title}</CardHeading>}
          <ol>
            {block.items.map((item, index) => (
              <li key={`${item.marker ?? item.title}-${index}`}>
                {item.marker && <span className="timeline-marker">{item.marker}</span>}
                <strong>{renderInline(item.title)}</strong>
                {item.detail && <span className="timeline-detail">{renderInline(item.detail)}</span>}
                {item.link && <ExternalLink className="timeline-link" href={item.link.url}>{item.link.label}</ExternalLink>}
                {(item.follow_ups ?? []).length > 0 && <span className="timeline-ask"><TopicChips topics={item.follow_ups} onFollowUp={onFollowUp} /></span>}
              </li>
            ))}
          </ol>
        </section>
      );
    case "provenance_note":
      return (
        <aside className="typography-block aside-block provenance-note">
          <span className="k">From the source</span>
          <p>{block.text}</p>
        </aside>
      );
    case "gap_state":
      return (
        <aside className="typography-block aside-block gap-state">
          <span className="k">Not in the library</span>
          <p>{block.message}</p>
        </aside>
      );
    case "listening_hero":
      return <ListeningHero block={block} />;
    case "pull_quote":
      return <PullQuote block={block} />;
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
  // A listening hero the model placed first leads the page, above the title.
  const firstBlock = groups[0]?.blocks[0];
  const hero = firstBlock?.type === "listening_hero" ? firstBlock : null;
  const bodyGroups = hero ? [{ ...groups[0], blocks: groups[0].blocks.slice(1) }, ...groups.slice(1)] : groups;
  return (
    <>
      {hero && <ListeningHero block={hero} />}
      <div className="content-heading">
        <h1 id="answer-title" tabIndex={-1}>{title}</h1>
      </div>
      {lead && <p className="answer-lead">{renderInline(lead)}</p>}
      {bodyGroups.map((group, groupIndex) => {
        if (hero && groupIndex === 0 && group.blocks.length === 0) return null;
        const groupTitle = group.blocks.length === 1 && sameHeading(group.title, blockHeading(group.blocks[0])) ? null : group.title;
        return (
        <section className={`experience-group group-${group.presentation}${groupTitle ? " has-heading" : ""}`} key={groupIndex}>
          {(groupTitle || group.lead) && (
            group.presentation === "argument" ? (
              <header className="group-heading claim">
                {groupTitle && <h2>{groupTitle}</h2>}
                {group.lead && <p className="claim-text">{renderInline(group.lead)}</p>}
              </header>
            ) : (
              <header className="group-heading">
                {groupTitle && <h2>{groupTitle}</h2>}
                {group.lead && <p>{renderInline(group.lead)}</p>}
              </header>
            )
          )}
          <HeadingContext.Provider value={groupTitle ? "h3" : "h2"}>
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
          </HeadingContext.Provider>
        </section>
        );
      })}
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

// The one shared now-playing bar for the whole app: hidden until something
// has played, then fixed to the bottom of the answer pane it lives in (never
// over the left rail, since it renders inside .content-pane). A 44px round
// gold play/pause button, a real range-input scrubber with tabular-numeral
// elapsed/total time, and one quiet external link to the tape's own details
// page — everything else (queueing, position, next/previous within the
// current queue) is the shared PlayerProvider's job.
function NowPlayingBar() {
  const player = usePlayer();
  const track = player.currentTrack;
  if (!track) return null;
  const isPlaying = player.status === "playing";
  const isLoading = player.status === "loading";
  const isError = player.status === "error";
  const duration = player.duration || track.durationSeconds || 0;
  const position = Math.min(player.position, duration || 0);
  const metaLine = [formatShowDate(track.showDate), track.venueName].filter(Boolean).join(" · ");
  return (
    <div className="now-playing-bar" role="region" aria-label="Now playing">
      {track.thumbnailUrl ? (
        <img className="now-playing-thumb" src={track.thumbnailUrl} alt="" loading="lazy" />
      ) : (
        <div className="now-playing-thumb placeholder" aria-hidden="true" />
      )}
      <div className="now-playing-info">
        <p className="now-playing-title">{track.title}</p>
        {isError ? <p className="now-playing-error">Couldn’t play this track</p> : metaLine ? <p className="now-playing-meta">{metaLine}</p> : null}
      </div>
      {isError ? (
        <button type="button" className="now-playing-retry" onClick={() => player.retry()}>
          Retry
        </button>
      ) : (
        <button
          type="button"
          className="now-playing-toggle"
          onClick={() => {
            if (!isLoading) player.toggle();
          }}
          aria-label={isPlaying ? "Pause" : "Play"}
          aria-busy={isLoading}
          disabled={isLoading}
        >
          <PlayPauseIcon playing={isPlaying} />
        </button>
      )}
      <div className="now-playing-scrubber">
        <span className="now-playing-time" aria-hidden="true">{formatClockTime(position)}</span>
        <input
          type="range"
          className="now-playing-range"
          min={0}
          max={duration || 0}
          step={1}
          value={position}
          aria-label={`Seek within ${track.title}`}
          aria-valuetext={formatSeekValueText(position, duration)}
          onChange={(event) => player.seek(Number(event.target.value))}
        />
        <span className="now-playing-time" aria-hidden="true">{formatClockTime(duration)}</span>
      </div>
      {track.recordingDetailsUrl && (
        <a className="now-playing-tape" href={track.recordingDetailsUrl} target="_blank" rel="noreferrer">
          Tape on the Internet Archive
        </a>
      )}
    </div>
  );
}

function App() {
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
  const workspaceRef = useRef<HTMLDivElement>(null);
  const conversationPaneRef = useRef<HTMLElement>(null);
  // Callbacks passed into askStreaming close over stale render state, so track
  // whether the answer has already started in a ref.
  const answerStartedRef = useRef(false);
  // Set right before a successful response lands, so the focus/live-region
  // effect below knows this render is the one to act on rather than firing on
  // every unrelated response change (a `?fixture=` load, for instance).
  const askJustCompletedRef = useRef(false);

  // The start screen is the whole content area until a question is asked (or
  // one is already in flight, or already answered). It drives both the empty
  // layout and the initial animation phase below.
  const atStart = !response && !loading && !pendingQuestion;

  // The ask transition's state machine. Emil Kowalski's rules: transform and
  // opacity only, never ease-in. "start" is the still, rail-less home screen;
  // "leaving" fades the lead and library while the composer stays put;
  // "opening" snaps the rail and content pane off-canvas with no transition
  // the instant the real layout replaces the start screen; "arriving" turns
  // the transitions on for one frame later so the browser animates from that
  // off-canvas position back to rest; "settled" is the ordinary, resting page.
  const [phase, setPhase] = useState<"start" | "leaving" | "opening" | "arriving" | "settled">(atStart ? "start" : "settled");
  // A visually hidden status line, announced once per answer instead of on
  // every render (finding 3).
  const [answerReadyMessage, setAnswerReadyMessage] = useState<string | null>(null);

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
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshIfServerChanged();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [visualFixture]);

  useEffect(() => {
    if (!visualFixture) return;
    void loadRequestedVisualFixture().then((fixture) => {
      if (fixture) setResponse(fixture);
    });
  }, [visualFixture]);

  // Once the app switches out of the start screen ("opening"), measure the
  // rail's actual width and hand it to the content pane as a CSS variable, so
  // the content pane's opening translateX matches the rail exactly even if
  // the rail isn't the 310px the grid track defaults to. Two nested rAFs
  // force a reflow at the off-canvas position before "arriving" turns the
  // transitions on, so the browser animates from there rather than skipping
  // straight to rest.
  const innerFrameRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (phase !== "opening") return;
    const rail = conversationPaneRef.current;
    const workspace = workspaceRef.current;
    if (rail && workspace) {
      workspace.style.setProperty("--rail-w", `${rail.getBoundingClientRect().width}px`);
    }
    const outer = requestAnimationFrame(() => {
      const inner = requestAnimationFrame(() => setPhase("arriving"));
      innerFrameRef.current = inner;
    });
    return () => {
      cancelAnimationFrame(outer);
      if (innerFrameRef.current !== null) cancelAnimationFrame(innerFrameRef.current);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== "arriving") return;
    const timer = window.setTimeout(() => setPhase("settled"), 1300);
    return () => window.clearTimeout(timer);
  }, [phase]);

  // Move focus to the answer heading once a response actually lands from an
  // ask (never on a `?fixture=` load, which never sets the ref). The page has
  // usually streamed in and the visitor may already be reading further down,
  // so focus moves without scrolling them back to the top.
  useEffect(() => {
    if (!response || !askJustCompletedRef.current) return;
    askJustCompletedRef.current = false;
    document.getElementById("answer-title")?.focus({ preventScroll: true });
  }, [response]);

  // The dev `?stream=` fixture replays a canned event sequence through the
  // same dispatch the network path uses, so progressive rendering can be
  // reviewed without a model. It no longer starts itself on mount: askQuestion
  // triggers it, the same way it triggers a real request, so the start screen
  // and the ask transition are both exercised by simply asking a question.
  async function replayStreamFixture(): Promise<void> {
    const events = await loadRequestedStreamEvents();
    if (!events) return;
    let statusCount = 0;
    for (const event of events) {
      await delay(event.type === "block" ? 600 : event.type === "answer" ? 40 : 300);
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
          setAnswerReadyMessage(`Answer ready: ${nextResponse.title}`);
          askJustCompletedRef.current = true;
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
  }

  async function askQuestion(nextQuestion?: string, { fresh = false }: { fresh?: boolean } = {}) {
    if (visualFixture) return;
    const trimmed = (nextQuestion ?? question).trim();
    if (!trimmed || loading) return;

    const cameFromStart = phase === "start";
    if (cameFromStart) {
      setPhase("leaving");
      await delay(180);
    }

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
    setAnswerReadyMessage(null);
    answerStartedRef.current = false;
    if (cameFromStart) setPhase("opening");

    if (import.meta.env.DEV && requestedStreamFixture) {
      await replayStreamFixture();
      return;
    }

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
      const finalResponse = streamed ?? await askPlain(body);
      setResponse(finalResponse);
      setAnswerReadyMessage(`Answer ready: ${finalResponse.title}`);
      askJustCompletedRef.current = true;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Deadbot could not answer just now. Try again, or rephrase the question.");
      if (cameFromStart) setPhase("start");
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
  // fall back to the plain request. A stream that started and then ended
  // without its response is a failure, not a reason to run the question
  // again: a second run writes a different answer, and the visitor would
  // watch the first one be replaced without knowing why.
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
      throw new Error(detail?.detail ?? "Deadbot could not answer just now. Try again, or rephrase the question.");
    }
    if (!result.body) return null;
    const reader = result.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer: ExperienceResponse | null = null;
    let sawEvent = false;
    const consume = (line: string) => {
      if (!line.trim()) return;
      sawEvent = true;
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
    if (answer === null && sawEvent) {
      throw new Error("The connection closed before Deadbot finished the page. Please ask again.");
    }
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
      throw new Error(detail?.detail ?? "Deadbot could not answer just now. Try again, or rephrase the question.");
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
    setAnswerReadyMessage(null);
    setPhase("start");
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

  // Shared by the rail and the start screen, which never render at the same
  // time (the rail is visually collapsed while atStart), but each needs its
  // own element id.
  function renderComposer(variant: "rail" | "start") {
    return (
      <form className={variant === "start" ? "composer start-composer" : "composer"} onSubmit={submit}>
        <div className="question-field">
          <textarea
            id={`question-${variant}`}
            aria-label="Question"
            rows={3}
            placeholder="Ask about a song, show, source, or recording"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={submitOnEnter}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !question.trim()}>{loading ? "Looking…" : "Explore"}</button>
        </div>
        {variant === "rail" && response && !loading && (
          <a className="view-answer-link" href="#answer-title">View answer <span aria-hidden="true">↓</span></a>
        )}
      </form>
    );
  }

  const workspaceClassName = [
    "workspace",
    atStart ? "start" : null,
    phase === "opening" ? "opening" : null,
    phase === "arriving" ? "arriving" : null
  ].filter(Boolean).join(" ");

  return (
    <main className="app-shell">
      <p role="status" className="sr-only">{answerReadyMessage}</p>
      <div className={workspaceClassName} ref={workspaceRef}>
        <aside className="conversation-pane" aria-label="Conversation" ref={conversationPaneRef}>
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
                <article className="message assistant pending">
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

            {error && !atStart && <p className="error" role="alert">{error}</p>}

            {renderComposer("rail")}
          </section>
        </aside>

        <section className="content-pane" aria-label="Deadbot guide">
          {atStart ? (
            <div className={`start-screen${phase === "leaving" ? " leaving" : ""}`}>
              <h1 className="start-lead">Exploration and listening across the entire Dead catalog.</h1>
              {renderComposer("start")}
              {error && <p className="error" role="alert">{error}</p>}
              <div className="library">
                {stats.map(({ count, noun }) => {
                  const group = startingPoints.find((candidate) => candidate.category.toLowerCase() === noun);
                  return (
                    <section className="library-stat" key={noun}>
                      <p className="num">{count}</p>
                      <p className="noun">{noun}</p>
                      {group && (
                        <ul className="qs">
                          {group.questions.map((prompt) => (
                            <li key={prompt}>
                              <button type="button" onClick={() => void askQuestion(prompt, { fresh: true })} disabled={loading}>
                                {prompt}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  );
                })}
              </div>
            </div>
          ) : loading && draft ? (
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
          ) : null}
          <NowPlayingBar />
        </section>
      </div>
    </main>
  );
}

export default function AppWithPlayer() {
  return (
    <PlayerProvider>
      <Rosettes />
      <App />
    </PlayerProvider>
  );
}
