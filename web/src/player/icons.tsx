

export function PlayPauseIcon({ playing }: { playing: boolean }) {
  if (playing) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="6" y="5" width="4.5" height="14" fill="currentColor" />
        <rect x="13.5" y="5" width="4.5" height="14" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M7 4.5v15l12-7.5z" />
    </svg>
  );
}

// Back and next for a queue: a bar against a triangle, the triangle pointing
// the way the queue moves.
export function StepIcon({ direction }: { direction: "previous" | "next" }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d={direction === "previous" ? "M6 5h2.5v14H6zM19 5v14L9 12z" : "M15.5 5H18v14h-2.5zM5 5v14l10-7z"} />
    </svg>
  );
}

export function ChevronIcon({ up }: { up: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d={up ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} />
    </svg>
  );
}

export function QueueIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M4 6h12v2H4zM4 11h12v2H4zM4 16h8v2H4zM18 13.5v6l4.5-3z" />
    </svg>
  );
}

export function PlayNextIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 5h14M12 19V9M7.5 13.5 12 9l4.5 4.5" />
    </svg>
  );
}

export function RemoveIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
    </svg>
  );
}

export function MoreIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="5" cy="12" r="1.8" fill="currentColor" />
      <circle cx="12" cy="12" r="1.8" fill="currentColor" />
      <circle cx="19" cy="12" r="1.8" fill="currentColor" />
    </svg>
  );
}

export function LoopIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M17 3l3 3-3 3M4 11V9a3 3 0 0 1 3-3h13M7 21l-3-3 3-3M20 13v2a3 3 0 0 1-3 3H4" />
    </svg>
  );
}

// Three bars that move while a track plays and rest when it pauses. The
// queue's Now playing row and a playing card's play button both show it.
export function Equalizer({ playing }: { playing: boolean }) {
  return (
    <span className={`eq${playing ? " playing" : ""}`} aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}
