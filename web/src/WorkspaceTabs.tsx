import { useRef } from "react";
import { WORKSPACE_TABS, type WorkspaceTab } from "./tab-routing";
import "./WorkspaceShell.css";

export type TabState = "ready" | "preparing" | "new" | "unused";

// The tabs of one exploration. A tab with nothing in it is grayed and skipped;
// arrow keys move focus and selection together.
export function WorkspaceTabs({ active, states, onSelect, idPrefix }: {
  active: WorkspaceTab | null;
  states: Record<WorkspaceTab, TabState>;
  onSelect(tab: WorkspaceTab): void;
  idPrefix: string;
}) {
  const refs = useRef<Partial<Record<WorkspaceTab, HTMLButtonElement | null>>>({});
  const usable = WORKSPACE_TABS.filter(({ id }) => states[id] !== "unused").map(({ id }) => id);

  const choose = (tab: WorkspaceTab) => {
    onSelect(tab);
    refs.current[tab]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent, tab: WorkspaceTab) => {
    if (usable.length === 0) return;
    const at = usable.indexOf(tab);
    let next: WorkspaceTab | undefined;
    if (event.key === "ArrowRight") next = usable[(at + 1) % usable.length];
    else if (event.key === "ArrowLeft") next = usable[(at - 1 + usable.length) % usable.length];
    else if (event.key === "Home") next = usable[0];
    else if (event.key === "End") next = usable[usable.length - 1];
    if (!next) return;
    event.preventDefault();
    choose(next);
  };

  return (
    <div role="tablist" aria-label="Views of this exploration" className="workspace-tabs">
      {WORKSPACE_TABS.map(({ id, label }) => {
        const state = states[id];
        const unused = state === "unused";
        const selected = active === id;
        return (
          <button
            key={id}
            ref={(node) => { refs.current[id] = node; }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${id}`}
            aria-controls={`${idPrefix}-panel-${id}`}
            aria-selected={selected}
            aria-disabled={unused ? "true" : undefined}
            className={unused ? "unused" : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => { if (!unused) onSelect(id); }}
            onKeyDown={(event) => onKeyDown(event, id)}
          >
            {label}
            {state === "preparing" && <span className="tab-mark">preparing</span>}
            {state === "new" && (
              <span className="tab-mark new">
                <span className="tab-dot" aria-hidden="true" />
                <span className="visually-hidden"> has new content</span>
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
