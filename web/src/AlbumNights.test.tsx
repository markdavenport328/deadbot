import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NightList, groupByNight } from "./AlbumNights";
import { PlayerProvider, usePlayer } from "./player";
import type { AlbumUnitBlock } from "./types";

type Track = AlbumUnitBlock["tracks"][number];

beforeAll(() => {
  HTMLMediaElement.prototype.play = function play() {
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.load = function load() {};
});
afterEach(cleanup);

function track(number: number, title: string, show: { id: string; date: string; venue: string; city?: string } | null, tape = true): Track {
  return {
    track_number: number,
    title,
    performance_id: `perf-${number}`,
    highlighted: false,
    audio_url: tape ? `https://archive.org/download/x/${number}.mp3` : null,
    show_id: show?.id ?? null,
    show_date: show?.date ?? null,
    venue_name: show?.venue ?? null,
    city: show?.city ?? null
  } as Track;
}

const LONDON = { id: "gd-1972-04-07", date: "1972-04-07", venue: "Empire Pool", city: "London" };
const NEWCASTLE = { id: "gd-1972-04-11", date: "1972-04-11", venue: "City Hall", city: "Newcastle" };

// Tracks arrive in the record's own order, not date order.
const BOX = [
  track(1, "Truckin'", NEWCASTLE),
  track(2, "Ramble On Rose", NEWCASTLE),
  track(3, "Bertha", NEWCASTLE),
  track(4, "Jack Straw", LONDON),
  track(5, "Sugaree", LONDON),
  track(6, "Tennessee Jed", LONDON),
  track(7, "Tuning Rap", null)
];

function Probe() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((item) => item.title).join("|")}</output>;
}

function renderNights(tracks: Track[]) {
  const groups = groupByNight(tracks);
  if (!groups) throw new Error("expected nights");
  render(
    <PlayerProvider>
      <NightList groups={groups} />
      <Probe />
    </PlayerProvider>
  );
}

describe("a multi-show record's tracklist", () => {
  it("groups tracks by night in date order, with tracks from no show last", () => {
    const groups = groupByNight(BOX)!;
    expect(groups.nights.map((night) => night.key)).toEqual([LONDON.id, NEWCASTLE.id]);
    expect(groups.nights[0].tracks.map((item) => item.title)).toEqual(["Jack Straw", "Sugaree", "Tennessee Jed"]);
    expect(groups.other.map((item) => item.title)).toEqual(["Tuning Rap"]);
  });

  it("leaves a compilation of a song or two per night as a plain tracklist", () => {
    expect(groupByNight([track(1, "A", LONDON), track(2, "B", NEWCASTLE), track(3, "C", NEWCASTLE)])).toBeNull();
  });

  it("leaves a single-show or studio record as a plain tracklist", () => {
    expect(groupByNight([track(1, "A", LONDON), track(2, "B", LONDON)])).toBeNull();
    expect(groupByNight([track(1, "A", null), track(2, "B", null)])).toBeNull();
  });

  it("shows a row per night with date, venue, city and count, and an Other tracks row", () => {
    renderNights(BOX);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Apr 7, 1972");
    expect(rows[0]).toHaveTextContent("Empire Pool, London · 3 tracks");
    expect(rows[2]).toHaveTextContent("Other tracks");
  });

  it("opens a night to its tracks", () => {
    renderNights(BOX);
    expect(screen.queryByText("Jack Straw")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Tracks on Apr 7, 1972/ }));
    expect(screen.getByText("Jack Straw")).toBeInTheDocument();
    expect(screen.queryByText("Truckin'")).toBeNull();
  });

  it("plays a night's tape as that night's queue", () => {
    renderNights(BOX);
    fireEvent.click(screen.getByRole("button", { name: /Play Apr 11, 1972/ }));
    expect(screen.getByTestId("queue").textContent).toBe("Truckin'|Ramble On Rose|Bertha");
    fireEvent.click(screen.getByRole("button", { name: /Play Apr 7, 1972/ }));
    expect(screen.getByTestId("queue").textContent).toBe("Jack Straw|Sugaree|Tennessee Jed");
  });

  it("offers no play for a night without tape", () => {
    renderNights([
      track(1, "A", LONDON, false), track(2, "B", LONDON, false), track(3, "C", LONDON, false),
      track(4, "D", NEWCASTLE), track(5, "E", NEWCASTLE), track(6, "F", NEWCASTLE)
    ]);
    expect(screen.queryByRole("button", { name: /Play Apr 7, 1972/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Play Apr 11, 1972/ })).toBeInTheDocument();
  });
});
