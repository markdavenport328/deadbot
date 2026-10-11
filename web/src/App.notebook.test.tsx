import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";

type Turn = { role: "user" | "assistant"; text: string };

function reply(title: string, notebook: string | null, conversation: Turn[]) {
  return {
    schema_version: "2", thread_id: "web-test", title, answer: conversation[conversation.length - 1].text,
    body_lead: null, mode: "answer", conversation, blocks: [], groups: [], sources: [],
    ...(notebook ? { notebook } : {})
  };
}

const KEY = "deadbot-research-notebook";
const sent: Record<string, unknown>[] = [];
let replies: (ReturnType<typeof reply> | "fail")[] = [];
let streaming = false;

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false
  })) as typeof window.matchMedia;
  Element.prototype.scrollIntoView = function scrollIntoView() {};
  Element.prototype.scrollTo = function scrollTo() {} as typeof Element.prototype.scrollTo;
  window.scrollTo = (() => {}) as typeof window.scrollTo;
});

function next(init?: RequestInit) {
  sent.push(JSON.parse(String(init?.body)));
  return replies.shift();
}

beforeEach(() => {
  sent.length = 0;
  streaming = false;
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    if (path.endsWith("/api/experience/stream")) {
      if (!streaming) return new Response(null, { status: 404 });
      const answer = next(init);
      if (answer === "fail") return new Response(JSON.stringify({ detail: "no" }), { status: 500 });
      const lines = [{ type: "status", text: "Looking." }, { type: "response", response: answer }];
      return new Response(lines.map((line) => JSON.stringify(line)).join("\n") + "\n", { status: 200 });
    }
    if (path.endsWith("/api/experience")) {
      const answer = next(init);
      if (answer === "fail") return new Response(JSON.stringify({ detail: "no" }), { status: 500 });
      return new Response(JSON.stringify(answer), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(null, { status: 404 });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function ask(text: string) {
  const box = screen.getAllByLabelText("Question").find((element) => !(element as HTMLTextAreaElement).disabled) as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

async function openApp() {
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
}

const europe = (notebook: string | null = "v1.first.sig") =>
  reply("Europe '72", notebook, [
    { role: "user", text: "What's on Europe '72?" }, { role: "assistant", text: "Twenty-two nights." }
  ]);
const lyceum = (notebook: string | null = "v1.second.sig") =>
  reply("The Lyceum", notebook, [
    { role: "user", text: "What's on Europe '72?" }, { role: "assistant", text: "Twenty-two nights." },
    { role: "user", text: "Tell me about the last Lyceum night." }, { role: "assistant", text: "May 26, 1972." }
  ]);

test("a follow-up sends back the notebook the last answer carried, and the tab keeps the newest", async () => {
  replies = [europe(), lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(sent[0].notebook).toBeUndefined();
  expect(window.sessionStorage.getItem(KEY)).toBe("v1.first.sig");
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
  expect(window.sessionStorage.getItem(KEY)).toBe("v1.second.sig");
});

test("the notebook rides the streamed response too", async () => {
  streaming = true;
  replies = [europe(), lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(window.sessionStorage.getItem(KEY)).toBe("v1.first.sig");
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
  expect(window.sessionStorage.getItem(KEY)).toBe("v1.second.sig");
});

test("a reload keeps the notebook for the next question", async () => {
  window.sessionStorage.setItem(KEY, "v1.kept.sig");
  replies = [europe()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(sent[0].notebook).toBe("v1.kept.sig");
});

test("an answer that carries no notebook clears the stale token", async () => {
  replies = [europe(), lyceum(null), europe("v1.third.sig")];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
  expect(window.sessionStorage.getItem(KEY)).toBeNull();
  ask("And the next one?");
  await vi.waitFor(() => expect(sent).toHaveLength(3));
  expect(sent[2].notebook).toBeUndefined();
});

test("a failed turn keeps the last notebook", async () => {
  replies = [europe(), "fail", lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  ask("Tell me about the last Lyceum night.");
  await vi.waitFor(() => expect(sent).toHaveLength(2));
  await vi.waitFor(() => expect(screen.getAllByLabelText("Question").some((e) => !(e as HTMLTextAreaElement).disabled)).toBe(true));
  expect(window.sessionStorage.getItem(KEY)).toBe("v1.first.sig");
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[2].notebook).toBe("v1.first.sig");
});

test("New chat forgets the notebook, so the next question sends none", async () => {
  replies = [europe(), europe("v1.other.sig")];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  fireEvent.click(screen.getByRole("button", { name: /new chat/i }));
  expect(window.sessionStorage.getItem(KEY)).toBeNull();
  ask("What's on Europe '72?");
  await vi.waitFor(() => expect(sent).toHaveLength(2));
  expect(sent[1].notebook).toBeUndefined();
});

test("with sessionStorage unavailable the notebook still travels in memory", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
  replies = [europe(), lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
});
