import { afterEach, expect, test, vi } from "vitest";
import { askPlain, askStreaming, isAbort, replayStreamEvents } from "./ask-client";

const response = { schema_version: "2", thread_id: "t", title: "T", answer: "A", conversation: [], blocks: [], groups: [], sources: [] };

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

test("streams statuses, answer and page events, then returns the response", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([
    JSON.stringify({ type: "status", text: "Looking" }),
    JSON.stringify({ type: "answer", text: "Yes" }),
    JSON.stringify({ type: "page_head", title: "T", lead: null }),
    JSON.stringify({ type: "response", response })
  ])));
  const seen: string[] = [];
  const result = await askStreaming("{}", {
    onStatus: (t) => seen.push(`s:${t}`), onAnswer: (t) => seen.push(`a:${t}`), onPage: (e) => seen.push(`p:${e.type}`)
  });
  expect(seen).toEqual(["s:Looking", "a:Yes", "p:page_head"]);
  expect(result?.title).toBe("T");
});

test("404 means no stream: the caller falls back", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
  expect(await askStreaming("{}", { onStatus() {}, onAnswer() {}, onPage() {} })).toBeNull();
});

test("a stream that ends without its response fails instead of re-asking", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([JSON.stringify({ type: "status", text: "x" })])));
  await expect(askStreaming("{}", { onStatus() {}, onAnswer() {}, onPage() {} })).rejects.toThrow("connection closed");
});

test("an error event throws its detail", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([JSON.stringify({ type: "error", detail: "Nope" })])));
  await expect(askStreaming("{}", { onStatus() {}, onAnswer() {}, onPage() {} })).rejects.toThrow("Nope");
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
    { onStatus: (t) => statuses.push(t), onAnswer() {}, onPage() {}, onResponse() {} },
    controller.signal
  );
  await vi.advanceTimersByTimeAsync(300);
  controller.abort();
  await vi.advanceTimersByTimeAsync(1000);
  await done;
  expect(statuses).toEqual(["one"]);
  vi.useRealTimers();
});
