import { type ReactNode, useId, useState } from "react";
import { type ExperienceBlock } from "../../types";
import { type FollowUp } from "../../core/ask-request";
import { formatClockTime, type PlayerTrack } from "../../player/player";
import { SpotifyPanelEmbed, SpotifyTextButton, useSpotifyPanel } from "../spotify-embed";
import { CardPlayButton, toTrack, type InPagePlay } from "../listening";
import { ListenControl, archiveTrack, trackFor, type TrackMeta } from "../listen-control";
import { formatShowDate, formatShowDateLong, formatReleaseType, countLabel } from "../../core/format";
import { renderInline } from "../inline";
import { type ShowMeta, toPlayerTrack, venueFirstShowLabel } from "../parts";
import { type UnitBlock, albumSpotify, RowSpotifyContext, albumQueue, isUnit, splitShowLabel, songName, unitKey } from "./shared";

// A mention's name, and what hearing it means: the unit's own tracks when the
// block carries them, otherwise its first listen link.
function unitIdentity(block: UnitBlock): { title: string; url?: string | null; track?: PlayerTrack | null; queue?: PlayerTrack[] } {
  switch (block.type) {
    case "show_unit": {
      const meta: ShowMeta = { showDate: block.show_date, venueName: block.venue_name, recordingDetailsUrl: block.recording_details_url };
      const queue = block.sets.flatMap((set) => set.songs.map((song) => toPlayerTrack(song, meta)).filter((track): track is PlayerTrack => track !== null));
      return { title: block.venue_name ? `${block.venue_name} (${formatShowDate(block.show_date)})` : formatShowDate(block.show_date), url: block.listen[0]?.url, queue };
    }
    case "performance_unit": {
      const meta: TrackMeta = { showDate: block.show_date, venueName: block.venue_name };
      const url = block.listen[0]?.url;
      const queue = (block.show_tracks ?? []).map((track) => toTrack(track, meta));
      const track = url && archiveTrack(url) && !block.listen[0]?.is_official
        ? queue.find((item) => item.audioUrl === url) ?? toTrack({ performance_id: block.performance_id, title: block.song_title, audio_url: url }, meta)
        : null;
      return { title: `${block.song_title}, ${venueFirstShowLabel(block.show_date, block.venue_name, block.show_label)}`, url, track, queue };
    }
    case "album_unit":
      return { title: block.release_date ? `${block.title} (${block.release_date.slice(0, 4)})` : block.title, url: block.listen[0]?.url };
    case "song_overview": {
      // The first stop the library placed; a stop with only the model's words has no recording.
      const first = block.representative_performances.find((stop) => stop.show_id);
      const track = first ? trackFor(first, songName(block), { showDate: first.show_date, venueName: first.venue_name ?? splitShowLabel(first.show_label).venue }) : null;
      return { title: block.title, url: first?.listen_url, track };
    }
  }
}

// A mention is one line: the object, the model's note, a way to hear it.
export function MentionRow({ block }: { block: UnitBlock }) {
  const identity = unitIdentity(block);
  return (
    <li className={`mention emphasis-mention ${block.type}`}>
      <ListenControl url={identity.url} label={identity.title} track={identity.track} queue={identity.queue} scope={identity.track ? "start" : "queue"} className="list-item-label" />
      {block.note && <span className="mention-note">{renderInline(block.note)}</span>}
    </li>
  );
}

// Units are keyed by identity, so a block that streamed in stays the same
// element when the final response replaces the draft; other blocks and mention
// lists are keyed by position. A repeated identity gets a numbered suffix.
export function chunkMentions(blocks: (ExperienceBlock | undefined)[]) {
  const out: Array<
    | { kind: "mentions"; key: string; blocks: UnitBlock[] }
    | { kind: "collapsed"; key: string; blocks: UnitBlock[] }
    | { kind: "block"; key: string; block: ExperienceBlock }
  > = [];
  const seen = new Map<string, number>();
  const uniqueKey = (base: string) => {
    const times = seen.get(base) ?? 0;
    seen.set(base, times + 1);
    return times === 0 ? base : `${base}-${times}`;
  };
  for (const block of blocks) {
    if (!block) continue;
    if (isUnit(block) && block.disclosure === "collapsed") {
      // Consecutive collapsed cards read as one list, one row each, down the page.
      const last = out[out.length - 1];
      if (last && last.kind === "collapsed") last.blocks.push(block);
      else out.push({ kind: "collapsed", key: uniqueKey(`collapsed-${out.length}`), blocks: [block] });
    } else if (isUnit(block) && block.emphasis === "mention") {
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

// What a collapsed card's row shows, all of it from the library: the record's
// name, one line of key facts, a cover for a record, and the one thing it
// plays in-page, when it plays.
function collapsedFacts(block: UnitBlock): {
  title: string;
  meta: (string | null | undefined)[];
  cover?: string | null;
  play: InPagePlay | null;
  // Where to hear it when nothing plays in-page: a streaming album.
  link?: { url: string; label: string } | null;
  // The streaming album as an embedded player, when the record has one.
  embedId?: string | null;
} {
  const playOf = (queue: PlayerTrack[]): InPagePlay | null => (queue.length > 0 ? { start: queue[0], queue } : null);
  switch (block.type) {
    case "show_unit": {
      const meta: TrackMeta = { showDate: block.show_date, venueName: block.venue_name };
      const own = (block.tracks ?? []).map((track) => toTrack(track, meta));
      // A row whose data came with a setlist plays that tape when it has none of its own.
      const queue = own.length > 0
        ? own
        : block.sets.flatMap((set) => set.songs.map((song) => toPlayerTrack(song, { showDate: block.show_date, venueName: block.venue_name, recordingDetailsUrl: block.recording_details_url })).filter((track): track is PlayerTrack => track !== null));
      return { title: block.venue_name || formatShowDateLong(block.show_date), meta: [block.venue_name ? formatShowDateLong(block.show_date) : null, block.location], play: playOf(queue) };
    }
    case "album_unit": {
      const year = block.release_date?.slice(0, 4);
      const shows = block.show_count === 1
        ? [block.show_venue_name, formatShowDateLong(block.first_show_date)].filter(Boolean).join(", ")
        : block.show_count > 1
          ? `${countLabel(block.show_count, "show")}, ${formatShowDate(block.first_show_date)}–${formatShowDate(block.last_show_date)}`
          : null;
      const queue = albumQueue(block);
      return {
        title: block.release_title?.trim() || block.title,
        meta: [year, formatReleaseType(block.release_type), shows],
        cover: block.cover_url,
        play: playOf(queue),
        link: queue.length === 0 ? block.listen[0] ?? null : null,
        embedId: albumSpotify(block)?.embedId ?? null
      };
    }
    case "performance_unit": {
      const track = block.audio_url
        ? toTrack({ performance_id: block.performance_id, title: block.song_title, audio_url: block.audio_url, duration_seconds: block.duration_seconds }, { showDate: block.show_date, venueName: block.venue_name })
        : null;
      return {
        title: block.song_title,
        meta: [block.venue_name, formatShowDateLong(block.show_date), block.duration_seconds ? formatClockTime(block.duration_seconds) : null],
        play: track ? { start: track, queue: [track] } : null
      };
    }
    case "song_overview": {
      const span = block.first_year && block.last_year ? (block.first_year === block.last_year ? String(block.first_year) : `${block.first_year}–${block.last_year}`) : null;
      return { title: block.title, meta: [countLabel(block.known_performance_count, "performance"), span], play: null };
    }
  }
}

// A collapsed card: one row of key facts with its play control, and a quiet
// control that opens the full card in place beneath the row.
export function CollapsedRow({ block, onFollowUp, children }: { block: UnitBlock; onFollowUp: FollowUp; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [coverFailed, setCoverFailed] = useState(false);
  const cardId = useId();
  const facts = collapsedFacts(block);
  const spotifyPanel = useSpotifyPanel();
  const metaLine = facts.meta.filter(Boolean).join(" · ");
  return (
    <li className={`collapsed-row ${block.type}${open ? " open" : ""}`}>
      <div className="collapsed-head">
        {block.type === "album_unit" && (
          facts.cover && !coverFailed
            ? <img className="collapsed-cover" src={facts.cover} alt="" loading="lazy" width={56} height={56} onError={() => setCoverFailed(true)} />
            : <span className="collapsed-cover placeholder" aria-hidden="true" />
        )}
        <div className="collapsed-text">
          {block.type === "album_unit" ? (
            <button type="button" className="collapsed-title ask-title" title={`Ask about ${facts.title}`} onClick={() => onFollowUp(`Tell me about ${facts.title}.`)}>
              {facts.title}
            </button>
          ) : (
            <p className="collapsed-title">{facts.title}</p>
          )}
          {metaLine && <p className="collapsed-meta">{metaLine}</p>}
          {block.note && <p className="collapsed-note">{renderInline(block.note)}</p>}
        </div>
        <div className="collapsed-actions">
          {facts.play ? (
            <CardPlayButton play={facts.play} label={`Play ${facts.title}`} />
          ) : facts.embedId ? (
            <SpotifyTextButton panel={spotifyPanel} label="Listen" name={`Listen to ${facts.title} on Spotify`} className="collapsed-listen" />
          ) : facts.link ? (
            <ListenControl url={facts.link.url} label={facts.title} className="collapsed-listen" queueable={false}>Listen</ListenControl>
          ) : null}
          <button type="button" className="collapsed-toggle" aria-expanded={open} aria-controls={cardId} onClick={() => setOpen((value) => !value)}>
            {open ? "Less" : "More"}
            <span className="visually-hidden"> about {facts.title}</span>
          </button>
        </div>
      </div>
      {facts.embedId && (
        <div className="collapsed-embed">
          <SpotifyPanelEmbed panel={spotifyPanel} embedId={facts.embedId} title={`${facts.title} on Spotify`} height={152} />
        </div>
      )}
      <div id={cardId} className="collapsed-card" hidden={!open}>
        <RowSpotifyContext.Provider value={facts.embedId ? spotifyPanel : null}>{open ? children : null}</RowSpotifyContext.Provider>
      </div>
    </li>
  );
}
