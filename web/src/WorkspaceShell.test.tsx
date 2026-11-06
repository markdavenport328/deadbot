import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import type { ExperienceBlock, ExperienceResponse } from "./types";
import { visualFixtures } from "./visual-fixtures";

// The workspace shell behind ?shell=workspace: history, tabs, the held
// previous page, and the player carrying on through all of it.

type Turn = { role: "user" | "assistant"; text: string };
type Reply =
  | { kind: "plain"; body: ExperienceResponse }
  | { kind: "stream"; chunks: (object | Promise<void>)[] }
  | "reject";

function page(title: string, notebook: string | null, conversation: Turn[], blocks: ExperienceBlock[] = [], groups: ExperienceResponse["groups"] = []): ExperienceResponse {
  return {
    schema_version: "2", thread_id: "web-test", title, answer: conversation[conversation.length - 1].text,
    body_lead: null, mode: "answer", conversation, blocks, groups, sources: [],
    ...(notebook ? { notebook } : {})
  } as ExperienceResponse;
}

const sent: Record<string, unknown>[] = [];
let replies: Reply[] = [];
let plainNext: ExperienceResponse | null = null;
let phone = false;

function streamOf(chunks: (object | Promise<void>)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      for (const chunk of chunks) {
        if (chunk instanceof Promise) await chunk;
        else controller.enqueue(encoder.encode(JSON.stringify(chunk) + "\n"));
      }
      controller.close();
    }
  });
}

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: phone && query.includes("max-width"), media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false
  })) as typeof window.matchMedia;
  Element.prototype.scrollIntoView = function scrollIntoView() {};
  Element.prototype.scrollTo = function scrollTo() {} as typeof Element.prototype.scrollTo;
  window.scrollTo = (() => {}) as typeof window.scrollTo;
  HTMLMediaElement.prototype.play = function play() { return Promise.resolve(); };
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.load = function load() {};
});

beforeEach(() => {
  sent.length = 0;
  plainNext = null;
  phone = false;
  window.sessionStorage.clear();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/?shell=workspace");
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    if (path.endsWith("/api/experience/stream")) {
      sent.push(JSON.parse(String(init?.body)));
      const reply = replies.shift();
      if (!reply || reply === "reject") throw new TypeError("Failed to fetch");
      if (reply.kind === "plain") {
        plainNext = reply.body;
        return new Response(null, { status: 404 });
      }
      return new Response(streamOf(reply.chunks), { status: 200 });
    }
    if (path.endsWith("/api/experience")) {
      return new Response(JSON.stringify(plainNext), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(null, { status: 404 });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

async function openWorkspace() {
  vi.resetModules();
  const { default: AppWithPlayer } = await import("./App");
  render(<AppWithPlayer />);
}

function ask(text: string) {
  const box = screen.getByLabelText("Question") as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

const rows = () => Array.from(document.querySelectorAll<HTMLButtonElement>(".history-row"));
const rail = () => document.querySelector(".workspace-rail") as HTMLElement;
const tab = (name: string) => screen.getByRole("tab", { name: new RegExp(`^${name}`) });

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const factGrid: ExperienceBlock = {
  type: "editorial", presentation: "fact_grid", eyebrow: null, title: "The runs", paragraphs: [],
  items: [{ marker: "Nights", title: "52", value: null, detail: "Across sixteen years.", link: null, follow_ups: [{ label: "Late ’80s", question: "Focus on the late ’80s" }] }]
} as ExperienceBlock;

const msgTurns: Turn[] = [{ role: "user", text: "MSG" }, { role: "assistant", text: "They played the Garden 52 times." }];
const msg = () => page("The Garden years", "v1.msg.sig", msgTurns, [factGrid], [{ presentation: "collection", criteria: [], block_indexes: [0] }]);
const late80sTurns: Turn[] = [...msgTurns, { role: "user", text: "Focus on the late ’80s" }, { role: "assistant", text: "The runs grew to nine nights." }];
const late80s = () => page("The late-’80s runs", "v1.late.sig", late80sTurns);

test("two asks make two history rows and two requests", async () => {
  replies = [{ kind: "plain", body: msg() }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  fireEvent.click(screen.getByRole("button", { name: "Late ’80s" }));
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  expect(rows()).toHaveLength(2);
  expect(sent).toHaveLength(2);
});

test("going back is free, keeps the later row, and a follow-up from there sends that entry's context", async () => {
  replies = [{ kind: "plain", body: msg() }, { kind: "plain", body: late80s() }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });

  fireEvent.click(rows()[0]);
  expect(sent).toHaveLength(2);
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeInTheDocument();
  expect(rows()).toHaveLength(2);
  expect(rows()[1]).toHaveClass("ahead");
  expect(window.sessionStorage.getItem("deadbot-research-notebook")).toBe("v1.msg.sig");

  ask("Which run had guests?");
  await vi.waitFor(() => expect(sent).toHaveLength(3));
  expect(sent[2].conversation).toEqual(msgTurns);
  expect(sent[2].notebook).toBe("v1.msg.sig");
});

test("an answer-only page grays Listen and Charts and keeps the rail to the request", async () => {
  const birthday = page("Jerry Garcia's birthday", null, [{ role: "user", text: "When was Jerry born?" }, { role: "assistant", text: "August 1, 1942, in San Francisco." }]);
  replies = [{ kind: "plain", body: birthday }];
  await openWorkspace();
  ask("When was Jerry born?");
  await screen.findByRole("heading", { level: 1, name: "Jerry Garcia's birthday" });
  expect(tab("Listen")).toHaveAttribute("aria-disabled", "true");
  expect(tab("Charts")).toHaveAttribute("aria-disabled", "true");
  expect(tab("Read")).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveTextContent("August 1, 1942, in San Francisco.");
  expect(within(rail()).queryByText(/August 1, 1942/)).toBeNull();
  expect(rows()).toHaveLength(1);
});

test("a tab the visitor picks mid-stream survives later groups and the final response", async () => {
  const show = clone(visualFixtures.harrisburg.blocks[0]);
  const editorial: ExperienceBlock = { type: "editorial", presentation: "narrative", eyebrow: null, title: "Why it mattered", paragraphs: ["The room changed the band."], items: [] } as ExperienceBlock;
  const final = page("Harrisburg", null, [{ role: "user", text: "Harrisburg?" }, { role: "assistant", text: "Twice." }], [show, editorial], [
    { presentation: "collection", criteria: [], block_indexes: [0] },
    { presentation: "argument", criteria: [], block_indexes: [1] }
  ]);
  let release!: () => void;
  const hold = new Promise<void>((resolve) => { release = resolve; });
  const meta = (index: number, presentation: string) => ({ index, title: null, lead: null, presentation, criteria: [] });
  replies = [{ kind: "stream", chunks: [
    { type: "status", text: "Looking." },
    { type: "answer", text: "Twice." },
    { type: "page_head", title: "Harrisburg", lead: null },
    { type: "group_open", ...meta(0, "collection") },
    { type: "block", group_index: 0, block: show },
    hold,
    { type: "group_close", ...meta(0, "collection") },
    { type: "group_open", ...meta(1, "argument") },
    { type: "block", group_index: 1, block: editorial },
    { type: "group_close", ...meta(1, "argument") },
    { type: "response", response: final }
  ] }];
  await openWorkspace();
  ask("Harrisburg?");
  await vi.waitFor(() => expect(document.querySelector("article.show-unit")).not.toBeNull());
  fireEvent.click(tab("Charts"));
  expect(tab("Charts")).toHaveAttribute("aria-selected", "true");
  await act(async () => { release(); });
  await vi.waitFor(() => expect(rows()).toHaveLength(1));
  expect(tab("Charts")).toHaveAttribute("aria-selected", "true");
  expect(tab("Charts")).toHaveAttribute("aria-disabled", "true");
});

test("the player keeps playing through requests and history moves", async () => {
  const withTape = clone(visualFixtures.harrisburg);
  const show = withTape.blocks[0] as Extract<ExperienceBlock, { type: "show_unit" }>;
  show.sets[0].songs.forEach((song, index) => {
    song.audio_url = `https://archive.org/download/gd1983-06-22/d1t0${index + 1}.mp3`;
  });
  const first = { ...withTape, notebook: undefined, conversation: msgTurns };
  replies = [{ kind: "plain", body: first }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: withTape.title });
  const play = document.querySelector(".exploration-pane:not([hidden]) .card-head .card-play") as HTMLElement;
  await act(async () => { fireEvent.click(play); });
  const nowPlaying = () => screen.getByRole("region", { name: "Now playing" }).querySelector(".now-playing-title")?.textContent;
  const title = nowPlaying();
  expect(title).toBeTruthy();
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  fireEvent.click(rows()[0]);
  fireEvent.click(tab("Read"));
  expect(nowPlaying()).toBe(title);
});

test("a failed request keeps the previous page and Retry sends the same request again", async () => {
  replies = [{ kind: "plain", body: msg() }, "reject", { kind: "plain", body: late80s() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Deadbot couldn't finish “Focus on the late ’80s”.");
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeInTheDocument();
  fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  expect(sent).toHaveLength(3);
  expect({ ...sent[2], thread_id: null }).toEqual({ ...sent[1], thread_id: null });
  expect(sent[2].thread_id).toBe(sent[1].thread_id);
});

test("clicking the held previous page does not count as taking over the new one", async () => {
  let release!: () => void;
  const hold = new Promise<void>((resolve) => { release = resolve; });
  replies = [{ kind: "plain", body: msg() }, { kind: "stream", chunks: [
    { type: "status", text: "Narrowing to 1987–1989" },
    hold,
    { type: "answer", text: "The runs grew to nine nights." },
    { type: "response", response: late80s() }
  ] }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  const banner = await screen.findByText(/Working on “Focus on the late ’80s”/);
  expect(banner.closest("[role=status]")).not.toBeNull();
  const held = document.querySelector(".exploration-pane.previous") as HTMLElement;
  expect(held).not.toBeNull();
  expect(within(held).getByText("Previous result")).toBeInTheDocument();
  fireEvent.pointerDown(held);
  fireEvent.click(tab("Read"));
  await act(async () => { release(); });
  const heading = await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  expect(document.activeElement).toBe(heading);
});

test("while a request runs, the composer and Ask chips start nothing new", async () => {
  let release!: () => void;
  const hold = new Promise<void>((resolve) => { release = resolve; });
  replies = [{ kind: "plain", body: msg() }, { kind: "stream", chunks: [
    { type: "status", text: "Looking." }, hold, { type: "response", response: late80s() }
  ] }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  await screen.findByText(/Working on/);
  ask("Something else");
  fireEvent.click(screen.getByRole("button", { name: "Late ’80s" }));
  expect(sent).toHaveLength(2);
  await act(async () => { release(); });
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
});

test("on a phone, history lives in the site menu and choosing a row closes it", async () => {
  phone = true;
  replies = [{ kind: "plain", body: msg() }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  expect(rail()).toBeNull();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));
  const menu = document.getElementById("site-menu") as HTMLElement;
  expect(menu).toHaveClass("open");
  const menuRows = menu.querySelectorAll<HTMLButtonElement>(".history-row");
  expect(menuRows).toHaveLength(2);
  fireEvent.click(menuRows[0]);
  expect(menu).not.toHaveClass("open");
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeInTheDocument();
  expect(sent).toHaveLength(2);
});

test("the msg-workspace stream lands a Listen card before the Read story", async () => {
  const { streamEventsFor } = await import("./visual-fixtures");
  const { fallbackTab } = await import("./tab-routing");
  const blocks = streamEventsFor("msg-workspace").flatMap((event) => (event.type === "block" ? [event.block] : []));
  const firstListen = blocks.findIndex((block) => fallbackTab(block) === "listen");
  const firstStory = blocks.findIndex((block) => block.type === "editorial");
  expect(firstListen).toBeGreaterThanOrEqual(0);
  expect(firstListen).toBeLessThan(firstStory);
  expect(blocks.some((block) => fallbackTab(block) === "charts")).toBe(true);
});

test("the wordmark goes to the start view without reloading, and history stays", async () => {
  replies = [{ kind: "plain", body: msg() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  const wordmark = within(rail()).getByRole("link", { name: "Deadbot" });
  expect(fireEvent.click(wordmark)).toBe(false);
  expect(screen.getByRole("heading", { level: 1, name: /Exploration and listening/ })).toBeInTheDocument();
  expect(rows()).toHaveLength(1);
});

test("a tab already looked at during a request does not get its new mark again", async () => {
  const show = clone(visualFixtures.harrisburg.blocks[0]);
  const second = clone(visualFixtures.harrisburg.blocks[1]);
  let release!: () => void;
  const hold = new Promise<void>((resolve) => { release = resolve; });
  const final = page("Harrisburg", null, [{ role: "user", text: "Harrisburg?" }, { role: "assistant", text: "Twice." }], [show, second], [
    { presentation: "collection", criteria: [], block_indexes: [0, 1] }
  ]);
  const meta = { index: 0, title: null, lead: null, presentation: "collection", criteria: [] };
  replies = [{ kind: "stream", chunks: [
    { type: "answer", text: "Twice." },
    { type: "group_open", ...meta },
    { type: "block", group_index: 0, block: show },
    hold,
    { type: "block", group_index: 0, block: second },
    { type: "group_close", ...meta },
    { type: "response", response: final }
  ] }];
  await openWorkspace();
  ask("Harrisburg?");
  await vi.waitFor(() => expect(tab("Listen")).toHaveTextContent("has new content"));
  fireEvent.click(tab("Listen"));
  fireEvent.click(tab("Read"));
  expect(tab("Listen")).not.toHaveTextContent("has new content");
  await act(async () => { release(); });
  await vi.waitFor(() => expect(rows()).toHaveLength(1));
});

test("on a phone, the player folds while the dock's ask box has focus", async () => {
  phone = true;
  const withTape = clone(visualFixtures.harrisburg);
  const show = withTape.blocks[0] as Extract<ExperienceBlock, { type: "show_unit" }>;
  show.sets[0].songs.forEach((song, index) => {
    song.audio_url = `https://archive.org/download/gd1983-06-22/d1t0${index + 1}.mp3`;
  });
  replies = [{ kind: "plain", body: { ...withTape, conversation: msgTurns } }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: withTape.title });
  const play = document.querySelector(".exploration-pane:not([hidden]) .card-head .card-play") as HTMLElement;
  await act(async () => { fireEvent.click(play); });
  const bar = () => document.querySelector(".mobile-dock .now-playing-bar") as HTMLElement;
  fireEvent.focus(screen.getByLabelText("Question"));
  expect(bar()).toHaveClass("collapsed");
});
