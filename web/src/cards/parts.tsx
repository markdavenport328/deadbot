import { type ReactNode } from "react";
import { type AlbumUnitBlock, type ExperienceBlock, type ShowUnitBlock } from "../types";
import { type PlayerTrack } from "../player/player";
import { CardSpotifyButton, SpotifyEmbed, type SpotifyPanel } from "./spotify-embed";
import { CardPlayButton, ListenLinks, type InPagePlay } from "./listening";
import { NightList, albumTrack, groupByNight } from "./AlbumNights";
import { ListenControl } from "./listen-control";
import { formatShowDate } from "../core/format";
import { ExternalLink } from "./inline";

export type SetlistSections = ShowUnitBlock["sets"];

export type SetlistSongType = SetlistSections[number]["songs"][number];

type ListenActions = ShowUnitBlock["listen"];

type UnitSources = ShowUnitBlock["sources"];

// The show-level facts a setlist row or a recording's listen action needs to
// build a PlayerTrack: date/venue for the now-playing bar's meta line, and
// the one Internet Archive item behind this show's tracks (once per show,
// not repeated per song) for the tape link and thumbnail.
export type ShowMeta = {
  showDate?: string | null;
  venueName?: string | null;
  recordingDetailsUrl?: string | null;
  thumbnailUrl?: string | null;
};

export function thumbnailForIdentifier(identifier?: string | null): string | null {
  return identifier ? `https://archive.org/services/img/${identifier}` : null;
}

export function toPlayerTrack(song: SetlistSongType, meta: ShowMeta): PlayerTrack | null {
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

export function venueFirstShowLabel(showDate?: string | null, venueName?: string | null, existingLabel?: string | null): string {
  const date = formatShowDate(showDate);
  const venue = venueName || existingLabel?.replace(/^\d{4}-\d{2}-\d{2} — /, "") || "";
  if (venue && date) return `${venue} (${date})`;
  return venue || date || existingLabel || "Unknown show";
}

export function MediaEmbed({ block }: { block: Extract<ExperienceBlock, { type: "media_link" }> }) {
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
    return <SpotifyEmbed embedId={block.embed_id} title={block.title} height={152} />;
  }
  return null;
}

// Listen actions on a card that has no in-page play of its own (a record, a
// media link): quiet text links, or a quiet play when an action is itself an
// archive track.
export function ListenActionList({ actions }: { actions: ListenActions }) {
  return <ListenLinks actions={actions} plays={actions.map(() => null)} />;
}

// A card's header: its one in-page play, round and gold, beside the title and
// identity line. Without an in-page play the header is the title alone.
// "tracks" is what the + adds when it differs from what play continues
// through (a performance adds its own song, not the rest of its show).
export function CardHead({ primary, spotify, children }: { primary: { play: InPagePlay; label: string; tracks?: PlayerTrack[] } | null; spotify?: { panel: SpotifyPanel; label: string } | null; children: ReactNode }) {
  if (!primary && !spotify) return <>{children}</>;
  return (
    <div className="card-head">
      {primary ? <CardPlayButton play={primary.play} label={primary.label} tracks={primary.tracks} /> : spotify ? <CardSpotifyButton panel={spotify.panel} label={spotify.label} /> : null}
      <div className="card-head-text">{children}</div>
    </div>
  );
}

// "Listen for" is a sentence, not a labeled row: cream links in muted body
// text, shown whenever a unit has highlighted songs or tracks.
type ListenItem = { key: string; title: string; url?: string | null; track?: PlayerTrack | null };

export function ListenFor({ items: allItems, queue }: { items: ListenItem[]; queue?: PlayerTrack[] }) {
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
          <ListenControl url={item.url} label={item.title} track={item.track} queue={queue} queueable={false} />
        </span>
      ))}
    </p>
  );
}

// One header row per card: the type on the left, a tabular-numeral fact on
// the right. Both are the same small-caps label style.
export function IdRow({ type, when }: { type: ReactNode; when?: ReactNode }) {
  return (
    <div className="id-row">
      <span className="k type">{type}</span>
      {when ? <span className="k when">{when}</span> : null}
    </div>
  );
}

// The meta line under a card's h2: parts joined by a quiet middot, blank
// parts dropped so a card missing one fact doesn't leave a stray separator.
export function Meta({ parts }: { parts: ReactNode[] }) {
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
// credits inside the drawer. A recording whose tape the card carries plays
// in-page; any other title links out when a url is given.
export function PlainList({ items }: { items: { key: string; title: string; url?: string | null; queue?: PlayerTrack[]; detail?: string | null }[] }) {
  return (
    <ul className="plain">
      {items.map((item) => (
        <li key={item.key}>
          <ListenControl url={item.url} label={item.title} queue={item.queue} scope="queue" className="plain-title" />
          {item.detail ? <span>{item.detail}</span> : null}
        </li>
      ))}
    </ul>
  );
}

// A "Name · instruments" grid, used for lineups and album personnel.
export function PeopleList({ people }: { people: { key: string; name: string; detail: string; guest?: boolean }[] }) {
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

// The album tracklist: the same numbered-link styling as the setlist, one
// column, no set grouping. A track whose performance has a tape plays in-page
// and continues through the record's other playable tracks.
export function TrackList({ tracks }: { tracks: AlbumUnitBlock["tracks"] }) {
  const nights = groupByNight(tracks);
  if (nights) return <NightList groups={nights} />;
  const playable = tracks.map(albumTrack);
  const queue = playable.filter((track): track is PlayerTrack => track !== null);
  return (
    <ol className="song-list">
      {tracks.map((track, index) => (
        <li key={track.track_number} value={track.track_number} className={track.highlighted ? "hi" : undefined}>
          <ListenControl url={track.listen_url} label={track.title} track={playable[index]} queue={queue} />
        </li>
      ))}
    </ol>
  );
}

// The "Go deeper" footer block: each source's title set in the serif as a
// cited headline, with publication and note sharing one muted line beneath.
export function GoDeeper({ sources }: { sources: UnitSources }) {
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
