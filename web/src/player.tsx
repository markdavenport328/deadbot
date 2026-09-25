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

// The one shared player for the whole app: a single <audio> element behind a
// context, so playback survives a page re-render or a follow-up question
// instead of resetting with every new answer. UI primitives (the now-playing
// bar, setlist rows) render this state; they never own an <audio> element
// themselves.

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
};

const PlayerContext = createContext<PlayerContextValue | null>(null);

export function usePlayer(): PlayerContextValue {
  const context = useContext(PlayerContext);
  if (!context) throw new Error("usePlayer must be used within a PlayerProvider");
  return context;
}

const initialState: PlayerState = { queue: [], index: -1, status: "idle", position: 0, duration: 0 };

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<PlayerState>(initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  // play() rejects with AbortError when a newer load interrupts it (a quick
  // second click); that is not a playback failure, so only real rejections
  // mark the track as errored.
  function onPlayRejected(error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    setState((previous) => ({ ...previous, status: "error" }));
  }

  function audio(): HTMLAudioElement {
    if (!audioRef.current) {
      audioRef.current = new Audio();
      audioRef.current.preload = "metadata";
    }
    return audioRef.current;
  }

  const loadTrack = useCallback((track: PlayerTrack, queue: PlayerTrack[], index: number) => {
    const element = audio();
    element.src = track.audioUrl;
    element.currentTime = 0;
    setState({ queue, index, status: "loading", position: 0, duration: track.durationSeconds ?? 0 });
    element.play().catch(onPlayRejected);
  }, []);

  useEffect(() => {
    const element = audio();
    const onTimeUpdate = () => setState((previous) => ({ ...previous, position: element.currentTime }));
    const onLoadedMetadata = () => {
      if (Number.isFinite(element.duration)) setState((previous) => ({ ...previous, duration: element.duration }));
    };
    const onPlaying = () => setState((previous) => ({ ...previous, status: "playing" }));
    const onPause = () => setState((previous) => (previous.status === "error" ? previous : { ...previous, status: "paused" }));
    const onWaiting = () => setState((previous) => ({ ...previous, status: "loading" }));
    const onErrorEvent = () => setState((previous) => ({ ...previous, status: "error" }));
    const onEnded = () => {
      const current = stateRef.current;
      const nextIndex = current.index + 1;
      const track = current.queue[nextIndex];
      if (track) loadTrack(track, current.queue, nextIndex);
      else setState((previous) => ({ ...previous, status: "paused", position: previous.duration }));
    };
    element.addEventListener("timeupdate", onTimeUpdate);
    element.addEventListener("loadedmetadata", onLoadedMetadata);
    element.addEventListener("playing", onPlaying);
    element.addEventListener("pause", onPause);
    element.addEventListener("waiting", onWaiting);
    element.addEventListener("error", onErrorEvent);
    element.addEventListener("ended", onEnded);
    return () => {
      element.removeEventListener("timeupdate", onTimeUpdate);
      element.removeEventListener("loadedmetadata", onLoadedMetadata);
      element.removeEventListener("playing", onPlaying);
      element.removeEventListener("pause", onPause);
      element.removeEventListener("waiting", onWaiting);
      element.removeEventListener("error", onErrorEvent);
      element.removeEventListener("ended", onEnded);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const play = useCallback(
    (track: PlayerTrack, queue?: PlayerTrack[]) => {
      const current = stateRef.current;
      if (current.index >= 0 && current.queue[current.index]?.id === track.id) {
        // The requested track is already loaded: resume rather than
        // reassigning src, which would restart it from zero.
        audio().play().catch(onPlayRejected);
        return;
      }
      const list = queue && queue.length > 0 ? queue : [track];
      const index = list.findIndex((item) => item.id === track.id);
      loadTrack(track, list, index >= 0 ? index : 0);
    },
    [loadTrack]
  );

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
    setState((previous) => ({ ...previous, position: seconds }));
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

  const next = useCallback(() => goTo(1), [goTo]);
  const previous = useCallback(() => goTo(-1), [goTo]);

  const currentTrack = state.queue[state.index] ?? null;

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
      retry
    }),
    [state, currentTrack, play, pause, toggle, seek, next, previous, retry]
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
