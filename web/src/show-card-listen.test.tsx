import { cleanup, render, screen, within } from "@testing-library/react";
import type { ExperienceBlock, ExperienceResponse } from "./types";
import { visualFixtures } from "./visual-fixtures";

// A show card with tape in the library plays it in our player; the outside
// link stays a quiet link. A collapsed row without its own tape plays the
// setlist's. An editorial item never repeats its block's heading.

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
  HTMLMediaElement.prototype.load = function load() {};
});

afterEach(() => {
  cleanup();
  vi.doUnmock("./visual-fixtures");
  window.history.replaceState({}, "", "/");
});

const TRACK = "https://archive.org/download/gd1983-06-22.sbd.miller.100000.flac16/gd83-06-22d1t01.mp3";

async function renderResponse(response: ExperienceResponse) {
  vi.doMock("./visual-fixtures", async (importOriginal) => ({
    ...(await importOriginal<typeof import("./visual-fixtures")>()),
    visualFixtureFromLocation: () => response
  }));
  window.history.replaceState({}, "", "/?fixture=harrisburg");
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: response.title });
}

function clone(response: ExperienceResponse): ExperienceResponse {
  return JSON.parse(JSON.stringify(response)) as ExperienceResponse;
}

type ShowUnit = Extract<ExperienceBlock, { type: "show_unit" }>;

describe("an expanded show card with tape", () => {
  it("plays the show in our player, with the outside link kept as a quiet link", async () => {
    const response = clone(visualFixtures.harrisburg);
    const [withTape] = response.blocks.filter((block): block is ShowUnit => block.type === "show_unit");
    withTape.sets[0].songs.forEach((song, index) => {
      song.audio_url = TRACK.replace("t01", `t0${index + 1}`);
    });
    await renderResponse(response);
    const first = document.querySelector("article.show-unit") as HTMLElement;
    const play = first.querySelector(".card-head .card-play") as HTMLElement;
    expect(play).toHaveAttribute("data-playable", "in-page");
    expect(play).toHaveAttribute("aria-label", expect.stringMatching(/^Play /));
    const relisten = within(first).getByRole("link", { name: /Stream the show on relisten\.net/ });
    expect(relisten).toHaveClass("listen-link");
    expect(first.querySelectorAll(".card-play").length).toBe(1);
  });

  it("keeps the outside link as the way to listen when the show has no tape of ours", async () => {
    await renderResponse(clone(visualFixtures.harrisburg));
    const first = document.querySelector("article.show-unit") as HTMLElement;
    expect(first.querySelector(".card-head .card-play")).toBeNull();
    expect(within(first).getByRole("link", { name: /Stream the show on relisten\.net/ })).toBeInTheDocument();
  });
});

describe("a collapsed show row", () => {
  it("plays the setlist's tape when the row carries no tape of its own", async () => {
    const response = clone(visualFixtures.shows1977);
    const [row] = response.blocks.filter((block): block is ShowUnit => block.type === "show_unit");
    row.tracks = [];
    row.sets[0].songs[0].audio_url = TRACK;
    await renderResponse(response);
    const first = document.querySelector(".collapsed-list > .collapsed-row") as HTMLElement;
    expect(first.querySelector(".collapsed-actions .card-play")).toHaveAttribute("data-playable", "in-page");
  });
});

describe("an editorial item that repeats its block's heading", () => {
  function editorial(presentation: "fact_grid" | "timeline", itemTitle: string): ExperienceResponse {
    const response = clone(visualFixtures.harrisburg);
    response.blocks.push({
      type: "editorial",
      presentation,
      eyebrow: "The cause",
      title: "Saving 'Springfield' Creamery",
      paragraphs: [],
      items: [{ title: itemTitle, value: "A dairy kept alive", detail: "The Dead played to save it.", follow_ups: [], tracks: [] }]
    } as ExperienceBlock);
    response.groups[response.groups.length - 1].block_indexes.push(response.blocks.length - 1);
    return response;
  }

  it("is written once in a fact grid, ignoring case and curly quotes", async () => {
    await renderResponse(editorial("fact_grid", "  saving ‘Springfield’ creamery "));
    const block = document.querySelector(".fact-grid-block") as HTMLElement;
    expect(within(block).getAllByText(/Springfield/i)).toHaveLength(1);
    expect(within(block).getByText("A dairy kept alive")).toBeInTheDocument();
    expect(within(block).getByText("The Dead played to save it.")).toBeInTheDocument();
  });

  it("is written once in a timeline", async () => {
    await renderResponse(editorial("timeline", "Saving 'Springfield' Creamery"));
    const block = document.querySelector(".timeline-block") as HTMLElement;
    expect(within(block).getAllByText(/Springfield/i)).toHaveLength(1);
    expect(within(block).getByText("The Dead played to save it.")).toBeInTheDocument();
  });

  it("keeps an item whose title is its own", async () => {
    await renderResponse(editorial("fact_grid", "Springfield Creamery"));
    const block = document.querySelector(".fact-grid-block") as HTMLElement;
    expect(within(block).getAllByText(/Springfield/i)).toHaveLength(2);
  });
});
