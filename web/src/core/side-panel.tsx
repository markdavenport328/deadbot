import { useState } from "react";

// The side columns (history on the left, the queue on the right) open by
// default and can be collapsed; each remembers the visitor's choice in this
// browser.
export function useRememberedOpen(key: string): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(() => {
    try {
      return window.localStorage.getItem(key) !== "closed";
    } catch {
      return true;
    }
  });
  function set(next: boolean) {
    setOpen(next);
    try {
      if (next) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, "closed");
    } catch {
      // Storage blocked: the choice lasts the visit.
    }
  }
  return [open, set];
}

// The panel mark: a rounded rectangle with the side column drawn in, on the
// side it belongs to.
export function PanelIcon({ side }: { side: "left" | "right" }) {
  const x = side === "left" ? 9 : 15;
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="5" width="17" height="14" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d={`M${x} 5v14`} stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

// The collapse or expand button for one side column.
export function PanelToggle({ side, open, label, onToggle }: { side: "left" | "right"; open: boolean; label: string; onToggle(): void }) {
  return (
    <button
      type="button"
      className="panel-toggle"
      aria-expanded={open}
      aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
      data-tip={`${open ? "Collapse" : "Expand"} ${label}`}
      data-tip-place="below"
      onClick={onToggle}
    >
      <PanelIcon side={side} />
    </button>
  );
}

// New chat's mark: a pen.
export function PenIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5l1-4L15.8 5.2a2 2 0 0 1 2.8 0l.2.2a2 2 0 0 1 0 2.8L8.5 18.5l-4 1zM14 7l3 3" />
    </svg>
  );
}
