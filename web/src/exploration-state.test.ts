import { describe, expect, test } from "vitest";
import { explorationReducer as reduce, initialExploration, requestContext, visible, isAsking, type ExplorationAction, type ExplorationState } from "./exploration-state";
import type { ExperienceResponse } from "./types";

const reply = (title: string, notebook: string | null, extra: Record<string, unknown> = {}) => ({
  schema_version: "2", thread_id: "t", title, answer: `${title} answer`, body_lead: null, mode: "answer",
  conversation: [{ role: "user", text: title }, { role: "assistant", text: `${title} answer` }],
  blocks: [{ type: "show_unit" }], groups: [{ title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [0] }],
  sources: [], notebook, ...extra
}) as unknown as ExperienceResponse;

function run(state: ExplorationState, ...actions: ExplorationAction[]) {
  return actions.reduce(reduce, state);
}
function ask(state: ExplorationState, id: string, title: string, { fresh = false, notebook = `nb-${id}` } = {}) {
  return run(state,
    { type: "submit", requestId: id, question: title, source: "typed", focus: null, fresh, threadId: `th-${id}` },
    { type: "complete", requestId: id, response: reply(title, notebook) });
}

test("two asks make two entries; local view changes make none", () => {
  let s = ask(initialExploration, "r1", "MSG", { fresh: true });
  s = ask(s, "r2", "Late 80s");
  for (let i = 0; i < 10; i += 1) s = reduce(s, { type: "view", patch: { tab: i % 2 ? "charts" : "read", scroll: { read: i } }, interacted: true });
  expect(s.entries.map((e) => e.request)).toEqual(["MSG", "Late 80s"]);
  expect(s.cursor).toBe(1);
});

test("a follow-up from entry 1 sends entry 1's conversation and notebook", () => {
  let s = ask(initialExploration, "r1", "MSG", { fresh: true });
  s = ask(s, "r2", "Late 80s");
  s = reduce(s, { type: "navigate", index: 0 });
  const ctx = requestContext(s, false);
  expect(ctx.notebook).toBe("nb-r1");
  expect(ctx.conversation.map((t) => t.text)).toEqual(["MSG", "MSG answer"]);
  expect(ctx.threadId).toBe("th-r1");
  expect(requestContext(s, true)).toEqual({ conversation: [], notebook: null, threadId: null });
});

describe("branching", () => {
  const twoDeep = () => reduce(ask(ask(initialExploration, "r1", "MSG", { fresh: true }), "r2", "Late 80s"), { type: "navigate", index: 0 });

  test("a successful follow-up from an old entry replaces what came after it", () => {
    const s = ask(twoDeep(), "r3", "Guests");
    expect(s.entries.map((e) => e.request)).toEqual(["MSG", "Guests"]);
    expect(s.entries[1].parentId).toBe("r1");
  });

  test("a successful fresh start from an old entry appends and drops nothing", () => {
    const s = ask(twoDeep(), "r3", "Birthday", { fresh: true });
    expect(s.entries.map((e) => e.request)).toEqual(["MSG", "Late 80s", "Birthday"]);
    expect(s.entries[2].root).toBe(true);
  });

  test("failure and cancel leave history alone", () => {
    let s = run(twoDeep(), { type: "submit", requestId: "r3", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" }, { type: "fail", requestId: "r3", message: "boom" });
    expect(s.entries).toHaveLength(2);
    expect(visible(s).kind).toBe("failed");
    s = run(s, { type: "dismiss" });
    expect(s.pending).toBeNull();
    s = run(s, { type: "submit", requestId: "r4", question: "y", source: "typed", focus: null, fresh: false, threadId: "t" }, { type: "cancel" });
    expect(s.entries).toHaveLength(2);
  });
});

test("events from a stale request are ignored", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "navigate", index: 0 });
  const before = s;
  expect(reduce(s, { type: "answer", requestId: "r2", text: "late" })).toBe(before);
  expect(reduce(s, { type: "complete", requestId: "r2", response: reply("late", null) })).toBe(before);
});

test("only one request at a time", () => {
  const s = run(initialExploration, { type: "submit", requestId: "r1", question: "a", source: "typed", focus: null, fresh: true, threadId: "t" });
  expect(isAsking(s)).toBe(true);
  expect(reduce(s, { type: "submit", requestId: "r2", question: "b", source: "typed", focus: null, fresh: true, threadId: "t" })).toBe(s);
});

describe("opening tab and the visitor's focus", () => {
  const started = () => run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "chip", focus: null, fresh: false, threadId: "t" });

  test("a follow-up holds the previous page until content arrives", () => {
    let s = started();
    expect(visible(s).kind).toBe("held");
    s = reduce(s, { type: "status", requestId: "r2", text: "Looking" });
    expect(visible(s).kind).toBe("held");
    s = reduce(s, { type: "answer", requestId: "r2", text: "Yes" });
    expect(visible(s).kind).toBe("draft");
  });

  test("the model's tab opens unless the visitor has acted", () => {
    let s = run(started(), { type: "initialTab", requestId: "r2", tab: "listen" }, { type: "answer", requestId: "r2", text: "Yes" });
    expect(s.pending?.view.tab).toBe("listen");
    s = reduce(s, { type: "view", patch: { tab: "charts" }, interacted: true });
    s = reduce(s, { type: "initialTab", requestId: "r2", tab: "read" });
    expect(s.pending?.view.tab).toBe("charts");
    s = reduce(s, { type: "complete", requestId: "r2", response: reply("x", null) });
    expect(s.entries[s.cursor].view.tab).toBe("charts");
  });

  test("without a model choice the first content picks once and then stays", () => {
    let s = run(started(), { type: "answer", requestId: "r2", text: "Yes" });
    expect(s.pending?.view.tab).toBe("read");
    s = reduce(s, { type: "page", requestId: "r2", event: { type: "block", group_index: 0, block: { type: "show_unit" } as never } });
    expect(s.pending?.view.tab).toBe("read");
  });
});

test("new chat shows the start view and keeps history", () => {
  const s = reduce(ask(initialExploration, "r1", "MSG", { fresh: true }), { type: "newChat" });
  expect(visible(s).kind).toBe("start");
  expect(s.entries).toHaveLength(1);
  expect(requestContext(s, false).notebook).toBeNull();
});

test("stale fail, page and status events leave the same state object", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "navigate", index: 0 });
  expect(reduce(s, { type: "fail", requestId: "r2", message: "late" })).toBe(s);
  expect(reduce(s, { type: "status", requestId: "r2", text: "late" })).toBe(s);
  expect(reduce(s, { type: "page", requestId: "r2", event: { type: "page_reset" } })).toBe(s);
});

test("view patches go to the held page, then to the draft once content shows", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "view", patch: { tab: "charts" } });
  expect(s.entries[0].view.tab).toBe("charts");
  expect(s.pending?.view.tab).toBeNull();
  s = reduce(s, { type: "answer", requestId: "r2", text: "Yes" });
  s = reduce(s, { type: "view", patch: { tab: "read" }, interacted: true });
  expect(s.pending?.view.tab).toBe("read");
  expect(s.entries[0].view.tab).toBe("charts");
});
