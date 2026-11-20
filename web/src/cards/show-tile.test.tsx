/// <reference types="node" />
import { existsSync } from "node:fs";
import { fireEvent, render } from "@testing-library/react";
import { expect, test } from "vitest";
import type { ExperienceBlock } from "../types";
import { PlayerProvider } from "../player/player";
import { ListeningHero } from "./listening";
import { showTile, trackCover, trackTile } from "./show-tile";

test("a show always gets the same tile, and its neighbours get different ones", () => {
  expect(showTile("1977-05-08")).toBe(showTile("1977-05-08"));
  // Three nights running, and one night across three years of an era.
  expect(new Set([showTile("1977-05-07"), showTile("1977-05-08"), showTile("1977-05-09")]).size).toBe(3);
  expect(new Set([showTile("1976-12-31"), showTile("1977-12-31"), showTile("1978-12-31")]).size).toBe(3);
  // Eras differ in palette.
  expect(showTile("1969-02-27")).toMatch(/\/e1v\d\.jpg$/);
  expect(showTile("1989-07-07")).toMatch(/\/e6v\d\.jpg$/);
});

test("every tile it can name is a file the site serves", () => {
  const dates = ["1966-01-08", "1969-02-27", "1972-08-27", "1974-06-18", "1977-05-08", "1983-06-22", "1990-03-29"];
  const names = new Set<string>();
  for (const date of dates) for (let day = 1; day <= 4; day += 1) names.add(showTile(`${date.slice(0, 8)}0${day}`));
  for (const seed of ["a", "gd1977-05-08.sbd", "x.mp3", ""]) names.add(showTile(null, seed));
  expect(names.size).toBeGreaterThanOrEqual(28);
  for (const name of names) expect(existsSync(`public${name}`), name).toBe(true);
});

test("a tape's waveform picture is not a cover; a release's cover is", () => {
  const tape = { id: "p1", showDate: "1977-05-08", thumbnailUrl: "https://archive.org/services/img/gd1977-05-08" };
  expect(trackCover(tape)).toBeNull();
  expect(trackTile(tape)).toBe("/icons/tiles/e4v0.jpg");
  expect(trackCover({ id: "p2", thumbnailUrl: "https://coverartarchive.org/release/x/front-500" })).toBe("https://coverartarchive.org/release/x/front-500");
  expect(trackTile({ id: "p3" })).toMatch(/^\/icons\/tiles\/e\dv\d\.jpg$/);
});

const hero = (extra: Record<string, unknown>) => ({
  type: "listening_hero", show_id: "gd-1977-05-08", show_date: "1977-05-08", venue_name: "Barton Hall, Cornell University", location: "Ithaca, NY",
  recording_identifier: "gd1977-05-08.sbd", queue: [], ...extra
}) as unknown as Extract<ExperienceBlock, { type: "listening_hero" }>;

test("the hero shows the real cover when there is one, and the show's tile when there is not or it fails", () => {
  const { container, rerender } = render(<PlayerProvider><ListeningHero block={hero({})} /></PlayerProvider>);
  const picture = () => container.querySelector("img.hero-cover") as HTMLImageElement;
  expect(picture().getAttribute("src")).toBe("/icons/tiles/e4v0.jpg");
  rerender(<PlayerProvider><ListeningHero block={hero({ image_url: "https://coverartarchive.org/release/x/front-500", image_alt: "Cornell 5/8/77 cover" })} /></PlayerProvider>);
  expect(picture().getAttribute("src")).toBe("https://coverartarchive.org/release/x/front-500");
  expect(picture()).toHaveAttribute("alt", "Cornell 5/8/77 cover");
  fireEvent.error(picture());
  expect(picture().getAttribute("src")).toBe("/icons/tiles/e4v0.jpg");
  fireEvent.error(picture());
  expect(container.querySelector("img.hero-cover")).toBeNull();
  expect(container.querySelector(".hero-cover.placeholder")).not.toBeNull();
});
