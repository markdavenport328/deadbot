import { useEffect, useRef, useState } from "react";

// The site's few pages share one document so the conversation, the page it
// composed and anything playing all survive a visit to About and back. A page
// change is a history entry; the app stays mounted underneath.

const NAVIGATE_EVENT = "deadbot:navigate";

export function currentPath(): string {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

export function usePath(): string {
  const [path, setPath] = useState(currentPath);
  useEffect(() => {
    const update = () => setPath(currentPath());
    window.addEventListener("popstate", update);
    window.addEventListener(NAVIGATE_EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener(NAVIGATE_EVENT, update);
    };
  }, []);
  return path;
}

export function navigate(href: string) {
  if (href !== currentPath()) window.history.pushState({}, "", href);
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
}

// An in-site link: a plain click moves within the page; a modified click
// (new tab, new window) keeps the browser's own behaviour.
export function followInSite(event: React.MouseEvent<HTMLAnchorElement>, href: string) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  event.preventDefault();
  navigate(href);
  return true;
}

const ASK_EVENT = "deadbot:ask";

// A question asked from another page: back to the app, which is still mounted
// underneath and takes it as a fresh question.
export function askFromPage(event: React.MouseEvent<HTMLAnchorElement>, question: string) {
  if (!followInSite(event, "/")) return;
  window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: question }));
}

export function useAskFromPage(onAsk: (question: string) => void) {
  const latest = useRef(onAsk);
  latest.current = onAsk;
  useEffect(() => {
    const listen = (event: Event) => {
      const question = (event as CustomEvent<unknown>).detail;
      if (typeof question === "string") latest.current(question);
    };
    window.addEventListener(ASK_EVENT, listen);
    return () => window.removeEventListener(ASK_EVENT, listen);
  }, []);
}
