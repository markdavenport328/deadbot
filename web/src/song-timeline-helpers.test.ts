import { afterEach, expect, test, vi } from "vitest";
import { bandX, countTicks, dayFraction, frame, lengthTicks, pinRows, pinY, pointX, yFor, yearLabelStep } from "./song-timeline-geometry";
import { askQuestion, flowLine, focusFor, initialYear, pickEyebrow, performanceTags, yearFacts } from "./song-timeline-text";
import type { SongTimelineData, YearPerformance, YearSummary } from "./song-timeline-types";
import { fetchSongYear, forgetSongYears, songYearUrl } from "./song-year";

const y1979: YearSummary = {
  year: 1979,
  count: 23,
  median_seconds: 758,
  longest: { performance_id: "p-long", seconds: 925 },
  top_next: { title: "Playing In The Band", count: 20 },
  pick: {
    performance_id: "p-msg",
    show_date: "1979-01-08",
    venue_name: "Madison Square Garden",
    set_label: "Set 2",
    seconds: 735,
    basis: "show_picked",
    basis_detail: "Charlie Miller",
    track: null
  }
};

const data: SongTimelineData = {
  song_id: "song-terrapin-station",
  title: "Terrapin Station",
  performance_count: 23,
  year_summaries: [{ year: 1978, count: 0, median_seconds: null, longest: null, top_next: null, pick: null }, y1979],
  length_points: [],
  stops: [],
  open_year: null,
  chart_view: null,
  year_questions: [{ year: 1979, question: "How did the 1979 Terrapins differ from 1977?" }]
};

const performance: YearPerformance = {
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
  track: null,
  releases: [],
  signals: [{ voice: "Charlie Miller", scope: "show" }],
  guests: []
};

afterEach(() => {
  forgetSongYears();
  vi.unstubAllGlobals();
});

test("years get equal bands and dates fall inside their year's band", () => {
  const f = frame(636, [1977, 1978, 1979], "count");
  expect(f.bandWidth).toBe(198);
  expect(bandX(f, 1979)).toBe(36 + 2 * 198);
  expect(dayFraction("1979-01-01")).toBeCloseTo(0.5 / 366);
  const x = pointX(f, "1979-07-02");
  expect(x).toBeGreaterThan(bandX(f, 1979));
  expect(x).toBeLessThan(bandX(f, 1979) + f.bandWidth);
});

test("the vertical scales round up to tidy gridlines", () => {
  expect(countTicks(28)).toEqual([0, 10, 20, 30]);
  expect(countTicks(3)).toEqual([0, 1, 2, 3]);
  expect(lengthTicks(1514)).toEqual([0, 300, 600, 900, 1200, 1500, 1800]);
  const f = frame(600, [1977], "length");
  expect(yFor(f, 0, 1800)).toBe(f.plotBottom);
  expect(yFor(f, 1800, 1800)).toBe(f.plotTop);
});

test("crowded pins stack into rows and year labels thin out when narrow", () => {
  expect(pinRows([10, 15, 60, 70, 74, 120])).toEqual([0, 1, 0, 1, 2, 0]);
  // Stops arrive in listening order; rows are assigned left to right.
  expect(pinRows([500, 100, 300, 112, 510])).toEqual([0, 0, 0, 1, 1]);
  expect(countTicks(1)).toEqual([0, 1]);
  expect(countTicks(2)).toEqual([0, 1, 2]);
  const roomy = frame(600, [1977], "count", 3);
  expect(roomy.plotTop - frame(600, [1977], "count").plotTop).toBe(38);
  expect(pinY(roomy, 2)).toBeGreaterThan(0);
  expect(yearLabelStep(50)).toBe(1);
  expect(yearLabelStep(25)).toBe(3);
  expect(yearLabelStep(12)).toBe(6);
});

test("a year's facts, pick and question read from the data", () => {
  expect(yearFacts(y1979)).toBe("23 performances · typically 12:38 · usually followed by Playing In The Band (20 of 23)");
  expect(pickEyebrow(y1979.pick!, null)).toBe("Show picked by Charlie Miller");
  expect(pickEyebrow(y1979.pick!, { number: 4, label: "Charlie Miller's pick" })).toBe("Stop 4 · Charlie Miller's pick");
  expect(pickEyebrow({ ...y1979.pick!, basis: "released", basis_detail: "Dave's Picks, Volume 31: Uptown Theatre" }, null)).toBe("On Dave's Picks, Volume 31");
  expect(askQuestion(data, 1979)).toBe("How did the 1979 Terrapins differ from 1977?");
  expect(askQuestion(data, 1980)).toBe("Tell me about Terrapin Station in 1980");
});

test("a performance's flow joins segues with › and names its tags", () => {
  expect(flowLine(performance, "Terrapin Station")).toBe("Terrapin Station › Playing In The Band");
  expect(flowLine({ ...performance, previous: { ...performance.previous!, segued: true }, next: null }, "Terrapin Station")).toBe(
    "Samson And Delilah › Terrapin Station, closing the set"
  );
  expect(performanceTags({ ...performance, releases: ["X"] }, 4)).toEqual(["Stop 4", "Show picked by Charlie Miller", "Released"]);
});

test("focus names the song, the year and its pick; the open year falls back to a played year", () => {
  expect(focusFor(data, y1979)).toEqual({
    label: "Terrapin Station in 1979",
    song_id: "song-terrapin-station",
    year: 1979,
    ids: ["song-terrapin-station", "p-msg"],
    facts: ["23 performances · typically 12:38 · usually followed by Playing In The Band (20 of 23)"]
  });
  expect(initialYear(data)).toBe(1979);
  expect(initialYear({ ...data, open_year: 1978 })).toBe(1979);
});

test("the year lookup asks once per song and year and retries after a failure", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 503 })
    .mockResolvedValue({ ok: true, json: async () => ({ song_id: "s", title: "T", year: 1979, performances: [] }) });
  vi.stubGlobal("fetch", fetchMock);
  expect(songYearUrl("song-terrapin-station", 1979)).toBe("/api/songs/song-terrapin-station/years/1979");
  await expect(fetchSongYear("s", 1979)).rejects.toThrow("The 1979 list could not load (503).");
  await fetchSongYear("s", 1979);
  await fetchSongYear("s", 1979);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
