import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { PlayerProvider, usePlayer } from "../player/player";
import type { ExperienceBlock } from "../types";
import { SongVersions, length } from "./SongVersions";

type Block = Extract<ExperienceBlock, { type: "song_versions" }>;
type Row = Block["rows"][number];

function row(date: string, venue: string, seconds: number | null, extra: Partial<Row> = {}): Row {
  const id = `gd-${date}-dark-star-1-1`;
  return {
    performance_id: id,
    show_id: `gd-${date}`,
    show_date: date,
    venue_name: venue,
    city: null,
    length_seconds: seconds,
    tape_seconds: seconds,
    release: null,
    track: { performance_id: id, title: "Dark Star", audio_url: `https://archive.org/download/gd${date}/${id}.mp3`, duration_seconds: seconds },
    note: null,
    ...extra
  };
}

const block: Block = {
  type: "song_versions",
  title: "Three Dark Stars",
  song: { song_id: "song-dark-star", title: "Dark Star" },
  rows: [
    row("1968-01-17", "Carousel Ballroom", 161, { note: "The first one on tape." }),
    row("1973-12-06", "Cleveland Convention Center", 2612),
    row("1974-06-18", "Providence Civic Center", null, {
      tape_seconds: null,
      track: null,
      length_seconds: 1500,
      release: { release_id: "r1", title: "Dick’s Picks 12", url: "https://example.org/dp12" }
    })
  ]
};

function Queue() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((track) => track.id).join(" ")}</output>;
}

function renderCard() {
  render(
    <PlayerProvider>
      <SongVersions block={block} />
      <Queue />
    </PlayerProvider>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

test("lengths read m:ss, and h:mm:ss over an hour", () => {
  expect(length(161)).toBe("2:41");
  expect(length(2612)).toBe("43:32");
  expect(length(3725)).toBe("1:02:05");
  expect(length(null)).toBe("–");
});

test("rows render in order with their lengths", () => {
  renderCard();
  expect(screen.getByRole("heading", { name: "Three Dark Stars" })).toBeInTheDocument();
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(3);
  expect(items[0]).toHaveTextContent("Carousel Ballroom");
  expect(items[0]).toHaveTextContent("Jan 17, 1968");
  expect(items[0]).toHaveTextContent("2:41");
  expect(items[1]).toHaveTextContent("43:32");
  expect(items[2]).toHaveTextContent("25:00");
});

test("a row's play button plays that row", async () => {
  renderCard();
  await userEvent.click(screen.getByRole("button", { name: "Play Dark Star, Cleveland Convention Center, Dec 6, 1973" }));
  expect(screen.getByRole("button", { name: /^(Pause|Loading) Dark Star, Cleveland/ })).toHaveAttribute("aria-pressed", "true");
});

test("Queue all enqueues every playable row in order, then reads as queued", async () => {
  renderCard();
  const button = screen.getByRole("button", { name: "Queue all" });
  expect(button).toHaveTextContent("+ Queue all 2 · 46:13");
  await userEvent.click(button);
  expect(screen.getByTestId("queue")).toHaveTextContent("gd-1968-01-17-dark-star-1-1 gd-1973-12-06-dark-star-1-1");
  expect(screen.getByRole("button", { name: "In the queue" })).toHaveTextContent("✓ In the queue");
});

test("a row with no tape shows its release as a text link and has no play button", () => {
  renderCard();
  expect(screen.getByRole("link", { name: "On Dick’s Picks 12" })).toHaveAttribute("href", "https://example.org/dp12");
  expect(screen.queryByRole("button", { name: /Providence/ })).not.toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /^Play Dark Star/ })).toHaveLength(2);
});

test("a note shows only on the row that has one", () => {
  renderCard();
  expect(screen.getAllByText("The first one on tape.")).toHaveLength(1);
  expect(screen.getAllByRole("listitem")[1]).not.toHaveTextContent("first one");
});

test("criteria show each version's judgments beside the points compared", () => {
  const compared: Block = {
    ...block,
    criteria: ["Length", "What follows"],
    rows: [row("1977-05-08", "Barton Hall", 540, { judgments: ["About nine minutes", "St. Stephen"] }), row("1977-05-09", "Buffalo Memorial Auditorium", 610, { judgments: ["", "The Other One"] })]
  };
  render(
    <PlayerProvider>
      <SongVersions block={compared} />
    </PlayerProvider>
  );
  expect(screen.getByText("St. Stephen")).toBeInTheDocument();
  expect(screen.getByText("The Other One")).toBeInTheDocument();
  // An empty judgment leaves its point out of that row only.
  expect(screen.getAllByText("Length")).toHaveLength(1);
  expect(screen.getAllByText("What follows")).toHaveLength(2);
});

test("rows of several songs lead with the song title and name it in the controls", () => {
  const mixed: Block = {
    ...block,
    title: null,
    rows: [
      row("1990-03-29", "Copps Coliseum", 600, { show_id: "gd-1990-03-29", song_id: "song-bird-song", song_title: "Bird Song" }),
      row("1990-03-29", "Copps Coliseum", 900, { show_id: "gd-1990-03-29", performance_id: "gd-1990-03-29-eyes-1-1", song_id: "song-eyes", song_title: "Eyes of the World" })
    ]
  };
  render(
    <PlayerProvider>
      <SongVersions block={mixed} />
    </PlayerProvider>
  );
  expect(screen.getByRole("heading", { name: "Copps Coliseum, Mar 29, 1990" })).toBeInTheDocument();
  expect(screen.getByText("Bird Song")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play Eyes of the World, Copps Coliseum, Mar 29, 1990" })).toBeInTheDocument();
});
