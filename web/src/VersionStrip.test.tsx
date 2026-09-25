import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { PlayerProvider, usePlayer } from "./player";
import type { ExperienceBlock } from "./types";
import { VersionStrip, clock, timeScale } from "./VersionStrip";

type VersionStripBlock = Extract<ExperienceBlock, { type: "version_strip" }>;

function night(date: string, venue: string, first: number | null, second: number | null, playable = true): VersionStripBlock["rows"][number] {
  const showId = `gd-${date}`;
  const track = (id: string, title: string, seconds: number | null) =>
    playable ? { performance_id: id, title, audio_url: `https://archive.org/download/gd${date}/${id}.mp3`, duration_seconds: seconds } : null;
  return {
    pair_id: `${showId}:2:1`,
    show_id: showId,
    show_date: date,
    venue_name: venue,
    location: null,
    segue: true,
    first_performance_id: `${showId}-china`,
    second_performance_id: `${showId}-rider`,
    first_seconds: first,
    second_seconds: second,
    first_track: track(`${showId}-china`, "China Cat Sunflower", first),
    second_track: track(`${showId}-rider`, "I Know You Rider", second)
  };
}

const block: VersionStripBlock = {
  type: "version_strip",
  pairing_id: "pairing:song-china-cat-sunflower>song-i-know-you-rider",
  title: "The China half kept growing",
  note: null,
  first_song: { song_id: "song-china-cat-sunflower", title: "China Cat Sunflower" },
  second_song: { song_id: "song-i-know-you-rider", title: "I Know You Rider" },
  total_count: 544,
  rows: [night("1974-06-26", "Providence Civic Center", 784, 365), night("1979-12-04", "Uptown Theatre", null, 428, false)],
  year_counts: [
    { year: 1974, count: 21 },
    { year: 1975, count: 0 },
    { year: 1976, count: 0 },
    { year: 1977, count: 1 }
  ]
};

function Queue() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((track) => track.title).join(" > ")}</output>;
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

test("the clock rounds up past the longest night and ticks every five minutes", () => {
  expect(timeScale(block.rows)).toEqual({ maxSeconds: 1260, ticks: [0, 5, 10, 15, 20] });
  expect(clock(784)).toBe("13:04");
  expect(clock(null)).toBe("–");
});

test("a row plays both halves of its night in turn", async () => {
  render(
    <PlayerProvider>
      <VersionStrip block={block} />
      <Queue />
    </PlayerProvider>
  );
  expect(screen.getByText("13:04 > 6:05")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Play China Cat Sunflower > I Know You Rider, Providence Civic Center, Jun 26, 1974/ }));
  expect(screen.getByTestId("queue")).toHaveTextContent("China Cat Sunflower > I Know You Rider");
  expect(screen.getByRole("button", { name: /Providence Civic Center/ })).toHaveAttribute("aria-pressed", "true");
});

test("a night without tape tracks draws what it knows and offers no play button", () => {
  render(
    <PlayerProvider>
      <VersionStrip block={block} />
    </PlayerProvider>
  );
  expect(screen.getByText("– > 7:08")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Uptown Theatre/ })).not.toBeInTheDocument();
});

test("the year strip keeps empty years as gaps", () => {
  render(
    <PlayerProvider>
      <VersionStrip block={block} />
    </PlayerProvider>
  );
  expect(screen.getByRole("img", { name: "1974: 21, 1975: 0, 1976: 0, 1977: 1" })).toBeInTheDocument();
  expect(screen.getByText(/nights, 1974 to 1977/)).toBeInTheDocument();
});
