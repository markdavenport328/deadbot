
import { useEffect, useRef, useState } from "react";

// Mark Davenport's résumé, linked from the rail, the phone drawer and About.
export const RESUME_URL = "https://mark-davenport.vercel.app";

// The site's few pages share one document so the conversation, the page it
// composed and anything playing all survive a visit to About and back. A page
// change is a history entry; the app stays mounted underneath.
//
// Every page a visitor opens has an address and a step in the browser's
// history: the start view is `/`, an answer is `/?q=<its question>` (a
// follow-up is `/?q=<the question its thread began with>&then=<its own>`),
// and About is `/about`. Back and Forward move between them. Each history
// step also carries the id of the page it stands for, so this browser returns
// to the exact page it showed; a link opened anywhere else finds the page by
// its question.

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

type HistoryState = { deadbot?: { page: string | null }; overlay?: string };

function historyState(): HistoryState {
  const state = window.history.state as unknown;
  return state && typeof state === "object" ? (state as HistoryState) : {};
}

// A new step in the browser's history. While a drawer or menu is open its
// own step is on top (see useBackCloses), and the new page takes that step's
// place, so Back from the new page returns to the page before it.
function step(mode: "push" | "replace", state: HistoryState, href: string) {
  const here = window.location.pathname + window.location.search + window.location.hash;
  const pathBefore = currentPath();
  if (mode === "replace" || historyState().overlay) window.history.replaceState(state, "", href);
  else if (href !== here || historyState().deadbot?.page !== state.deadbot?.page) window.history.pushState(state, "", href);
  if (currentPath() !== pathBefore) window.dispatchEvent(new Event(NAVIGATE_EVENT));
}

export function navigate(href: string) {
  if (href === currentPath() && !historyState().overlay) {
    window.dispatchEvent(new Event(NAVIGATE_EVENT));
    return;
  }
  step("push", {}, href);
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

// The address of an answer: the question that reopens it and, for a
// follow-up, its own question after the one its thread began with.
export type PageAddress = { question: string | null; followUp: string | null };

export function readPageAddress(): PageAddress & { page: string | null | undefined } {
  const params = new URLSearchParams(window.location.search);
  const question = params.get("q")?.trim() || null;
  return { question, followUp: question ? params.get("then")?.trim() || null : null, page: historyState().deadbot?.page };
}

// The address as a link. Anything else in the query (a development
// `?stream=` name, say) stays.
export function pageHref({ question, followUp }: PageAddress): string {
  const params = new URLSearchParams(window.location.search);
  params.delete("q");
  params.delete("then");
  if (question) {
    params.set("q", question);
    if (followUp) params.set("then", followUp);
  }
  const query = params.toString();
  return query ? `/?${query}` : "/";
}

// Move the browser to a page of the app: a new history step when the visitor
// went somewhere ("push"), or the current step rewritten when the page on
// screen changed under them ("replace").
export function writePage(mode: "push" | "replace", page: string | null, address: PageAddress) {
  step(mode, { deadbot: { page } }, pageHref(address));
}

// True when the browser's current step already stands for this page.
export function atPage(page: string | null, address: PageAddress): boolean {
  return historyState().deadbot?.page === page && window.location.pathname + window.location.search === pageHref(address);
}

// A drawer, menu or panel that the Back button closes: opening it adds a
// history step, Back takes that step away and the panel with it, and closing
// the panel any other way removes the step so Back never lands on it.
export function useBackCloses(name: string, open: boolean, close: () => void) {
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    if (!open) return;
    const here = window.location.pathname + window.location.search + window.location.hash;
    window.history.pushState({ ...historyState(), overlay: name }, "", here);
    const onPop = () => {
      if (historyState().overlay !== name) closeRef.current();
    };
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      if (historyState().overlay === name) window.history.back();
    };
  }, [open, name]);
}

const ASK_EVENT = "deadbot:ask";

// A question asked from another page: back to the app, which is still mounted
// underneath and takes it as a fresh question (its address is the app's).
export function askFromPage(event: React.MouseEvent<HTMLAnchorElement>, question: string) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  askQuestion(question);
}

// A question asked from anywhere in the app (the queue's "Go to this show"):
// the shell takes it as a fresh question, as it does one from another page.
export function askQuestion(question: string) {
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
