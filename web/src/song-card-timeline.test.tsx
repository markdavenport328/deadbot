import { cleanup, render, screen, within } from "@testing-library/react";
import { askFocus } from "./song-timeline-text";
import { visualFixtures } from "./visual-fixtures";

// A song card with by_year in the real app: the timeline replaces the old
// chart and History tab, and asking about a year sends the year as focus
// (the app ignores questions in fixture mode, so the mapping is tested alone).

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false
  })) as typeof window.matchMedia;
  Element.prototype.scrollIntoView = function scrollIntoView() {};
  Element.prototype.scrollTo = function scrollTo() {} as typeof Element.prototype.scrollTo;
  window.scrollTo = (() => {}) as typeof window.scrollTo;
  HTMLMediaElement.prototype.play = function play() {
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {};
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

async function renderTimeline() {
  window.history.replaceState({}, "", "/?fixture=timeline");
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: visualFixtures.timeline.title });
}

test("the song card shows its timeline open on the model's year, without a History tab", async () => {
  await renderTimeline();
  const panel = screen.getByRole("region", { name: "1979" });
  expect(within(panel).getByText(/Stop 4 · Charlie Miller's pick/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Times played" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("region", { name: "Listening path" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: /History/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^History/ })).not.toBeInTheDocument();
});

test("the timeline's focus becomes the question's AskFocus", () => {
  expect(
    askFocus({ label: "Terrapin Station in 1979", song_id: "song-terrapin-station", year: 1979, ids: ["song-terrapin-station", "p-msg"], facts: ["23 performances"] })
  ).toEqual({ block_type: "song_overview", block_id: "song-terrapin-station", label: "Terrapin Station in 1979", ids: ["song-terrapin-station", "p-msg"], facts: ["23 performances"] });
});
