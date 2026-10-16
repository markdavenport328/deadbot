import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { DataChart, type DataChartBlock } from "./DataChart";
import { forgetRowDetails, rowFocus, rowUrl, type RowDetail } from "./RowOpener";

// A ranked row, chart bar or roster name that names a record opens in place to
// the server's facts for it, one play and one ask that carries the row as focus.

const TRACK = "https://archive.org/download/gd1972-05-11.sbd.miller.100000.flac16/gd72-05-11d2t01.mp3";

const ned: RowDetail = {
  id: "person-ned-lagin",
  kind: "person",
  title: "Ned Lagin",
  facts: [
    { label: "Shows", value: "33" },
    { label: "Years", value: "1970–1975" }
  ],
  play: {
    show_id: "gd-1974-08-05",
    show_date: "1974-08-05",
    venue_name: "Civic Convention Hall Auditorium",
    why: "Picked by Charlie Miller",
    tracks: [{ performance_id: "gd-1974-08-05-seastones-2-1", title: "Seastones", audio_url: TRACK, duration_seconds: 900, set_label: "Set 2" }]
  },
  ask: "Tell me about Ned Lagin with the Dead"
};

const pitb: RowDetail = {
  id: "song-playing-in-the-band",
  kind: "song",
  title: "Playing In The Band",
  facts: [{ label: "Played", value: "750 times" }],
  play: null,
  ask: "The story of Playing In The Band on stage"
};

const details: Record<string, RowDetail> = { "person-ned-lagin": ned, "song-playing-in-the-band": pitb };
const sent: Record<string, unknown>[] = [];
const rowRequests: string[] = [];

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false
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

function page() {
  return {
    schema_version: "2", thread_id: "web-test", title: "Who sat in", answer: "Plenty of people.", body_lead: null, mode: "answer",
    conversation: [{ role: "user", text: "Who sat in with the Dead?" }, { role: "assistant", text: "Plenty of people." }],
    sources: [],
    blocks: [
      {
        type: "person_roster",
        title: "The guests",
        lead: null,
        items: [
          { person_id: "person-ned-lagin", name: "Ned Lagin", roles: ["keyboards"], show_count: 33, first_year: "1970", last_year: "1975", note: null },
          { person_id: "person-branford-marsalis", name: "Branford Marsalis", roles: ["saxophone"], show_count: 5, first_year: "1990", last_year: "1994", note: null }
        ]
      },
      {
        type: "ranked_list",
        aggregation_id: "agg-songs",
        title: "Most played",
        note: null,
        dimension_label: "Song",
        metric_label: "Performances",
        more_count: 0,
        rows: [
          { rank: 1, id: "song-playing-in-the-band", label: "Playing In The Band", value: 750, note: null, opens: true },
          { rank: 2, id: "song-gone", label: "A song the library lost", value: 3, note: null, opens: false }
        ]
      }
    ],
    groups: [{ presentation: "collection", title: null, block_indexes: [0, 1] }]
  };
}

let replies: unknown[] = [];

beforeEach(() => {
  sent.length = 0;
  rowRequests.length = 0;
  forgetRowDetails();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    const row = /\/api\/rows\/([^?]+)/.exec(path);
    if (row) {
      rowRequests.push(path);
      const detail = details[decodeURIComponent(row[1])];
      return detail ? new Response(JSON.stringify(detail), { status: 200 }) : new Response(null, { status: 404 });
    }
    if (path.endsWith("/api/experience/stream")) return new Response(null, { status: 404 });
    if (path.endsWith("/api/experience")) {
      sent.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify(replies.shift()), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(null, { status: 404 });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openPage() {
  replies = [page(), { ...page(), title: "Ned Lagin" }];
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
  const box = screen.getAllByLabelText("Question").find((element) => !(element as HTMLTextAreaElement).disabled) as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: "Who sat in with the Dead?" } });
  fireEvent.keyDown(box, { key: "Enter" });
  await screen.findByRole("heading", { level: 1, name: "Who sat in" });
}

describe("a roster name", () => {
  it("opens to the person's facts, one play and one ask, and closes again", async () => {
    await openPage();
    const name = screen.getByRole("button", { name: "Ned Lagin" });
    expect(name).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(name);
    expect(name).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(name.getAttribute("aria-controls") as string) as HTMLElement;
    expect(await within(panel).findByText("1970–1975")).toBeInTheDocument();
    expect(within(panel).getByText("Shows")).toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: /^Play Ned Lagin, August 5, 1974/ })).toHaveLength(1);
    expect(within(panel).getByText(/Picked by Charlie Miller/)).toBeInTheDocument();
    expect(rowRequests).toEqual(["/api/rows/person-ned-lagin"]);
    fireEvent.click(name);
    expect(name).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector(".row-panel")).toBeNull();
  });

  it("keeps one row open at a time", async () => {
    await openPage();
    fireEvent.click(screen.getByRole("button", { name: "Ned Lagin" }));
    fireEvent.click(screen.getByRole("button", { name: "Playing In The Band" }));
    await screen.findByText("750 times");
    expect(document.querySelectorAll(".row-panel")).toHaveLength(2);
    // One per block: opening a second roster name closes the first.
    fireEvent.click(screen.getByRole("button", { name: "Branford Marsalis" }));
    expect(screen.getByRole("button", { name: "Ned Lagin" })).toHaveAttribute("aria-expanded", "false");
  });

  it("opens and closes from the keyboard, focus returning to the name on Escape", async () => {
    const user = userEvent.setup();
    await openPage();
    const name = screen.getByRole("button", { name: "Ned Lagin" });
    name.focus();
    await user.keyboard("{Enter}");
    expect(name).toHaveAttribute("aria-expanded", "true");
    const ask = await screen.findByRole("button", { name: "Tell me about Ned Lagin with the Dead" });
    ask.focus();
    await user.keyboard("{Escape}");
    expect(name).toHaveAttribute("aria-expanded", "false");
    expect(name).toHaveFocus();
  });

  it("sends its ask to the chat with the opened row as focus", async () => {
    await openPage();
    fireEvent.click(screen.getByRole("button", { name: "Ned Lagin" }));
    fireEvent.click(await screen.findByRole("button", { name: "Tell me about Ned Lagin with the Dead" }));
    await screen.findByRole("heading", { level: 1, name: "Ned Lagin" });
    expect(sent[1].question).toBe("Tell me about Ned Lagin with the Dead");
    expect(sent[1].focus).toEqual({
      block_type: "person_roster",
      block_id: "The guests",
      label: "Ned Lagin",
      ids: ["person-ned-lagin", "gd-1974-08-05"],
      facts: ["Shows: 33.", "Years: 1970–1975."]
    });
  });
});

describe("a ranked list row", () => {
  it("opens without a play button when nothing has tape, and a row that does not resolve stays plain", async () => {
    await openPage();
    fireEvent.click(screen.getByRole("button", { name: "Playing In The Band" }));
    await screen.findByText("750 times");
    const panel = document.querySelector(".ranked-rows .row-panel") as HTMLElement;
    expect(panel.querySelector(".opened-play")).toBeNull();
    expect(within(panel).getByRole("button", { name: "The story of Playing In The Band on stage" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "A song the library lost" })).toBeNull();
    expect(screen.getByText("A song the library lost")).toBeInTheDocument();
  });
});

const chart: DataChartBlock = {
  type: "data_chart",
  aggregation_id: "agg-songs",
  chart: "bar",
  columns: [
    { key: "label", label: "Song", type: "categorical" },
    { key: "value", label: "Performances", type: "quantitative" }
  ],
  date_range: null,
  empty_reason: null,
  excluded_count: 0,
  metric_label: "Performances",
  note: null,
  orientation: "horizontal",
  rows: [
    { id: "song-playing-in-the-band", label: "Playing In The Band", value: 750 },
    { id: "song-gone", label: "Gone", value: 3 }
  ],
  title: "Most played",
  total: 753,
  open_ids: ["song-playing-in-the-band"]
};

describe("a chart's bar", () => {
  it("opens from its axis label by keyboard, under the chart, and asks with the chart as focus", async () => {
    const user = userEvent.setup();
    const onFollowUp = vi.fn();
    render(<DataChart block={chart} onFollowUp={onFollowUp} />);
    const label = screen.getByRole("button", { name: "Playing In The Band" });
    expect(screen.queryByRole("button", { name: "Gone" })).toBeNull();
    label.focus();
    await user.keyboard("{Enter}");
    expect(label).toHaveAttribute("aria-expanded", "true");
    const panel = await screen.findByRole("region", { name: "Playing In The Band" });
    expect(within(panel).getByText("750 times")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "The story of Playing In The Band on stage" }));
    expect(onFollowUp).toHaveBeenCalledWith("The story of Playing In The Band on stage", {
      block_type: "data_chart",
      block_id: "agg-songs",
      label: "Playing In The Band",
      ids: ["song-playing-in-the-band"],
      facts: ["Played: 750 times."]
    });
    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Playing In The Band" })).toBeNull());
    expect(label).toHaveFocus();
  });

  it("opens when its bar is clicked", async () => {
    const { container } = render(<DataChart block={chart} />);
    const bars = container.querySelectorAll(".recharts-bar-rectangle");
    expect(bars.length).toBe(2);
    fireEvent.click(bars[0].querySelector("path") ?? bars[0]);
    expect(await screen.findByText("750 times")).toBeInTheDocument();
  });

  it("draws plain labels when no row opens", () => {
    render(<DataChart block={{ ...chart, open_ids: [] }} />);
    expect(screen.queryByRole("button", { name: "Playing In The Band" })).toBeNull();
  });
});

describe("a year opened within a song", () => {
  it("asks the server for that song's year and names the song in its focus", () => {
    expect(rowUrl("1972", "song-dark-star")).toBe("/api/rows/1972?scope=song-dark-star");
    const year: RowDetail = { id: "1972", kind: "year", title: "Dark Star in 1972", facts: [], play: null, ask: "Dark Star in 1972" };
    expect(rowFocus(year, { blockType: "data_chart", blockId: "agg", scope: "song-dark-star" }).ids).toEqual(["song-dark-star"]);
  });
});
