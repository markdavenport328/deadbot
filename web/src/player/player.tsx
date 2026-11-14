import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";
import { archiveFallbackUrls } from "./archive-fallback";

// The one shared player for the whole app, behind a context, so playback
// survives a page re-render or a follow-up question instead of resetting with
// every new answer. UI primitives (the now-playing bar, setlist rows) render
// this state; they never own an <audio> element themselves.
//
// Two <audio> elements take turns: the active one plays, and the spare loads
// the next track in the queue as the current one nears its end, so a segue
// starts the moment the last track stops instead of after a fresh load. The
// queue and the place in it are saved in the browser, so a reload or a return
// visit picks up where the visitor left off. The phone's lock screen,
// headphones and car controls drive the queue through the Media Session API.

export type PlayerTrack = {
  // Stable key; the performance_id for a setlist track.
  id: string;
  title: string;
  audioUrl: string;
  durationSeconds?: number | null;
  showDate?: string | null;
  venueName?: string | null;
  recordingDetailsUrl?: string | null;
  thumbnailUrl?: string | null;
};

export type PlayerLoop = { start: number | null; end: number | null };

const NO_LOOP: PlayerLoop = { start: null, end: null };

export type PlayerStatus = "idle" | "loading" | "playing" | "paused" | "error";

type PlayerState = {
  queue: PlayerTrack[];
  index: number;
  status: PlayerStatus;
  position: number;
  duration: number;
};

export type PlayerContextValue = {
  status: PlayerStatus;
  position: number;
  duration: number;
  queue: PlayerTrack[];
  currentTrack: PlayerTrack | null;
  hasNext: boolean;
  hasPrevious: boolean;
  play: (track: PlayerTrack, queue?: PlayerTrack[]) => void;
  pause: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  next: () => void;
  previous: () => void;
  // Reload the current track from scratch after an error, rather than
  // resuming (play() no-ops on an already-loaded track; this bypasses that).
  retry: () => void;
  // Playback speed, kept for every track and remembered on the device.
  rate: number;
  setRate: (rate: number) => void;
  // A practice loop within the current track: once both ends are set,
  // playing past the end jumps back to the start. A new track clears it.
  loop: PlayerLoop;
  setLoopStart: () => void;
  setLoopEnd: () => void;
  clearLoop: () => void;
  // The visitor's own queue edits. play() still replaces the queue; these
  // add to it and rearrange it without interrupting what is playing.
  // enqueue appends the tracks not already queued; into an empty player it
  // loads the first one paused, so the bar appears ready to play.
  enqueue: (tracks: PlayerTrack[]) => void;
  // Move the track at a queue position to just after the current track.
  playNext: (index: number) => void;
  // Take a track out of the queue; the current track stays.
  remove: (index: number) => void;
  // Play the track at a queue position.
  jumpTo: (index: number) => void;
};

const PlayerContext = createContext<PlayerContextValue | null>(null);

export function usePlayer(): PlayerContextValue {
  const context = useContext(PlayerContext);
  if (!context) throw new Error("usePlayer must be used within a PlayerProvider");
  return context;
}

const initialState: PlayerState = { queue: [], index: -1, status: "idle", position: 0, duration: 0 };

// The spare element starts loading the next track this many seconds before
// the current one ends.
const PRELOAD_LEAD_SECONDS = 30;
// "Previous" restarts the current track once it has played this long.
const RESTART_THRESHOLD_SECONDS = 3;
const SKIP_SECONDS = 10;
// Between two loop checks, playback advances well under this; a bigger move is a seek.
const LOOP_SEEK_SECONDS = 1.5;

export const PLAYER_STORAGE_KEY = "deadbot.player.v1";
export const PLAYER_RATE_KEY = "deadbot.player.rate";
// The speed control is mostly for learning a solo by ear, so it reaches
// half speed. Browsers keep the pitch when they slow a recording, so it
// stays in key.
export const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5] as const;

function readSavedRate(): number {
  try {
    const rate = Number(window.localStorage.getItem(PLAYER_RATE_KEY));
    return rate >= 0.5 && rate <= 3 ? rate : 1;
  } catch {
    return 1;
  }
}

type SavedPlayer = { queue: PlayerTrack[]; index: number; position: number };

function isTrack(value: unknown): value is PlayerTrack {
  const track = value as PlayerTrack | null;
  return Boolean(track) && typeof track!.id === "string" && typeof track!.title === "string" && typeof track!.audioUrl === "string";
}

// The visitor's saved queue, read leniently: tracks that do not parse drop
// out, and anything unreadable starts the player empty.
export function readSavedPlayer(): SavedPlayer | null {
  try {
    const raw = window.localStorage.getItem(PLAYER_STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Partial<SavedPlayer>;
    const queue = Array.isArray(saved.queue) ? saved.queue.filter(isTrack) : [];
    if (queue.length === 0) return null;
    const index = Number.isInteger(saved.index) ? Math.min(Math.max(saved.index as number, 0), queue.length - 1) : 0;
    const position = typeof saved.position === "number" && Number.isFinite(saved.position) && saved.position > 0 ? saved.position : 0;
    return { queue, index, position };
  } catch {
    return null;
  }
}

function writeSavedPlayer(state: PlayerState) {
  try {
    if (state.queue.length === 0 || state.index < 0) {
      window.localStorage.removeItem(PLAYER_STORAGE_KEY);
      return;
    }
    // A track that played to its end comes back from the top.
    const nearEnd = state.duration > 0 && state.position >= state.duration - 2;
    const saved: SavedPlayer = { queue: state.queue, index: state.index, position: nearEnd ? 0 : Math.floor(state.position) };
    window.localStorage.setItem(PLAYER_STORAGE_KEY, JSON.stringify(saved));
  } catch {
    // Storage full or blocked: the player still works, it just forgets.
  }
}

function restoredState(): PlayerState {
  const saved = readSavedPlayer();
  if (!saved) return initialState;
  const track = saved.queue[saved.index];
  return { queue: saved.queue, index: saved.index, status: "paused", position: saved.position, duration: track.durationSeconds ?? 0 };
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// "May 8, 1977" for the lock screen, which has room for the long form.
function lockScreenDate(iso: string | null | undefined): string | null {
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso) : null;
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  return match && month ? `${month} ${Number(match[3])}, ${match[1]}` : iso ?? null;
}

function mediaSession(): MediaSession | null {
  return typeof navigator !== "undefined" && "mediaSession" in navigator ? navigator.mediaSession : null;
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  // The element playing now, and the spare that loads what comes next.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const spareRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<PlayerState>(restoredState);
  const stateRef = useRef(state);
  stateRef.current = state;
  // A restored position, applied once the restored track's metadata loads.
  const pendingSeekRef = useRef<number | null>(state.position > 0 ? state.position : null);
  const [loop, setLoop] = useState<PlayerLoop>(NO_LOOP);
  const loopRef = useRef(loop);
  loopRef.current = loop;
  // Where the loop check last saw playback, to tell crossing the end from a seek.
  const loopLastRef = useRef(0);

  // Jump back to the loop's start when playback crosses its end. A move of
  // more than a moment is a seek, the visitor's own choice, and is left alone.
  function checkLoop(element: HTMLAudioElement) {
    const { start, end } = loopRef.current;
    const now = element.currentTime;
    const last = loopLastRef.current;
    if (start != null && end != null && last < end && now >= end && now - last < LOOP_SEEK_SECONDS) {
      element.currentTime = start;
      loopLastRef.current = start;
    } else {
      loopLastRef.current = now;
    }
  }
  const [rate, setRateState] = useState(readSavedRate);
  const rateRef = useRef(rate);
  rateRef.current = rate;

  // Loading a file resets an element's speed to its default, so both are set.
  function applyRate(element: HTMLAudioElement) {
    element.defaultPlaybackRate = rateRef.current;
    element.playbackRate = rateRef.current;
  }
  // The current load's second chance: archive.org links that fail get the
  // item's primary servers (see archive-fallback.ts). Undefined urls means
  // the lookup has not run yet.
  const fallbackRef = useRef<{ trackId: string; urls?: string[] } | null>(null);

  // play() rejects with AbortError when a newer load interrupts it (a quick
  // second click), and with NotSupportedError when the source fails, which
  // the error event handles; only other rejections mark the track as errored.
  function onPlayRejected(error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    if (error instanceof DOMException && error.name === "NotSupportedError" && audioRef.current?.error) return;
    setState((previous) => ({ ...previous, status: "error" }));
  }

  function audio(): HTMLAudioElement {
    if (!audioRef.current) {
      audioRef.current = new Audio();
      audioRef.current.preload = "metadata";
      applyRate(audioRef.current);
    }
    return audioRef.current;
  }

  function spare(): HTMLAudioElement {
    if (!spareRef.current) {
      spareRef.current = new Audio();
      spareRef.current.preload = "auto";
      applyRate(spareRef.current);
    }
    return spareRef.current;
  }

  // The spare already holds this file and loaded it without an error.
  function spareHolds(url: string): boolean {
    const element = spareRef.current;
    return Boolean(element && element.getAttribute("src") === url && !element.error);
  }

  // Start loading the queue's next track into the spare element.
  function preloadNext() {
    const current = stateRef.current;
    const next = current.queue[current.index + 1];
    if (!next || spare().getAttribute("src") === next.audioUrl) return;
    spare().src = next.audioUrl;
    spare().load();
  }

  const loadTrack = useCallback((track: PlayerTrack, queue: PlayerTrack[], index: number) => {
    pendingSeekRef.current = null;
    setLoop(NO_LOOP);
    let element = audio();
    if (spareHolds(track.audioUrl)) {
      // The spare loaded this track ahead of time: it becomes the player, and
      // the old player becomes the spare.
      const ready = spare();
      element.pause();
      element.removeAttribute("src");
      element.load();
      element.preload = "auto";
      ready.preload = "metadata";
      spareRef.current = element;
      audioRef.current = ready;
      element = ready;
    } else {
      element.src = track.audioUrl;
    }
    fallbackRef.current = { trackId: track.id };
    applyRate(element);
    element.currentTime = 0;
    setState({ queue, index, status: "loading", position: 0, duration: track.durationSeconds ?? 0 });
    element.play().catch(onPlayRejected);
  }, []);

  useEffect(() => {
    // Both elements carry the listeners; only the active one's events count.
    const elements = [audio(), spare()];
    const active = (handler: (element: HTMLAudioElement) => void) => (event: Event) => {
      const current = audioRef.current;
      if (current && event.target === current) handler(current);
    };
    const onTimeUpdate = active((element) => {
      // The frame watcher below stops in a background tab or on a locked
      // phone; time updates keep the loop going there.
      checkLoop(element);
      setState((previous) => ({ ...previous, position: element.currentTime }));
      const current = stateRef.current;
      const duration = Number.isFinite(element.duration) ? element.duration : current.duration;
      if (duration > 0 && duration - element.currentTime <= PRELOAD_LEAD_SECONDS) preloadNext();
    });
    const onLoadedMetadata = active((element) => {
      const seekTo = pendingSeekRef.current;
      if (seekTo != null) {
        pendingSeekRef.current = null;
        if (!Number.isFinite(element.duration) || seekTo < element.duration) element.currentTime = seekTo;
      }
      if (Number.isFinite(element.duration)) setState((previous) => ({ ...previous, duration: element.duration }));
    });
    const onPlaying = active(() => setState((previous) => ({ ...previous, status: "playing" })));
    const onPause = active(() => setState((previous) => (previous.status === "error" ? previous : { ...previous, status: "paused" })));
    const onWaiting = active(() => setState((previous) => ({ ...previous, status: "loading" })));
    const markError = () => setState((previous) => ({ ...previous, status: "error" }));
    const tryNextSource = (fallback: { urls?: string[] }) => {
      const url = fallback.urls?.shift();
      if (!url) return markError();
      const element = audio();
      element.src = url;
      element.play().catch(onPlayRejected);
    };
    const onErrorEvent = active(() => {
      const fallback = fallbackRef.current;
      const track = stateRef.current.queue[stateRef.current.index];
      if (!fallback || !track || fallback.trackId !== track.id) return markError();
      if (fallback.urls) return tryNextSource(fallback);
      fallback.urls = [];
      void archiveFallbackUrls(track.audioUrl).then((urls) => {
        // A newer load replaced this one while the lookup ran.
        if (fallbackRef.current !== fallback) return;
        fallback.urls = urls;
        tryNextSource(fallback);
      });
    });
    const onEnded = active((element) => {
      // A loop whose end is the track's end goes round again.
      const { start, end } = loopRef.current;
      if (start != null && end != null) {
        element.currentTime = start;
        element.play().catch(onPlayRejected);
        return;
      }
      const current = stateRef.current;
      const nextIndex = current.index + 1;
      const track = current.queue[nextIndex];
      if (track) loadTrack(track, current.queue, nextIndex);
      else setState((previous) => ({ ...previous, status: "paused", position: previous.duration }));
    });
    const listeners: [string, (event: Event) => void][] = [
      ["timeupdate", onTimeUpdate],
      ["loadedmetadata", onLoadedMetadata],
      ["playing", onPlaying],
      ["pause", onPause],
      ["waiting", onWaiting],
      ["error", onErrorEvent],
      ["ended", onEnded]
    ];
    for (const element of elements) for (const [name, listener] of listeners) element.addEventListener(name, listener);

    // A restored queue loads its track paused, ready to resume.
    const restored = stateRef.current.queue[stateRef.current.index];
    if (restored && !audio().getAttribute("src")) {
      fallbackRef.current = { trackId: restored.id };
      audio().src = restored.audioUrl;
    }

    return () => {
      for (const element of elements) for (const [name, listener] of listeners) element.removeEventListener(name, listener);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Save the queue whenever it changes, the position every few seconds, and
  // both when the visitor leaves the page.
  const savedSecond = Math.floor(state.position / 5);
  useEffect(() => {
    writeSavedPlayer(stateRef.current);
  }, [state.queue, state.index, savedSecond]);
  useEffect(() => {
    const onPageHide = () => writeSavedPlayer(stateRef.current);
    window.addEventListener("pagehide", onPageHide);
    return () => window.removeEventListener("pagehide", onPageHide);
  }, []);

  const play = useCallback(
    (track: PlayerTrack, queue?: PlayerTrack[]) => {
      const current = stateRef.current;
      if (current.index >= 0 && current.queue[current.index]?.id === track.id) {
        // The requested track is already loaded: resume rather than
        // reassigning src, which would restart it from zero. A different
        // queue around the same track still replaces the one that follows it.
        if (queue && queue.length > 0 && !(queue.length === current.queue.length && queue.every((item, i) => item.id === current.queue[i].id))) {
          const index = queue.findIndex((item) => item.id === track.id);
          if (index >= 0) setState((previous) => ({ ...previous, queue, index }));
        }
        audio().play().catch(onPlayRejected);
        return;
      }
      const list = queue && queue.length > 0 ? queue : [track];
      const index = list.findIndex((item) => item.id === track.id);
      loadTrack(track, list, index >= 0 ? index : 0);
    },
    [loadTrack]
  );

  const setRate = useCallback((next: number) => {
    rateRef.current = next;
    setRateState(next);
    for (const element of [audioRef.current, spareRef.current]) if (element) applyRate(element);
    try {
      window.localStorage.setItem(PLAYER_RATE_KEY, String(next));
    } catch {
      // Storage blocked: the speed lasts the visit.
    }
  }, []);

  const setLoopStart = useCallback(() => {
    const now = audio().currentTime;
    // A start after the end begins a new loop from here.
    setLoop((previous) => ({ start: now, end: previous.end != null && previous.end > now ? previous.end : null }));
  }, []);

  const setLoopEnd = useCallback(() => {
    const now = audio().currentTime;
    // Playback is at the end already: the next check goes straight back to
    // the start, so the visitor hears the loop right away.
    loopLastRef.current = now - 0.001;
    // An end before the start (or with no start) loops from the top.
    setLoop((previous) => ({ start: previous.start != null && previous.start < now ? previous.start : 0, end: now }));
  }, []);

  const clearLoop = useCallback(() => setLoop(NO_LOOP), []);

  // While a loop plays on screen, check every frame (timeupdate comes only
  // about four times a second), so the jump back lands right at the end.
  const loopActive = loop.start != null && loop.end != null;
  const playing = state.status === "playing";
  useEffect(() => {
    if (!loopActive || !playing) return;
    let frame = 0;
    const watch = () => {
      checkLoop(audio());
      frame = requestAnimationFrame(watch);
    };
    frame = requestAnimationFrame(watch);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loopActive, playing]);

  const retry = useCallback(() => {
    const current = stateRef.current;
    const track = current.queue[current.index];
    if (track) loadTrack(track, current.queue, current.index);
  }, [loadTrack]);

  const pause = useCallback(() => {
    audio().pause();
  }, []);

  const toggle = useCallback(() => {
    const current = stateRef.current;
    const element = audio();
    if (current.status === "playing" || current.status === "loading") {
      element.pause();
    } else if (current.queue[current.index]) {
      element.play().catch(onPlayRejected);
    }
  }, []);

  const seek = useCallback((seconds: number) => {
    const element = audio();
    element.currentTime = seconds;
    loopLastRef.current = seconds;
    setState((previous) => ({ ...previous, position: seconds }));
    // Keep the lock screen's scrubber where the visitor moved it.
    const session = mediaSession();
    const duration = Number.isFinite(element.duration) ? element.duration : stateRef.current.duration;
    if (session && typeof session.setPositionState === "function" && duration > 0) {
      try {
        session.setPositionState({ duration, playbackRate: rateRef.current, position: Math.min(Math.max(seconds, 0), duration) });
      } catch {
        // A position the browser rejects; the lock screen keeps its last one.
      }
    }
  }, []);

  const goTo = useCallback(
    (delta: number) => {
      const current = stateRef.current;
      const nextIndex = current.index + delta;
      const track = current.queue[nextIndex];
      if (track) loadTrack(track, current.queue, nextIndex);
    },
    [loadTrack]
  );

  const enqueue = useCallback((tracks: PlayerTrack[]) => {
    const current = stateRef.current;
    // Two cards can name one tape file under different ids; the file is the track.
    const seen = new Set(current.queue.flatMap((track) => [track.id, track.audioUrl]));
    const added = tracks.filter((track) => {
      if (seen.has(track.id) || seen.has(track.audioUrl)) return false;
      seen.add(track.id).add(track.audioUrl);
      return true;
    });
    if (added.length === 0) return;
    if (current.index < 0) {
      const element = audio();
      pendingSeekRef.current = null;
      fallbackRef.current = { trackId: added[0].id };
      element.src = added[0].audioUrl;
      setState({ queue: added, index: 0, status: "paused", position: 0, duration: added[0].durationSeconds ?? 0 });
      return;
    }
    setState((previous) => ({ ...previous, queue: [...previous.queue, ...added] }));
  }, []);

  const playNext = useCallback((index: number) => {
    setState((previous) => {
      if (index === previous.index || index < 0 || index >= previous.queue.length) return previous;
      const queue = previous.queue.slice();
      const [track] = queue.splice(index, 1);
      const current = index < previous.index ? previous.index - 1 : previous.index;
      queue.splice(current + 1, 0, track);
      return { ...previous, queue, index: current };
    });
  }, []);

  const remove = useCallback((index: number) => {
    setState((previous) => {
      if (index === previous.index || index < 0 || index >= previous.queue.length) return previous;
      const queue = previous.queue.filter((_, i) => i !== index);
      return { ...previous, queue, index: index < previous.index ? previous.index - 1 : previous.index };
    });
  }, []);

  const jumpTo = useCallback(
    (index: number) => {
      const current = stateRef.current;
      const track = current.queue[index];
      if (track && index !== current.index) loadTrack(track, current.queue, index);
    },
    [loadTrack]
  );

  const next = useCallback(() => goTo(1), [goTo]);
  const previous = useCallback(() => goTo(-1), [goTo]);

  const currentTrack = state.queue[state.index] ?? null;

  // The lock screen, headphones and car: what is playing, and the buttons
  // that drive the queue. Handlers read the latest state through refs, so
  // they are registered once.
  useEffect(() => {
    const session = mediaSession();
    if (!session) return;
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => {
        const current = stateRef.current;
        if (current.queue[current.index]) audio().play().catch(onPlayRejected);
      }],
      ["pause", () => audio().pause()],
      ["previoustrack", () => {
        // Like a CD player: the first press goes back to the top of the track.
        if (audio().currentTime > RESTART_THRESHOLD_SECONDS || stateRef.current.index <= 0) seek(0);
        else previous();
      }],
      ["nexttrack", () => next()],
      ["seekto", (details) => {
        if (details.seekTime != null) seek(details.seekTime);
      }],
      ["seekbackward", (details) => seek(Math.max(0, audio().currentTime - (details.seekOffset ?? SKIP_SECONDS)))],
      ["seekforward", (details) => {
        const element = audio();
        const end = Number.isFinite(element.duration) ? element.duration : stateRef.current.duration;
        seek(Math.min(end || Infinity, element.currentTime + (details.seekOffset ?? SKIP_SECONDS)));
      }]
    ];
    for (const [action, handler] of handlers) {
      try {
        session.setActionHandler(action, handler);
      } catch {
        // This browser does not offer that button.
      }
    }
    return () => {
      for (const [action] of handlers) {
        try {
          session.setActionHandler(action, null);
        } catch {
          // Never registered.
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seek, next, previous]);

  useEffect(() => {
    const session = mediaSession();
    if (!session) return;
    if (!currentTrack || typeof MediaMetadata === "undefined") {
      session.metadata = null;
      return;
    }
    session.metadata = new MediaMetadata({
      title: currentTrack.title,
      artist: "Grateful Dead",
      album: [lockScreenDate(currentTrack.showDate), currentTrack.venueName].filter(Boolean).join(" · "),
      artwork: currentTrack.thumbnailUrl ? [{ src: currentTrack.thumbnailUrl }] : []
    });
  }, [currentTrack]);

  const sessionDuration = state.duration || currentTrack?.durationSeconds || 0;
  useEffect(() => {
    const session = mediaSession();
    if (!session) return;
    session.playbackState = !currentTrack ? "none" : state.status === "playing" || state.status === "loading" ? "playing" : "paused";
    // The lock screen's scrubber: set when playback starts, pauses or the
    // track changes; the browser advances it between updates.
    if (!currentTrack || !(sessionDuration > 0) || typeof session.setPositionState !== "function") return;
    try {
      session.setPositionState({ duration: sessionDuration, playbackRate: rate, position: Math.min(audio().currentTime || state.position, sessionDuration) });
    } catch {
      // A position the browser rejects; the lock screen keeps its last one.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTrack, state.status, sessionDuration, rate]);

  const value = useMemo<PlayerContextValue>(
    () => ({
      status: state.status,
      position: state.position,
      duration: state.duration || currentTrack?.durationSeconds || 0,
      queue: state.queue,
      currentTrack,
      hasNext: state.index >= 0 && state.index + 1 < state.queue.length,
      hasPrevious: state.index > 0,
      play,
      pause,
      toggle,
      seek,
      next,
      previous,
      retry,
      rate,
      setRate,
      loop,
      setLoopStart,
      setLoopEnd,
      clearLoop,
      enqueue,
      playNext,
      remove,
      jumpTo
    }),
    [state, currentTrack, play, pause, toggle, seek, next, previous, retry, rate, setRate, loop, setLoopStart, setLoopEnd, clearLoop, enqueue, playNext, remove, jumpTo]
  );

  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}

export function formatClockTime(seconds: number | null | undefined): string {
  if (!Number.isFinite(seconds) || seconds == null || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

// A scrubber's accessible value text: "2:14 of 11:26", read by a screen
// reader instead of the raw seconds a range input otherwise announces.
export function formatSeekValueText(position: number, duration: number): string {
  return `${formatClockTime(position)} of ${formatClockTime(duration)}`;
}
