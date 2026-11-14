// Song versions: chosen versions of one song, each a bar on one shared clock
// (width = its length over the longest), each row playable. Gold marks what
// plays here; the tape is what plays, the length shown is the release's when
// there is one. A row with no tape draws what it knows and links its record.
import { CardHeading } from "./components";
import { AddToQueue, PlayGlyph, toTrack, usePlayControl, type InPagePlay } from "./listen-control";
import { usePlayer, type PlayerTrack } from "../player/player";
import type { ExperienceBlock } from "../types";
import "./SongVersions.css";

type SongVersionsBlock = Extract<ExperienceBlock, { type: "song_versions" }>;
type SongVersionsRow = SongVersionsBlock["rows"][number];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function shortDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  return match && month ? `${month} ${Number(match[3])}, ${match[1]}` : iso;
}

// m:ss, or h:mm:ss over an hour.
export function length(seconds?: number | null): string {
  if (seconds == null) return "–";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

// The whole queue's running time, read the same way as a row's length.
const total = (seconds: number): string => length(seconds);

function rowTrack(row: SongVersionsRow): PlayerTrack | null {
  return row.track ? toTrack(row.track, { showDate: row.show_date, venueName: row.venue_name }) : null;
}

function Row({ block, row, longest, queue }: { block: SongVersionsBlock; row: SongVersionsRow; longest: number; queue: PlayerTrack[] }) {
  const track = rowTrack(row);
  const play: InPagePlay | null = track ? { start: track, queue } : null;
  const control = usePlayControl(play, "start");
  const name = `${block.song.title}, ${row.venue_name}, ${shortDate(row.show_date)}`;
  const label = control.errored ? `Retry ${name}` : control.playing ? `Pause ${name}` : control.loading ? `Loading ${name}` : `Play ${name}`;
  const width = row.length_seconds != null && longest > 0 ? Math.max((row.length_seconds / longest) * 100, 1) : 0;
  return (
    <li className={`sv-row${control.mine ? " current" : ""}${track ? " playable" : ""}`}>
      {track ? (
        <button type="button" className="sv-play" aria-label={label} aria-pressed={control.mine} aria-busy={control.loading} onClick={control.onClick}>
          <PlayGlyph playing={control.playing} />
        </button>
      ) : (
        <span className="sv-play-placeholder" aria-hidden="true" />
      )}
      <div className="sv-night">
        <strong className="sv-venue">{row.venue_name}</strong>
        <span className="sv-date">{[row.city, shortDate(row.show_date)].filter(Boolean).join(" · ")}</span>
        {!track && row.release &&
          (row.release.url ? (
            <a className="sv-release" href={row.release.url} target="_blank" rel="noreferrer">
              On {row.release.title}
            </a>
          ) : (
            <span className="sv-release">On {row.release.title}</span>
          ))}
      </div>
      <div className="sv-bar" aria-hidden="true">
        {width > 0 && <span className="sv-fill" style={{ width: `${width}%` }} />}
      </div>
      <span className="sv-length">{length(row.length_seconds)}</span>
      <span className="sv-add">{track && <AddToQueue tracks={[track]} name={name} />}</span>
      {row.note && <p className="sv-note">{row.note}</p>}
    </li>
  );
}

export function SongVersions({ block }: { block: SongVersionsBlock }) {
  const player = usePlayer();
  const tracks = block.rows.map(rowTrack).filter((track): track is PlayerTrack => track != null);
  const seconds = block.rows.reduce((sum, row) => sum + (row.track ? (row.tape_seconds ?? 0) : 0), 0);
  const queued = tracks.length > 0 && tracks.every((track) => player.queue.some((item) => item.id === track.id || item.audioUrl === track.audioUrl));
  const longest = Math.max(0, ...block.rows.map((row) => row.length_seconds ?? 0));
  return (
    <section className="song-versions">
      <div className="sv-head">
        <CardHeading className="sv-title">{block.title || block.song.title}</CardHeading>
        {tracks.length > 0 && (
          <button type="button" className={`sv-queue-all${queued ? " queued" : ""}`} aria-label={queued ? "In the queue" : "Queue all"} onClick={() => !queued && player.enqueue(tracks)}>
            {queued ? "✓ In the queue" : `+ Queue all ${tracks.length} · ${total(seconds)}`}
          </button>
        )}
      </div>
      <ol className="sv-rows">
        {block.rows.map((row) => (
          <Row key={row.performance_id} block={block} row={row} longest={longest} queue={tracks} />
        ))}
      </ol>
    </section>
  );
}
