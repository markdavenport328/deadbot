import { afterEach, expect, test, vi } from "vitest";
import { HISTORY_KEY, MAX_THREADS, keepThreads, loadHistory, saveHistory } from "./history-store";
import { explorationReducer as reduce, initialExploration, type ExplorationState } from "./exploration-state";
import { SCHEMA_VERSION } from "./schema-version";

const reply = (title: string, version: string = SCHEMA_VERSION) => ({ schema_version: version, thread_id: "t", title, answer: "a", conversation: [], blocks: [], groups: [], sources: [] }) as never;
const ask = (s: ExplorationState, id: string, fresh: boolean) =>
  reduce(reduce(s, { type: "submit", requestId: id, question: `Q ${id}`, source: "typed", focus: null, fresh, threadId: id }), { type: "complete", requestId: id, response: reply(id) });

function threads(count: number, followUps = 0): ExplorationState {
  let s = initialExploration;
  for (let t = 0; t < count; t++) {
    s = ask(s, `t${t}`, true);
    for (let f = 0; f < followUps; f++) s = ask(s, `t${t}f${f}`, false);
  }
  return s;
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

test("nothing saved means no history", () => {
  expect(loadHistory()).toBeNull();
});

test("a saved history comes back with its place", () => {
  const s = reduce(threads(2, 1), { type: "navigate", index: 1 });
  saveHistory(s);
  const back = loadHistory()!;
  expect(back.entries.map((entry) => entry.id)).toEqual(["t0", "t0f0", "t1", "t1f0"]);
  expect(back.cursor).toBe(1);
  expect(back.pending).toBeNull();
});

test("corrupt or partial storage is read leniently", () => {
  window.localStorage.setItem(HISTORY_KEY, "{not json");
  expect(loadHistory()).toBeNull();
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify({ entries: [{ id: 3 }, ...threads(1).entries], cursor: 99 }));
  const back = loadHistory()!;
  expect(back.entries).toHaveLength(1);
  expect(back.cursor).toBe(0);
  expect(back.entries[0].root).toBe(true);
});

test(`at most ${MAX_THREADS} threads are kept, the newest`, () => {
  saveHistory(threads(MAX_THREADS + 3, 1));
  const back = loadHistory()!;
  expect(back.entries.filter((entry) => entry.root)).toHaveLength(MAX_THREADS);
  expect(back.entries[0].id).toBe("t3");
});

test("when storage is full the oldest half of the threads go until it fits", () => {
  const real = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
    if (value.length > 3000) throw new DOMException("full", "QuotaExceededError");
    real.call(this, key, value);
  });
  saveHistory(threads(16, 1));
  const back = loadHistory()!;
  const kept = back.entries.filter((entry) => entry.root).length;
  expect(kept).toBeGreaterThan(0);
  expect(kept).toBeLessThan(16);
  expect(back.entries[back.entries.length - 1].id).toBe("t15f0");
});

test("keeping fewer threads moves the cursor with its page, or to the start view", () => {
  const s = threads(3);
  expect(keepThreads({ entries: s.entries, cursor: 2, startView: false }, 2)).toMatchObject({ cursor: 1, startView: false });
  expect(keepThreads({ entries: s.entries, cursor: 0, startView: false }, 2)).toMatchObject({ startView: true });
});

test("the current version is the one in the page contract", () => {
  expect(SCHEMA_VERSION).toMatch(/^\d+$/);
});

test("pages saved under another version of the page contract are dropped", () => {
  const s = threads(3, 1);
  const stale = (id: string) => ({ ...s.entries.find((entry) => entry.id === id)!, response: reply(id, "1") });
  // The oldest thread and the middle thread's opening page were saved by an older build.
  const entries = s.entries.map((entry) => (["t0", "t0f0", "t1"].includes(entry.id) ? stale(entry.id) : entry));
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify({ entries, cursor: 5, startView: false }));
  const back = loadHistory()!;
  expect(back.entries.map((entry) => entry.id)).toEqual(["t1f0", "t2", "t2f0"]);
  // A follow-up that lost its thread's first page begins a thread of its own.
  expect(back.entries[0]).toMatchObject({ root: true, parentId: null });
  expect(back.entries[back.cursor].id).toBe("t2f0");
  expect(back.startView).toBe(false);
});

test("when the page the visitor was on was dropped, they start fresh with the rest kept", () => {
  const s = threads(2);
  const entries = [s.entries[0], { ...s.entries[1], response: reply("t1", "1") }];
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify({ entries, cursor: 1, startView: false }));
  const back = loadHistory()!;
  expect(back.entries.map((entry) => entry.id)).toEqual(["t0"]);
  expect(back.startView).toBe(true);
});

test("a history saved entirely by an older build is no history", () => {
  const s = threads(2);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify({ entries: s.entries.map((entry) => ({ ...entry, response: reply(entry.id, "2-old") })), cursor: 0 }));
  expect(loadHistory()).toBeNull();
});
