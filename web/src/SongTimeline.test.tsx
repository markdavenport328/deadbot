import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { PlayerProvider, usePlayer } from "./player";
import { SongTimeline } from "./SongTimeline";
import type { SongTimelineData, SongYearDetail, TimelineTrack } from "./song-timeline-types";

// jsdom has no PointerEvent; this stand-in carries the pointer type and position the timeline reads.
if (!("PointerEvent" in window)) {
  class PointerEventStandIn extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test shim, not app code
  (window as any).PointerEvent = PointerEventStandIn;
}

const track = (id: string): TimelineTrack => ({ performance_id: id, title: "Terrapin Station", audio_url: `https://archive.org/download/gd/${id}.mp3`, duration_seconds: 600, set_label: "Set 2" });

const data: SongTimelineData = {
  song_id: "song-terrapin-station",
  title: "Terrapin Station",
  performance_count: 3,
  year_summaries: [
    {
      year: 1977,
      count: 2,
      median_seconds: 640,
      longest: { performance_id: "p-hartford", seconds: 671 },
      top_next: { title: "Playing In The Band", count: 1 }
    },
    { year: 1978, count: 0, median_seconds: null, longest: null, top_next: null },
    {
      year: 1979,
      count: 1,
      median_seconds: 735,
      longest: { performance_id: "p-msg", seconds: 735 },
      top_next: { title: "Playing In The Band", count: 1 }
    }
  ],
  length_points: [
    { performance_id: "p-debut", show_date: "1977-02-26", seconds: 668 },
    { performance_id: "p-hartford", show_date: "1977-05-28", seconds: 671 },
    { performance_id: "p-msg", show_date: "1979-01-08", seconds: 735 }
  ],
  stops: [
    { performance_id: "p-debut", label: "The debut", why: "First time out.", show_date: "1977-02-26", venue_name: "Swing Auditorium", seconds: 668, track: track("p-debut") },
    { performance_id: "p-lost", label: "A lost night", why: "Not in the library.", show_date: null },
    { performance_id: "p-msg", label: "Charlie Miller's pick", why: "From your first question.", show_date: "1979-01-08", venue_name: "Madison Square Garden", seconds: 735, track: track("p-msg") }
  ],
  open_year: 1979,
  chart_view: null,
  year_questions: [{ year: 1979, question: "How did the 1979 Terrapins differ from 1977?" }]
};

const detail1979: SongYearDetail = {
  song_id: "song-terrapin-station",
  title: "Terrapin Station",
  year: 1979,
  performances: [
    {
      performance_id: "p-msg",
      show_id: "gd-1979-01-08",
      show_date: "1979-01-08",
      venue_name: "Madison Square Garden",
      city: "New York, NY",
      set_label: "Set 2",
      position_in_set: 4,
      encore: false,
      previous: { song_id: "song-samson", title: "Samson And Delilah", segued: false },
      next: { song_id: "song-playin", title: "Playing In The Band", segued: true },
      seconds: 735,
      length_source: "tape",
      track: track("p-msg"),
      releases: [],
      signals: [{ voice: "Charlie Miller", scope: "show" }],
      guests: []
    }
  ]
};

function Queue() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((item) => item.id).join(" > ")}</output>;
}

function setup(overrides: Partial<SongTimelineData> = {}, fetchYear = vi.fn().mockResolvedValue(detail1979)) {
  const onAsk = vi.fn();
  const view = render(
    <PlayerProvider>
      <SongTimeline data={{ ...data, ...overrides }} onAsk={onAsk} fetchYear={fetchYear} />
      <Queue />
    </PlayerProvider>
  );
  return { ...view, onAsk, fetchYear };
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

test("played years are buttons; a year it was not played is not", () => {
  setup();
  expect(screen.getByRole("button", { name: /^1977: 2 performances/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^1979: 1 performance ·/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^1978/ })).not.toBeInTheDocument();
});

test("the model's open year opens first with its facts and stop", () => {
  setup();
  const panel = screen.getByRole("region", { name: "1979" });
  expect(within(panel).getByText("1 performance · typically 12:15 · usually followed by Playing In The Band (1 of 1)")).toBeInTheDocument();
  expect(within(panel).getByText("Stop 3 · Charlie Miller's pick")).toBeInTheDocument();
  expect(within(panel).getByText("From your first question.")).toBeInTheDocument();
});

test("choosing a year opens it, and arrows skip the years it was not played", async () => {
  const user = userEvent.setup();
  setup({ open_year: null });
  await user.click(screen.getByRole("button", { name: /^1979:/ }));
  expect(screen.getByRole("region", { name: "1979" })).toBeInTheDocument();
  screen.getByRole("button", { name: /^1977:/ }).focus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("region", { name: "1977" })).toBeInTheDocument();
  expect(screen.getByText("Stop 1 · The debut")).toBeInTheDocument();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("region", { name: "1979" })).toBeInTheDocument();
});

test("a year without a stop features no performance; See all and Ask stay", async () => {
  const user = userEvent.setup();
  setup({ stops: [], open_year: 1979 });
  const panel = screen.getByRole("region", { name: "1979" });
  expect(within(panel).queryByRole("button", { name: /^Play / })).not.toBeInTheDocument();
  expect(within(panel).getByRole("button", { name: "See all 1 from 1979" })).toBeInTheDocument();
  await user.click(within(panel).getByRole("button", { name: /How did the 1979 Terrapins differ/ }));
  expect(screen.queryByText(/Show picked by/)).not.toBeInTheDocument();
});

test("the Length view draws one dot per performance with a length", async () => {
  const user = userEvent.setup();
  const { container } = setup();
  expect(container.querySelectorAll(".st-dot")).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Length" }));
  expect(container.querySelectorAll(".st-dot")).toHaveLength(3);
  expect(screen.getByRole("button", { name: "Length" })).toHaveAttribute("aria-pressed", "true");
});

test("See all loads a year once and lists its performances", async () => {
  const user = userEvent.setup();
  const { fetchYear } = setup();
  await user.click(screen.getByRole("button", { name: "See all 1 from 1979" }));
  expect(await screen.findByText("Terrapin Station › Playing In The Band")).toBeInTheDocument();
  expect(screen.getByText(/New York, NY · Stop 3 · Show picked by Charlie Miller/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Hide the 1979 list" }));
  await user.click(screen.getByRole("button", { name: "See all 1 from 1979" }));
  expect(fetchYear).toHaveBeenCalledTimes(1);
  expect(fetchYear).toHaveBeenCalledWith("song-terrapin-station", 1979);
});

test("a failed year lookup says so and can try again", async () => {
  const user = userEvent.setup();
  const fetchYear = vi.fn().mockRejectedValueOnce(new Error("The 1979 list could not load (503).")).mockResolvedValue(detail1979);
  setup({}, fetchYear);
  await user.click(screen.getByRole("button", { name: "See all 1 from 1979" }));
  expect(await screen.findByText(/could not load \(503\)/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Terrapin Station › Playing In The Band")).toBeInTheDocument();
});

test("Play the path queues the stops that have tapes, in order", async () => {
  const user = userEvent.setup();
  setup();
  await user.click(screen.getByRole("button", { name: /Play the path/ }));
  expect(screen.getByTestId("queue")).toHaveTextContent("p-debut > p-msg");
});

test("asking sends the year's question with the year as focus", async () => {
  const user = userEvent.setup();
  const { onAsk } = setup();
  await user.click(screen.getByRole("button", { name: /How did the 1979 Terrapins differ from 1977\?/ }));
  expect(onAsk).toHaveBeenCalledWith("How did the 1979 Terrapins differ from 1977?", {
    label: "Terrapin Station in 1979",
    song_id: "song-terrapin-station",
    year: 1979,
    ids: ["song-terrapin-station", "p-msg"],
    facts: ["1 performance · typically 12:15 · usually followed by Playing In The Band (1 of 1)"]
  });
});

test("a stop the library could not resolve keeps the model's words without a Play", () => {
  setup();
  expect(screen.getByText("A lost night")).toBeInTheDocument();
  expect(screen.getByText("Not in the library.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /A lost night/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play stop 1, The debut" })).toBeInTheDocument();
});

test("a song with no dated performances says so", () => {
  setup({ year_summaries: [], length_points: [], stops: [] });
  expect(screen.getByText("No dated performances of Terrapin Station are in the library.")).toBeInTheDocument();
});

test("a dot plays its performance once its year has loaded", async () => {
  const user = userEvent.setup();
  const { container } = setup();
  await user.click(screen.getByRole("button", { name: "Length" }));
  const msgDot = [...container.querySelectorAll(".st-dot")][2];
  await user.click(msgDot.querySelector(".st-dot-hit")!);
  await waitFor(() => expect(screen.getByTestId("queue")).toHaveTextContent("p-msg"));
});

test("a year with a stop asks about the stop", async () => {
  const user = userEvent.setup();
  const { onAsk } = setup();
  await user.click(screen.getByRole("button", { name: /^1977:/ }));
  await user.click(screen.getByRole("button", { name: /Tell me about Terrapin Station in 1977/ }));
  expect(onAsk.mock.calls[0][1].ids).toEqual(["song-terrapin-station", "p-debut"]);
});

test("a slow lookup for an earlier dot does not replace a later choice", async () => {
  const user = userEvent.setup();
  let finish1977: (detail: SongYearDetail) => void = () => undefined;
  const fetchYear = vi.fn((_song: string, year: number) =>
    year === 1977 ? new Promise<SongYearDetail>((resolve) => (finish1977 = resolve)) : Promise.resolve(detail1979)
  );
  const { container } = setup({}, fetchYear);
  await user.click(screen.getByRole("button", { name: "Length" }));
  const dots = [...container.querySelectorAll(".st-dot-hit")];
  await user.click(dots[1]);
  await user.click(dots[2]);
  await waitFor(() => expect(screen.getByTestId("queue")).toHaveTextContent("p-msg"));
  finish1977({ ...detail1979, year: 1977, performances: [{ ...detail1979.performances[0], performance_id: "p-hartford", show_date: "1977-05-28", track: track("p-hartford") }] });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.getByTestId("queue")).toHaveTextContent("p-msg");
  expect(screen.getByTestId("queue")).not.toHaveTextContent("p-hartford");
});


test("dragging a finger across the chart opens the years under it", () => {
  setup({ open_year: 1977 });
  const chart = screen.getByRole("group", { name: "Terrapin Station by year" });
  // 600px wide, three years: 1977 starts at 36px, 1978 (not played) at 222px, 1979 at 408px.
  fireEvent.pointerDown(chart, { pointerType: "touch", clientX: 500, pointerId: 1 });
  expect(screen.getByRole("region", { name: "1979" })).toBeInTheDocument();
  fireEvent.pointerMove(chart, { pointerType: "touch", clientX: 100, pointerId: 1 });
  expect(screen.getByRole("region", { name: "1977" })).toBeInTheDocument();
  fireEvent.pointerUp(chart, { pointerType: "touch", clientX: 100, pointerId: 1 });
  // A mouse moving over the chart opens nothing on its own.
  fireEvent.pointerMove(chart, { pointerType: "mouse", clientX: 500, pointerId: 2 });
  expect(screen.getByRole("region", { name: "1977" })).toBeInTheDocument();
});

test("a tap on a dot opens its year's list instead of aiming at the dot", async () => {
  const user = userEvent.setup();
  const { container, fetchYear } = setup({ open_year: 1977 });
  await user.click(screen.getByRole("button", { name: "Length" }));
  const chart = screen.getByRole("group", { name: "Terrapin Station by year" });
  fireEvent.pointerDown(chart, { pointerType: "touch", clientX: 500, pointerId: 3 });
  fireEvent.pointerUp(chart, { pointerType: "touch", clientX: 500, pointerId: 3 });
  fireEvent.click([...container.querySelectorAll(".st-dot-hit")][2]);
  expect(await screen.findByText("Terrapin Station › Playing In The Band")).toBeInTheDocument();
  expect(fetchYear).toHaveBeenCalledWith("song-terrapin-station", 1979);
  expect(screen.getByTestId("queue")).toHaveTextContent("");
});
