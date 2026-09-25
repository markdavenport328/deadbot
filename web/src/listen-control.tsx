// The one listen affordance. Every place the page offers a way to hear
// something renders it through ListenControl: given a URL and whatever track
// metadata the block carries, it plays in-page through the shared player when
// the URL is an Internet Archive track (or a recording whose tape the block
// queues), and otherwise renders a quiet external link carrying the model's
// label verbatim. Gold means "plays here": only the in-page control carries
// the gold mark. The choice is made from the URL's host and path and the
// block's data, never from the label's wording.
import { type ReactNode } from "react";
import { usePlayer, type PlayerTrack } from "./player";

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// Internet Archive URLs, told apart by host and path, never by the label.
// A /download/<item>/<file> URL is one audio file the browser can play; any
// other archive.org page (a /details/ item, a search) is a recording page.
export function archiveTrack(url: string): { identifier: string } | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname.replace(/^www\./, "") !== "archive.org") return null;
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts[0] !== "download" || parts.length < 3) return null;
    return /\.(mp3|ogg|m4a|flac|wav)$/i.test(parts[parts.length - 1]) ? { identifier: parts[1] } : null;
  } catch {
    return null;
  }
}

export function isArchivePage(url: string): boolean {
  return hostOf(url) === "archive.org" && !archiveTrack(url);
}

export function archiveThumbnail(identifier?: string | null): string | null {
  return identifier ? `https://archive.org/services/img/${identifier}` : null;
}

export function destination(url: string): string {
  return hostOf(url) || "the recording site";
}

export type TrackMeta = { showDate?: string | null; venueName?: string | null; recordingDetailsUrl?: string | null; thumbnailUrl?: string | null };

type PlayableTrackData = { performance_id: string; title: string; audio_url: string; duration_seconds?: number | null };

// A block's playable track as the shared player's track: the song title,
// with the show named by its venue and date for the now-playing bar.
export function toTrack(track: PlayableTrackData, meta: TrackMeta): PlayerTrack {
  const identifier = archiveTrack(track.audio_url)?.identifier;
  return {
    id: track.performance_id,
    title: track.title,
    audioUrl: track.audio_url,
    durationSeconds: track.duration_seconds ?? null,
    showDate: meta.showDate ?? null,
    venueName: meta.venueName ?? null,
    recordingDetailsUrl: meta.recordingDetailsUrl ?? (identifier ? `https://archive.org/details/${identifier}` : null),
    thumbnailUrl: meta.thumbnailUrl ?? archiveThumbnail(identifier)
  };
}

// A row's track when the block carries one: its own audio URL, or failing
// that a listen URL that is itself an archive track.
export function trackFor(
  item: { performance_id: string; audio_url?: string | null; duration_seconds?: number | null; listen_url?: string | null },
  title: string,
  meta: TrackMeta
): PlayerTrack | null {
  const audio = item.audio_url || (item.listen_url && archiveTrack(item.listen_url) ? item.listen_url : null);
  return audio ? toTrack({ performance_id: item.performance_id, title, audio_url: audio, duration_seconds: item.duration_seconds }, meta) : null;
}

// What a control plays in-page: a start track and the queue it plays through.
export type InPagePlay = { start: PlayerTrack; queue: PlayerTrack[] };

type ListenAction = { label: string; url: string; provider: string; is_official?: boolean };

// A card's listen action, played in-page when it can: a track URL plays that
// track (continuing through the show when the card carries its tape), and a
// recording page plays the card's queue from the top. An official release's
// link always leaves the site.
export function inPagePlay(
  action: ListenAction,
  queue: PlayerTrack[],
  standalone?: (url: string) => PlayerTrack | null
): InPagePlay | null {
  if (action.is_official) return null;
  if (archiveTrack(action.url)) {
    const index = queue.findIndex((track) => track.audioUrl === action.url);
    if (index >= 0) return { start: queue[index], queue };
    const track = standalone?.(action.url) ?? { id: action.url, title: action.label, audioUrl: action.url };
    return { start: track, queue: [track] };
  }
  if (isArchivePage(action.url) && queue.length > 0) return { start: queue[0], queue };
  return null;
}

// Resolve what one control plays from its URL, its track and its queue.
function resolvePlay(url: string | null | undefined, label: string, track: PlayerTrack | null | undefined, queue: PlayerTrack[] | undefined): InPagePlay | null {
  const list = queue ?? [];
  if (track) {
    return { start: track, queue: list.some((item) => item.id === track.id) ? list : [track] };
  }
  if (url && archiveTrack(url)) {
    const queued = list.find((item) => item.audioUrl === url);
    if (queued) return { start: queued, queue: list };
    const standalone: PlayerTrack = { id: url, title: label, audioUrl: url, recordingDetailsUrl: `https://archive.org/details/${archiveTrack(url)?.identifier}`, thumbnailUrl: archiveThumbnail(archiveTrack(url)?.identifier) };
    return { start: standalone, queue: [standalone] };
  }
  if (url && isArchivePage(url) && list.length > 0) return { start: list[0], queue: list };
  if (!url && list.length > 0) return { start: list[0], queue: list };
  return null;
}

export function PlayGlyph({ playing }: { playing: boolean }) {
  return playing ? (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="6" y="5" width="4.5" height="14" fill="currentColor" />
      <rect x="13.5" y="5" width="4.5" height="14" fill="currentColor" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M7 4.5v15l12-7.5z" />
    </svg>
  );
}

// The shared player's state for one in-page play, and the click that
// starts, pauses, resumes or retries it. "start" is current only while its
// own track plays; "queue" is current while any track of its queue plays.
export function usePlayControl(play: InPagePlay | null, scope: "start" | "queue") {
  const player = usePlayer();
  const current = player.currentTrack;
  const mine = Boolean(
    play && current && (scope === "start" ? current.id === play.start.id && current.audioUrl === play.start.audioUrl : play.queue.some((track) => track.id === current.id))
  );
  const playing = mine && player.status === "playing";
  const loading = mine && player.status === "loading";
  const errored = mine && player.status === "error";
  function onClick() {
    if (!play || loading) return;
    if (playing) player.pause();
    else if (errored) player.retry();
    else if (mine) player.toggle();
    else player.play(play.start, play.queue);
  }
  return { mine, playing, loading, errored, onClick };
}

type ListenControlProps = {
  // Where the listen link points, when the block has one.
  url?: string | null;
  // The visible words, verbatim: the model's label or the library's name.
  label: string;
  // Richer display for the same words (emphasis in model prose); defaults to label.
  children?: ReactNode;
  // What plays in-page, when the block carries its track or its tape.
  track?: PlayerTrack | null;
  queue?: PlayerTrack[];
  // A precomputed play (a card's listen action), used as given.
  play?: InPagePlay | null;
  // A whole-queue control is current while any of its tracks plays.
  scope?: "start" | "queue";
  // The accessible name for the play, when the label alone does not say
  // what plays (a venue name on a history row).
  name?: string;
  // Another control on the same row already plays this; show the words only.
  playsElsewhere?: boolean;
  className?: string;
};

// Plays in-page when it can; otherwise a quiet external link; otherwise text.
export function ListenControl({ url, label, children, track, queue, play: given, scope = "start", name, playsElsewhere, className }: ListenControlProps) {
  const play = given !== undefined ? given : resolvePlay(url, label, track, queue);
  if (play && playsElsewhere) return <span className={className}>{children ?? label}</span>;
  if (play) return <InPageListen play={play} label={label} name={name} scope={scope} className={className}>{children}</InPageListen>;
  if (url) {
    return (
      <a
        className={`listen-link${className ? ` ${className}` : ""}`}
        href={url}
        target="_blank"
        rel="noreferrer"
        aria-label={`${label} on ${destination(url)} (opens in a new tab)`}
        title={`Opens ${destination(url)} in a new tab`}
      >
        {children ?? label}
      </a>
    );
  }
  return <span className={className}>{children ?? label}</span>;
}

function InPageListen({ play, label, name, scope, className, children }: { play: InPagePlay; label: string; name?: string; scope: "start" | "queue"; className?: string; children?: ReactNode }) {
  const control = usePlayControl(play, scope);
  const base = name ?? label;
  const accessibleName = control.errored ? `Retry ${base}` : control.playing ? `Pause ${base}` : control.loading ? `Loading ${base}` : name ? `Play ${base}` : undefined;
  const state = control.errored ? " errored" : control.loading ? " loading" : control.playing ? " playing" : "";
  return (
    <button
      type="button"
      className={`listen-play${control.mine ? " current" : ""}${state}${className ? ` ${className}` : ""}`}
      data-playable="in-page"
      aria-label={accessibleName}
      aria-pressed={control.mine}
      aria-busy={control.loading}
      title={control.errored ? "Couldn’t play this track. Try again." : undefined}
      onClick={control.onClick}
    >
      <span className="listen-play-mark" aria-hidden="true">
        <PlayGlyph playing={control.playing} />
      </span>
      <span className="listen-play-label">{children ?? label}</span>
      {control.errored && <span className="listen-play-error" aria-hidden="true">Couldn’t play · retry</span>}
    </button>
  );
}
