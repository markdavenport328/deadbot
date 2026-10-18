import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NowPlayingBar } from "./App";
import { ListenControl } from "./listen-control";
import { PlayerProvider, usePlayer, type PlayerTrack } from "./player";

// The visitor's queue: a "+" beside a play adds to it without interrupting,
// and the bar's queue toggle opens a list that can jump, move and remove.

const show: PlayerTrack[] = ["Bertha", "Playing In The Band", "Loser"].map((title, index) => ({
  id: `gd-1972-05-04-${index + 1}`,
  title,
  audioUrl: `https://archive.org/download/gd1972-05-04/d1t0${index + 1}.mp3`,
  durationSeconds: 300 + index * 60,
  showDate: "1972-05-04",
  venueName: "Olympia Theatre"
}));

const other: PlayerTrack = {
  id: "gd-1977-05-08-dark-star",
  title: "Scarlet Begonias",
  audioUrl: "https://archive.org/download/gd1977-05-08/d2t01.mp3",
  durationSeconds: 600,
  showDate: "1977-05-08",
  venueName: "Barton Hall"
};

function QueueProbe() {
  const player = usePlayer();
  return <p data-testid="queue">{player.queue.map((track) => track.title).join(" | ")}</p>;
}

beforeAll(() => {
  HTMLMediaElement.prototype.play = function play() {
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.load = function load() {};
});

afterEach(cleanup);

function renderPage() {
  render(
    <PlayerProvider>
      <ListenControl label="Bertha" track={show[0]} queue={show} />
      <ListenControl label="Scarlet Begonias" track={other} />
      <QueueProbe />
      <NowPlayingBar />
    </PlayerProvider>
  );
}

async function click(element: HTMLElement) {
  await act(async () => {
    fireEvent.click(element);
  });
}

const queueText = () => screen.getByTestId("queue").textContent;

describe("adding to the queue", () => {
  it("loads a track paused into an empty player", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Add Scarlet Begonias to queue" }));
    expect(queueText()).toBe("Scarlet Begonias");
    const bar = screen.getByRole("region", { name: "Now playing" });
    expect(within(bar).getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("appends without replacing what plays, and the check takes it back out", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Bertha" }));
    expect(queueText()).toBe("Bertha | Playing In The Band | Loser");
    await click(screen.getByRole("button", { name: "Add Scarlet Begonias to queue" }));
    expect(queueText()).toBe("Bertha | Playing In The Band | Loser | Scarlet Begonias");
    expect(within(screen.getByRole("region", { name: "Now playing" })).getByText("Bertha")).toBeInTheDocument();
    await click(screen.getByRole("button", { name: "Remove Scarlet Begonias from queue" }));
    expect(queueText()).toBe("Bertha | Playing In The Band | Loser");
  });

  it("Play still replaces the queue", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Bertha" }));
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    expect(queueText()).toBe("Scarlet Begonias");
  });
});

describe("the Up next panel", () => {
  async function openQueue() {
    renderPage();
    await click(screen.getByRole("button", { name: "Bertha" }));
    await click(screen.getByRole("button", { name: "Add Scarlet Begonias to queue" }));
    const toggle = screen.getByRole("button", { name: "Queue, 3 tracks up next" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    return screen.getByRole("region", { name: "Queue" });
  }

  it("lists the queue and collapses again", async () => {
    const panel = await openQueue();
    expect(within(panel).getAllByRole("listitem")).toHaveLength(4);
    expect(within(panel).getByRole("button", { name: "Bertha, playing now" })).toBeDisabled();
    // A run from one show names the show once.
    expect(within(panel).getAllByText("5/4/72 · Olympia Theatre")).toHaveLength(1);
    await click(screen.getByRole("button", { name: /^Queue,/ }));
    expect(screen.queryByRole("region", { name: "Queue" })).toBeNull();
  });

  it("moves a track up to play next", async () => {
    const panel = await openQueue();
    await click(within(panel).getByRole("button", { name: "Play Scarlet Begonias next" }));
    expect(queueText()).toBe("Bertha | Scarlet Begonias | Playing In The Band | Loser");
    expect(within(panel).queryByRole("button", { name: "Play Scarlet Begonias next" })).toBeNull();
  });

  it("removes a track and jumps to another", async () => {
    const panel = await openQueue();
    await click(within(panel).getByRole("button", { name: "Remove Playing In The Band from queue" }));
    expect(queueText()).toBe("Bertha | Loser | Scarlet Begonias");
    await click(within(panel).getByRole("button", { name: "Play Loser" }));
    const bar = screen.getByRole("region", { name: "Now playing" });
    expect(within(bar).getByRole("button", { name: "Loser, playing now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Queue, 1 track up next" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const panel = await openQueue();
    await act(async () => {
      fireEvent.keyDown(within(panel).getByRole("button", { name: "Play Loser" }), { key: "Escape" });
    });
    expect(screen.queryByRole("region", { name: "Queue" })).toBeNull();
    expect(screen.getByRole("button", { name: /^Queue,/ })).toHaveFocus();
  });
});
