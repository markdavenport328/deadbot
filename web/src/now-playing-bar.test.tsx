import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NowPlayingBar } from "./App";
import { PlayerProvider, usePlayer, type PlayerTrack } from "./player";

// The bar's back and next steps: present only for a queue, dimmed at its ends.

const tracks: PlayerTrack[] = ["Cold Rain And Snow", "Me And Bobby McGee", "Loser"].map((title, index) => ({
  id: `gd-1971-02-21-${index + 1}`,
  title,
  audioUrl: `https://archive.org/download/gd1971-02-21/d1t0${index + 1}.mp3`,
  showDate: "1971-02-21",
  venueName: "Capitol Theatre"
}));

function Harness({ queue }: { queue: PlayerTrack[] }) {
  const player = usePlayer();
  return (
    <>
      <button type="button" onClick={() => player.play(queue[0], queue)}>
        Start
      </button>
      <NowPlayingBar />
    </>
  );
}

beforeAll(() => {
  HTMLMediaElement.prototype.play = function play() {
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.load = function load() {};
});

afterEach(cleanup);

async function start(queue: PlayerTrack[]) {
  render(
    <PlayerProvider>
      <Harness queue={queue} />
    </PlayerProvider>
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
  });
  return screen.getByRole("region", { name: "Now playing" });
}

describe("now-playing bar steps", () => {
  it("shows no steps for a single track", async () => {
    const bar = await start([tracks[0]]);
    expect(within(bar).queryByRole("button", { name: "Previous track" })).toBeNull();
    expect(within(bar).queryByRole("button", { name: "Next track" })).toBeNull();
  });

  it("steps through a queue, dimming each step at its end", async () => {
    const bar = await start(tracks);
    const previous = within(bar).getByRole("button", { name: "Previous track" });
    const next = within(bar).getByRole("button", { name: "Next track" });
    expect(previous).toBeDisabled();
    expect(next).toBeEnabled();

    await act(async () => {
      fireEvent.click(next);
    });
    expect(within(bar).getByText("Me And Bobby McGee")).toBeInTheDocument();
    expect(previous).toBeEnabled();

    await act(async () => {
      fireEvent.click(next);
    });
    expect(within(bar).getByText("Loser")).toBeInTheDocument();
    expect(next).toBeDisabled();

    await act(async () => {
      fireEvent.click(previous);
    });
    expect(within(bar).getByText("Me And Bobby McGee")).toBeInTheDocument();
  });
});
