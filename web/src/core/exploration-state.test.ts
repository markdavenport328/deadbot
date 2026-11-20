import { describe, expect, test } from "vitest";
import { addressOf, explorationReducer as reduce, initialExploration, openingFor, requestContext, shownPane, visible, isAsking, type ExplorationAction, type ExplorationState } from "./exploration-state";
import type { ExperienceResponse } from "../types";

const reply = (title: string, notebook: string | null, extra: Record<string, unknown> = {}) => ({
  schema_version: "3", thread_id: "t", headline: title, lead: `${title} answer`, mode: "answer",
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
  for (let i = 0; i < 10; i += 1) s = reduce(s, { type: "view", patch: { scroll: i * 10 }, interacted: true });
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

test("events from a stopped request are ignored", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "cancel" });
  const before = s;
  expect(reduce(s, { type: "lead", requestId: "r2", text: "late" })).toBe(before);
  expect(reduce(s, { type: "complete", requestId: "r2", response: reply("late", null) })).toBe(before);
});

describe("looking at another page while an answer is written", () => {
  const twoThreads = () => ask(ask(ask(initialExploration, "a", "A", { fresh: true }), "a1", "A1"), "b", "B", { fresh: true });
  const submit = (id: string, fresh = false): ExplorationAction => ({ type: "submit", requestId: id, question: `Q ${id}`, source: "typed", focus: null, fresh, threadId: "t" });

  test("the request keeps running, fills in, and lands in the history unread", () => {
    let s = run(twoThreads(), submit("c", true), { type: "navigate", index: 0 });
    expect(isAsking(s)).toBe(true);
    expect(visible(s)).toMatchObject({ kind: "entry", entry: { id: "a" } });
    s = run(s, { type: "status", requestId: "c", text: "Looking" }, { type: "lead", requestId: "c", text: "Yes" });
    expect(s.pending?.lead).toBe("Yes");
    expect(visible(s)).toMatchObject({ kind: "entry", entry: { id: "a" } });
    s = reduce(s, { type: "complete", requestId: "c", response: reply("C", null) });
    expect(s.entries.map((e) => e.id)).toEqual(["a", "a1", "b", "c"]);
    expect(s.entries[3].unseen).toBe(true);
    expect(s.entries[s.cursor].id).toBe("a");
    s = reduce(s, { type: "navigate", index: 3 });
    expect(s.entries[3].unseen).toBeUndefined();
  });

  test("its row goes back to it, and it then finishes on screen", () => {
    let s = run(twoThreads(), submit("c", true), { type: "lead", requestId: "c", text: "Yes" }, { type: "navigate", index: 1 }, { type: "watch" });
    expect(visible(s).kind).toBe("draft");
    s = reduce(s, { type: "complete", requestId: "c", response: reply("C", null) });
    expect(s.entries[s.cursor].id).toBe("c");
    expect(s.entries[s.cursor].unseen).toBeUndefined();
  });

  test("a follow-up that finishes behind a later page of its own thread does not take that page away", () => {
    // Asked from A, then the visitor opens A1, which a follow-up from A would otherwise replace.
    let s = run(twoThreads(), { type: "navigate", index: 0 }, submit("a2"), { type: "navigate", index: 1 });
    s = reduce(s, { type: "complete", requestId: "a2", response: reply("A2", null) });
    expect(s.entries.map((e) => e.id)).toEqual(["a", "a1", "a2", "b"]);
    expect(s.entries[s.cursor].id).toBe("a1");
  });

  test("a follow-up replaces what came after it in its own thread and leaves later threads alone", () => {
    const s = ask(reduce(twoThreads(), { type: "navigate", index: 0 }), "a2", "A2");
    expect(s.entries.map((e) => e.id)).toEqual(["a", "a2", "b"]);
    expect(s.entries[s.cursor].id).toBe("a2");
  });

  test("the start view is a place to go while it runs, and stopping from the page returns to where it was asked", () => {
    let s = run(twoThreads(), submit("c", true), { type: "newChat" });
    expect(isAsking(s)).toBe(true);
    expect(visible(s).kind).toBe("start");
    s = run(reduce(twoThreads(), { type: "newChat" }), submit("d", true), { type: "cancel" });
    expect(visible(s).kind).toBe("start");
  });
});

test("a failed request keeps the draft it had written on screen", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" },
    { type: "lead", requestId: "r2", text: "The runs grew" });
  s = reduce(s, { type: "fail", requestId: "r2", message: "boom" });
  expect(visible(s).kind).toBe("failed");
  expect(shownPane(s)?.id).toBe("r2");
  expect(s.pending?.lead).toBe("The runs grew");
  // Looking elsewhere keeps it; its row brings it back.
  s = run(s, { type: "navigate", index: 0 }, { type: "watch" });
  expect(shownPane(s)?.id).toBe("r2");
  // With nothing written, the page it was asked from stays instead.
  let bare = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  bare = reduce(bare, { type: "fail", requestId: "r2", message: "boom" });
  expect(shownPane(bare)?.id).toBe("r1");
});

describe("addresses", () => {
  const history = () => ask(ask(ask(initialExploration, "a", "Best Morning Dew?", { fresh: true }), "a1", "And in 1977?"), "b", "MSG", { fresh: true });

  test("a page is named by its question; a follow-up by its thread's first question and then its own", () => {
    const s = history();
    expect(addressOf(s)).toEqual({ page: "b", question: "MSG", followUp: null, title: "MSG" });
    expect(addressOf(reduce(s, { type: "navigate", index: 1 }))).toMatchObject({ page: "a1", question: "Best Morning Dew?", followUp: "And in 1977?" });
    expect(addressOf(reduce(s, { type: "newChat" }))).toEqual({ page: null, question: null, followUp: null, title: null });
    const asking = reduce(reduce(s, { type: "navigate", index: 0 }), { type: "submit", requestId: "a2", question: "And in 1989?", source: "typed", focus: null, fresh: false, threadId: "t" });
    expect(addressOf(asking)).toMatchObject({ page: "a2", question: "Best Morning Dew?", followUp: "And in 1989?", title: "And in 1989?" });
  });

  test("an address opens the saved page by its id or by its question, without asking", () => {
    const s = history();
    expect(openingFor(s, { page: "a1", question: "anything", followUp: null })).toEqual({ kind: "entry", index: 1, offer: null });
    expect(openingFor(s, { page: "gone", question: "  best morning   dew? ", followUp: null })).toEqual({ kind: "entry", index: 0, offer: null });
    expect(openingFor(s, { question: "Best Morning Dew?", followUp: "And in 1977?" })).toEqual({ kind: "entry", index: 1, offer: null });
    expect(openingFor(s, { question: null, followUp: null })).toEqual({ kind: "start" });
  });

  test("a question this browser has no page for is asked fresh", () => {
    expect(openingFor(history(), { question: "Best Dark Star?", followUp: null })).toEqual({ kind: "ask", question: "Best Dark Star?", offer: null });
    // A follow-up's own words are not a fresh question's page.
    expect(openingFor(history(), { question: "And in 1977?", followUp: null })).toMatchObject({ kind: "ask" });
  });

  test("a follow-up this browser does not have opens its thread's first page and is offered, not asked", () => {
    expect(openingFor(history(), { question: "Best Morning Dew?", followUp: "And in 1989?" })).toEqual({ kind: "entry", index: 0, offer: "And in 1989?" });
    expect(openingFor(initialExploration, { question: "Best Morning Dew?", followUp: "And in 1989?" })).toEqual({ kind: "ask", question: "Best Morning Dew?", offer: "And in 1989?" });
  });

  test("the request in flight is found by its id", () => {
    const s = reduce(history(), { type: "submit", requestId: "c", question: "Veneta", source: "typed", focus: null, fresh: true, threadId: "t" });
    expect(openingFor(s, { page: "c", question: "Veneta", followUp: null })).toEqual({ kind: "pending" });
  });
});

test("only one request at a time", () => {
  const s = run(initialExploration, { type: "submit", requestId: "r1", question: "a", source: "typed", focus: null, fresh: true, threadId: "t" });
  expect(isAsking(s)).toBe(true);
  expect(reduce(s, { type: "submit", requestId: "r2", question: "b", source: "typed", focus: null, fresh: true, threadId: "t" })).toBe(s);
});

describe("the page being written and the visitor's place", () => {
  const started = () => run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "chip", focus: null, fresh: false, threadId: "t" });

  test("a follow-up holds the previous page until content arrives", () => {
    let s = started();
    expect(visible(s).kind).toBe("held");
    s = reduce(s, { type: "status", requestId: "r2", text: "Looking" });
    expect(visible(s).kind).toBe("held");
    s = reduce(s, { type: "lead", requestId: "r2", text: "Yes" });
    expect(visible(s).kind).toBe("draft");
  });

  test("the scroll the visitor reached on the draft carries into the finished page", () => {
    let s = run(started(), { type: "lead", requestId: "r2", text: "Yes" });
    s = reduce(s, { type: "view", patch: { scroll: 420 }, interacted: true });
    s = reduce(s, { type: "complete", requestId: "r2", response: reply("x", null) });
    expect(s.entries[s.cursor].view.scroll).toBe(420);
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
  s = reduce(s, { type: "cancel" });
  expect(reduce(s, { type: "fail", requestId: "r2", message: "late" })).toBe(s);
  expect(reduce(s, { type: "status", requestId: "r2", text: "late" })).toBe(s);
  expect(reduce(s, { type: "page", requestId: "r2", event: { type: "page_reset" } })).toBe(s);
});

test("view patches go to the held page, then to the draft once content shows", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "view", patch: { scroll: 300 } });
  expect(s.entries[0].view.scroll).toBe(300);
  expect(s.pending?.view.scroll).toBeNull();
  s = reduce(s, { type: "lead", requestId: "r2", text: "Yes" });
  s = reduce(s, { type: "view", patch: { scroll: 80 }, interacted: true });
  expect(s.pending?.view.scroll).toBe(80);
  expect(s.entries[0].view.scroll).toBe(300);
});
