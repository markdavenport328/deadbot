import { useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import { QueuePanel } from "./QueuePanel";

// How far the handle is pulled down before letting go closes the sheet.
const DRAG_TO_CLOSE = 80;

// The queue on a phone: a sheet that slides up over most of the screen from
// the player's Queue button, with the whole queue in it (Clear and Undo, the
// drag grips, each row's menu). A tap on the dimmed page, the close button,
// Escape, the Back button (the bar's job, since the bar stays mounted), or
// pulling the handle down closes it, and focus goes back to the Queue button. It renders into the body so the dock's own
// positioning never clips it.
export function QueueSheet({ id, onClose, returnFocus }: { id: string; onClose(): void; returnFocus: RefObject<HTMLButtonElement | null> }) {
  const panelRef = useRef<HTMLElement | null>(null);
  const [pull, setPull] = useState<{ startY: number; dy: number } | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // Once, while the sheet is open: focus moves in, Escape closes, and the
  // page behind it holds still.
  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    document.documentElement.classList.add("sheet-open");
    const focusTarget = returnFocus;
    return () => {
      document.removeEventListener("keydown", onKey);
      document.documentElement.classList.remove("sheet-open");
      focusTarget.current?.focus({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function grab(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setPull({ startY: event.clientY, dy: 0 });
  }
  function drag(event: PointerEvent<HTMLDivElement>) {
    if (pull) setPull({ ...pull, dy: Math.max(0, event.clientY - pull.startY) });
  }
  function release() {
    if (pull && pull.dy > DRAG_TO_CLOSE) onClose();
    setPull(null);
  }

  return createPortal(
    <>
      <div className="queue-sheet-scrim" onClick={onClose} aria-hidden="true" />
      <div
        className={pull ? "queue-sheet dragging" : "queue-sheet"}
        role="dialog"
        aria-modal="true"
        aria-label="Queue"
        style={pull ? { transform: `translateY(${pull.dy}px)` } : undefined}
      >
        <div className="queue-sheet-handle" onPointerDown={grab} onPointerMove={drag} onPointerUp={release} onPointerCancel={() => setPull(null)} aria-hidden="true">
          <span />
        </div>
        <QueuePanel
          id={id}
          variant="sheet"
          panelRef={panelRef}
          onClose={onClose}
          headExtra={
            <button type="button" className="queue-sheet-close" onClick={onClose} aria-label="Close queue">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          }
        />
      </div>
    </>,
    document.body
  );
}
