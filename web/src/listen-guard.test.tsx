import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import openapi from "../openapi.json";
import type { ExperienceBlock, ExperienceResponse } from "./types";
import { visualFixtureNames, visualFixtures, type VisualFixtureName } from "./visual-fixtures";

// The guard that keeps every listen link on the page: each fixture renders in
// the real app, with every drawer tab opened in turn, and no raw link to an
// Internet Archive audio file may appear. Such a link would leave the site
// instead of playing in the shared player. Every control marked as playing
// in-page must have an accessible name, and the gold play mark may appear
// only on a control that really plays in-page.

const TRACK = "https://archive.org/download/gd1973-06-10.sbd.miller.89640.sbeok.flac16/gd73-06-10d2t02.mp3";

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

function accessibleName(element: Element): string {
  const label = element.getAttribute("aria-label");
  if (label?.trim()) return label.trim();
  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const text = labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent ?? "").join(" ").trim();
    if (text) return text;
  }
  return (element.textContent ?? "").trim();
}

function assertListenAffordances(where: string) {
  const rawTracks = [...document.querySelectorAll('a[href*="archive.org/download"]')].map((anchor) => anchor.getAttribute("href"));
  expect(rawTracks, `${where}: raw archive track links`).toEqual([]);
  for (const element of document.querySelectorAll("[data-playable]")) {
    expect(accessibleName(element), `${where}: a playable control without a name: ${element.outerHTML.slice(0, 160)}`).not.toBe("");
  }
  // The gold row mark belongs to in-page play only, never to a link out.
  for (const mark of document.querySelectorAll(".listen-play-mark")) {
    expect(mark.closest("[data-playable]"), `${where}: a gold mark outside an in-page control`).not.toBeNull();
    expect(mark.closest("a"), `${where}: a gold mark inside a link`).toBeNull();
  }
  expect(document.querySelectorAll("a .play-mark, a.hero-play, a.card-play").length, `${where}: a gold play styled link`).toBe(0);
}

async function renderFixture(name: string, response: ExperienceResponse) {
  window.history.replaceState({}, "", `/?fixture=${name}`);
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: response.title });
}

// Open every tab of every drawer in turn: a closed panel is not in the DOM.
function eachDrawerState(where: string) {
  assertListenAffordances(where);
  const tabs = [...document.querySelectorAll<HTMLButtonElement>(".drawer .tab")];
  for (const tab of tabs) {
    if (tab.getAttribute("aria-expanded") !== "true") fireEvent.click(tab);
    assertListenAffordances(`${where} › ${tab.textContent}`);
  }
}

describe("listen links across the visual fixtures", () => {
  it.each(visualFixtureNames)("%s renders no raw archive track link and names every play", async (name) => {
    const response = visualFixtures[name as VisualFixtureName];
    await renderFixture(name, response);
    eachDrawerState(name);
  });

  it("covers every block type the API can send", () => {
    const mapping = (openapi as { components: { schemas: { ExperienceResponse: { properties: { blocks: { items: { discriminator: { mapping: Record<string, string> } } } } } } } })
      .components.schemas.ExperienceResponse.properties.blocks.items.discriminator.mapping;
    const covered = new Set(Object.values(visualFixtures).flatMap((response) => response.blocks.map((block) => block.type)));
    expect(Object.keys(mapping).filter((type) => !covered.has(type as ExperienceBlock["type"]))).toEqual([]);
  });
});

// Every URL-shaped field of every fixture block pointed at an audio file: the
// worst case for a renderer that forgets to route a link through the player.
function everyUrlATrack(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(everyUrlATrack);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => {
        if (typeof child === "string" && /(^url|_url)$/.test(key) && key !== "image_url") return [key, TRACK];
        return [key, everyUrlATrack(child)];
      })
    );
  }
  return value;
}

describe("listen links when every URL is an archive track", () => {
  it.each(visualFixtureNames)("%s still plays every track in-page", async (name) => {
    const base = visualFixtures[name as VisualFixtureName];
    const response = everyUrlATrack(base) as ExperienceResponse;
    response.blocks.push({
      type: "editorial",
      presentation: "narrative",
      eyebrow: null,
      title: "Inline links",
      paragraphs: [`The model can link a track in prose: [hear the *RFK* Eyes](${TRACK}).`],
      items: []
    } as ExperienceBlock);
    response.groups[response.groups.length - 1].block_indexes.push(response.blocks.length - 1);
    vi.doMock("./visual-fixtures", async (importOriginal) => ({
      ...(await importOriginal<typeof import("./visual-fixtures")>()),
      visualFixtureFromLocation: () => response
    }));
    await renderFixture(name, response);
    eachDrawerState(`${name} (every url a track)`);
    // Prose keeps the model's words verbatim on the in-page control.
    expect(screen.getByRole("button", { name: "hear the RFK Eyes" })).toHaveAttribute("data-playable", "in-page");
  });
});

describe("era and song cards play in-page", () => {
  it("an era row plays its track in the shared player and names it in the now-playing bar", async () => {
    await renderFixture("evolution", visualFixtures.evolution);
    const era = screen.getByRole("heading", { name: "1973: the open road" }).closest("section") as HTMLElement;
    const row = within(era).getByRole("button", { name: "Play Eyes Of The World, Robert F. Kennedy Stadium (6/10/73)" });
    await act(async () => {
      fireEvent.click(row);
    });
    const bar = screen.getByRole("region", { name: "Now playing" });
    expect(within(bar).getByText("Eyes Of The World")).toBeInTheDocument();
    expect(within(bar).getByText("6/10/73 · Robert F. Kennedy Stadium")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-pressed", "true");
  });

  it("the song card's History rows and representatives play in-page; On record links out quietly", async () => {
    await renderFixture("playing", visualFixtures.playing);
    const card = screen.getByRole("heading", { name: "Playing In The Band" }).closest("article") as HTMLElement;
    expect(within(card).getByRole("button", { name: "Play Playing In The Band, Old Renaissance Faire Grounds (8/27/72)" })).toHaveAttribute("data-playable", "in-page");
    const historyTab = within(card).getByRole("button", { name: "History" });
    if (historyTab.getAttribute("aria-expanded") !== "true") fireEvent.click(historyTab);
    const last = within(card).getByRole("button", { name: "Play Playing In The Band, Riverport Amphitheatre, July 5, 1995" });
    expect(last).toHaveAttribute("data-playable", "in-page");
    // The first performance has no tape: it is words, not a control.
    expect(within(card).queryByRole("button", { name: /Capitol Theatre/ })).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: /^On record/ }));
    const ace = within(card).getByRole("link", { name: "Ace on open.spotify.com (opens in a new tab)" });
    expect(ace).toHaveClass("listen-link");
    expect(ace.querySelector(".listen-play-mark, svg")).toBeNull();
  });
});
