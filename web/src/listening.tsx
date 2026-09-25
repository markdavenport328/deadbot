// Listening primitives: the page's listening hero, the pulled line, the card
// play button and quiet listen links, the "More" expander for long model
// prose, and the rosette background. Gold means "plays here": every gold mark
// in this file is a control that plays in-page (see listen-control.tsx).
import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import type { ExperienceBlock } from "./types";
import type { PlayerTrack } from "./player";
import { ListenControl, PlayGlyph, archiveThumbnail, inPagePlay, toTrack, usePlayControl, type InPagePlay, type TrackMeta } from "./listen-control";
import warmRosette from "./assets/rosette-warm.svg";
import coolRosette from "./assets/rosette-cool.svg";

export { archiveTrack, archiveThumbnail, inPagePlay, toTrack, type InPagePlay, type TrackMeta } from "./listen-control";

type ListenAction = { label: string; url: string; provider: string; is_official?: boolean };
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

// The one primary listen control on a card: a round gold button in the card's
// header, beside the title. The action's own label is its accessible name.
export function CardPlayButton({ play, label }: { play: InPagePlay; label: string }) {
  const control = usePlayControl(play, "start");
  return (
    <button
      type="button"
      className={`card-play${control.mine ? " current" : ""}`}
      data-playable="in-page"
      aria-label={control.errored ? `Retry: ${label}` : control.playing ? `Pause: ${label}` : label}
      title={label}
      aria-pressed={control.mine}
      aria-busy={control.loading}
      onClick={control.onClick}
    >
      <PlayGlyph playing={control.playing} />
    </button>
  );
}

// Every listen action but the header's play, as quiet text in one line: an
// action that plays in-page is a quiet play control; the rest leave the site.
export function ListenLinks({ actions, plays }: { actions: ListenAction[]; plays: (InPagePlay | null)[] }) {
  if (actions.length === 0) return null;
  return (
    <ul className="listen-links" aria-label="Listen">
      {actions.map((action, index) => (
        <li key={action.url}>
          <ListenControl url={action.url} label={action.label} play={plays[index] ?? undefined} scope="queue" />
        </li>
      ))}
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
              data-playable="in-page"
              aria-label={control.playing ? `Pause: ${label}` : undefined}
              aria-pressed={control.mine}
              aria-busy={control.loading}
              onClick={control.onClick}
            >
              <PlayGlyph playing={control.playing} />
              <span>{label}</span>
            </button>
          ) : block.play_url ? (
            <ListenControl url={block.play_url} label={label} className="hero-link" />
          ) : null}
          {block.link && <ListenControl url={block.link.url} label={block.link.label} className="hero-link" />}
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
