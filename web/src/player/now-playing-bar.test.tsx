import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NowPlayingBar } from "./NowPlayingBar";
import { PlayerProvider, usePlayer, type PlayerTrack } from "./player";

// The bar's back and next steps: present only for a queue, dimmed at its ends.

const tracks: PlayerTrack[] = ["Cold Rain And Snow", "Me And Bobby McGee", "Loser"].map((title, index) => ({
  id: `gd-1971-02-21-${index + 1}`,
  title,
  audioUrl: `https://archive.org/download/gd1971-02-21/d1t0${index + 1}.mp3`,
  showDate: "1971-02-21",
  venueName: "Capitol Theatre"
}));

function Harness({ queue, sheet = false }: { queue: PlayerTrack[]; sheet?: boolean }) {
  const player = usePlayer();
  return (
    <>
      <button type="button" onClick={() => player.play(queue[0], queue)}>
        Start
      </button>
      {sheet ? <NowPlayingBar collapsible queueSheet /> : <NowPlayingBar />}
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

async function start(queue: PlayerTrack[], sheet = false) {
  render(
    <PlayerProvider>
      <Harness queue={queue} sheet={sheet} />
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

describe("the phone's queue sheet", () => {
  it("opens from a labeled Queue button with Clear and reorder, and closes back to the button", async () => {
    const bar = await start(tracks, true);
    const button = within(bar).getByRole("button", { name: "Queue, 2 tracks up next" });
    expect(button).toHaveTextContent("Queue");
    await act(async () => { fireEvent.click(button); });
    const sheet = screen.getByRole("dialog", { name: "Queue" });
    expect(within(sheet).getByRole("button", { name: "Clear queue" })).toBeInTheDocument();
    expect(within(sheet).getAllByRole("button", { name: /^Reorder / })).toHaveLength(2);
    // The sheet's Clear empties Up next and offers Undo in place.
    fireEvent.click(within(sheet).getByRole("button", { name: "Clear queue" }));
    expect(within(sheet).getByRole("button", { name: "Cleared. Undo" })).toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: "Cleared. Undo" }));
    await act(async () => { fireEvent.click(within(sheet).getByRole("button", { name: "Close queue" })); });
    expect(screen.queryByRole("dialog", { name: "Queue" })).toBeNull();
    expect(button).toHaveFocus();
    await act(async () => { fireEvent.click(button); });
    await act(async () => { fireEvent.keyDown(document, { key: "Escape" }); });
    expect(screen.queryByRole("dialog", { name: "Queue" })).toBeNull();
  });
});
