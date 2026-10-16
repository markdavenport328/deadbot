import { useId, useState } from "react";
import type { AlbumUnitBlock } from "./types";
import type { PlayerTrack } from "./player";
import { CardPlayButton, toTrack } from "./listening";
import { ListenControl } from "./listen-control";

type AlbumTrack = AlbumUnitBlock["tracks"][number];

export type Night = { key: string; date: string | null; venue: string | null; city: string | null; tracks: AlbumTrack[] };

// A live record's track, as the tape of the performance it was taken from.
export function albumTrack(track: AlbumTrack): PlayerTrack | null {
  if (!track.audio_url) return null;
  return toTrack(
    { performance_id: track.performance_id ?? `track-${track.track_number}`, title: track.title, audio_url: track.audio_url, duration_seconds: track.audio_duration_seconds },
    { showDate: track.show_date, venueName: track.venue_name }
  );
}

// A record whose tracks come from more than one show is read night by night:
// the nights in date order, then any tracks from no known show. A record from
// one show (or none) has no nights to show, and keeps its plain tracklist.
export function groupByNight(tracks: AlbumTrack[]): { nights: Night[]; other: AlbumTrack[] } | null {
  const nights = new Map<string, Night>();
  const other: AlbumTrack[] = [];
  for (const track of tracks) {
    if (!track.show_id) {
      other.push(track);
      continue;
    }
    const night = nights.get(track.show_id) ?? { key: track.show_id, date: track.show_date ?? null, venue: track.venue_name ?? null, city: track.city ?? null, tracks: [] };
    night.tracks.push(track);
    nights.set(track.show_id, night);
  }
  // A box of whole nights, not a compilation drawing a song or two from each.
  const placed = tracks.length - other.length;
  if (nights.size < 2 || placed < 3 * nights.size) return null;
  const ordered = [...nights.values()].sort((a, b) => (a.date ?? "9999").localeCompare(b.date ?? "9999"));
  return { nights: ordered, other };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function nightDate(iso: string | null): string {
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso) : null;
  if (!match) return iso ?? "Date unknown";
  return `${MONTHS[Number(match[2]) - 1]} ${Number(match[3])}, ${match[1]}`;
}

function TrackItems({ tracks, queue }: { tracks: AlbumTrack[]; queue: PlayerTrack[] }) {
  return (
    <ol className="song-list">
      {tracks.map((track) => (
        <li key={track.track_number} value={track.track_number} className={track.highlighted ? "hi" : undefined}>
          <ListenControl url={track.listen_url} label={track.title} track={albumTrack(track)} queue={queue} />
        </li>
      ))}
    </ol>
  );
}

function NightRow({ title, meta, tracks }: { title: string; meta: string; tracks: AlbumTrack[] }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  const queue = tracks.map(albumTrack).filter((track): track is PlayerTrack => track !== null);
  const count = `${tracks.length} ${tracks.length === 1 ? "track" : "tracks"}`;
  return (
    <li className={`night-row${open ? " open" : ""}`}>
      <div className="collapsed-head">
        <div className="collapsed-text">
          <p className="collapsed-title">{title}</p>
          <p className="collapsed-meta">{[meta, count].filter(Boolean).join(" · ")}</p>
        </div>
        <div className="collapsed-actions">
          {queue.length > 0 && <CardPlayButton play={{ start: queue[0], queue }} label={`Play ${title}`} />}
          <button type="button" className="collapsed-toggle" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((value) => !value)}>
            {open ? "Less" : "Tracks"}
            <span className="visually-hidden"> on {title}</span>
          </button>
        </div>
      </div>
      <div id={bodyId} className="night-tracks" hidden={!open}>
        {open && <TrackItems tracks={tracks} queue={queue} />}
      </div>
    </li>
  );
}

// The tracklist of a multi-show live record: one row per night, each opening
// to its tracks, with a play for the night's tape.
export function NightList({ groups }: { groups: { nights: Night[]; other: AlbumTrack[] } }) {
  return (
    <ul className="night-list">
      {groups.nights.map((night) => (
        <NightRow key={night.key} title={nightDate(night.date)} meta={[night.venue, night.city].filter(Boolean).join(", ")} tracks={night.tracks} />
      ))}
      {groups.other.length > 0 && <NightRow key="other" title="Other tracks" meta="" tracks={groups.other} />}
    </ul>
  );
}
