import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { PlayerProvider, usePlayer } from "../player/player";
import type { ExperienceBlock, ShowUnitBlock } from "../types";
import { ShowUnit } from "./units/ShowUnit";

// A show card plays and queues its whole show whichever facets it shows; a
// setlist of several sets offers each set's play and +; a performance card's
// + adds its own song.


const TAPE = "https://archive.org/download/gd1972-08-27.sbd";
const track = (id: string, title: string) => ({ performance_id: id, title, audio_url: `${TAPE}/${id}.mp3`, duration_seconds: 300 });

function show(extra: Partial<ShowUnitBlock>): ShowUnitBlock {
  return {
    type: "show_unit",
    show_id: "gd-1972-08-27",
    title: null,
    show_date: "1972-08-27",
    venue_name: "Old Renaissance Faire Grounds",
    location: "Veneta, OR",
    emphasis: "primary",
    disclosure: "expanded",
    tracks: [],
    note: null,
    visible_facets: [],
    setlist_disclosure: "expanded",
    sets: [],
    setlist_note: null,
    recording_identifier: null,
    recording_details_url: null,
    guests: [],
    lineup: [],
    recordings: [],
    judgments: [],
    listen: [],
    sources: [],
    follow_ups: [],
    ...extra
  } as ShowUnitBlock;
}

const song = (id: string, title: string) => ({ performance_id: id, song_id: `song-${id}`, title, highlighted: false, audio_url: `${TAPE}/${id}.mp3`, duration_seconds: 300, segue_into_next: false });

function Queue() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((item) => item.id).join(" ")}</output>;
}

function renderWithPlayer(node: React.ReactNode) {
  render(
    <PlayerProvider>
      {node}
      <Queue />
    </PlayerProvider>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
});

test("a show card with no setlist plays and queues the tape it carries", async () => {
  const unit = show({ visible_facets: ["guests"], tracks: [track("p1", "Promised Land"), track("p2", "Sugaree")] });
  renderWithPlayer(<ShowUnit unit={unit} criteria={[]} soleUnit onFollowUp={() => {}} />);
  expect(document.querySelector(".card-head .card-play")).not.toBeNull();
  await userEvent.click(screen.getByRole("button", { name: /^Add .* to queue$/ }));
  expect(screen.getByTestId("queue")).toHaveTextContent("p1 p2");
});

test("a setlist of several sets offers each set's play and +", async () => {
  const unit = show({
    visible_facets: ["setlist"],
    sets: [
      { label: "Set 1", songs: [song("p1", "Promised Land"), song("p2", "Sugaree")] },
      { label: "Set 2", songs: [song("p3", "Dark Star"), song("p4", "El Paso")] }
    ]
  });
  renderWithPlayer(<ShowUnit unit={unit} criteria={[]} soleUnit onFollowUp={() => {}} />);
  await userEvent.click(screen.getByRole("button", { name: "Add Set 2 to queue" }));
  expect(screen.getByTestId("queue")).toHaveTextContent(/^p3 p4$/);
  await userEvent.click(screen.getByRole("button", { name: "Play Set 1" }));
  expect(screen.getByTestId("queue")).toHaveTextContent(/^p1 p2$/);
});

test("a one-set setlist leaves the whole-show controls to the card's header", () => {
  const unit = show({ visible_facets: ["setlist"], sets: [{ label: "Set 1", songs: [song("p1", "Promised Land"), song("p2", "Sugaree")] }] });
  renderWithPlayer(<ShowUnit unit={unit} criteria={[]} soleUnit onFollowUp={() => {}} />);
  expect(screen.queryByRole("button", { name: "Play Set 1" })).toBeNull();
  expect(document.querySelector(".card-head .card-play")).not.toBeNull();
});
