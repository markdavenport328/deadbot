// Spotify on the page. One component mounts Spotify's embedded player and
// keeps it from playing over the shared player: when the embed starts, our
// player pauses; when our player starts (or another Spotify embed does), the
// embed pauses. Coordination uses Spotify's iFrame API, loaded once and only
// when an embed first mounts. If the script cannot load, the embed is a plain
// iframe: it still plays, just without the coordination.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { PlayGlyph } from "./listen-control";
import { usePlayer } from "./player";

type PlaybackUpdate = { data: { isPaused: boolean; isBuffering?: boolean } };

export type SpotifyController = {
  addListener: (event: string, listener: (event: PlaybackUpdate) => void) => void;
  pause: () => void;
  play?: () => void;
  destroy?: () => void;
};

export type SpotifyIFrameApi = {
  createController: (
    element: HTMLElement,
    options: { uri: string; width?: string | number; height?: string | number },
    callback: (controller: SpotifyController) => void
  ) => void;
};

declare global {
  interface Window {
    onSpotifyIframeApiReady?: (api: SpotifyIFrameApi) => void;
  }
}

const API_SCRIPT = "https://open.spotify.com/embed/iframe-api/v1";
const API_TIMEOUT_MS = 10000;
const IFRAME_ALLOW = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";

let apiPromise: Promise<SpotifyIFrameApi> | null = null;

// The iFrame API script, loaded once for the whole page, on first use.
export function loadSpotifyApi(): Promise<SpotifyIFrameApi> {
  if (apiPromise) return apiPromise;
  apiPromise = new Promise<SpotifyIFrameApi>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("Spotify iFrame API did not load")), API_TIMEOUT_MS);
    window.onSpotifyIframeApiReady = (api) => {
      window.clearTimeout(timer);
      resolve(api);
    };
    const script = document.createElement("script");
    script.src = API_SCRIPT;
    script.async = true;
    script.onerror = () => {
      window.clearTimeout(timer);
      reject(new Error("Spotify iFrame API failed to load"));
    };
    document.head.appendChild(script);
  });
  return apiPromise;
}

// For tests: forget the cached script so each case starts from a clean page.
export function resetSpotifyApiForTests() {
  apiPromise = null;
  activeEmbeds.clear();
}

// Every mounted embed that the iFrame API controls, so starting one pauses
// the others.
type ActiveEmbed = { pause: () => void; playing: boolean };
const activeEmbeds = new Set<ActiveEmbed>();

function spotifyUri(embedId: string): string {
  return `spotify:${embedId.replace("/", ":")}`;
}

type SpotifyEmbedProps = {
  // "album/<id>", as the server derives it from the stored Spotify URL.
  embedId: string;
  title: string;
  // 352 shows the tracklist; 152 is the compact player.
  height?: number;
  // Move keyboard focus into the player once it appears.
  autoFocus?: boolean;
};

export function SpotifyEmbed({ embedId, title, height = 152, autoFocus = false }: SpotifyEmbedProps) {
  const player = usePlayer();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [plain, setPlain] = useState(false);
  const entry = useRef<ActiveEmbed>({ pause: () => {}, playing: false });
  const playerRef = useRef(player);
  playerRef.current = player;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    const mine = entry.current;
    loadSpotifyApi()
      .then((api) => {
        if (cancelled) return;
        const target = document.createElement("div");
        host.appendChild(target);
        api.createController(target, { uri: spotifyUri(embedId), width: "100%", height }, (controller) => {
          if (cancelled) {
            controller.destroy?.();
            return;
          }
          const frame = host.querySelector("iframe");
          if (frame) {
            frame.title = title;
            frame.setAttribute("loading", "lazy");
            if (autoFocus) frame.focus();
          }
          mine.pause = () => controller.pause();
          activeEmbeds.add(mine);
          controller.addListener("playback_update", (event) => {
            const playing = !event.data.isPaused;
            mine.playing = playing;
            if (!playing) return;
            const status = playerRef.current.status;
            if (status === "playing" || status === "loading") playerRef.current.pause();
            for (const other of activeEmbeds) if (other !== mine && other.playing) other.pause();
          });
        });
      })
      .catch(() => {
        if (!cancelled) setPlain(true);
      });
    return () => {
      cancelled = true;
      activeEmbeds.delete(mine);
      mine.playing = false;
      mine.pause = () => {};
      host.replaceChildren();
    };
  }, [embedId, height, title, autoFocus]);

  // Our player starting pauses the embed.
  useEffect(() => {
    if ((player.status === "playing" || player.status === "loading") && entry.current.playing) entry.current.pause();
  }, [player.status]);

  if (plain) {
    return (
      <div className="spotify-embed" style={{ minHeight: height }}>
        <iframe
          src={`https://open.spotify.com/embed/${embedId}`}
          title={title}
          width="100%"
          height={height}
          loading="lazy"
          allow={IFRAME_ALLOW}
          ref={(frame) => {
            if (frame && autoFocus) frame.focus();
          }}
        />
      </div>
    );
  }
  return <div className="spotify-embed" style={{ minHeight: height }} ref={hostRef} />;
}

// One card's Spotify player: closed until the visitor asks for it, so a page
// of albums loads no iframes up front. Opening it pauses our player.
export function useSpotifyPanel() {
  const player = usePlayer();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const status = player.status;
  const pause = player.pause;
  const toggle = useCallback(() => {
    if (!open && (status === "playing" || status === "loading")) pause();
    setOpen(!open);
  }, [open, status, pause]);
  return { open, toggle, panelId };
}

export type SpotifyPanel = ReturnType<typeof useSpotifyPanel>;

// The card's one primary listen control when Spotify is how the record is
// heard: the same round gold button as an in-page play.
export function CardSpotifyButton({ panel, label }: { panel: SpotifyPanel; label: string }) {
  return (
    <button type="button" className="card-play" data-playable="spotify" aria-label={label} title={label} aria-expanded={panel.open} aria-controls={panel.open ? panel.panelId : undefined} onClick={panel.toggle}>
      <PlayGlyph playing={false} />
    </button>
  );
}

// The same control as a quiet text play, in a row header or beside a tape's
// own play.
export function SpotifyTextButton({ panel, label, name, className }: { panel: SpotifyPanel; label: string; name?: string; className?: string }) {
  return (
    <button
      type="button"
      className={`listen-play${panel.open ? " current" : ""}${className ? ` ${className}` : ""}`}
      data-playable="spotify"
      aria-label={name}
      aria-expanded={panel.open}
      aria-controls={panel.open ? panel.panelId : undefined}
      onClick={panel.toggle}
    >
      <span className="listen-play-mark" aria-hidden="true">
        <PlayGlyph playing={false} />
      </span>
      <span className="listen-play-label">{label}</span>
    </button>
  );
}

// The embed in its open panel: focused when the visitor opens it, so a
// keyboard user lands on it.
export function SpotifyPanelEmbed({ panel, embedId, title, height }: { panel: SpotifyPanel; embedId: string; title: string; height: number }) {
  if (!panel.open) return null;
  return (
    <div id={panel.panelId} className="spotify-panel">
      <SpotifyEmbed embedId={embedId} title={title} height={height} autoFocus />
    </div>
  );
}
