import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import { SCHEMA_VERSION } from "./core/schema-version";

type Turn = { role: "user" | "assistant"; text: string };

function reply(headline: string, notebook: string | null, conversation: Turn[]) {
  return {
    schema_version: SCHEMA_VERSION, thread_id: "web-test", headline, lead: conversation[conversation.length - 1].text,
    mode: "answer", conversation, blocks: [], groups: [], sources: [],
    ...(notebook ? { notebook } : {})
  };
}

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

test("a follow-up sends back the notebook the last answer carried", async () => {
  replies = [europe(), lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(sent[0].notebook).toBeUndefined();
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
});

test("the notebook rides the streamed response too", async () => {
  streaming = true;
  replies = [europe(), lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
});

test("with no answer on screen, the first question sends no notebook and the next sends the new one", async () => {
  replies = [europe(), lyceum()];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(sent[0].notebook).toBeUndefined();
  ask("Tell me about the Lyceum.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
});

test("an answer that carries no notebook clears the stale token", async () => {
  replies = [europe(), lyceum(null), europe("v1.third.sig")];
  await openApp();
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
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

test("a question in the link is asked on arrival and stays in the address bar", async () => {
  replies = [europe()];
  window.history.replaceState({}, "", "/?q=What%27s%20on%20Europe%20%2772%3F");
  await openApp();
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(sent).toHaveLength(1);
  expect(sent[0].question).toBe("What's on Europe '72?");
  expect(new URLSearchParams(window.location.search).get("q")).toBe("What's on Europe '72?");
});

test("an empty question in the link leaves the home screen as it is", async () => {
  window.history.replaceState({}, "", "/?q=%20");
  await openApp();
  expect(sent).toHaveLength(0);
  expect(window.location.search).toBe("");
});
