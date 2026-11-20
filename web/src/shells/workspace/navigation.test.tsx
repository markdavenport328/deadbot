import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import type { ExperienceBlock, ExperienceResponse } from "../../types";
import { SCHEMA_VERSION } from "../../core/schema-version";
import { CardFallback, ErrorBoundary, cardWords } from "../../core/error-boundary";
import { loadChart } from "../../cards/lazy-chart";
import { PageGroups } from "../../cards/PageGroups";

// Moving around the workspace: a request carries on while the visitor looks
// at another page, Back and Forward move between pages, every answer has an
// address and a tab title, and one bad card or page does not take the rest.

type Turn = { role: "user" | "assistant"; text: string };
type Reply = { kind: "plain"; body: ExperienceResponse } | { kind: "stream"; chunks: (object | Promise<void>)[] } | "reject";

function page(headline: string, question: string, answer: string, blocks: ExperienceBlock[] = []): ExperienceResponse {
  const conversation: Turn[] = [{ role: "user", text: question }, { role: "assistant", text: answer }];
  return {
    schema_version: SCHEMA_VERSION, thread_id: "web-test", headline, lead: answer, mode: "answer", conversation, blocks,
    groups: blocks.length > 0 ? [{ presentation: "collection", criteria: [], block_indexes: blocks.map((_, index) => index) }] : [], sources: []
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
      try {
        for (const chunk of chunks) {
          if (chunk instanceof Promise) await chunk;
          else controller.enqueue(encoder.encode(JSON.stringify(chunk) + "\n"));
        }
        controller.close();
      } catch (error) {
        controller.error(error);
      }
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
});

beforeEach(() => {
  sent.length = 0;
  plainNext = null;
  phone = false;
  window.sessionStorage.clear();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
  document.title = "Deadbot";
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
  vi.restoreAllMocks();
  window.localStorage.clear();
});

async function openWorkspace() {
  vi.resetModules();
  const { default: AppWithPlayer } = await import("../../App");
  render(<AppWithPlayer />);
}

const box = () => screen.getByLabelText("Question") as HTMLTextAreaElement;
function ask(text: string) {
  fireEvent.change(box(), { target: { value: text } });
  fireEvent.keyDown(box(), { key: "Enter" });
}
const rows = () => Array.from(document.querySelectorAll<HTMLButtonElement>(".history-row"));
const query = () => new URLSearchParams(window.location.search);
const dew = () => page("The Cornell Dew", "Best Morning Dew?", "Cornell, by most counts.");
const garden = () => page("The Garden years", "MSG", "They played the Garden 52 times.");
const late80s = () => page("The late-’80s runs", "Focus on the late ’80s", "The runs grew to nine nights.");

async function goBack() {
  await act(async () => {
    window.history.back();
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

test("opening an earlier page while an answer is written does not stop it: it finishes in its own row", async () => {
  let release!: () => void;
  const hold = new Promise<void>((resolve) => { release = resolve; });
  replies = [{ kind: "plain", body: dew() }, { kind: "stream", chunks: [
    { type: "status", text: "Counting nights" }, hold, { type: "lead", text: "They played the Garden 52 times." }, { type: "response", response: garden() }
  ] }];
  await openWorkspace();
  ask("Best Morning Dew?");
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  ask("MSG");
  const pending = await screen.findByRole("button", { name: /Asking · MSG/ });
  expect(pending).toHaveAttribute("aria-current", "true");

  fireEvent.click(rows()[0]);
  expect(screen.getByRole("heading", { level: 1, name: "The Cornell Dew" })).toBeVisible();
  expect(screen.getByRole("button", { name: /Asking · MSG/ })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();

  await act(async () => { release(); });
  await vi.waitFor(() => expect(rows()).toHaveLength(2));
  // Still on the page the visitor chose; the finished one waits, marked new.
  expect(screen.getByRole("heading", { level: 1, name: "The Cornell Dew" })).toBeVisible();
  const finished = rows().find((row) => row.textContent?.includes("MSG"))!;
  expect(finished).toHaveClass("unseen");
  expect(sent).toHaveLength(2);
  fireEvent.click(finished);
  expect(screen.getByRole("heading", { level: 1, name: "The Garden years" })).toBeVisible();
  expect(finished).not.toHaveClass("unseen");
});

test("a stream that fails keeps the draft on screen, with Retry", async () => {
  let fail!: (error: Error) => void;
  const broken = new Promise<void>((_, reject) => { fail = reject; });
  replies = [{ kind: "stream", chunks: [{ type: "status", text: "Looking" }, { type: "lead", text: "They played the Garden 52 times." }, broken] }, { kind: "plain", body: garden() }];
  await openWorkspace();
  ask("MSG");
  await screen.findByText("They played the Garden 52 times.");
  await act(async () => { fail(new Error("network down")); });
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Deadbot couldn't finish “MSG”.");
  expect(screen.getByText("They played the Garden 52 times.")).toBeVisible();
  fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  expect(sent).toHaveLength(2);
});

test("a finished answer leaves focus in the ask box when the visitor is in it", async () => {
  replies = [{ kind: "plain", body: dew() }, { kind: "plain", body: garden() }];
  await openWorkspace();
  ask("Best Morning Dew?");
  const first = await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  expect(document.activeElement).toBe(first);
  box().focus();
  ask("MSG");
  fireEvent.change(box(), { target: { value: "And the next" } });
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  expect(document.activeElement).toBe(box());
  expect(box().value).toBe("And the next");
});

test("each answer has an address and a tab title, and Back and Forward move between the pages opened", async () => {
  replies = [{ kind: "plain", body: dew() }, { kind: "plain", body: late80s() }];
  await openWorkspace();
  expect(document.title).toBe("Deadbot");
  ask("Best Morning Dew?");
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  expect(query().get("q")).toBe("Best Morning Dew?");
  expect(document.title).toBe("The Cornell Dew · Deadbot");
  ask("Focus on the late ’80s");
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  // A follow-up is named by the question its thread began with, then its own.
  expect(query().get("q")).toBe("Best Morning Dew?");
  expect(query().get("then")).toBe("Focus on the late ’80s");
  expect(document.title).toBe("The late-’80s runs · Deadbot");

  await goBack();
  expect(screen.getByRole("heading", { level: 1, name: "The Cornell Dew" })).toBeVisible();
  expect(query().get("then")).toBeNull();
  await goBack();
  expect(screen.getByRole("heading", { level: 1, name: /Exploration and listening/ })).toBeVisible();
  expect(window.location.search).toBe("");
  expect(document.title).toBe("Deadbot");
  await act(async () => {
    window.history.forward();
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  expect(screen.getByRole("heading", { level: 1, name: "The Cornell Dew" })).toBeVisible();
  expect(sent).toHaveLength(2);
});

test("a link to a question this browser has saved reopens that page without asking", async () => {
  replies = [{ kind: "plain", body: dew() }, { kind: "plain", body: garden() }];
  await openWorkspace();
  ask("Best Morning Dew?");
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  ask("MSG");
  await screen.findByRole("heading", { level: 1, name: "The Garden years" });
  cleanup();
  window.history.replaceState(null, "", "/?q=best%20morning%20dew%3F");
  await openWorkspace();
  expect(screen.getByRole("heading", { level: 1, name: "The Cornell Dew" })).toBeVisible();
  expect(sent).toHaveLength(2);
});

test("a link to a follow-up, opened where it is not saved, shows the first page and offers the follow-up", async () => {
  replies = [{ kind: "plain", body: dew() }, { kind: "plain", body: late80s() }];
  window.history.replaceState(null, "", "/?q=Best%20Morning%20Dew%3F&then=Focus%20on%20the%20late%20%E2%80%9980s");
  await openWorkspace();
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  expect(sent).toHaveLength(1);
  expect(sent[0].question).toBe("Best Morning Dew?");
  expect(screen.getByText("This link went on to ask “Focus on the late ’80s”")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Ask it" }));
  await screen.findByRole("heading", { level: 1, name: "The late-’80s runs" });
  expect(sent[1].question).toBe("Focus on the late ’80s");
  expect((sent[1].conversation as Turn[]).map((turn) => turn.text)).toEqual(["Best Morning Dew?", "Cornell, by most counts."]);
});

test("Copy link copies the page's address", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  replies = [{ kind: "plain", body: dew() }];
  await openWorkspace();
  ask("Best Morning Dew?");
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Copy link" })); });
  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/?q=Best+Morning+Dew%3F`);
  expect(screen.getByText("Link copied")).toBeVisible();
});

test("New chat starts at the top of the page", async () => {
  replies = [{ kind: "plain", body: dew() }];
  await openWorkspace();
  ask("Best Morning Dew?");
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  Object.defineProperty(window, "scrollY", { configurable: true, value: 640 });
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
  // The page left behind keeps its place for the way back.
  fireEvent.click(rows()[0]);
  expect(scrollTo).toHaveBeenLastCalledWith(0, 640);
  Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
});

test("on a phone, Back closes the history drawer before it leaves the page", async () => {
  phone = true;
  replies = [{ kind: "plain", body: dew() }];
  await openWorkspace();
  ask("Best Morning Dew?");
  await screen.findByRole("heading", { level: 1, name: "The Cornell Dew" });
  fireEvent.click(screen.getByRole("button", { name: /Your explorations/ }));
  const drawer = document.getElementById("history-drawer") as HTMLElement;
  expect(drawer).not.toHaveAttribute("hidden");
  await goBack();
  expect(drawer).toHaveAttribute("hidden");
  expect(screen.getByRole("heading", { level: 1, name: "The Cornell Dew" })).toBeVisible();
  expect(query().get("q")).toBe("Best Morning Dew?");
});

test("a page saved by another version of the app is not shown, and the app still opens", async () => {
  const old = { ...dew(), schema_version: "0", blocks: [{ type: "show_unit" }], groups: [{ presentation: "collection", criteria: [], block_indexes: [0] }] };
  const entry = { id: "old", parentId: null, root: true, request: "Best Morning Dew?", source: "typed", focus: null, threadId: "t", response: old, view: { scroll: null } };
  window.localStorage.setItem("deadbot.history.v1", JSON.stringify({ entries: [entry], cursor: 0, startView: false }));
  await openWorkspace();
  expect(screen.getByRole("heading", { level: 1, name: /Exploration and listening/ })).toBeVisible();
  expect(rows()).toHaveLength(0);
});

test("a card that cannot be drawn leaves its own words and the rest of the page", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  // A show card without the lists its renderer walks, beside a sound one.
  const broken = { type: "show_unit", headline: "Barton Hall", note: "The second set never lets go." } as unknown as ExperienceBlock;
  const sound = { type: "gap_state", message: "No tape of the soundcheck circulates." } as unknown as ExperienceBlock;
  render(<PageGroups groups={[{ title: null, lead: null, presentation: "collection", criteria: [], blocks: [broken, sound] }]} sources={[]} composing={false} onFollowUp={() => {}} />);
  expect(screen.getByText("Barton Hall")).toBeVisible();
  expect(screen.getByText("The second set never lets go.")).toBeVisible();
  expect(screen.getByText("No tape of the soundcheck circulates.")).toBeVisible();
});

test("a card's words are read without knowing its kind", () => {
  expect(cardWords({ type: "x", title: "T", note: "N", paragraphs: ["P1", " "], items: [1] })).toEqual({ title: "T", lines: ["N", "P1"] });
  expect(cardWords(null)).toEqual({ title: null, lines: [] });
  const { container } = render(<CardFallback block={{ type: "x" }} />);
  expect(container).toBeEmptyDOMElement();
});

test("a boundary tries again when what it draws changes", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const Bomb = ({ explode }: { explode: boolean }) => {
    if (explode) throw new Error("boom");
    return <p>fine</p>;
  };
  const { rerender } = render(<ErrorBoundary name="a test" resetKey={1} fallback={<p>fallback</p>}><Bomb explode /></ErrorBoundary>);
  expect(screen.getByText("fallback")).toBeVisible();
  rerender(<ErrorBoundary name="a test" resetKey={2} fallback={<p>fallback</p>}><Bomb explode={false} /></ErrorBoundary>);
  expect(screen.getByText("fine")).toBeVisible();
});

test("a chart whose code does not arrive is retried once, then says so in place of an error", async () => {
  const Chart = () => <p>chart</p>;
  const flaky = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch dynamically imported module")).mockResolvedValue({ DataChart: Chart });
  expect((await loadChart(flaky, 0)).default).toBe(Chart);
  const gone = vi.fn().mockRejectedValue(new TypeError("Failed to fetch dynamically imported module"));
  const { default: Fallback } = await loadChart(gone, 0);
  expect(gone).toHaveBeenCalledTimes(2);
  render(<Fallback block={{ type: "data_chart", title: "Dark Star by year" } as never} />);
  expect(screen.getByText("Dark Star by year")).toBeVisible();
  expect(screen.getByRole("button", { name: "Reload the page" })).toBeVisible();
});
