// The visitor's explorations, kept in this browser so they survive a reload.
// Each saved entry carries its whole response (and with it the research
// notebook token), so reopening an old page asks the model nothing and a
// follow-up from it picks up its research. At most MAX_THREADS threads are
// kept; when storage is full the oldest half go, and again, until it fits.
// Anything unreadable starts the visitor with no history rather than an
// error.
import type { Entry, ExplorationState } from "./exploration-state";

export const HISTORY_KEY = "deadbot.history.v1";
export const MAX_THREADS = 20;

type Saved = { entries: Entry[]; cursor: number; startView: boolean };

function isEntry(value: unknown): value is Entry {
  const entry = value as Entry | null;
  return Boolean(entry) && typeof entry!.id === "string" && typeof entry!.request === "string" && typeof entry!.threadId === "string"
    && typeof entry!.root === "boolean" && typeof entry!.response === "object" && entry!.response !== null;
}

// The index of each thread's first entry.
export function threadStarts(entries: Entry[]): number[] {
  return entries.flatMap((entry, index) => (entry.root || index === 0 ? [index] : []));
}

// Keep the newest `max` threads, moving the cursor with its entry.
export function keepThreads(saved: Saved, max: number): Saved {
  const starts = threadStarts(saved.entries);
  if (starts.length <= max) return saved;
  const cut = starts[starts.length - max];
  const entries = saved.entries.slice(cut);
  const cursor = saved.cursor - cut;
  return cursor < 0 ? { entries, cursor: entries.length - 1, startView: true } : { ...saved, entries, cursor };
}

export function loadHistory(): ExplorationState | null {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Partial<Saved>;
    // Views saved before the page was one column kept a scroll per tab; start those at the top.
    const entries = (Array.isArray(saved.entries) ? saved.entries.filter(isEntry) : []).map((entry) => ({
      ...entry,
      view: { scroll: typeof (entry.view as { scroll?: unknown } | undefined)?.scroll === "number" ? entry.view.scroll : null }
    }));
    if (entries.length === 0) return null;
    // A first entry that lost its thread's start still begins a thread.
    entries[0] = { ...entries[0], root: true, parentId: null };
    const cursor = Number.isInteger(saved.cursor) ? Math.min(Math.max(saved.cursor as number, 0), entries.length - 1) : entries.length - 1;
    return { entries, cursor, pending: null, startView: saved.startView === true };
  } catch {
    return null;
  }
}

export function saveHistory(state: ExplorationState): void {
  let saved: Saved = keepThreads({ entries: state.entries, cursor: state.cursor, startView: state.startView }, MAX_THREADS);
  try {
    if (saved.entries.length === 0) {
      window.localStorage.removeItem(HISTORY_KEY);
      return;
    }
  } catch {
    return;
  }
  for (;;) {
    try {
      window.localStorage.setItem(HISTORY_KEY, JSON.stringify(saved));
      return;
    } catch {
      // Full: drop the oldest half of the threads and try again.
      const threads = threadStarts(saved.entries).length;
      if (threads <= 1) {
        try {
          window.localStorage.removeItem(HISTORY_KEY);
        } catch {
          // Storage is blocked; history lasts the visit.
        }
        return;
      }
      saved = keepThreads(saved, Math.floor(threads / 2));
    }
  }
}
