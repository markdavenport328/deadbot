import { type RefObject, useEffect, useId, useRef, useState } from "react";
import { PLAYBACK_RATES, usePlayer, formatClockTime, formatSeekValueText } from "./player";
import { formatShowDate } from "../core/format";
import { PlayPauseIcon, StepIcon, ChevronIcon, QueueIcon, MoreIcon, LoopIcon } from "./icons";
import { QueuePanel, focusQueueRail } from "./QueuePanel";

// The one shared now-playing bar for the whole app: hidden until something
// has played, then held at the bottom of the screen within the answer pane
// (never over the left rail, since it renders inside .content-pane). A 44px
// round gold play/pause button and a real range-input scrubber with
// tabular-numeral elapsed/total time; the tapes themselves are credited in
// the page's sources footer. When more than one track is queued (a set, a
// path, a play-all), quiet back and next steps flank the gold button; each
// dims at its end of the queue rather than vanishing, so the bar holds
// still. A queue toggle beside them opens the queue above the bar (UpNext)
// and shows how many tracks are left. Queueing and position are the shared
// PlayerProvider's job.
// On a phone the bar lives in the bottom dock above the ask box and can fold
// to one slim row (cover, title, play) so the page keeps its room; the fold is
// remembered on the device, and the ask box folds it while the keyboard is up.
// Folding also closes the queue.
const COLLAPSED_PLAYER_KEY = "deadbot.player.collapsed";

function readCollapsedPlayer(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_PLAYER_KEY) === "1";
  } catch {
    return false;
  }
}

// Speed and loop, for learning a passage by ear: a "⋯" at the end of the
// scrubber opens them in the panel slot above the bar, where the queue opens.
// While the speed is not normal or a loop is set, the button says so in cream.
function formatRate(rate: number): string {
  return `${rate}×`;
}

function PracticeToggle({ open, panelId, onToggle, toggleRef }: { open: boolean; panelId: string; onToggle: () => void; toggleRef: RefObject<HTMLButtonElement | null> }) {
  const player = usePlayer();
  const changedRate = player.rate !== 1;
  const looping = player.loop.start != null && player.loop.end != null;
  const state = [changedRate ? formatRate(player.rate) : null, looping ? "looping" : null].filter(Boolean).join(", ");
  return (
    <button
      ref={toggleRef}
      type="button"
      className={`now-playing-more${open ? " open" : ""}${changedRate || looping ? " changed" : ""}`}
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={open ? panelId : undefined}
      aria-label={state ? `Speed and loop: ${state}` : "Speed and loop"}
      title="Speed and loop"
    >
      {changedRate && <span className="now-playing-more-rate">{formatRate(player.rate)}</span>}
      {looping && <LoopIcon />}
      <MoreIcon />
    </button>
  );
}

function PracticePanel({ id, onClose }: { id: string; onClose: () => void }) {
  const player = usePlayer();
  const { start, end } = player.loop;
  return (
    <div
      id={id}
      className="now-playing-queue now-playing-practice"
      role="region"
      aria-label="Speed and loop"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <div className="practice-row" role="group" aria-labelledby={`${id}-speed`}>
        <span className="practice-label" id={`${id}-speed`}>Speed</span>
        <span className="practice-choices">
          {PLAYBACK_RATES.map((rate) => (
            <button key={rate} type="button" className="practice-choice" aria-pressed={player.rate === rate} onClick={() => player.setRate(rate)}>
              {formatRate(rate)}
            </button>
          ))}
        </span>
      </div>
      <div className="practice-row" role="group" aria-labelledby={`${id}-loop`}>
        <span className="practice-label" id={`${id}-loop`}>Loop</span>
        <span className="practice-choices">
          <button type="button" className="practice-choice" aria-pressed={start != null} onClick={player.setLoopStart} aria-label={start != null ? `Loop start ${formatClockTime(start)}, set to now` : "Set loop start to now"}>
            {start != null ? `Start ${formatClockTime(start)}` : "Set start"}
          </button>
          <button type="button" className="practice-choice" aria-pressed={end != null} onClick={player.setLoopEnd} aria-label={end != null ? `Loop end ${formatClockTime(end)}, set to now` : "Set loop end to now"}>
            {end != null ? `End ${formatClockTime(end)}` : "Set end"}
          </button>
          {(start != null || end != null) && (
            <button type="button" className="practice-clear" onClick={player.clearLoop}>
              Clear
            </button>
          )}
        </span>
      </div>
    </div>
  );
}

// The loop on the scrubber: a band from start to end, or a tick at the start
// until the end is set.
function LoopBand({ duration }: { duration: number }) {
  const { start, end } = usePlayer().loop;
  if (start == null || !(duration > 0)) return null;
  const left = Math.min(start / duration, 1) * 100;
  const width = end != null ? Math.max(((end - start) / duration) * 100, 0.5) : 0;
  return <span className={`now-playing-loop${end == null ? " open-ended" : ""}`} style={{ left: `${left}%`, width: end != null ? `${width}%` : undefined }} aria-hidden="true" />;
}

// queueInRail means the queue has a place of its own on the page (the
// workspace's right rail): the queue button takes focus there instead of
// opening the panel above the bar.
export function NowPlayingBar({ collapsible = false, forceCollapsed = false, queueInRail = false }: { collapsible?: boolean; forceCollapsed?: boolean; queueInRail?: boolean } = {}) {
  const player = usePlayer();
  const [folded, setFolded] = useState(readCollapsedPlayer);
  const [queueOpen, setQueueOpen] = useState(false);
  const queueToggleRef = useRef<HTMLButtonElement | null>(null);
  const queueId = useId();
  const [practiceOpen, setPracticeOpen] = useState(false);
  const practiceToggleRef = useRef<HTMLButtonElement | null>(null);
  const practiceId = useId();
  const track = player.currentTrack;
  if (!track) return null;
  const collapsed = collapsible && (folded || forceCollapsed);
  function toggleFolded() {
    const next = !folded;
    setFolded(next);
    if (next) {
      setQueueOpen(false);
      setPracticeOpen(false);
    }
    try {
      window.localStorage.setItem(COLLAPSED_PLAYER_KEY, next ? "1" : "0");
    } catch {
      // Private browsing: the fold just lasts the visit.
    }
  }
  const isPlaying = player.status === "playing";
  const isLoading = player.status === "loading";
  const isError = player.status === "error";
  const duration = player.duration || track.durationSeconds || 0;
  const position = Math.min(player.position, duration || 0);
  const metaLine = [formatShowDate(track.showDate), track.venueName].filter(Boolean).join(" · ");
  const queued = player.queue.length > 1;
  const upcoming = Math.max(player.queue.length - player.queue.findIndex((item) => item.id === track.id) - 1, 0);
  // An open queue stays open after Clear, so its Undo stays in reach.
  const showQueue = queueOpen && !collapsed && !queueInRail;
  const showPractice = practiceOpen && !collapsed && !showQueue;
  const closeQueue = () => {
    setQueueOpen(false);
    queueToggleRef.current?.focus();
  };
  const closePractice = () => {
    setPracticeOpen(false);
    practiceToggleRef.current?.focus();
  };
  // The queue and the speed-and-loop panel share the slot above the bar.
  const barClassName = ["now-playing-bar", collapsible ? "collapsible" : null, collapsed ? "collapsed" : null, showQueue || showPractice ? "queue-open" : null].filter(Boolean).join(" ");
  return (
    <div className={barClassName} role="region" aria-label="Now playing">
      {showQueue && <QueuePanel id={queueId} variant="popover" onClose={closeQueue} />}
      {showPractice && <PracticePanel id={practiceId} onClose={closePractice} />}
      {track.thumbnailUrl ? (
        <img className="now-playing-thumb" src={track.thumbnailUrl} alt="" loading="lazy" />
      ) : (
        <div className="now-playing-thumb placeholder" aria-hidden="true" />
      )}
      <div className="now-playing-info" onClick={collapsible ? toggleFolded : undefined}>
        <p className="now-playing-title">{track.title}</p>
        {isError ? <p className="now-playing-error">Couldn’t play this track</p> : metaLine ? <p className="now-playing-meta">{metaLine}</p> : null}
      </div>
      <div className="now-playing-controls">
        {queued && !collapsed && (
          <button type="button" className="now-playing-step" onClick={player.previous} disabled={!player.hasPrevious} aria-label="Previous track">
            <StepIcon direction="previous" />
          </button>
        )}
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
        {queued && !collapsed && (
          <button type="button" className="now-playing-step" onClick={player.next} disabled={!player.hasNext} aria-label="Next track">
            <StepIcon direction="next" />
          </button>
        )}
        {(queued || showQueue) && !collapsed && (
          <button
            ref={queueToggleRef}
            type="button"
            className={`now-playing-queue-toggle${showQueue ? " open" : ""}`}
            onClick={() => {
              if (queueInRail) return focusQueueRail();
              setQueueOpen((open) => !open);
              setPracticeOpen(false);
            }}
            aria-expanded={queueInRail ? undefined : showQueue}
            aria-controls={showQueue ? queueId : undefined}
            aria-label={`Queue, ${upcoming === 1 ? "1 track" : `${upcoming} tracks`} up next`}
            title={queueInRail ? "Go to the queue" : showQueue ? "Hide queue" : "Show queue"}
          >
            <QueueIcon />
            <span className="now-playing-queue-count" aria-hidden="true">{upcoming}</span>
          </button>
        )}
      </div>
      {collapsible && (
        <button
          type="button"
          className="now-playing-fold"
          onClick={toggleFolded}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Show player controls" : "Hide player controls"}
        >
          <ChevronIcon up={collapsed} />
        </button>
      )}
      {!collapsed && (
      <div className="now-playing-scrubber">
        <span className="now-playing-time" aria-hidden="true">{formatClockTime(position)}</span>
        <span className="now-playing-range-wrap">
        <LoopBand duration={duration} />
        <input
          type="range"
          className="now-playing-range"
          min={0}
          max={duration || 0}
          step={1}
          value={position}
          aria-label={`Seek within ${track.title}`}
          aria-valuetext={formatSeekValueText(position, duration)}
          style={{ ["--progress" as string]: `${duration > 0 ? Math.min(100, (position / duration) * 100) : 0}%` }}
          onChange={(event) => player.seek(Number(event.target.value))}
        />
        </span>
        <span className="now-playing-time" aria-hidden="true">{formatClockTime(duration)}</span>
        <PracticeToggle
          open={showPractice}
          panelId={practiceId}
          toggleRef={practiceToggleRef}
          onToggle={() => {
            setPracticeOpen((open) => !open);
            setQueueOpen(false);
          }}
        />
      </div>
      )}
    </div>
  );
}
