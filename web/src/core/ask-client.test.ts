import { afterEach, expect, test, vi } from "vitest";
import { ASK_ERROR, MAX_QUESTION_LENGTH, askPlain, askStreaming, dispatchStreamEvent, isAbort, refusalMessage, replayStreamEvents } from "./ask-client";

const response = { schema_version: "3", thread_id: "t", headline: "T", lead: "A", conversation: [], blocks: [], groups: [], sources: [] };

function streamOf(lines: string[], { status = 200 } = {}) {
  const text = lines.join("\n");
  const body = new ReadableStream({
    start(controller) {
      // Split mid-line to prove buffering.
      const bytes = new TextEncoder().encode(text);
      controller.enqueue(bytes.slice(0, 7));
      controller.enqueue(bytes.slice(7));
      controller.close();
    }
  });
  return new Response(body, { status });
}

afterEach(() => vi.unstubAllGlobals());

test("streams statuses, lead and page events, then returns the response", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([
    JSON.stringify({ type: "status", text: "Looking" }),
    JSON.stringify({ type: "lead", text: "Yes" }),
    JSON.stringify({ type: "page_head", headline: "T", lead: null }),
    JSON.stringify({ type: "response", response })
  ])));
  const seen: string[] = [];
  const result = await askStreaming("{}", {
    onStatus: (t) => seen.push(`s:${t}`), onLead: (t) => seen.push(`a:${t}`), onPage: (e) => seen.push(`p:${e.type}`)
  });
  expect(seen).toEqual(["s:Looking", "a:Yes", "p:page_head"]);
  expect(result?.headline).toBe("T");
});

test("404 means no stream: the caller falls back", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
  expect(await askStreaming("{}", { onStatus() {}, onLead() {}, onPage() {} })).toBeNull();
});

test("a stream that ends without its response fails instead of re-asking", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([JSON.stringify({ type: "status", text: "x" })])));
  await expect(askStreaming("{}", { onStatus() {}, onLead() {}, onPage() {} })).rejects.toThrow("connection closed");
});

test("an error event throws its detail", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([JSON.stringify({ type: "error", detail: "Nope" })])));
  await expect(askStreaming("{}", { onStatus() {}, onLead() {}, onPage() {} })).rejects.toThrow("Nope");
});

test("the signal reaches fetch, and an abort is recognisable", async () => {
  const controller = new AbortController();
  const fetchMock = vi.fn(async (_url: unknown, init?: RequestInit) => {
    expect(init?.signal).toBe(controller.signal);
    throw new DOMException("aborted", "AbortError");
  });
  vi.stubGlobal("fetch", fetchMock);
  controller.abort();
  const error = await askPlain("{}", controller.signal).catch((e) => e);
  expect(isAbort(error)).toBe(true);
});

test("replay stops once aborted", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const statuses: string[] = [];
  const done = replayStreamEvents(
    [{ type: "status", text: "one" }, { type: "status", text: "two" }],
    { onStatus: (t) => statuses.push(t), onLead() {}, onPage() {}, onResponse() {} },
    controller.signal
  );
  await vi.advanceTimersByTimeAsync(300);
  controller.abort();
  await vi.advanceTimersByTimeAsync(1000);
  await done;
  expect(statuses).toEqual(["one"]);
  vi.useRealTimers();
});

it("hands a page_tab event to the page handler", () => {
  const seen: string[] = [];
  dispatchStreamEvent({ type: "page_tab", tab: "listen" }, { onStatus() {}, onLead() {}, onPage: (event) => seen.push(event.type), onResponse() {} });
  expect(seen).toEqual(["page_tab"]);
});

const refused = (status: number, body: unknown) => new Response(typeof body === "string" ? body : JSON.stringify(body), { status });

test("a question the server finds too long is answered with a sentence, not [object Object]", async () => {
  const detail = [{ type: "string_too_long", loc: ["body", "question"], msg: "String should have at most 2000 characters", input: "x", ctx: { max_length: 2000 } }];
  vi.stubGlobal("fetch", vi.fn(async () => refused(422, { detail })));
  const noop = { onStatus() {}, onLead() {}, onPage() {} };
  await expect(askStreaming("{}", noop)).rejects.toThrow(/too long.*2,000 characters/);
  await expect(askPlain("{}")).rejects.toThrow(/too long.*2,000 characters/);
  expect(MAX_QUESTION_LENGTH).toBe(2000);
});

test("other refusals read as sentences too", async () => {
  expect(await refusalMessage(refused(422, { detail: [{ type: "missing", loc: ["body", "question"], msg: "Field required" }] }))).toMatch(/could not read that question/);
  expect(await refusalMessage(refused(429, { detail: "You have asked a lot in the last hour. Try again after 3:15." }))).toBe("You have asked a lot in the last hour. Try again after 3:15.");
  expect(await refusalMessage(refused(429, "slow down"))).toMatch(/Give it a minute/);
  expect(await refusalMessage(refused(429, { detail: [{ msg: "x" }] }))).toMatch(/Give it a minute/);
  expect(await refusalMessage(refused(500, { detail: { code: 7 } }))).toBe(ASK_ERROR);
  expect(await refusalMessage(refused(500, { detail: "The library is being rebuilt." }))).toBe("The library is being rebuilt.");
});
