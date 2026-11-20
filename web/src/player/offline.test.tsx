import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ListenControl } from "../cards/listen-control";
import { QueuePanel } from "./QueuePanel";
import { PlayerProvider, type PlayerTrack } from "./player";
import { OFFLINE_AUDIO_CACHE, estimateBytes, formatBytes, offlineSource, resetOfflineState, saveTracks } from "./offline";

// Saving the queue to the device: the size shown before saving, the files
// kept whole in the cache, and the player loading a saved song from the
// device once the service worker can serve it.

const show: PlayerTrack[] = ["Scarlet Begonias", "Fire On The Mountain"].map((title, index) => ({
  id: `p${index + 1}`,
  title,
  audioUrl: `https://archive.org/download/gd1977-05-08/d2t0${index + 1}.mp3`,
  durationSeconds: 600
}));

// A minimal Cache Storage: one cache of URL → Response.
const store = new Map<string, Response>();
const cache = {
  keys: async () => [...store.keys()].map((url) => new Request(url)),
  put: async (url: string, response: Response) => void store.set(url, response),
  delete: async (url: string) => store.delete(url),
  match: async (url: string) => store.get(url)
};
let controller: object | null = null;
let fetched: string[] = [];
let played: HTMLMediaElement[] = [];

beforeAll(() => {
  HTMLMediaElement.prototype.play = function play() {
    played.push(this);
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = () => {};
  HTMLMediaElement.prototype.load = () => {};
});

beforeEach(() => {
  store.clear();
  fetched = [];
  played = [];
  controller = null;
  resetOfflineState();
  vi.stubGlobal("caches", { open: async (name: string) => (name === OFFLINE_AUDIO_CACHE ? cache : undefined) });
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, get: () => ({ controller }) });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      fetched.push(url);
      return new Response(new Blob(["mp3 bytes"], { type: "audio/mpeg" }), { status: 200 });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- removing a test stub
  delete (navigator as any).serviceWorker;
});

function renderQueue() {
  render(
    <PlayerProvider>
      <ListenControl label="Scarlet Begonias" track={show[0]} queue={show} />
      <QueuePanel variant="rail" />
    </PlayerProvider>
  );
}

it("sizes a save from the songs' lengths", () => {
  expect(formatBytes(estimateBytes(show))).toBe("30 MB");
  expect(formatBytes(estimateBytes([{ durationSeconds: 3 * 3600 }]))).toBe("270 MB");
});

it("offers to save the queue with its size, saves each song whole, then offers to remove them", async () => {
  renderQueue();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Scarlet Begonias" }));
  });
  const save = await screen.findByRole("button", { name: "Save the queue to listen offline" });
  expect(screen.getByText(/about 30 MB, best on Wi-Fi/)).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(save);
  });
  expect(fetched).toEqual(show.map((track) => track.audioUrl));
  expect([...store.keys()]).toEqual(show.map((track) => track.audioUrl));
  expect(await screen.findByText("All 2 songs on this device to listen offline.")).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  });
  expect(store.size).toBe(0);
  expect(await screen.findByRole("button", { name: "Save the queue to listen offline" })).toBeInTheDocument();
});

it("loads a saved song from the device only while the service worker can serve it", async () => {
  await saveTracks([show[0].audioUrl]);
  expect(offlineSource(show[0].audioUrl)).toBe(show[0].audioUrl);
  controller = {};
  expect(offlineSource(show[0].audioUrl)).toBe(`/offline-audio?src=${encodeURIComponent(show[0].audioUrl)}`);
  expect(offlineSource(show[1].audioUrl)).toBe(show[1].audioUrl);
});

it("plays a saved song from the device and the rest from the network", async () => {
  await saveTracks([show[0].audioUrl]);
  controller = {};
  renderQueue();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Scarlet Begonias" }));
  });
  const element = played[played.length - 1];
  expect(element.getAttribute("src")).toBe(`/offline-audio?src=${encodeURIComponent(show[0].audioUrl)}`);
  await act(async () => {
    element.dispatchEvent(new Event("ended"));
  });
  expect(played[played.length - 1].getAttribute("src")).toBe(show[1].audioUrl);
});
