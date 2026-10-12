import type { Mock } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { PlayerProvider, usePlayer, type PlayerTrack } from "./player";
import { SpotifyEmbed, resetSpotifyApiForTests, type SpotifyController, type SpotifyIFrameApi } from "./spotify-embed";
import { visualFixtures } from "./visual-fixtures";

// Spotify on the page: the embed mounts when asked for, coordinates with the
// shared player through Spotify's iFrame API, and falls back to a plain
// iframe when that script cannot load.

type MockController = SpotifyController & { pause: Mock<() => void>; destroy: Mock<() => void>; emit: (isPaused: boolean) => void; uri: string; height: unknown };

let controllers: MockController[] = [];
let audio: HTMLMediaElement | null = null;

function mockApi(): SpotifyIFrameApi {
  return {
    createController(element, options, callback) {
      const frame = document.createElement("iframe");
      frame.src = `https://open.spotify.com/embed/${options.uri.replace("spotify:", "").replace(":", "/")}`;
      element.replaceWith(frame);
      const listeners: Array<(event: { data: { isPaused: boolean } }) => void> = [];
      const controller: MockController = {
        uri: options.uri,
        height: options.height,
        pause: vi.fn<() => void>(),
        destroy: vi.fn<() => void>(),
        addListener: (_event, listener) => {
          listeners.push(listener);
        },
        emit: (isPaused) => listeners.forEach((listener) => listener({ data: { isPaused } }))
      };
      controllers.push(controller);
      callback(controller);
    }
  };
}

function apiScript(): HTMLScriptElement | null {
  return document.head.querySelector('script[src="https://open.spotify.com/embed/iframe-api/v1"]');
}

async function apiReady() {
  await act(async () => {
    window.onSpotifyIframeApiReady?.(mockApi());
  });
}

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false
  })) as typeof window.matchMedia;
  Element.prototype.scrollIntoView = function scrollIntoView() {};
  Element.prototype.scrollTo = function scrollTo() {} as typeof Element.prototype.scrollTo;
  window.scrollTo = (() => {}) as typeof window.scrollTo;
  HTMLMediaElement.prototype.play = function play() {
    audio = this;
    this.dispatchEvent(new Event("playing"));
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() {
    this.dispatchEvent(new Event("pause"));
  };
  HTMLMediaElement.prototype.load = function load() {};
});

beforeEach(() => {
  controllers = [];
  audio = null;
  resetSpotifyApiForTests();
  delete window.onSpotifyIframeApiReady;
});

afterEach(() => {
  cleanup();
  apiScript()?.remove();
  vi.doUnmock("./visual-fixtures");
  window.history.replaceState({}, "", "/");
});

async function renderFixture(name: string, response: { title: string }) {
  window.history.replaceState({}, "", `/?fixture=${name}`);
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
  await screen.findByRole("heading", { level: 1, name: response.title });
}

describe("an album card's Spotify player", () => {
  it("mounts only when the card's listen control is pressed, tall enough for the tracklist", async () => {
    await renderFixture("album", visualFixtures.album);
    const card = document.querySelector("article.album-unit") as HTMLElement;
    // Nothing loads up front: no script, no iframe.
    expect(apiScript()).toBeNull();
    expect(card.querySelector("iframe")).toBeNull();

    const listen = within(card).getByRole("button", { name: "Listen to Workingman's Dead" });
    expect(listen).toHaveAttribute("aria-expanded", "false");
    await act(async () => {
      fireEvent.click(listen);
    });
    expect(apiScript()).not.toBeNull();
    await apiReady();

    expect(listen).toHaveAttribute("aria-expanded", "true");
    expect(controllers).toHaveLength(1);
    expect(controllers[0].uri).toBe("spotify:album:0Dx3ntxFk1ZzIWFp2mL6oN");
    expect(controllers[0].height).toBe(352);
    const frame = card.querySelector("iframe") as HTMLIFrameElement;
    expect(frame).not.toBeNull();
    expect(frame.title).toBe("Workingman's Dead on Spotify");
    expect(frame.getAttribute("loading")).toBe("lazy");
    expect(document.activeElement).toBe(frame);
    // The site link stays, quiet, beside the player.
    expect(within(card).getByRole("link", { name: /Open in Spotify/ })).toHaveAttribute("href", "https://open.spotify.com/album/0Dx3ntxFk1ZzIWFp2mL6oN");

    // Pressing again closes it.
    await act(async () => {
      fireEvent.click(listen);
    });
    expect(card.querySelector("iframe")).toBeNull();
  });

  it("opens in a collapsed row at the compact height, from the opened record", async () => {
    await renderFixture("releases1972", visualFixtures.releases1972);
    const row = document.querySelector(".collapsed-list > .collapsed-row") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /^More/ }));
    await act(async () => {
      fireEvent.click(within(row).getByRole("button", { name: /^Listen on Spotify|^Listen to .* on Spotify/ }));
    });
    await apiReady();
    expect(controllers).toHaveLength(1);
    expect(controllers[0].height).toBe(152);
    expect(row.querySelectorAll("iframe")).toHaveLength(1);
  });
});

describe("when Spotify's script cannot load", () => {
  it("falls back to a plain iframe that still plays", async () => {
    render(
      <PlayerProvider>
        <SpotifyEmbed embedId="album/abc123" title="Ace on Spotify" height={352} />
      </PlayerProvider>
    );
    await act(async () => {
      fireEvent.error(apiScript() as HTMLScriptElement);
    });
    const frame = screen.getByTitle("Ace on Spotify") as HTMLIFrameElement;
    expect(frame.getAttribute("src")).toBe("https://open.spotify.com/embed/album/abc123");
    expect(frame.getAttribute("loading")).toBe("lazy");
    expect(frame.getAttribute("allow")).toBe("autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture");
    expect(frame.getAttribute("height")).toBe("352");
  });
});

const track: PlayerTrack = { id: "t1", title: "Eyes Of The World", audioUrl: "https://archive.org/download/gd1973-06-10/d2t02.mp3" };

function Harness({ embeds = 1 }: { embeds?: number }) {
  const player = usePlayer();
  return (
    <>
      <button type="button" onClick={() => player.play(track, [track])}>
        Play tape
      </button>
      <output aria-label="status">{player.status}</output>
      {Array.from({ length: embeds }, (_, index) => (
        <SpotifyEmbed key={index} embedId={`album/id${index}`} title={`Album ${index}`} />
      ))}
    </>
  );
}

describe("one thing plays at a time", () => {
  it("pauses our player when the embed starts, and the embed when our player starts", async () => {
    render(
      <PlayerProvider>
        <Harness />
      </PlayerProvider>
    );
    await apiReady();
    const status = () => screen.getByLabelText("status").textContent;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play tape" }));
    });
    expect(status()).toBe("playing");
    expect(audio).not.toBeNull();

    // Spotify starts: our player pauses.
    await act(async () => {
      controllers[0].emit(false);
    });
    expect(status()).toBe("paused");
    expect(controllers[0].pause).not.toHaveBeenCalled();

    // Our player starts again: the embed is paused.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play tape" }));
    });
    expect(status()).toBe("playing");
    expect(controllers[0].pause).toHaveBeenCalledTimes(1);
  });

  it("leaves a paused embed alone when our player starts", async () => {
    render(
      <PlayerProvider>
        <Harness />
      </PlayerProvider>
    );
    await apiReady();
    await act(async () => {
      controllers[0].emit(false);
      controllers[0].emit(true);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play tape" }));
    });
    expect(controllers[0].pause).not.toHaveBeenCalled();
  });

  it("pauses the other Spotify embed when one starts", async () => {
    render(
      <PlayerProvider>
        <Harness embeds={2} />
      </PlayerProvider>
    );
    await apiReady();
    expect(controllers).toHaveLength(2);
    await act(async () => {
      controllers[0].emit(false);
    });
    await act(async () => {
      controllers[1].emit(false);
    });
    expect(controllers[0].pause).toHaveBeenCalledTimes(1);
    expect(controllers[1].pause).not.toHaveBeenCalled();
  });

  it("keeps our player going when a late position update arrives from the embed it paused", async () => {
    render(
      <PlayerProvider>
        <Harness />
      </PlayerProvider>
    );
    await apiReady();
    const status = () => screen.getByLabelText("status").textContent;
    await act(async () => {
      controllers[0].emit(false);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Play tape" }));
    });
    expect(controllers[0].pause).toHaveBeenCalledTimes(1);
    // Spotify repeats "playing" while its position moves; one sent before it paused lands now.
    await act(async () => {
      controllers[0].emit(false);
    });
    expect(status()).toBe("playing");
  });

  it("lets go of the Spotify controller when the embed closes", async () => {
    const { unmount } = render(
      <PlayerProvider>
        <Harness />
      </PlayerProvider>
    );
    await apiReady();
    unmount();
    expect(controllers[0].destroy).toHaveBeenCalledTimes(1);
  });

  it("loads the iFrame API script once for any number of embeds", async () => {
    render(
      <PlayerProvider>
        <Harness embeds={3} />
      </PlayerProvider>
    );
    expect(document.head.querySelectorAll('script[src*="iframe-api"]')).toHaveLength(1);
  });
});
