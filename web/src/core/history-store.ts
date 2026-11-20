// The visitor's explorations, kept in this browser so they survive a reload.
// Each saved entry carries its whole response (and with it the research
// notebook token), so reopening an old page asks the model nothing and a
// follow-up from it picks up its research. At most MAX_THREADS threads are
// kept; when storage is full the oldest half go, and again, until it fits.
// A page saved under another version of the page contract is dropped: this
// build may no longer have the cards it was made of. Anything unreadable
// starts the visitor with no history rather than an error.
import type { Entry, ExplorationState } from "./exploration-state";
import { SCHEMA_VERSION } from "./schema-version";

export const HISTORY_KEY = "deadbot.history.v1";
export const MAX_THREADS = 20;

type Saved = { entries: Entry[]; cursor: number; startView: boolean };

function isEntry(value: unknown): value is Entry {
  const entry = value as Entry | null;
  return Boolean(entry) && typeof entry!.id === "string" && typeof entry!.request === "string" && typeof entry!.threadId === "string"
    && typeof entry!.root === "boolean" && typeof entry!.response === "object" && entry!.response !== null;
}

// A page this build can draw: saved under the current contract, with the
// lists the renderers walk.
function isCurrent(entry: Entry): boolean {
  const response = entry.response as Partial<Entry["response"]>;
  return response.schema_version === SCHEMA_VERSION && Array.isArray(response.blocks) && Array.isArray(response.groups)
    && Array.isArray(response.sources) && Array.isArray(response.conversation);
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
    const all = Array.isArray(saved.entries) ? saved.entries : [];
    const kept = all.filter((entry): entry is Entry => isEntry(entry) && isCurrent(entry));
    if (kept.length === 0) return null;
    const ids = new Set(kept.map((entry) => entry.id));
    const entries = kept.map((entry, index) => ({
      ...entry,
      // A follow-up whose thread lost its earlier pages begins a thread of its own.
      ...(index === 0 || (!entry.root && !(entry.parentId && ids.has(entry.parentId))) ? { root: true, parentId: null } : {}),
      // Views saved before the page was one column kept a scroll per tab; start those at the top.
      view: { scroll: typeof (entry.view as { scroll?: unknown } | undefined)?.scroll === "number" ? entry.view.scroll : null }
    }));
    // The page the visitor was on comes back if it was kept; otherwise they start fresh, with the rest in the rail.
    const wanted = Number.isInteger(saved.cursor) ? all[Math.min(Math.max(saved.cursor as number, 0), all.length - 1)] : all[all.length - 1];
    const cursor = isEntry(wanted) ? entries.findIndex((entry) => entry.id === wanted.id) : -1;
    if (cursor < 0) return { entries, cursor: entries.length - 1, pending: null, startView: true };
    return { entries, cursor, pending: null, startView: saved.startView === true };
  } catch {
    return null;
  }
}

// Forget every saved exploration (the reset offered when the app cannot start).
export function clearSavedHistory(): void {
  try {
    window.localStorage.removeItem(HISTORY_KEY);
  } catch {
    // Storage is blocked; there is nothing saved to forget.
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
