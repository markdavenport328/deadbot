// Listening primitives: the page's listening hero, the pulled line, the card
// play button and quiet listen links, the "More" expander for long model
// prose, and the rosette background. Gold means "plays here": every gold mark
// in this file is a control that plays in-page (see listen-control.tsx).
import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import type { ExperienceBlock } from "../types";
import type { PlayerTrack } from "../player/player";
import { AddToQueue, ListenControl, PlayGlyph, inPagePlay, toTrack, usePlayControl, type InPagePlay, type TrackMeta } from "./listen-control";
import { showTile } from "./show-tile";
import { Equalizer } from "../player/icons";
import warmRosette from "../assets/rosette-warm.svg";
import coolRosette from "../assets/rosette-cool.svg";

export { archiveTrack, inPagePlay, toTrack, type InPagePlay, type TrackMeta } from "./listen-control";

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

// A card's two round controls, as on WAMU: the gold play, then + beside it.
// Play starts what the card plays; while it plays it shows an equalizer, and
// pause on hover or focus. + adds the same tracks to the end of the queue
// without interrupting, and turns to a check once they are in. The action's
// own label is the play's accessible name. Hovering or focusing either
// names what it does: play starts now in place of the queue, + adds to it.
// "tracks" is what + adds when it differs from the play's queue (a hero that
// starts partway through a tape adds from that track on); "large" is the
// hero's size.
export function CardPlayButton({ play, label, tracks, large = false, scope = "start" }: { play: InPagePlay; label: string; tracks?: PlayerTrack[]; large?: boolean; scope?: "start" | "queue" }) {
  const control = usePlayControl(play, scope);
  const what = label.replace(/^Play\s+/i, "");
  return (
    <span className={`card-controls${large ? " large" : ""}`}>
      <button
        type="button"
        className={`card-play${control.mine ? " current" : ""}${control.playing ? " playing" : ""}`}
        data-playable="in-page"
        aria-label={control.errored ? `Retry: ${label}` : control.playing ? `Pause: ${label}` : label}
        data-tip={control.errored ? "Try again" : control.playing ? "Pause" : control.mine ? "Resume" : "Play now, replacing the queue"}
        aria-pressed={control.mine}
        aria-busy={control.loading}
        onClick={control.onClick}
      >
        {control.playing ? (
          <>
            <Equalizer playing />
            <span className="card-play-pause"><PlayGlyph playing /></span>
          </>
        ) : (
          <PlayGlyph playing={false} />
        )}
      </button>
      <AddToQueue tracks={tracks ?? (play.queue.length > 0 ? play.queue : [play.start])} name={what} variant="round" />
    </span>
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
// quiet link sits beside it. Its picture is the real cover when the response
// has one, and otherwise the show's tile; a cover that fails to load gives
// way to the tile.
export function ListeningHero({ block }: { block: ListeningHeroBlock }) {
  const [failed, setFailed] = useState<string[]>([]);
  const isShow = Boolean(block.show_id);
  const venue = splitVenue(block.venue_name);
  const date = longDate(isShow ? block.show_date : block.release_date);
  const name = isShow ? venue.name ?? date ?? "This show" : block.release_title ?? "This record";
  const kicker = isShow ? [venue.rest, block.location].filter(Boolean).join(" · ") : "Official release";
  const tile = showTile(isShow ? block.show_date : block.release_date, block.recording_identifier ?? block.release_title ?? block.venue_name);
  const cover = block.image_url && !failed.includes(block.image_url) ? block.image_url : null;
  const image = cover ?? (failed.includes(tile) ? null : tile);
  const meta: TrackMeta = {
    showDate: block.show_date,
    venueName: venue.name ?? block.venue_name,
    recordingDetailsUrl: block.recording_details_url,
    thumbnailUrl: cover
  };
  const queue = (block.queue ?? []).map((track) => toTrack(track, meta));
  const start = queue[Math.min(block.start_index ?? 0, Math.max(queue.length - 1, 0))];
  const play = start ? { start, queue } : null;
  const label = block.play_label?.trim() || `Play ${name}`;
  const heard = [name, date].filter(Boolean).join(", ");

  return (
    <section className="listening-hero" aria-label={`Listen: ${heard}`}>
      {image ? (
        <img className={cover ? "hero-cover" : "hero-cover tile"} src={image} alt={cover ? block.image_alt ?? "" : ""} onError={() => setFailed((gone) => [...gone, image])} />
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
            <>
              <CardPlayButton play={play} label={label} tracks={queue.slice(queue.indexOf(play.start))} large scope="queue" />
              <span className="hero-play-label" aria-hidden="true">{label}</span>
            </>
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
