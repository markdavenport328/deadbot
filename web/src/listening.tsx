// Listening primitives: the page's listening hero, the pulled line, the card
// play button and quiet listen links, the "More" expander for long model
// prose, and the rosette background. Gold means "hear this": every gold mark
// in this file is a control that plays or leads to a recording.
import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import type { ExperienceBlock } from "./types";
import { usePlayer, type PlayerTrack } from "./player";
import warmRosette from "./assets/rosette-warm.svg";
import coolRosette from "./assets/rosette-cool.svg";

type ListenAction = { label: string; url: string; provider: string; is_official?: boolean };
type PlayableTrack = { performance_id: string; title: string; audio_url: string; duration_seconds?: number | null; set_label?: string | null };
type ListeningHeroBlock = Extract<ExperienceBlock, { type: "listening_hero" }>;
type PullQuoteBlock = Extract<ExperienceBlock, { type: "pull_quote" }>;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function longDate(iso?: string | null): string | null {
  if (!iso) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return /^\d{4}/.test(iso) ? iso.slice(0, 4) : iso;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${month} ${Number(match[3])}, ${match[1]}` : iso;
}

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

function isArchivePage(url: string): boolean {
  return hostOf(url) === "archive.org" && !archiveTrack(url);
}

export function archiveThumbnail(identifier?: string | null): string | null {
  return identifier ? `https://archive.org/services/img/${identifier}` : null;
}

export type TrackMeta = { showDate?: string | null; venueName?: string | null; recordingDetailsUrl?: string | null; thumbnailUrl?: string | null };

export function toTrack(track: PlayableTrack, meta: TrackMeta): PlayerTrack {
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

// What an action plays in-page, when it can: a track URL plays that track
// (continuing through the show when the card carries its tape), and a
// recording page plays the card's queue from the top.
export type InPagePlay = { start: PlayerTrack; queue: PlayerTrack[] };

export function inPagePlay(
  action: ListenAction,
  queue: PlayerTrack[],
  standalone?: (url: string) => PlayerTrack | null
): InPagePlay | null {
  if (action.is_official) return null;
  if (archiveTrack(action.url)) {
    const index = queue.findIndex((track) => track.audioUrl === action.url);
    if (index >= 0) return { start: queue[index], queue };
    const track = standalone?.(action.url) ?? null;
    return track ? { start: track, queue: [track] } : null;
  }
  if (isArchivePage(action.url) && queue.length > 0) return { start: queue[0], queue };
  return null;
}

function PlayGlyph({ playing }: { playing: boolean }) {
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
// starts, pauses, resumes or retries it.
function usePlayControl(play: InPagePlay | null, scope: "start" | "queue") {
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
  return { mine, playing, loading, onClick };
}

// The one primary listen control on a card: a round gold button in the card's
// header, beside the title. The action's own label is its accessible name.
export function CardPlayButton({ play, label }: { play: InPagePlay; label: string }) {
  const control = usePlayControl(play, "start");
  return (
    <button
      type="button"
      className={`card-play${control.mine ? " current" : ""}`}
      aria-label={control.playing ? `Pause: ${label}` : label}
      title={label}
      aria-pressed={control.mine}
      aria-busy={control.loading}
      onClick={control.onClick}
    >
      <PlayGlyph playing={control.playing} />
    </button>
  );
}

function QuietPlay({ play, label }: { play: InPagePlay; label: string }) {
  const control = usePlayControl(play, "queue");
  return (
    <button type="button" className="listen-link" aria-pressed={control.mine} aria-busy={control.loading} onClick={control.onClick}>
      {label}
    </button>
  );
}

function destination(url: string): string {
  return hostOf(url) || "the recording site";
}

// Every listen action but the header's play, as quiet text in one line. When
// nothing on the card plays in-page, the first action leads with the small
// gold play mark: it is still the card's one way to hear it.
export function ListenLinks({ actions, plays, leadsListening }: { actions: ListenAction[]; plays: (InPagePlay | null)[]; leadsListening: boolean }) {
  if (actions.length === 0) return null;
  return (
    <ul className="listen-links" aria-label="Listen">
      {actions.map((action, index) => {
        const play = plays[index];
        const lead = leadsListening && index === 0;
        return (
          <li key={action.url}>
            {play ? (
              <QuietPlay play={play} label={action.label} />
            ) : (
              <a
                className={`listen-link${lead ? " lead" : ""}`}
                href={action.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`${action.label} on ${destination(action.url)} (opens in a new tab)`}
                title={`Opens ${destination(action.url)} in a new tab`}
              >
                {lead && <span className="play-mark" aria-hidden="true">▶</span>}
                {action.label}
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// Split a card's listen actions into its one header play (the first action
// that plays in-page) and the rest, kept in their given order.
export function splitListen(actions: ListenAction[], queue: PlayerTrack[], standalone?: (url: string) => PlayerTrack | null) {
  const plays = actions.map((action) => inPagePlay(action, queue, standalone));
  const primaryIndex = plays.findIndex((play) => play !== null);
  const primary = primaryIndex >= 0 ? { action: actions[primaryIndex], play: plays[primaryIndex] as InPagePlay } : null;
  const restActions = actions.filter((_, index) => index !== primaryIndex);
  const restPlays = plays.filter((_, index) => index !== primaryIndex);
  return { primary, restActions, restPlays };
}

// Model prose clamped to about three lines, with a More toggle only when the
// rendered text overflows. The full text stays in the DOM; the toggle belongs
// to this block alone.
export function ClampText({ className, children }: { className?: string; children: ReactNode }) {
  const id = useId();
  const ref = useRef<HTMLParagraphElement | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || expanded) return;
    const measure = () => setOverflows(element.scrollHeight > element.clientHeight + 1);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [expanded]);
  return (
    <div className="clamp-block">
      <p id={id} ref={ref} className={`${className ?? ""}${expanded ? "" : " clamped"}`.trim()}>
        {children}
      </p>
      {(overflows || expanded) && (
        <button type="button" className="more-toggle" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Less" : "More"}
        </button>
      )}
    </div>
  );
}

function splitVenue(venue?: string | null): { name: string | null; rest: string | null } {
  if (!venue) return { name: null, rest: null };
  const comma = venue.indexOf(", ");
  return comma > 0 ? { name: venue.slice(0, comma), rest: venue.slice(comma + 2) } : { name: venue, rest: null };
}

// The page's lead when the answer is best heard. A show is named by its venue
// and date together: the venue set heavy, the date light beneath it, the
// place on the small line above. One gold Play starts the queue; at most one
// quiet link sits beside it.
export function ListeningHero({ block }: { block: ListeningHeroBlock }) {
  const [imageFailed, setImageFailed] = useState(false);
  const isShow = Boolean(block.show_id);
  const venue = splitVenue(block.venue_name);
  const date = longDate(isShow ? block.show_date : block.release_date);
  const name = isShow ? venue.name ?? date ?? "This show" : block.release_title ?? "This record";
  const kicker = isShow ? [venue.rest, block.location].filter(Boolean).join(" · ") : "Official release";
  const fallbackImage = archiveThumbnail(block.recording_identifier);
  const image = imageFailed ? (fallbackImage !== block.image_url ? fallbackImage : null) : block.image_url;
  const meta: TrackMeta = {
    showDate: block.show_date,
    venueName: venue.name ?? block.venue_name,
    recordingDetailsUrl: block.recording_details_url,
    thumbnailUrl: image ?? fallbackImage
  };
  const queue = (block.queue ?? []).map((track) => toTrack(track, meta));
  const start = queue[Math.min(block.start_index ?? 0, Math.max(queue.length - 1, 0))];
  const play = start ? { start, queue } : null;
  const control = usePlayControl(play, "queue");
  const label = block.play_label?.trim() || "Play";
  const heard = [name, date].filter(Boolean).join(", ");

  return (
    <section className="listening-hero" aria-label={`Listen: ${heard}`}>
      {image ? (
        <img className="hero-cover" src={image} alt={block.image_alt ?? ""} onError={() => setImageFailed(true)} />
      ) : (
        <div className="hero-cover placeholder" aria-hidden="true" />
      )}
      <div className="hero-body">
        {kicker && <p className="hero-kicker">{kicker}</p>}
        <p className="hero-name">
          <span className="hero-name-main">{name}</span>
          {date && name !== date && <span className="hero-name-date">{date}</span>}
        </p>
        {block.line && <p className="hero-line">{block.line}</p>}
        <div className="hero-actions">
          {play ? (
            <button
              type="button"
              className="hero-play"
              aria-label={control.playing ? `Pause: ${label}` : undefined}
              aria-pressed={control.mine}
              aria-busy={control.loading}
              onClick={control.onClick}
            >
              <PlayGlyph playing={control.playing} />
              <span>{label}</span>
            </button>
          ) : block.play_url ? (
            <a
              className="hero-play"
              href={block.play_url}
              target="_blank"
              rel="noreferrer"
              aria-label={`${label} on ${destination(block.play_url)} (opens in a new tab)`}
            >
              <PlayGlyph playing={false} />
              <span>{label}</span>
            </a>
          ) : null}
          {block.link && (
            <a className="hero-link" href={block.link.url} target="_blank" rel="noreferrer">
              {block.link.label}
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

// One sentence of the model's, set large: Fraunces italic in cream, with a
// rose opening mark hanging in the margin.
export function PullQuote({ block }: { block: PullQuoteBlock }) {
  return (
    <figure className="pull-quote">
      <span className="pull-mark" aria-hidden="true">“</span>
      <blockquote>{block.text}</blockquote>
    </figure>
  );
}

// Two tie-dye rosettes fixed behind everything: the warm one centred on the
// viewport's top-right corner, the cool one on its bottom-left.
export function Rosettes() {
  return (
    <div className="rosettes" aria-hidden="true">
      <img className="rosette rosette-warm" src={warmRosette} alt="" />
      <img className="rosette rosette-cool" src={coolRosette} alt="" />
    </div>
  );
}
