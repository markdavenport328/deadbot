import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NowPlayingBar } from "./NowPlayingBar";
import { ListenControl, toTrack } from "../cards/listen-control";
import { PlayerProvider, locate, songTime, trackKey, type PlayerTrack } from "./player";

// A song that is not one whole file: a window of a file it shares with the
// next song, or a jam the tape cuts into two files. Pressing play plays that
// song from its start to its end, and the bar shows the song's own clock.

const TAPE = "https://archive.org/download/gd1970-02-13.aud";

// I Know You Rider, 4:41 into a China Cat > Rider file, 5:12 long.
const rider: PlayerTrack = {
  id: "rider",
  title: "I Know You Rider",
  audioUrl: `${TAPE}/d1t02.mp3`,
  durationSeconds: 312,
  segments: [{ url: `${TAPE}/d1t02.mp3`, start: 281, end: 593 }]
};

// Dark Star over two files: 27:50 and 2:03.
const darkStar: PlayerTrack = {
  id: "dark-star",
  title: "Dark Star",
  audioUrl: `${TAPE}/d2t01.mp3`,
  durationSeconds: 1793,
  segments: [
    { url: `${TAPE}/d2t01.mp3`, start: 0, end: 1670 },
    { url: `${TAPE}/d2t02.mp3`, start: 0, end: 123 }
  ]
};

const after: PlayerTrack = { id: "after", title: "Cryptical Envelopment", audioUrl: `${TAPE}/d2t03.mp3`, durationSeconds: 120 };

let played: HTMLMediaElement[] = [];

beforeAll(() => {
  HTMLMediaElement.prototype.play = function play() {
    played.push(this);
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.load = function load() {};
});

beforeEach(() => {
  played = [];
  window.localStorage.clear();
});

afterEach(cleanup);

function renderQueue(start: PlayerTrack, queue: PlayerTrack[]) {
  render(
    <PlayerProvider>
      <ListenControl label={start.title} track={start} queue={queue} />
      <NowPlayingBar />
    </PlayerProvider>
  );
}

const bar = () => screen.getByRole("region", { name: "Now playing" });

function setTime(element: HTMLMediaElement, seconds: number) {
  Object.defineProperty(element, "currentTime", { configurable: true, writable: true, value: seconds });
}

function setFileLength(element: HTMLMediaElement, seconds: number) {
  Object.defineProperty(element, "duration", { configurable: true, value: seconds });
}

async function fire(element: HTMLMediaElement, name: string) {
  await act(async () => {
    element.dispatchEvent(new Event(name));
  });
}

async function startPlaying(track: PlayerTrack, queue: PlayerTrack[]): Promise<HTMLMediaElement> {
  renderQueue(track, queue);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: track.title }));
  });
  return played[played.length - 1];
}

const scrubber = (title: string) => within(bar()).getByRole("slider", { name: `Seek within ${title}` });

describe("a song that starts partway into its file", () => {
  it("starts at the song, counts from zero, and shows the song's length", async () => {
    const element = await startPlaying(rider, [rider, after]);
    expect(element.getAttribute("src")).toBe(rider.audioUrl);
    setFileLength(element, 900);
    await fire(element, "loadedmetadata");
    expect(element.currentTime).toBe(281);
    // The file is 15:00; the song is 5:12.
    expect(scrubber("I Know You Rider")).toHaveAttribute("aria-valuetext", "0:00 of 5:12");

    setTime(element, 400);
    await fire(element, "timeupdate");
    expect(scrubber("I Know You Rider")).toHaveAttribute("aria-valuetext", "1:59 of 5:12");
  });

  it("seeks on the song's clock", async () => {
    const element = await startPlaying(rider, [rider, after]);
    setFileLength(element, 900);
    await fire(element, "loadedmetadata");
    await act(async () => {
      fireEvent.change(scrubber("I Know You Rider"), { target: { value: "100" } });
    });
    expect(element.currentTime).toBe(381);
  });

  it("moves on to the next song where this one ends, not at the end of the file", async () => {
    const element = await startPlaying(rider, [rider, after]);
    setFileLength(element, 900);
    await fire(element, "loadedmetadata");
    setTime(element, 593.2);
    await fire(element, "timeupdate");
    expect(within(bar()).getByText("Cryptical Envelopment")).toBeInTheDocument();
    expect(played[played.length - 1].getAttribute("src")).toBe(after.audioUrl);
  });

  it("stops where the song ends when nothing follows it", async () => {
    const element = await startPlaying(rider, [rider]);
    setFileLength(element, 900);
    await fire(element, "loadedmetadata");
    const pause = vi.spyOn(element, "pause");
    setTime(element, 594);
    await fire(element, "timeupdate");
    expect(pause).toHaveBeenCalled();
    expect(scrubber("I Know You Rider")).toHaveAttribute("aria-valuetext", "5:12 of 5:12");
  });
});

describe("a song the tape cuts into two files", () => {
  it("plays the second file after the first, as one track with one length", async () => {
    const first = await startPlaying(darkStar, [darkStar, after]);
    expect(first.getAttribute("src")).toBe(`${TAPE}/d2t01.mp3`);
    setFileLength(first, 1670);
    await fire(first, "loadedmetadata");
    expect(scrubber("Dark Star")).toHaveAttribute("aria-valuetext", "0:00 of 29:53");

    await fire(first, "ended");
    const second = played[played.length - 1];
    expect(second.getAttribute("src")).toBe(`${TAPE}/d2t02.mp3`);
    // Still Dark Star, 27:50 in.
    expect(within(bar()).getByText("Dark Star")).toBeInTheDocument();
    setFileLength(second, 123);
    await fire(second, "loadedmetadata");
    setTime(second, 10);
    await fire(second, "timeupdate");
    expect(scrubber("Dark Star")).toHaveAttribute("aria-valuetext", "28:00 of 29:53");

    await fire(second, "ended");
    expect(within(bar()).getByText("Cryptical Envelopment")).toBeInTheDocument();
  });

  it("seeks across the files", async () => {
    const first = await startPlaying(darkStar, [darkStar, after]);
    setFileLength(first, 1670);
    await fire(first, "loadedmetadata");
    await act(async () => {
      fireEvent.change(scrubber("Dark Star"), { target: { value: "1700" } });
    });
    const element = played[played.length - 1];
    expect(element.getAttribute("src")).toBe(`${TAPE}/d2t02.mp3`);
    await fire(element, "loadedmetadata");
    expect(element.currentTime).toBe(30);
    expect(scrubber("Dark Star")).toHaveAttribute("aria-valuetext", "28:20 of 29:53");
  });
});

describe("the song's clock", () => {
  it("maps a moment of the song to a file and back", () => {
    expect(locate(rider, 100)).toEqual({ segment: 0, fileTime: 381 });
    expect(locate(darkStar, 1700)).toEqual({ segment: 1, fileTime: 30 });
    expect(songTime(darkStar, 1, 30)).toBe(1700);
    // A part with no stated end is placed once its file has been measured.
    const unmeasured: PlayerTrack = { ...darkStar, segments: darkStar.segments!.map((segment) => ({ ...segment, end: null })) };
    expect(locate(unmeasured, 1700)).toEqual({ segment: 0, fileTime: 1700 });
    expect(locate(unmeasured, 1700, [1670])).toEqual({ segment: 1, fileTime: 30 });
    expect(songTime(unmeasured, 1, 30, [1670])).toBe(1700);
    expect(songTime(rider, 0, 700)).toBe(312);
  });

  it("tells two songs in one file apart", () => {
    const chinaCat: PlayerTrack = { ...rider, id: "china-cat", segments: [{ url: rider.audioUrl, start: 0, end: 281 }] };
    expect(trackKey(chinaCat)).not.toBe(trackKey(rider));
  });

  it("reads the API's audio_parts into segments", () => {
    const track = toTrack(
      {
        performance_id: "rider",
        title: "I Know You Rider",
        audio_url: rider.audioUrl,
        duration_seconds: 312,
        audio_parts: [{ audio_url: rider.audioUrl, start_seconds: 281, end_seconds: 593 }]
      },
      {}
    );
    expect(track.segments).toEqual(rider.segments);
    expect(toTrack({ performance_id: "x", title: "X", audio_url: after.audioUrl }, {}).segments).toBeNull();
  });
});
