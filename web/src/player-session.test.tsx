import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NowPlayingBar } from "./App";
import { ListenControl } from "./listen-control";
import { PLAYER_RATE_KEY, PLAYER_STORAGE_KEY, PlayerProvider, readSavedPlayer, type PlayerTrack } from "./player";

// The player beyond the page: a queue that survives a reload, the next track
// loaded before the current one ends, and the phone's lock screen controls.

const show: PlayerTrack[] = ["Scarlet Begonias", "Fire On The Mountain", "Estimated Prophet"].map((title, index) => ({
  id: `gd-1977-05-08-${index + 1}`,
  title,
  audioUrl: `https://archive.org/download/gd1977-05-08/d2t0${index + 1}.mp3`,
  durationSeconds: 600,
  showDate: "1977-05-08",
  venueName: "Barton Hall",
  thumbnailUrl: "https://archive.org/services/img/gd1977-05-08"
}));

// Every element play() and load() were called on, in order.
let played: HTMLMediaElement[] = [];
let loaded: HTMLMediaElement[] = [];

beforeAll(() => {
  HTMLMediaElement.prototype.play = function play() {
    played.push(this);
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.load = function load() {
    loaded.push(this);
  };
});

beforeEach(() => {
  played = [];
  loaded = [];
});

afterEach(cleanup);

function renderPage() {
  render(
    <PlayerProvider>
      <ListenControl label="Scarlet Begonias" track={show[0]} queue={show} />
      <NowPlayingBar />
    </PlayerProvider>
  );
}

async function click(element: HTMLElement) {
  await act(async () => {
    fireEvent.click(element);
  });
}

function setTime(element: HTMLMediaElement, seconds: number) {
  Object.defineProperty(element, "currentTime", { configurable: true, writable: true, value: seconds });
}

const bar = () => screen.getByRole("region", { name: "Now playing" });

describe("saving the queue", () => {
  it("saves the queue and the place in it as the visitor plays", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    const saved = readSavedPlayer();
    expect(saved?.queue.map((track) => track.title)).toEqual(["Scarlet Begonias", "Fire On The Mountain", "Estimated Prophet"]);
    expect(saved?.index).toBe(0);
  });

  it("restores a saved queue paused, at the saved track and position", async () => {
    window.localStorage.setItem(PLAYER_STORAGE_KEY, JSON.stringify({ queue: show, index: 1, position: 125 }));
    renderPage();
    expect(within(bar()).getByText("Fire On The Mountain")).toBeInTheDocument();
    expect(within(bar()).getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(within(bar()).getByText("2:05")).toBeInTheDocument();
    expect(played).toHaveLength(0);
  });

  it("ignores saved data it cannot read and keeps the tracks it can", () => {
    window.localStorage.setItem(PLAYER_STORAGE_KEY, "{not json");
    expect(readSavedPlayer()).toBeNull();
    window.localStorage.setItem(PLAYER_STORAGE_KEY, JSON.stringify({ queue: [{ title: "No URL" }, show[2]], index: 7, position: "x" }));
    expect(readSavedPlayer()).toEqual({ queue: [show[2]], index: 0, position: 0 });
  });
});

describe("loading the next track early", () => {
  it("loads the next track as the current one nears its end, and plays that element when it ends", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    const first = played[played.length - 1];
    expect(first.getAttribute("src")).toBe(show[0].audioUrl);

    setTime(first, 400);
    await act(async () => {
      first.dispatchEvent(new Event("timeupdate"));
    });
    expect(loaded).toHaveLength(0);

    setTime(first, 580);
    await act(async () => {
      first.dispatchEvent(new Event("timeupdate"));
    });
    const spare = loaded[loaded.length - 1];
    expect(spare).not.toBe(first);
    expect(spare.getAttribute("src")).toBe(show[1].audioUrl);

    await act(async () => {
      first.dispatchEvent(new Event("ended"));
    });
    expect(played[played.length - 1]).toBe(spare);
    expect(within(bar()).getByText("Fire On The Mountain")).toBeInTheDocument();
    // The old element's late events no longer move the player.
    await act(async () => {
      first.dispatchEvent(new Event("pause"));
      spare.dispatchEvent(new Event("playing"));
    });
    expect(within(bar()).getByRole("button", { name: "Pause" })).toBeInTheDocument();
  });
});

describe("speed and loop", () => {
  const more = () => within(bar()).getByRole("button", { name: /^Speed and loop/ });
  const panel = () => within(bar()).getByRole("region", { name: "Speed and loop" });

  async function startPlaying() {
    renderPage();
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    const element = played[played.length - 1];
    await act(async () => {
      element.dispatchEvent(new Event("playing"));
    });
    return element;
  }

  it("sets the speed from the menu, keeps it on the next track, and remembers it", async () => {
    await startPlaying();
    await click(more());
    await click(within(panel()).getByRole("button", { name: "0.5×" }));
    expect(within(panel()).getByRole("button", { name: "0.5×" })).toHaveAttribute("aria-pressed", "true");
    expect(played[played.length - 1].playbackRate).toBe(0.5);
    // The closed menu still says the speed changed.
    expect(more()).toHaveAccessibleName("Speed and loop: 0.5×");
    expect(more()).toHaveTextContent("0.5×");

    await click(within(bar()).getByRole("button", { name: "Next track" }));
    expect(played[played.length - 1].playbackRate).toBe(0.5);
    expect(window.localStorage.getItem(PLAYER_RATE_KEY)).toBe("0.5");

    cleanup();
    renderPage();
    expect(more()).toHaveTextContent("0.5×");
  });

  it("opens in the queue's place, one panel at a time", async () => {
    await startPlaying();
    await click(more());
    expect(panel()).toBeInTheDocument();
    await click(within(bar()).getByRole("button", { name: /^Queue/ }));
    expect(within(bar()).queryByRole("region", { name: "Speed and loop" })).toBeNull();
    expect(within(bar()).getByRole("region", { name: "Queue" })).toBeInTheDocument();
  });

  it("loops a passage: crossing the end jumps back to the start, and a new track clears it", async () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => frames.push(callback));
    vi.stubGlobal("cancelAnimationFrame", () => {});
    const runFrame = () => act(async () => frames.shift()?.(0));
    try {
      const element = await startPlaying();
      await click(more());
      setTime(element, 30);
      await click(within(panel()).getByRole("button", { name: "Set loop start to now" }));
      setTime(element, 41);
      await click(within(panel()).getByRole("button", { name: "Set loop end to now" }));
      expect(within(panel()).getByRole("button", { name: "Loop start 0:30, set to now" })).toBeInTheDocument();
      expect(within(panel()).getByRole("button", { name: "Loop end 0:41, set to now" })).toBeInTheDocument();
      expect(more()).toHaveAccessibleName("Speed and loop: looping");
      expect(bar().querySelector(".now-playing-loop")).toHaveStyle({ left: "5%" });

      // Setting the end while playing goes straight back to the start.
      setTime(element, 41.02);
      await runFrame();
      expect(element.currentTime).toBe(30);

      setTime(element, 40.9);
      await runFrame();
      expect(element.currentTime).toBe(40.9);
      setTime(element, 41.05);
      await runFrame();
      expect(element.currentTime).toBe(30);

      // A seek past the end is the visitor's choice: no jump back.
      setTime(element, 200);
      await runFrame();
      expect(element.currentTime).toBe(200);

      await click(within(panel()).getByRole("button", { name: "Clear" }));
      expect(within(panel()).getByRole("button", { name: "Set loop start to now" })).toBeInTheDocument();

      setTime(element, 50);
      await click(within(panel()).getByRole("button", { name: "Set loop start to now" }));
      await click(within(bar()).getByRole("button", { name: "Next track" }));
      expect(bar().querySelector(".now-playing-loop")).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("goes round again when the loop's end is the track's end", async () => {
    const element = await startPlaying();
    await click(more());
    setTime(element, 590);
    await click(within(panel()).getByRole("button", { name: "Set loop start to now" }));
    setTime(element, 600);
    await click(within(panel()).getByRole("button", { name: "Set loop end to now" }));
    await act(async () => {
      element.dispatchEvent(new Event("ended"));
    });
    expect(element.currentTime).toBe(590);
    expect(within(bar()).getByText("Scarlet Begonias")).toBeInTheDocument();
  });
});

describe("lock screen controls", () => {
  type Handler = (details: { seekTime?: number; seekOffset?: number }) => void;
  let handlers: Record<string, Handler | null>;
  let session: { metadata: unknown; playbackState: string; setActionHandler: (action: string, handler: Handler | null) => void; setPositionState: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    handlers = {};
    session = {
      metadata: null,
      playbackState: "none",
      setActionHandler: (action, handler) => {
        handlers[action] = handler;
      },
      setPositionState: vi.fn()
    };
    Object.defineProperty(navigator, "mediaSession", { configurable: true, value: session });
    vi.stubGlobal(
      "MediaMetadata",
      class {
        constructor(public init: Record<string, unknown>) {}
      }
    );
  });

  afterEach(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- removing a test stub
    delete (navigator as any).mediaSession;
    vi.unstubAllGlobals();
  });

  it("names the track, show and artwork, and drives the queue from the buttons", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    expect((session.metadata as { init: Record<string, unknown> }).init).toEqual({
      title: "Scarlet Begonias",
      artist: "Grateful Dead",
      album: "May 8, 1977 · Barton Hall",
      artwork: [{ src: "https://archive.org/services/img/gd1977-05-08" }]
    });
    const element = played[played.length - 1];
    await act(async () => {
      element.dispatchEvent(new Event("playing"));
    });
    expect(session.playbackState).toBe("playing");

    await act(async () => {
      handlers.nexttrack?.({});
    });
    expect(within(bar()).getByText("Fire On The Mountain")).toBeInTheDocument();

    // "Previous" past the first few seconds restarts the track.
    const current = played[played.length - 1];
    setTime(current, 90);
    await act(async () => {
      handlers.previoustrack?.({});
    });
    expect(current.currentTime).toBe(0);
    expect(within(bar()).getByText("Fire On The Mountain")).toBeInTheDocument();
    await act(async () => {
      handlers.previoustrack?.({});
    });
    expect(within(bar()).getByText("Scarlet Begonias")).toBeInTheDocument();

    await act(async () => {
      handlers.seekto?.({ seekTime: 42 });
    });
    expect(session.setPositionState).toHaveBeenLastCalledWith({ duration: 600, playbackRate: 1, position: 42 });
  });
});
