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

describe("playback speed", () => {
  it("steps through the speeds, keeps the speed on the next track, and remembers it", async () => {
    renderPage();
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    const speed = () => within(bar()).getByRole("button", { name: /^Playback speed/ });
    expect(speed()).toHaveTextContent("1×");
    await click(speed());
    await click(speed());
    expect(speed()).toHaveTextContent("0.5×");
    expect(speed()).toHaveAccessibleName("Playback speed 0.5×, change to 1.25×");
    expect(played[played.length - 1].playbackRate).toBe(0.5);

    await click(within(bar()).getByRole("button", { name: "Next track" }));
    expect(played[played.length - 1].playbackRate).toBe(0.5);
    expect(window.localStorage.getItem(PLAYER_RATE_KEY)).toBe("0.5");

    cleanup();
    renderPage();
    expect(speed()).toHaveTextContent("0.5×");
  });

  it("steps up to the faster speeds after the slow ones, then back to normal", async () => {
    window.localStorage.setItem(PLAYER_RATE_KEY, "0.5");
    renderPage();
    await click(screen.getByRole("button", { name: "Scarlet Begonias" }));
    const speed = () => within(bar()).getByRole("button", { name: /^Playback speed/ });
    await click(speed());
    expect(speed()).toHaveTextContent("1.25×");
    await click(speed());
    expect(speed()).toHaveTextContent("1.5×");
    await click(speed());
    expect(speed()).toHaveTextContent("1×");
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
