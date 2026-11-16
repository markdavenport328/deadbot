import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NowPlayingBar } from "./NowPlayingBar";
import { ListenControl } from "../cards/listen-control";
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
  // jsdom has no PointerEvent; a mouse event carries the fields a drag reads.
  if (!("PointerEvent" in window)) {
    class TestPointerEvent extends MouseEvent {
      pointerId: number;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 0;
      }
    }
    (window as unknown as { PointerEvent: typeof TestPointerEvent }).PointerEvent = TestPointerEvent;
  }
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

describe("the queue panel", () => {
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

  async function menuFor(panel: HTMLElement, title: string) {
    await click(within(panel).getByRole("button", { name: `More for ${title}` }));
    return screen.getByRole("menu", { name: `Actions for ${title}` });
  }

  const status = (panel: HTMLElement) => within(panel).getByRole("status").textContent;

  it("shows what is playing, then Up next with its time, and collapses again", async () => {
    const panel = await openQueue();
    expect(within(panel).getByText("Now playing")).toBeInTheDocument();
    expect(within(panel).getByText(/3 tracks · 23 min/)).toBeInTheDocument();
    expect(within(panel).getAllByRole("listitem")).toHaveLength(3);
    // A run from one show names the show once.
    expect(within(panel).getAllByText("5/4/72 · Olympia Theatre")).toHaveLength(1);
    expect(within(panel).getByText("5/8/77 · Barton Hall")).toBeInTheDocument();
    await click(screen.getByRole("button", { name: /^Queue,/ }));
    expect(screen.queryByRole("region", { name: "Queue" })).toBeNull();
  });

  it("plays a track next from its menu", async () => {
    const panel = await openQueue();
    const menu = await menuFor(panel, "Scarlet Begonias");
    await click(within(menu).getByRole("menuitem", { name: "Play next" }));
    expect(queueText()).toBe("Bertha | Scarlet Begonias | Playing In The Band | Loser");
  });

  it("moves a track up and down from its menu and says so", async () => {
    const panel = await openQueue();
    await click(within(await menuFor(panel, "Loser")).getByRole("menuitem", { name: "Move up" }));
    expect(queueText()).toBe("Bertha | Loser | Playing In The Band | Scarlet Begonias");
    expect(status(panel)).toBe("Moved Loser to 1 in Up next");
    const menu = await menuFor(panel, "Loser");
    expect(within(menu).getByRole("menuitem", { name: "Move up" })).toBeDisabled();
    await click(within(menu).getByRole("menuitem", { name: "Move down" }));
    expect(queueText()).toBe("Bertha | Playing In The Band | Loser | Scarlet Begonias");
  });

  it("moves through the menu with the keyboard and Escape returns to ⋯", async () => {
    const panel = await openQueue();
    const menu = await menuFor(panel, "Loser");
    expect(within(menu).getByRole("menuitem", { name: "Play now" })).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(within(menu).getByRole("menuitem", { name: "Play next" })).toHaveFocus();
    fireEvent.keyDown(menu, { key: "End" });
    expect(within(menu).getByRole("menuitem", { name: "Remove from queue" })).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(within(menu).getByRole("menuitem", { name: "Play now" })).toHaveFocus();
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(within(panel).getByRole("button", { name: "More for Loser" })).toHaveFocus();
    // Escape in the menu closes only the menu, not the panel.
    expect(screen.getByRole("region", { name: "Queue" })).toBeInTheDocument();
  });

  it("removes a track from its menu and plays another from its title", async () => {
    const panel = await openQueue();
    await click(within(await menuFor(panel, "Playing In The Band")).getByRole("menuitem", { name: "Remove from queue" }));
    expect(queueText()).toBe("Bertha | Loser | Scarlet Begonias");
    expect(status(panel)).toBe("Removed Playing In The Band from the queue");
    await click(within(panel).getByRole("button", { name: "Play Loser" }));
    const bar = screen.getByRole("region", { name: "Now playing" });
    expect(bar.querySelector(".now-playing-title")).toHaveTextContent("Loser");
    expect(screen.getByRole("button", { name: "Queue, 1 track up next" })).toBeInTheDocument();
    // What has played stays listed below, quieter.
    expect(within(screen.getByRole("region", { name: "Queue" })).getByText("Played")).toBeInTheDocument();
  });

  it("drags a row by its grip to a new place", async () => {
    const panel = await openQueue();
    within(panel).getAllByRole("listitem").forEach((row, index) => {
      row.getBoundingClientRect = () => ({ top: index * 40, height: 40, bottom: index * 40 + 40, left: 0, right: 300, width: 300, x: 0, y: index * 40, toJSON() {} });
    });
    const grip = within(panel).getByRole("button", { name: /^Reorder Scarlet Begonias/ });
    await act(async () => { fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientY: 100 }); });
    await act(async () => { fireEvent.pointerMove(grip, { pointerId: 1, clientY: 10 }); });
    // The list shows where the row would land before it is dropped.
    expect(within(panel).getAllByRole("listitem")[0]).toHaveTextContent("Scarlet Begonias");
    expect(queueText()).toBe("Bertha | Playing In The Band | Loser | Scarlet Begonias");
    await act(async () => { fireEvent.pointerUp(grip, { pointerId: 1, clientY: 10 }); });
    expect(queueText()).toBe("Bertha | Scarlet Begonias | Playing In The Band | Loser");
  });

  it("moves a row with the arrow keys on its grip", async () => {
    const panel = await openQueue();
    await act(async () => { fireEvent.keyDown(within(panel).getByRole("button", { name: /^Reorder Playing In The Band/ }), { key: "ArrowDown" }); });
    expect(queueText()).toBe("Bertha | Loser | Playing In The Band | Scarlet Begonias");
  });

  it("clears what is queued around the playing track, with Undo", async () => {
    const panel = await openQueue();
    await click(within(panel).getByRole("button", { name: "Clear queue" }));
    expect(queueText()).toBe("Bertha");
    await click(within(panel).getByRole("button", { name: "Cleared. Undo" }));
    expect(queueText()).toBe("Bertha | Playing In The Band | Loser | Scarlet Begonias");
    expect(status(panel)).toBe("Restored the queue");
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
