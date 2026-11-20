// What the workspace remembers about one visit: the model turns the visitor
// has had (each one a full page), where they are in that history, and the
// request in flight. Looking at another page never stops that request: it
// carries on behind the page on screen and lands in the history when it is
// done. Local moves (scrolling) change only the current entry's view and
// never add a history step. Player state does not live here; the player
// keeps playing across every change below.
import type { AskFocus, ExperienceResponse } from "../types";
import type { PageEvent } from "./stream-events";
import { applyPageEvent, type Draft } from "./page-draft";

export type RequestSource = "typed" | "chip";
// Where the visitor had scrolled the page, kept so going back returns there.
export type EntryView = { scroll: number | null };
export type Entry = {
  id: string; // the request id that produced it
  parentId: string | null;
  root: boolean;
  request: string;
  source: RequestSource;
  focus: AskFocus | null;
  threadId: string;
  response: ExperienceResponse;
  view: EntryView;
  // Finished while the visitor was on another page, and not opened since.
  unseen?: boolean;
};
export type Pending = {
  requestId: string;
  baseEntryId: string | null; // null: a fresh start
  question: string;
  source: RequestSource;
  focus: AskFocus | null;
  threadId: string;
  statuses: string[];
  lead: string | null;
  draft: Draft | null;
  view: EntryView;
  interacted: boolean;
  error: string | null;
  // False once the visitor has gone to look at another page; the request
  // carries on, and its row in the history brings them back to it.
  watching: boolean;
  // Asked from the start view, so stopping it returns there.
  fromStart: boolean;
};
export type ExplorationState = { entries: Entry[]; cursor: number; pending: Pending | null; startView: boolean };
export type ExplorationAction =
  | { type: "submit"; requestId: string; question: string; source: RequestSource; focus: AskFocus | null; fresh: boolean; threadId: string }
  | { type: "status"; requestId: string; text: string }
  | { type: "lead"; requestId: string; text: string }
  | { type: "page"; requestId: string; event: PageEvent }
  | { type: "complete"; requestId: string; response: ExperienceResponse }
  | { type: "fail"; requestId: string; message: string }
  | { type: "cancel" }
  | { type: "dismiss" }
  | { type: "navigate"; index: number }
  // Back to the page being written, or to the one that did not finish.
  | { type: "watch" }
  | { type: "newChat" }
  // Clear empties the history to the start view; restore puts a cleared one back (Undo).
  | { type: "clear" }
  | { type: "restore"; entries: Entry[]; cursor: number }
  | { type: "view"; patch: Partial<EntryView>; interacted?: boolean };

export const initialExploration: ExplorationState = { entries: [], cursor: -1, pending: null, startView: false };

const emptyView = (): EntryView => ({ scroll: null });

export function currentEntry(state: ExplorationState): Entry | null {
  return state.entries[state.cursor] ?? null;
}

export function isAsking(state: ExplorationState): boolean {
  return state.pending !== null && state.pending.error === null;
}

export function pendingHasContent(pending: Pending): boolean {
  return Boolean(pending.lead && pending.lead.trim()) || (pending.draft?.groups ?? []).some((group) => group.blocks.length > 0);
}

export function requestContext(state: ExplorationState, fresh: boolean): { conversation: ExperienceResponse["conversation"]; notebook: string | null; threadId: string | null } {
  const entry = currentEntry(state);
  if (fresh || !entry || state.startView) return { conversation: [], notebook: null, threadId: null };
  return { conversation: entry.response.conversation, notebook: entry.response.notebook ?? null, threadId: entry.threadId };
}

export type Visible =
  | { kind: "start" }
  | { kind: "working"; pending: Pending } // fresh start, nothing to show yet
  | { kind: "held"; entry: Entry; pending: Pending } // follow-up, previous page held
  | { kind: "draft"; pending: Pending } // streamed content is showing
  | { kind: "failed"; entry: Entry | null; pending: Pending }
  | { kind: "entry"; entry: Entry };

export function visible(state: ExplorationState): Visible {
  const { pending } = state;
  const entry = currentEntry(state);
  if (!pending || !pending.watching) return state.startView || !entry ? { kind: "start" } : { kind: "entry", entry };
  const base = pending.baseEntryId ? state.entries.find((candidate) => candidate.id === pending.baseEntryId) ?? null : null;
  if (pending.error !== null) return { kind: "failed", entry: base, pending };
  if (pendingHasContent(pending)) return { kind: "draft", pending };
  return base ? { kind: "held", entry: base, pending } : { kind: "working", pending };
}

// The pane on screen and the view state that belongs to it, or null for the
// start view. The scroll position is saved into that view. A request that
// failed keeps the draft it had written on screen.
export function shownPane(state: ExplorationState): { id: string; view: EntryView; draft: boolean } | null {
  const shown = visible(state);
  switch (shown.kind) {
    case "start":
      return null;
    case "working":
      return { id: shown.pending.requestId, view: shown.pending.view, draft: false };
    case "draft":
      return { id: shown.pending.requestId, view: shown.pending.view, draft: true };
    case "failed":
      if (pendingHasContent(shown.pending)) return { id: shown.pending.requestId, view: shown.pending.view, draft: false };
      return shown.entry ? { id: shown.entry.id, view: shown.entry.view, draft: false } : null;
    case "held":
    case "entry":
      return { id: shown.entry.id, view: shown.entry.view, draft: false };
  }
}

// The index of the question that began the thread `index` is in.
export function threadStart(entries: Entry[], index: number): number {
  let start = Math.min(index, entries.length - 1);
  while (start > 0 && !entries[start].root) start -= 1;
  return Math.max(start, 0);
}

// One past the last entry of the thread `index` is in.
function threadEnd(entries: Entry[], index: number): number {
  let end = index + 1;
  while (end < entries.length && !entries[end].root) end += 1;
  return end;
}

// Where the visitor is, as the address bar and the tab say it: the page's id
// (null for the start view), the question that reopens it, and its title. A
// follow-up is named by the question that began its thread and then its own,
// because its answer leaned on that thread.
export type Address = { page: string | null; question: string | null; followUp: string | null; title: string | null };

export function addressOf(state: ExplorationState): Address {
  const { pending, entries } = state;
  if (pending && pending.watching) {
    const baseIndex = pending.baseEntryId ? entries.findIndex((entry) => entry.id === pending.baseEntryId) : -1;
    const title = pending.draft?.headline ?? pending.question;
    if (baseIndex < 0) return { page: pending.requestId, question: pending.question, followUp: null, title };
    return { page: pending.requestId, question: entries[threadStart(entries, baseIndex)].request, followUp: pending.question, title };
  }
  const entry = currentEntry(state);
  if (state.startView || !entry) return { page: null, question: null, followUp: null, title: null };
  const start = threadStart(entries, state.cursor);
  return {
    page: entry.id,
    question: entries[start].request,
    followUp: start === state.cursor ? null : entry.request,
    title: entry.response.headline ?? entry.request
  };
}

function plain(question: string): string {
  return question.trim().replace(/\s+/g, " ").toLowerCase();
}

// What an address opens: a page this browser already has (by its id, or by
// its question), the start view, or a question to ask fresh. A follow-up
// this browser does not have opens the page its thread began with and hands
// the follow-up back to be offered, since asking it alone would answer a
// different question.
export type Opening =
  | { kind: "pending" }
  | { kind: "entry"; index: number; offer: string | null }
  | { kind: "ask"; question: string; offer: string | null }
  | { kind: "start" };

export function openingFor(state: ExplorationState, address: { page?: string | null; question: string | null; followUp: string | null }): Opening {
  const { entries, pending } = state;
  if (address.page) {
    if (pending?.requestId === address.page) return { kind: "pending" };
    const index = entries.findIndex((entry) => entry.id === address.page);
    if (index >= 0) return { kind: "entry", index, offer: null };
  }
  const question = address.question?.trim();
  if (!question) return { kind: "start" };
  const followUp = address.followUp?.trim() || null;
  let rootIndex = -1;
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    if (!entries[index].root || plain(entries[index].request) !== plain(question)) continue;
    if (rootIndex < 0) rootIndex = index;
    if (!followUp) break;
    for (let next = threadEnd(entries, index) - 1; next > index; next -= 1) {
      if (plain(entries[next].request) === plain(followUp)) return { kind: "entry", index: next, offer: null };
    }
  }
  if (rootIndex >= 0) return { kind: "entry", index: rootIndex, offer: followUp };
  return { kind: "ask", question, offer: followUp };
}

export function explorationReducer(state: ExplorationState, action: ExplorationAction): ExplorationState {
  const { pending } = state;
  switch (action.type) {
    case "submit": {
      if (isAsking(state)) return state;
      const entry = currentEntry(state);
      const fromStart = !entry || state.startView;
      const baseEntryId = action.fresh || fromStart ? null : entry.id;
      return {
        ...state,
        startView: false,
        pending: {
          requestId: action.requestId, baseEntryId, question: action.question, source: action.source, focus: action.focus,
          threadId: action.threadId, statuses: [], lead: null, draft: null, view: emptyView(),
          interacted: false, error: null, watching: true, fromStart
        }
      };
    }
    case "status":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: { ...pending, statuses: [...pending.statuses, action.text] } };
    case "lead":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: { ...pending, lead: action.text } };
    case "page":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: { ...pending, draft: applyPageEvent(pending.draft, action.event) } };
    case "complete": {
      if (!pending || pending.requestId !== action.requestId) return state;
      const { response } = action;
      const baseIndex = pending.baseEntryId === null ? -1 : state.entries.findIndex((candidate) => candidate.id === pending.baseEntryId);
      const entry: Entry = {
        id: pending.requestId, parentId: pending.baseEntryId, root: pending.baseEntryId === null,
        request: pending.question, source: pending.source, focus: pending.focus, threadId: pending.threadId,
        response, view: pending.view, ...(pending.watching ? {} : { unseen: true })
      };
      let entries: Entry[];
      if (entry.root || baseIndex < 0) {
        // A fresh start is a new line of inquiry and drops nothing.
        entries = [...state.entries, entry];
      } else {
        // A follow-up replaces what came after the page it grew from, in its
        // own thread only; later threads stay. The page the visitor is
        // looking at is never taken from under them: then the answer joins
        // the end of the thread instead.
        const end = threadEnd(state.entries, baseIndex);
        const lookingAhead = !pending.watching && !state.startView && state.cursor > baseIndex && state.cursor < end;
        const from = lookingAhead ? end : baseIndex + 1;
        entries = [...state.entries.slice(0, from), entry, ...state.entries.slice(end)];
      }
      if (pending.watching) return { ...state, entries, cursor: entries.indexOf(entry), startView: false, pending: null };
      const viewed = currentEntry(state);
      const cursor = viewed ? entries.indexOf(viewed) : -1;
      return { ...state, entries, cursor: cursor >= 0 ? cursor : entries.indexOf(entry), pending: null };
    }
    case "fail":
      // The draft stays with the failure, so what was already written stays on screen.
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: { ...pending, error: action.message } };
    case "cancel":
      if (!pending) return state;
      return { ...state, pending: null, startView: pending.watching ? pending.fromStart : state.startView };
    case "dismiss":
      if (!pending || pending.error === null) return state;
      return { ...state, pending: null, startView: pending.watching ? pending.fromStart : state.startView };
    case "navigate": {
      // Looking at another page leaves the request in flight alone.
      const away = pending ? { ...pending, watching: false } : null;
      if (!Number.isInteger(action.index) || action.index < 0 || action.index >= state.entries.length) return { ...state, pending: away, startView: false };
      let entries = state.entries;
      if (entries[action.index].unseen) {
        const seen = { ...entries[action.index] };
        delete seen.unseen;
        entries = entries.slice();
        entries[action.index] = seen;
      }
      return { ...state, entries, pending: away, cursor: action.index, startView: false };
    }
    case "watch": {
      if (!pending) return state;
      const baseIndex = pending.baseEntryId ? state.entries.findIndex((candidate) => candidate.id === pending.baseEntryId) : -1;
      return { ...state, pending: { ...pending, watching: true }, cursor: baseIndex >= 0 ? baseIndex : state.cursor, startView: false };
    }
    case "newChat":
      return { ...state, startView: true, pending: pending ? { ...pending, watching: false } : null };
    case "clear":
      if (isAsking(state)) return state;
      return { entries: [], cursor: -1, pending: null, startView: true };
    case "restore":
      if (isAsking(state) || action.entries.length === 0) return state;
      return { entries: action.entries, cursor: Math.min(Math.max(action.cursor, 0), action.entries.length - 1), pending: null, startView: false };
    case "view": {
      // The patch goes to the pane on screen: the page being written once it
      // shows, otherwise the entry in view.
      const mark = action.interacted && pending ? { ...pending, interacted: true } : pending;
      const pane = shownPane(state);
      if (mark && pane && pane.id === mark.requestId) {
        return { ...state, pending: { ...mark, view: { ...mark.view, ...action.patch } } };
      }
      const index = pane ? state.entries.findIndex((candidate) => candidate.id === pane.id) : -1;
      if (index < 0) return mark === pending ? state : { ...state, pending: mark };
      const entries = state.entries.slice();
      entries[index] = { ...entries[index], view: { ...entries[index].view, ...action.patch } };
      return { ...state, entries, pending: mark };
    }
  }
}
