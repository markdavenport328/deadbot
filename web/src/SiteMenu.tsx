import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { followInSite, usePath } from "./site-nav";
import "./SiteMenu.css";

const RESUME_URL = "https://mark-davenport.vercel.app";

// The site menu: one quiet button in the top-right corner that opens a
// full-screen panel of a few very large links separated by hairlines. While it
// is open the rest of the page is inert, so focus stays inside the panel.
export function SiteMenu() {
  const [open, setOpen] = useState(false);
  const path = usePath();
  const toggleRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    const root = document.getElementById("root");
    if (open) {
      wasOpen.current = true;
      root?.setAttribute("inert", "");
      document.documentElement.classList.add("site-menu-open");
      closeRef.current?.focus();
      const onKey = (event: KeyboardEvent) => {
        if (event.key === "Escape") setOpen(false);
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }
    root?.removeAttribute("inert");
    document.documentElement.classList.remove("site-menu-open");
    if (wasOpen.current) toggleRef.current?.focus();
    return undefined;
  }, [open]);

  // A page change from anywhere (the browser's back button included) closes
  // the menu.
  useEffect(() => setOpen(false), [path]);

  return (
    <>
      <button
        ref={toggleRef}
        type="button"
        className="site-menu-toggle"
        aria-label="Menu"
        aria-expanded={open}
        aria-controls="site-menu"
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true" />
      </button>
      {createPortal(
        <div
          id="site-menu"
          className={open ? "site-menu open" : "site-menu"}
          role="dialog"
          aria-modal="true"
          aria-label="Site menu"
          inert={!open}
        >
          <div className="site-menu-bar">
            <a className="wordmark" href="/" onClick={(event) => followInSite(event, "/") && setOpen(false)}>
              Deadbot
            </a>
            <button ref={closeRef} type="button" className="site-menu-close" aria-label="Close menu" onClick={() => setOpen(false)}>
              <span aria-hidden="true" />
            </button>
          </div>
          <nav aria-label="Site">
            <ul className="site-menu-list">
              <li>
                <a
                  className="site-menu-link"
                  href="/about"
                  aria-current={path === "/about" ? "page" : undefined}
                  onClick={(event) => followInSite(event, "/about") && setOpen(false)}
                >
                  About Deadbot
                </a>
              </li>
              <li>
                <a className="site-menu-link" href={RESUME_URL} target="_blank" rel="noopener">
                  <span>
                    About Mark Davenport<span className="site-menu-out" aria-hidden="true">↗</span>
                  </span>
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
              </li>
            </ul>
          </nav>
        </div>,
        document.body
      )}
    </>
  );
}
