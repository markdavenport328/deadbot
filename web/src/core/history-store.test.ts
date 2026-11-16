import { afterEach, expect, test, vi } from "vitest";
import { HISTORY_KEY, MAX_THREADS, keepThreads, loadHistory, saveHistory } from "./history-store";
import { explorationReducer as reduce, initialExploration, type ExplorationState } from "./exploration-state";

const reply = (title: string) => ({ schema_version: "2", thread_id: "t", title, answer: "a", conversation: [], blocks: [], groups: [], sources: [] }) as never;
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
