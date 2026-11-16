import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import type { ExperienceBlock, ExperienceResponse } from "../../types";
import { visualFixtures } from "../../visual-fixtures";

// The workspace shell behind ?shell=workspace: history, tabs, the held
// previous page, and the player carrying on through all of it.

type Turn = { role: "user" | "assistant"; text: string };
type Reply =
  | { kind: "plain"; body: ExperienceResponse }
  | { kind: "stream"; chunks: (object | Promise<void>)[] }
  | "reject";

function page(headline: string | null, notebook: string | null, conversation: Turn[], blocks: ExperienceBlock[] = [], groups: ExperienceResponse["groups"] = []): ExperienceResponse {
  return {
    schema_version: "3", thread_id: "web-test", headline, lead: conversation[conversation.length - 1].text,
    mode: "answer", conversation, blocks, groups, sources: [],
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
  const { default: AppWithPlayer } = await import("../../App");
  render(<AppWithPlayer />);
}

function ask(text: string) {
  const box = screen.getByLabelText("Question") as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

const rows = () => Array.from(document.querySelectorAll<HTMLButtonElement>(".history-row"));
const rail = () => document.querySelector(".workspace-rail") as HTMLElement;
const column = () => document.querySelector(".exploration-pane:not([hidden]) .workspace-panel") as HTMLElement;

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

test("a page is one column: no tab bar, the lead once above the sections, the rail keeps the request", async () => {
  const birthday = page("Jerry Garcia's birthday", null, [{ role: "user", text: "When was Jerry born?" }, { role: "assistant", text: "August 1, 1942, in San Francisco." }]);
  replies = [{ kind: "plain", body: birthday }];
  await openWorkspace();
  ask("When was Jerry born?");
  await screen.findByRole("heading", { level: 1, name: "Jerry Garcia's birthday" });
  expect(screen.queryByRole("tablist")).toBeNull();
  expect(screen.queryByRole("tab")).toBeNull();
  expect(screen.getAllByText("August 1, 1942, in San Francisco.")).toHaveLength(1);
  expect(column()).not.toHaveTextContent("August 1, 1942");
  expect(within(rail()).queryByText(/August 1, 1942/)).toBeNull();
  expect(rows()).toHaveLength(1);
});

test("the headline sits above the lead, and the lead above the sections", async () => {
  const birthday = page("Jerry Garcia's birthday", null, [{ role: "user", text: "When was Jerry born?" }, { role: "assistant", text: "August 1, 1942, in San Francisco." }]);
  replies = [{ kind: "plain", body: birthday }];
  await openWorkspace();
  ask("When was Jerry born?");
  const heading = await screen.findByRole("heading", { level: 1, name: "Jerry Garcia's birthday" });
  const lead = screen.getByText("August 1, 1942, in San Francisco.");
  expect(heading.compareDocumentPosition(lead) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(lead.compareDocumentPosition(column()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("a page without a headline opens with just the lead", async () => {
  const bare = page(null, null, [{ role: "user", text: "When was Jerry born?" }, { role: "assistant", text: "August 1, 1942, in San Francisco." }]);
  replies = [{ kind: "plain", body: bare }];
  await openWorkspace();
  ask("When was Jerry born?");
  const lead = await screen.findByText("August 1, 1942, in San Francisco.");
  expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  expect(lead.compareDocumentPosition(column()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("sections stream in and stay in the model's order, show before story, from draft to final", async () => {
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
    { type: "lead", text: "Twice." },
    { type: "page_head", title: "Harrisburg", lead: null },
    { type: "page_tab", tab: "charts" },
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
  await vi.waitFor(() => expect(column().querySelector("article.show-unit")).not.toBeNull());
  expect(screen.getByText("Twice.")).toBeVisible();
  await act(async () => { release(); });
  await vi.waitFor(() => expect(rows()).toHaveLength(1));
  const showCard = column().querySelector("article.show-unit") as HTMLElement;
  const story = within(column()).getByText("Why it mattered");
  expect(showCard.compareDocumentPosition(story) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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
  await screen.findByRole("heading", { level: 1, name: withTape.headline ?? "" });
  const play = document.querySelector(".exploration-pane:not([hidden]) .card-head .card-play") as HTMLElement;
  await act(async () => { fireEvent.click(play); });
  const nowPlaying = () => screen.getByRole("region", { name: "Now playing" }).querySelector(".now-playing-title")?.textContent;
  const title = nowPlaying();
  expect(title).toBeTruthy();
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  fireEvent.click(rows()[0]);
  expect(nowPlaying()).toBe(title);
});

test("on a desktop, the ask box sits at the foot of the answer pane and the player runs below both columns", async () => {
  const withTape = clone(visualFixtures.harrisburg);
  const show = withTape.blocks[0] as Extract<ExperienceBlock, { type: "show_unit" }>;
  show.sets[0].songs.forEach((song, index) => {
    song.audio_url = `https://archive.org/download/gd1983-06-22/d1t0${index + 1}.mp3`;
  });
  replies = [{ kind: "plain", body: { ...withTape, conversation: msgTurns } }];
  await openWorkspace();
  expect(rail().querySelector("textarea")).toBeNull();
  expect(document.querySelector(".workspace-main > .pane-composer textarea")).toBe(screen.getByLabelText("Question"));
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: withTape.headline ?? "" });
  const play = document.querySelector(".exploration-pane:not([hidden]) .card-head .card-play") as HTMLElement;
  await act(async () => { fireEvent.click(play); });
  const dock = document.querySelector(".workspace-shell > .player-dock") as HTMLElement;
  expect(dock.querySelector(".now-playing-bar")).not.toBeNull();
  expect(document.querySelector(".workspace-main .now-playing-bar")).toBeNull();
});

test("on a wide desktop the queue has its own rail, and the bar's queue button goes to it", async () => {
  const withTape = clone(visualFixtures.harrisburg);
  const show = withTape.blocks[0] as Extract<ExperienceBlock, { type: "show_unit" }>;
  show.sets[0].songs.forEach((song, index) => {
    song.audio_url = `https://archive.org/download/gd1983-06-22/d1t0${index + 1}.mp3`;
  });
  replies = [{ kind: "plain", body: { ...withTape, conversation: msgTurns } }];
  await openWorkspace();
  expect(document.querySelector(".queue-rail")).toBeNull();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: withTape.headline ?? "" });
  const play = document.querySelector(".exploration-pane:not([hidden]) .card-head .card-play") as HTMLElement;
  await act(async () => { fireEvent.click(play); });
  const rail = document.querySelector(".workspace-grid > .queue-rail") as HTMLElement;
  expect(within(rail).getByRole("region", { name: "Queue" })).toBeInTheDocument();
  const button = screen.getByRole("button", { name: /^Queue,/ });
  expect(button).not.toHaveAttribute("aria-expanded");
  await act(async () => { fireEvent.click(button); });
  await vi.waitFor(() => expect(document.getElementById("queue-rail")).toHaveFocus());
  expect(document.querySelector(".player-dock .now-playing-queue")).toBeNull();

  // Collapsed, the rail is a slim strip; the bar's queue button opens it again.
  fireEvent.click(within(rail).getByRole("button", { name: "Collapse queue" }));
  expect(document.querySelector(".queue-rail.collapsed")).not.toBeNull();
  expect(window.localStorage.getItem("deadbot.rail.queue")).toBe("closed");
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: /^Queue,/ })); });
  await vi.waitFor(() => expect(document.getElementById("queue-rail")).toHaveFocus());
});

test("the rail carries the site's links instead of a menu, and collapses to its controls", async () => {
  await openWorkspace();
  expect(within(rail()).getByRole("link", { name: "About Deadbot" })).toHaveAttribute("href", "/about");
  expect(within(rail()).getByRole("link", { name: /About Mark Davenport/ })).toHaveAttribute("target", "_blank");
  expect(within(rail()).queryByRole("button", { name: "Menu" })).toBeNull();
  expect(document.documentElement).toHaveClass("workspace-desktop");
  fireEvent.click(within(rail()).getByRole("button", { name: "Collapse sidebar" }));
  expect(document.querySelector(".workspace-shell")).toHaveClass("history-collapsed");
  expect(within(rail()).queryByText("Recent")).toBeNull();
  expect(within(rail()).getByRole("button", { name: "New chat" })).toBeInTheDocument();
  expect(window.localStorage.getItem("deadbot.rail.history")).toBe("closed");
  fireEvent.click(within(rail()).getByRole("button", { name: "Expand sidebar" }));
  expect(within(rail()).getByText("Recent")).toBeInTheDocument();
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
    { type: "lead", text: "The runs grew to nine nights." },
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

test("on a phone, history is a drawer from the left: choosing a row closes it, Escape returns focus", async () => {
  phone = true;
  replies = [{ kind: "plain", body: msg() }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  expect(rail()).toBeNull();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  const toggle = screen.getByRole("button", { name: "Your explorations" });
  fireEvent.click(toggle);
  const drawer = document.getElementById("history-drawer") as HTMLElement;
  expect(drawer).not.toHaveAttribute("hidden");
  expect(within(drawer).getByRole("button", { name: "New chat" })).toHaveFocus();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(drawer).toHaveAttribute("hidden");
  expect(toggle).toHaveFocus();
  fireEvent.click(toggle);
  const drawerRows = drawer.querySelectorAll<HTMLButtonElement>(".history-row");
  expect(drawerRows).toHaveLength(2);
  fireEvent.click(drawerRows[0]);
  expect(drawer).toHaveAttribute("hidden");
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeInTheDocument();
  expect(sent).toHaveLength(2);
});

test("history survives a reload and reopens a page without asking again", async () => {
  replies = [{ kind: "plain", body: msg() }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  cleanup();
  window.sessionStorage.clear();
  await openWorkspace();
  expect(screen.getByRole("heading", { level: 1, name: "The late-’80s runs" })).toBeInTheDocument();
  expect(rows()).toHaveLength(2);
  fireEvent.click(rows()[0]);
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeInTheDocument();
  expect(sent).toHaveLength(2);
  expect(window.sessionStorage.getItem("deadbot-research-notebook")).toBe("v1.msg.sig");
});

test("Clear empties the history, and Undo puts it back", async () => {
  replies = [{ kind: "plain", body: msg() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
  expect(rows()).toHaveLength(0);
  expect(window.localStorage.getItem("deadbot.history.v1")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Undo clearing history" }));
  expect(rows()).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeInTheDocument();
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
  await screen.findByRole("heading", { level: 1, name: withTape.headline ?? "" });
  const play = document.querySelector(".exploration-pane:not([hidden]) .card-head .card-play") as HTMLElement;
  await act(async () => { fireEvent.click(play); });
  const bar = () => document.querySelector(".mobile-dock .now-playing-bar") as HTMLElement;
  fireEvent.focus(screen.getByLabelText("Question"));
  expect(bar()).toHaveClass("collapsed");
});
