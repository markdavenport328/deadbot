// What the workspace remembers about one visit: the model turns the visitor
// has had (each one a full page), where they are in that history, and the
// request in flight. Local moves (switching a tab, scrolling) change only the
// current entry's view and never add a history step. Player state does not
// live here; the player keeps playing across every change below.
import type { AskFocus, ExperienceResponse } from "./types";
import type { PageEvent } from "./stream-events";
import { applyPageEvent, groupsOfResponse, type Draft } from "./page-draft";
import { openingTab, readTab, routeGroups, type WorkspaceTab } from "./tab-routing";

export type RequestSource = "typed" | "chip";
export type EntryView = { tab: WorkspaceTab | null; scroll: Partial<Record<WorkspaceTab, number>> };
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
};
export type Pending = {
  requestId: string;
  baseEntryId: string | null; // null: a fresh start
  question: string;
  source: RequestSource;
  focus: AskFocus | null;
  threadId: string;
  statuses: string[];
  answer: string | null;
  draft: Draft | null;
  initialTab: WorkspaceTab | null;
  view: EntryView;
  interacted: boolean;
  error: string | null;
};
export type ExplorationState = { entries: Entry[]; cursor: number; pending: Pending | null; startView: boolean };
export type ExplorationAction =
  | { type: "submit"; requestId: string; question: string; source: RequestSource; focus: AskFocus | null; fresh: boolean; threadId: string }
  | { type: "status"; requestId: string; text: string }
  | { type: "answer"; requestId: string; text: string }
  | { type: "page"; requestId: string; event: PageEvent }
  | { type: "initialTab"; requestId: string; tab: WorkspaceTab }
  | { type: "complete"; requestId: string; response: ExperienceResponse }
  | { type: "fail"; requestId: string; message: string }
  | { type: "cancel" }
  | { type: "dismiss" }
  | { type: "navigate"; index: number }
  | { type: "newChat" }
  | { type: "view"; patch: Partial<EntryView>; interacted?: boolean };

export const initialExploration: ExplorationState = { entries: [], cursor: -1, pending: null, startView: false };

const emptyView = (): EntryView => ({ tab: null, scroll: {} });

export function currentEntry(state: ExplorationState): Entry | null {
  return state.entries[state.cursor] ?? null;
}

export function isAsking(state: ExplorationState): boolean {
  return state.pending !== null && state.pending.error === null;
}

export function pendingHasContent(pending: Pending): boolean {
  return Boolean(pending.answer && pending.answer.trim()) || (pending.draft?.groups ?? []).some((group) => group.blocks.length > 0);
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
  if (!pending) return state.startView || !entry ? { kind: "start" } : { kind: "entry", entry };
  const base = pending.baseEntryId ? state.entries.find((candidate) => candidate.id === pending.baseEntryId) ?? null : null;
  if (pending.error !== null) return { kind: "failed", entry: base, pending };
  if (pendingHasContent(pending)) return { kind: "draft", pending };
  return base ? { kind: "held", entry: base, pending } : { kind: "working", pending };
}

// The first content picks the opening tab once (the model's choice, else by
// what arrived); after that, later events never move the visitor.
function settleTab(pending: Pending): Pending {
  if (pending.view.tab !== null || pending.interacted || !pendingHasContent(pending)) return pending;
  const tab = openingTab(pending.initialTab, routeGroups(pending.draft?.groups ?? []));
  return { ...pending, view: { ...pending.view, tab } };
}

export function explorationReducer(state: ExplorationState, action: ExplorationAction): ExplorationState {
  const { pending } = state;
  switch (action.type) {
    case "submit": {
      if (isAsking(state)) return state;
      const entry = currentEntry(state);
      const baseEntryId = action.fresh || !entry || state.startView ? null : entry.id;
      return {
        ...state,
        startView: false,
        pending: {
          requestId: action.requestId, baseEntryId, question: action.question, source: action.source, focus: action.focus,
          threadId: action.threadId, statuses: [], answer: null, draft: null, initialTab: null, view: emptyView(),
          interacted: false, error: null
        }
      };
    }
    case "status":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: { ...pending, statuses: [...pending.statuses, action.text] } };
    case "answer":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: settleTab({ ...pending, answer: action.text }) };
    case "page":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: settleTab({ ...pending, draft: applyPageEvent(pending.draft, action.event) }) };
    case "initialTab": {
      if (!pending || pending.requestId !== action.requestId) return state;
      const view = pending.interacted ? pending.view : { ...pending.view, tab: action.tab };
      return { ...state, pending: { ...pending, initialTab: action.tab, view } };
    }
    case "complete": {
      if (!pending || pending.requestId !== action.requestId) return state;
      const { response } = action;
      const tab = pending.view.tab ?? openingTab(readTab(response.initial_tab), routeGroups(groupsOfResponse(response)));
      const entry: Entry = {
        id: pending.requestId, parentId: pending.baseEntryId, root: pending.baseEntryId === null,
        request: pending.question, source: pending.source, focus: pending.focus, threadId: pending.threadId,
        response, view: { ...pending.view, tab }
      };
      const baseIndex = pending.baseEntryId === null ? -1 : state.entries.findIndex((candidate) => candidate.id === pending.baseEntryId);
      // A follow-up replaces whatever came after the page it grew from; a
      // fresh start is a new line of inquiry and drops nothing.
      const kept = entry.root || baseIndex < 0 ? state.entries : state.entries.slice(0, baseIndex + 1);
      const entries = [...kept, entry];
      return { ...state, entries, cursor: entries.length - 1, pending: null };
    }
    case "fail":
      if (!pending || pending.requestId !== action.requestId) return state;
      return { ...state, pending: { ...pending, error: action.message } };
    case "cancel":
      return pending ? { ...state, pending: null } : state;
    case "dismiss":
      return pending && pending.error !== null ? { ...state, pending: null } : state;
    case "navigate":
      if (!Number.isInteger(action.index) || action.index < 0 || action.index >= state.entries.length) return { ...state, pending: null, startView: false };
      return { ...state, pending: null, cursor: action.index, startView: false };
    case "newChat":
      if (isAsking(state)) return state;
      return { ...state, startView: true, pending: null };
    case "view": {
      const mark = action.interacted && pending ? { ...pending, interacted: true } : pending;
      if (visible(state).kind === "draft" && mark) {
        return { ...state, pending: { ...mark, view: { ...mark.view, ...action.patch } } };
      }
      const entry = currentEntry(state);
      if (!entry) return mark === pending ? state : { ...state, pending: mark };
      const entries = state.entries.slice();
      entries[state.cursor] = { ...entry, view: { ...entry.view, ...action.patch } };
      return { ...state, entries, pending: mark };
    }
  }
}
