import { type ComponentProps, type KeyboardEvent, type ReactNode, createContext, useContext, useId, useRef, useState } from "react";

// Cards inside a titled group must not sit at the same heading level as the
// group's own <h2>. ComposedPage sets this to "h3" for the duration of a
// titled group's blocks; every card-level heading renders through here so it
// follows without each renderer knowing which level applies.
export const HeadingContext = createContext<"h2" | "h3">("h2");

export function CardHeading(props: ComponentProps<"h2">) {
  const Tag = useContext(HeadingContext);
  return <Tag {...props} />;
}

export type DrawerTab = { id: string; label: string; count?: number; content: ReactNode };

// The tabbed drawer that replaced the stacked <details> facets. A disclosure
// decides once, when it first appears, whether to start open (the same
// reasoning as the old Facet component): later renders must not snap it open
// or closed beneath the reader.
export function Drawer({ tabs, initialOpen }: { tabs: DrawerTab[]; initialOpen: string | null }) {
  const [open, setOpen] = useState(initialOpen);
  const baseId = useId();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  if (tabs.length === 0) return null;

  function focusTabAt(index: number) {
    const target = tabs[(index + tabs.length) % tabs.length];
    tabRefs.current[target.id]?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTabAt(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTabAt(index - 1);
    }
  }

  return (
    <div className="drawer">
      <div className="tabs">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            type="button"
            id={`${baseId}-tab-${tab.id}`}
            aria-expanded={open === tab.id}
            aria-controls={`${baseId}-panel-${tab.id}`}
            className="tab"
            ref={(element) => { tabRefs.current[tab.id] = element; }}
            onClick={() => setOpen((current) => (current === tab.id ? null : tab.id))}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            {tab.label}
            {tab.count !== undefined && <span className="n">{tab.count}</span>}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`${baseId}-panel-${tab.id}`}
          className="panel"
          hidden={open !== tab.id}
        >
          {open === tab.id ? tab.content : null}
        </div>
      ))}
    </div>
  );
}
