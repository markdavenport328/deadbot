import { useEffect, useId, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode, type RefObject } from "react";
import { formatClockTime, trackFiles, usePlayer, type PlayerTrack } from "./player";
import { formatShowDate, formatShowDateLong } from "../core/format";
import { Equalizer, MoreIcon, QueueIcon } from "./icons";
import { PanelToggle, useRememberedOpen } from "../core/side-panel";
import { estimateBytes, formatBytes, lastSaveFailures, offlineSupported, removeTracks, saveTracks, useOffline } from "./offline";

// The queue: what is playing, then what plays next, then what has already
// played. A row's title plays it; its grip drags it to a new place (or moves
// it with the arrow keys); its ⋯ menu holds every other action, including
// Details, which opens the row in place to the song's show and recording. A
// run of tracks from one show names the show once, at its first track, so a
// tape reads as one night. Clear on the Up next line empties it and Clear
// on the Played line empties what has played; each keeps the playing track and
// offers Undo for ten seconds. Each change is announced.
//
// The same panel serves as the workspace's right rail ("rail"), and as the
// panel the bar opens above itself on phones and narrow desktops ("popover").

const UNDO_SECONDS = 10;

export function formatListeningTime(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
}

function showLabel(track: PlayerTrack): string {
  return [formatShowDate(track.showDate), track.venueName].filter(Boolean).join(" · ");
}

function sameShow(a: PlayerTrack | undefined, b: PlayerTrack): boolean {
  return Boolean(a) && a!.showDate === b.showDate && a!.venueName === b.venueName;
}

function moved<T>(items: T[], from: number, to: number): T[] {
  const copy = items.slice();
  const [item] = copy.splice(from, 1);
  copy.splice(to, 0, item);
  return copy;
}

function GripIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {[7, 12, 17].map((y) => (
        <g key={y}>
          <circle cx="9" cy={y} r="1.5" fill="currentColor" />
          <circle cx="15" cy={y} r="1.5" fill="currentColor" />
        </g>
      ))}
    </svg>
  );
}

type MenuItem = { label: string; run: () => void; disabled?: boolean };

// A row's ⋯ menu. Arrow keys move through it, Home and End jump to its ends,
// Escape closes it and returns focus to ⋯, and Tab or a click outside closes it.
function RowMenu({ title, items }: { title: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();
  const enabled = items.filter((item) => !item.disabled);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLButtonElement>("[role=menuitem]:not(:disabled)")?.focus();
    const outside = (event: globalThis.PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function close(returnFocus: boolean) {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }

  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    const buttons = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]:not(:disabled)") ?? []);
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const focus = (index: number) => buttons[(index + buttons.length) % buttons.length]?.focus();
    if (event.key === "ArrowDown") focus(at + 1);
    else if (event.key === "ArrowUp") focus(at - 1);
    else if (event.key === "Home") focus(0);
    else if (event.key === "End") focus(buttons.length - 1);
    else if (event.key === "Escape") close(true);
    else if (event.key === "Tab") close(false);
    else return;
    event.preventDefault();
    event.stopPropagation();
  }

  if (enabled.length === 0) return null;
  return (
    <span className="queue-menu-wrap">
      <button
        ref={triggerRef}
        type="button"
        className={`queue-more${open ? " open" : ""}`}
        aria-label={`More for ${title}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <MoreIcon />
      </button>
      {open && (
        <div ref={menuRef} id={menuId} className="queue-menu" role="menu" aria-label={`Actions for ${title}`} onKeyDown={onMenuKey}>
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              tabIndex={-1}
              disabled={item.disabled}
              onClick={() => {
                close(true);
                item.run();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

// A row opened in place from its ⋯ menu: the facts the queue holds about the
// track. The recording page leaves the site; nothing here asks Deadbot.
function TrackDetails({ track, onClose }: { track: PlayerTrack; onClose: () => void }) {
  const facts: [string, ReactNode][] = [];
  if (track.showDate) facts.push(["Show", formatShowDateLong(track.showDate)]);
  if (track.venueName) facts.push(["Venue", track.venueName]);
  if (track.durationSeconds) facts.push(["Length", formatClockTime(track.durationSeconds)]);
  if (track.recordingDetailsUrl) {
    facts.push([
      "Recording",
      <a href={track.recordingDetailsUrl} target="_blank" rel="noreferrer">
        Internet Archive<span aria-hidden="true"> ↗</span><span className="visually-hidden"> (opens in a new tab)</span>
      </a>
    ]);
  }
  return (
    <div className="queue-details" role="group" aria-label={`Details for ${track.title}`}>
      {facts.length > 0 ? (
        <dl>
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>No details for this track.</p>
      )}
      <button type="button" className="queue-clear" onClick={onClose}>Hide details</button>
    </div>
  );
}

type Drag = { from: number; to: number; mids: number[]; first: number };

// The queue's songs kept on this device for listening without a signal: one
// quiet line at the foot of the queue, with the size before anything saves.
function OfflineLine({ queue }: { queue: PlayerTrack[] }) {
  // A song cut across files saves every one of them.
  const urls = [...new Set(queue.flatMap(trackFiles))];
  const { ready, savedCount, unsaved, progress } = useOffline(urls);
  if (!offlineSupported() || !ready || queue.length === 0) return null;
  const toSave = queue.filter((track) => trackFiles(track).some((url) => unsaved.includes(url)));
  const size = formatBytes(estimateBytes(toSave));
  const failed = lastSaveFailures();
  const songs = (count: number) => (count === 1 ? "1 song" : `${count} songs`);
  let text: string;
  let action: ReactNode = null;
  if (progress) {
    text = `Saving ${Math.min(progress.done + 1, progress.total)} of ${progress.total} for listening offline…`;
  } else if (savedCount === 0) {
    text = "";
    action = (
      <button type="button" className="queue-clear queue-link" onClick={() => void saveTracks(urls)}>
        Save the queue to listen offline
      </button>
    );
  } else if (toSave.length === 0) {
    text = savedCount === 1 ? "On this device to listen offline." : `All ${savedCount} songs on this device to listen offline.`;
    action = (
      <button type="button" className="queue-clear queue-link" onClick={() => void removeTracks(urls)}>
        Remove
      </button>
    );
  } else {
    text = `${savedCount} of ${songs(queue.length)} on this device.`;
    action = (
      <button type="button" className="queue-clear queue-link" onClick={() => void saveTracks(urls)}>
        Save the rest
      </button>
    );
  }
  return (
    <div className="queue-offline">
      <p role="status">
        {text}
        {!progress && failed > 0 ? ` ${songs(failed)} couldn’t be saved.` : ""}
      </p>
      {action && (
        <p>
          {action}
          {toSave.length > 0 && !progress && <span className="queue-count"> · about {size}, best on Wi-Fi</span>}
        </p>
      )}
    </div>
  );
}

export function QueuePanel({ id, variant, onClose, panelRef, headExtra }: {
  id?: string;
  variant: "rail" | "popover";
  onClose?: () => void;
  panelRef?: RefObject<HTMLElement | null>;
  headExtra?: ReactNode; // the rail's collapse control, after Clear
}) {
  const player = usePlayer();
  const headingId = useId();
  const [announcement, setAnnouncement] = useState("");
  // The queue before a Clear, and which list was cleared, for Undo.
  const [cleared, setCleared] = useState<{ queue: PlayerTrack[]; what: "upcoming" | "played" } | null>(null);
  const [opened, setOpened] = useState<Set<string>>(() => new Set());
  const [drag, setDrag] = useState<Drag | null>(null);
  const listRef = useRef<HTMLOListElement | null>(null);
  const currentRef = useRef<HTMLDivElement | null>(null);

  // Undo is offered for ten seconds after Clear.
  useEffect(() => {
    if (!cleared) return;
    const timer = window.setTimeout(() => setCleared(null), UNDO_SECONDS * 1000);
    return () => window.clearTimeout(timer);
  }, [cleared]);

  const queue = player.queue;
  const current = queue.findIndex((track) => track.id === player.currentTrack?.id);
  const first = current + 1;
  // While a row is dragged, the list shows where it would land.
  const shown = drag ? moved(queue, drag.from, drag.to) : queue;
  const upNext = shown.slice(first);
  const played = current > 0 ? shown.slice(0, current) : [];
  const nowPlaying = current >= 0 ? queue[current] : null;
  const upNextSeconds = queue.slice(first).reduce((sum, track) => sum + (track.durationSeconds ?? 0), 0);
  const progress = player.duration > 0 ? Math.min(100, (player.position / player.duration) * 100) : 0;

  function moveTo(from: number, to: number) {
    if (to < first || to >= queue.length || from === to) return;
    const track = queue[from];
    player.move(from, to);
    setAnnouncement(`Moved ${track.title} to ${to - current} in Up next`);
  }

  function remove(index: number) {
    const track = queue[index];
    player.remove(index);
    setAnnouncement(`Removed ${track.title} from the queue`);
  }

  // Clear queue empties Up next; what has played stays listed.
  function clear() {
    if (!nowPlaying) return;
    setCleared({ queue: queue.slice(), what: "upcoming" });
    player.replaceQueue(queue.slice(0, current + 1));
    setAnnouncement("Cleared the queue. Undo is available for ten seconds.");
  }

  function clearPlayed() {
    if (!nowPlaying) return;
    setCleared({ queue: queue.slice(), what: "played" });
    player.replaceQueue(queue.slice(current));
    setAnnouncement("Cleared what has played. Undo is available for ten seconds.");
  }

  function undo() {
    if (!cleared) return;
    player.replaceQueue(cleared.queue);
    setCleared(null);
    setAnnouncement(cleared.what === "played" ? "Restored what has played" : "Restored the queue");
  }

  function toggleDetails(track: PlayerTrack) {
    setOpened((previous) => {
      const next = new Set(previous);
      if (next.has(track.id)) next.delete(track.id);
      else next.add(track.id);
      return next;
    });
  }

  // Dragging by the grip: the other rows' midpoints are measured once, and
  // the row lands after however many of them the pointer has passed.
  function startDrag(event: PointerEvent<HTMLButtonElement>, from: number) {
    if (event.button > 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const rows = Array.from(listRef.current?.querySelectorAll<HTMLElement>("[data-queue-index]") ?? []);
    const mids = rows
      .filter((row) => Number(row.dataset.queueIndex) !== from)
      .map((row) => {
        const box = row.getBoundingClientRect();
        return box.top + box.height / 2;
      });
    setDrag({ from, to: from, mids, first });
  }

  function dragMove(event: PointerEvent<HTMLButtonElement>) {
    if (!drag) return;
    const passed = drag.mids.filter((mid) => mid < event.clientY).length;
    const to = drag.first + passed;
    if (to !== drag.to) setDrag({ ...drag, to });
  }

  function endDrag() {
    if (!drag) return;
    setDrag(null);
    moveTo(drag.from, drag.to);
  }

  function gripKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const to = index + (event.key === "ArrowUp" ? -1 : 1);
    moveTo(index, to);
    // Keep the grip in hand as its row moves.
    requestAnimationFrame(() => listRef.current?.querySelector<HTMLButtonElement>(`[data-queue-index="${to}"] .queue-grip`)?.focus());
  }

  function rowMenu(track: PlayerTrack, index: number, upcoming: boolean): MenuItem[] {
    return [
      { label: "Play now", run: () => player.jumpTo(index) },
      { label: "Play next", run: () => { player.playNext(index); setAnnouncement(`${track.title} plays next`); }, disabled: index === first },
      { label: "Move up", run: () => moveTo(index, index - 1), disabled: !upcoming || index <= first },
      { label: "Move down", run: () => moveTo(index, index + 1), disabled: !upcoming || index >= queue.length - 1 },
      { label: opened.has(track.id) ? "Hide details" : "Details", run: () => toggleDetails(track) },
      { label: "Remove from queue", run: () => remove(index) }
    ];
  }

  function row(track: PlayerTrack, index: number, previous: PlayerTrack | undefined, upcoming: boolean) {
    const show = showLabel(track);
    const dragging = drag && drag.to === index;
    return (
      <li key={track.id} data-queue-index={index} className={`queue-item${upcoming ? "" : " heard"}${dragging ? " dragging" : ""}`}>
        <span className="queue-n" aria-hidden="true">{upcoming ? index - current : ""}</span>
        <button type="button" className="queue-title" onClick={() => player.jumpTo(index)} aria-label={`Play ${track.title}`}>
          <span className="queue-title-text">{track.title}</span>
          {show && !sameShow(previous, track) && <span className="queue-show">{show}</span>}
        </button>
        <span className="queue-time">{track.durationSeconds ? formatClockTime(track.durationSeconds) : ""}</span>
        {upcoming ? (
          <button
            type="button"
            className="queue-grip"
            aria-label={`Reorder ${track.title}: drag, or use the arrow keys`}
            title="Drag to reorder"
            onPointerDown={(event) => startDrag(event, index)}
            onPointerMove={dragMove}
            onPointerUp={endDrag}
            onPointerCancel={() => setDrag(null)}
            onKeyDown={(event) => gripKey(event, index)}
          >
            <GripIcon />
          </button>
        ) : (
          <span className="queue-grip-space" aria-hidden="true" />
        )}
        <RowMenu title={track.title} items={rowMenu(track, index, upcoming)} />
        {opened.has(track.id) && <TrackDetails track={track} onClose={() => toggleDetails(track)} />}
      </li>
    );
  }

  return (
    <section
      ref={panelRef as RefObject<HTMLElement>}
      id={id}
      className={variant === "popover" ? "queue-panel popover now-playing-queue" : "queue-panel rail"}
      aria-labelledby={headingId}
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape" && onClose) onClose();
      }}
    >
      <p className="sr-only" role="status">{announcement}</p>
      <header className="queue-panel-head">
        <h2 id={headingId}>Queue</h2>
        <span className="queue-head-actions">
          {headExtra}
        </span>
      </header>

      {nowPlaying && (
        <div className="queue-now" ref={currentRef}>
          <p className="queue-section">Now playing</p>
          <div className="queue-now-row">
            <Equalizer playing={player.status === "playing"} />
            <span className="queue-now-text">
              <span className="queue-title-text">{nowPlaying.title}</span>
              {showLabel(nowPlaying) && <span className="queue-show">{showLabel(nowPlaying)}</span>}
            </span>
            <span className="queue-time">{nowPlaying.durationSeconds ? formatClockTime(nowPlaying.durationSeconds) : ""}</span>
          </div>
          <span className="queue-progress" aria-hidden="true"><span style={{ width: `${progress}%` }} /></span>
        </div>
      )}

      <p className="queue-section">
        Up next
        <span className="queue-count">
          {upNext.length === 1 ? "1 track" : `${upNext.length} tracks`}
          {upNextSeconds > 0 ? ` · ${formatListeningTime(upNextSeconds)}` : ""}
        </span>
        {cleared?.what === "upcoming" ? (
          <button type="button" className="queue-clear queue-link queue-section-action" onClick={undo}>Cleared. Undo</button>
        ) : (
          upNext.length > 0 && <button type="button" className="queue-clear queue-link queue-section-action" onClick={clear} aria-label="Clear queue">Clear</button>
        )}
      </p>
      {upNext.length > 0 ? (
        <ol className="queue-list" ref={listRef}>
          {upNext.map((track, offset) => row(track, first + offset, offset === 0 ? nowPlaying ?? undefined : upNext[offset - 1], true))}
        </ol>
      ) : (
        <p className="queue-empty">Nothing queued after this. Use + on any track to add it.</p>
      )}

      {(played.length > 0 || cleared?.what === "played") && (
        <>
          <p className="queue-section">
            Played
            {cleared?.what === "played" ? (
              <button type="button" className="queue-clear queue-link queue-section-action" onClick={undo}>Cleared. Undo</button>
            ) : (
              <button type="button" className="queue-clear queue-link queue-section-action" onClick={clearPlayed} aria-label="Clear played">Clear</button>
            )}
          </p>
          <ol className="queue-list played">
            {played.map((track, index) => row(track, index, played[index - 1], false))}
          </ol>
        </>
      )}

      <OfflineLine queue={queue} />
    </section>
  );
}

export const QUEUE_RAIL_ID = "queue-rail";

const EXPAND_EVENT = "deadbot:expand-queue-rail";

// The bar's queue button, when the queue has its own rail: open the rail if
// it is collapsed, then focus it and bring the playing track into view.
export function focusQueueRail() {
  window.dispatchEvent(new Event(EXPAND_EVENT));
  requestAnimationFrame(() => {
    const rail = document.getElementById(QUEUE_RAIL_ID);
    if (!rail) return;
    rail.focus({ preventScroll: true });
    rail.closest(".queue-rail")?.scrollTo?.({ top: 0 });
  });
}

// The workspace's right rail: the queue, from the moment anything plays. It
// takes no room before then.
// It collapses to a slim strip (the expand control and the queue mark with
// its count) and remembers that.
export function QueueRail() {
  const player = usePlayer();
  const [open, setOpen] = useRememberedOpen("deadbot.rail.queue");
  useEffect(() => {
    const expand = () => setOpen(true);
    window.addEventListener(EXPAND_EVENT, expand);
    return () => window.removeEventListener(EXPAND_EVENT, expand);
  });
  if (!player.currentTrack) return null;
  const toggle = <PanelToggle side="right" open={open} label="queue" onToggle={() => setOpen(!open)} />;
  if (!open) {
    const current = player.queue.findIndex((track) => track.id === player.currentTrack?.id);
    const upcoming = Math.max(player.queue.length - current - 1, 0);
    return (
      <aside className="queue-rail collapsed" aria-label="Queue">
        {toggle}
        <span className="queue-rail-mark" aria-label={`${upcoming === 1 ? "1 track" : `${upcoming} tracks`} up next`}>
          <QueueIcon />
          <span aria-hidden="true">{upcoming}</span>
        </span>
      </aside>
    );
  }
  return (
    <aside className="queue-rail" aria-label="Queue">
      <QueuePanel id={QUEUE_RAIL_ID} variant="rail" headExtra={toggle} />
    </aside>
  );
}
