// The version strip: chosen nights of one song pairing (China Cat Sunflower >
// I Know You Rider), each drawn as one bar on a shared clock. The first song's
// tape track is the solid gold segment, the second song's the pale one. Gold
// means playable: pressing a row plays that night's two tracks in turn in the
// shared player.
import { type CSSProperties } from "react";
import { CardHeading } from "./components";
import { toTrack } from "./listening";
import { usePlayer, type PlayerTrack } from "./player";
import type { ExperienceBlock } from "./types";
import "./VersionStrip.css";

type VersionStripBlock = Extract<ExperienceBlock, { type: "version_strip" }>;
type VersionStripRow = VersionStripBlock["rows"][number];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function shortDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  return match && month ? `${month} ${Number(match[3])}, ${match[1]}` : iso;
}

export function clock(seconds?: number | null): string {
  if (seconds == null) return "–";
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

// A tick step that gives the clock at most four or five intervals.
const STEPS = [1, 2, 5, 10, 15, 20, 30, 60];

export function timeScale(rows: VersionStripRow[]): { maxSeconds: number; ticks: number[] } {
  const longest = Math.max(60, ...rows.map((row) => (row.first_seconds ?? 0) + (row.second_seconds ?? 0)));
  // A little room past the longest night so its bar never meets the edge.
  const maxSeconds = Math.ceil((longest * 1.08) / 60) * 60;
  const minutes = maxSeconds / 60;
  const step = STEPS.find((candidate) => minutes / candidate <= 5) ?? 60;
  const ticks: number[] = [];
  for (let minute = 0; minute * 60 <= maxSeconds; minute += step) ticks.push(minute);
  return { maxSeconds, ticks };
}

// Positions on the clock are fractions of the bar area, which leaves room at
// its right edge for the times label (the room is a CSS property, so it can
// collapse on a phone where the label moves under the bar).
function along(fraction: number, offset = "0px"): string {
  return `calc((100% - var(--vs-label-room)) * ${fraction.toFixed(4)} + ${offset})`;
}

function rowTracks(row: VersionStripRow): PlayerTrack[] {
  const meta = { showDate: row.show_date, venueName: row.venue_name };
  return [row.first_track, row.second_track]
    .filter((track): track is NonNullable<typeof track> => track != null)
    .map((track) => toTrack(track, meta));
}

function PlayGlyph({ playing }: { playing: boolean }) {
  return playing ? (
    <svg viewBox="0 0 14 14" aria-hidden="true">
      <rect x="2.5" y="2" width="3" height="10" fill="currentColor" />
      <rect x="8.5" y="2" width="3" height="10" fill="currentColor" />
    </svg>
  ) : (
    <svg viewBox="0 0 14 14" aria-hidden="true">
      <path fill="currentColor" d="M4 2.2v9.6l7.6-4.8z" />
    </svg>
  );
}

function StripRow({ block, row, maxSeconds }: { block: VersionStripBlock; row: VersionStripRow; maxSeconds: number }) {
  const player = usePlayer();
  const queue = rowTracks(row);
  const current = player.currentTrack;
  const mine = Boolean(current && queue.some((track) => track.id === current.id && track.audioUrl === current.audioUrl));
  const playing = mine && player.status === "playing";
  const loading = mine && player.status === "loading";
  const pairing = `${block.first_song.title} > ${block.second_song.title}`;
  const label = `${playing ? "Pause" : "Play"} ${pairing}, ${row.venue_name}, ${shortDate(row.show_date)}`;

  function onPlay() {
    if (queue.length === 0 || loading) return;
    if (playing) player.pause();
    else if (mine && player.status === "error") player.retry();
    else if (mine) player.toggle();
    else player.play(queue[0], queue);
  }

  const first = (row.first_seconds ?? 0) / maxSeconds;
  const second = (row.second_seconds ?? 0) / maxSeconds;
  const hasFirst = row.first_seconds != null;
  const hasSecond = row.second_seconds != null;
  const secondStart = hasFirst ? along(first, "3px") : along(0);
  const end = hasSecond ? along(first + second, hasFirst ? "3px" : "0px") : along(first);
  const playable = queue.length > 0;

  return (
    <li
      className={`vs-row${mine ? " current" : ""}${playable ? " playable" : ""}`}
      onClick={playable ? onPlay : undefined}
    >
      {playable ? (
        <button
          type="button"
          className="vs-play"
          aria-label={label}
          aria-pressed={mine}
          aria-busy={loading}
          onClick={(event) => {
            event.stopPropagation();
            onPlay();
          }}
        >
          <PlayGlyph playing={playing} />
        </button>
      ) : (
        <span className="vs-play-placeholder" aria-hidden="true" />
      )}
      <div className="vs-night">
        <span className="vs-date">{shortDate(row.show_date)}</span>
        <span className="vs-venue">{[row.venue_name, row.location].filter(Boolean).join(", ")}</span>
      </div>
      <div className="vs-track">
        <div className="vs-bars" aria-hidden="true">
          {hasFirst && <span className="vs-first" style={{ left: 0, width: along(first) }} />}
          {hasSecond && <span className="vs-second" style={{ left: secondStart, width: along(second) }} />}
        </div>
        <span className="vs-times" style={{ "--vs-end": end } as CSSProperties}>
          {clock(row.first_seconds)} &gt; {clock(row.second_seconds)}
        </span>
      </div>
    </li>
  );
}

function YearCounts({ block }: { block: VersionStripBlock }) {
  const player = usePlayer();
  const years = block.year_counts ?? [];
  if (years.length === 0) return null;
  const most = Math.max(1, ...years.map((entry) => entry.count));
  const playingRow = block.rows.find((row) =>
    [row.first_performance_id, row.second_performance_id].includes(player.currentTrack?.id ?? "")
  );
  const playingYear = playingRow ? Number(playingRow.show_date.slice(0, 4)) : null;
  const first = years[0].year;
  const last = years[years.length - 1].year;
  return (
    <figure className="vs-years">
      <figcaption className="vs-years-caption">
        <span className="vs-years-total">{block.total_count.toLocaleString()}</span> nights, {first} to {last}
      </figcaption>
      <div className="vs-years-bars" role="img" aria-label={years.map((entry) => `${entry.year}: ${entry.count}`).join(", ")}>
        {years.map((entry) => (
          <span
            key={entry.year}
            title={`${entry.year}: ${entry.count}`}
            className={`vs-year${entry.year === playingYear ? " current" : ""}`}
            style={{ height: entry.count ? `${Math.max((entry.count / most) * 100, 3)}%` : 0 }}
          />
        ))}
      </div>
      <div className="vs-years-axis" aria-hidden="true">
        <span>{first}</span>
        <span>{last}</span>
      </div>
    </figure>
  );
}

export function VersionStrip({ block }: { block: VersionStripBlock }) {
  const { maxSeconds, ticks } = timeScale(block.rows);
  return (
    <section className="version-strip">
      {block.title && <CardHeading className="vs-title">{block.title}</CardHeading>}
      {block.note && <p className="vs-note">{block.note}</p>}
      <div className="vs-head">
        <span aria-hidden="true" />
        <div className="vs-legend">
          <span><i className="vs-swatch first" aria-hidden="true" />{block.first_song.title}</span>
          <span><i className="vs-swatch second" aria-hidden="true" />{block.second_song.title}</span>
        </div>
        <div className="vs-ticks" aria-hidden="true">
          {ticks.map((minute) => (
            <span
              key={minute}
              className={minute === 0 ? "start" : (minute * 60) / maxSeconds > 0.9 ? "end" : undefined}
              style={{ left: along((minute * 60) / maxSeconds) }}
            >
              {minute} min
            </span>
          ))}
        </div>
      </div>
      <ol className="vs-rows">
        {block.rows.map((row) => (
          <StripRow key={row.pair_id} block={block} row={row} maxSeconds={maxSeconds} />
        ))}
      </ol>
      <p className="vs-caption">
        Lengths are the {block.first_song.title} and {block.second_song.title} tracks on each night’s Internet Archive tape.
        Where a tape splits the transition, the split decides which half it counts toward.
      </p>
      <YearCounts block={block} />
    </section>
  );
}
