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
import { loadSavedTracks, offlineSource } from "./offline";
import { TILE_SIZE, trackCover, trackTile } from "../cards/show-tile";

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
  // A song that is not one whole file: a stretch of a file it shares with
  // another song, or several files played back to back. Absent, the track is
  // audioUrl from its top to its end.
  segments?: TrackSegment[] | null;
};

// One stretch of one file, in the file's own seconds; a null end plays to
// the file's end.
export type TrackSegment = { url: string; start: number; end: number | null };

// The API's audio_parts, as the player's segments.
export type AudioPartData = { audio_url: string; start_seconds?: number | null; end_seconds?: number | null };

export function segmentsFrom(parts: AudioPartData[] | null | undefined): TrackSegment[] | null {
  const segments = (parts ?? [])
    .filter((part) => part && typeof part.audio_url === "string" && part.audio_url)
    .map((part) => ({ url: part.audio_url, start: Math.max(part.start_seconds ?? 0, 0), end: part.end_seconds ?? null }));
  return segments.length > 0 ? segments : null;
}

export function trackSegments(track: PlayerTrack): TrackSegment[] {
  return track.segments && track.segments.length > 0 ? track.segments : [{ url: track.audioUrl, start: 0, end: null }];
}

// Every file a track plays, for saving it to the device.
export function trackFiles(track: PlayerTrack): string[] {
  return [...new Set(trackSegments(track).map((segment) => segment.url))];
}

// What makes two tracks the same audio: the file and where the song starts in
// it (two songs can share one file).
export function trackKey(track: PlayerTrack): string {
  const first = trackSegments(track)[0];
  return first.start > 0 ? `${first.url}#${first.start}` : first.url;
}

function segmented(track: PlayerTrack): boolean {
  const segments = trackSegments(track);
  return segments.length > 1 || segments[0].start > 0 || segments[0].end != null;
}

// A segment's length, when known: its window, else the file as measured.
function segmentLength(segment: TrackSegment, measured?: number): number | null {
  if (segment.end != null) return Math.max(segment.end - segment.start, 0);
  return measured != null && Number.isFinite(measured) ? Math.max(measured - segment.start, 0) : null;
}

// Where a moment of the song falls: the segment and the time in its file.
export function locate(track: PlayerTrack, seconds: number, measured: (number | undefined)[] = []): { segment: number; fileTime: number } {
  const segments = trackSegments(track);
  let offset = 0;
  for (let i = 0; i < segments.length; i += 1) {
    const length = segmentLength(segments[i], measured[i]);
    if (i === segments.length - 1 || length == null || seconds < offset + length) {
      return { segment: i, fileTime: segments[i].start + Math.max(seconds - offset, 0) };
    }
    offset += length;
  }
  return { segment: 0, fileTime: segments[0].start };
}

// The song's clock at a segment and a time in its file.
export function songTime(track: PlayerTrack, segment: number, fileTime: number, measured: (number | undefined)[] = []): number {
  const segments = trackSegments(track);
  let offset = 0;
  for (let i = 0; i < segment && i < segments.length; i += 1) offset += segmentLength(segments[i], measured[i]) ?? 0;
  const current = segments[segment] ?? segments[0];
  const into = Math.max(fileTime - current.start, 0);
  return offset + (current.end != null ? Math.min(into, current.end - current.start) : into);
}

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
  // Move the track at one queue position to another; the current track keeps
  // playing wherever it lands.
  move: (from: number, to: number) => void;
  // Put a whole queue in place (Clear and its Undo). It must hold the current
  // track, which keeps playing; a queue without it is ignored.
  replaceQueue: (tracks: PlayerTrack[]) => void;
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
  return { queue: saved.queue, index: saved.index, status: "paused", position: saved.position, duration: stateDuration(track) };
}

// What the bar shows as the track's length: the song's stated length, or for
// a segmented song with none, the sum of the windows it knows.
function stateDuration(track: PlayerTrack): number {
  if (track.durationSeconds) return track.durationSeconds;
  if (!segmented(track)) return 0;
  const lengths = trackSegments(track).map((segment) => segmentLength(segment));
  return lengths.every((length) => length != null) ? lengths.reduce<number>((sum, length) => sum + (length ?? 0), 0) : 0;
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// The show's picture, then Deadbot's square: a lock screen or a car's
// screen picks the size it wants, and never shows a blank.
export const FALLBACK_ARTWORK = [
  { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
  { src: "/icons/icon-1024.png", sizes: "1024x1024", type: "image/png" }
];

// A release's real cover when the track came with one, then the show's tile
// (a square JPEG at a fixed address, which iOS and Android both draw).
function lockScreenArtwork(track: PlayerTrack): MediaImage[] {
  const cover = trackCover(track);
  const tile = { src: trackTile(track), sizes: `${TILE_SIZE}x${TILE_SIZE}`, type: "image/jpeg" };
  return cover ? [{ src: cover }, tile, ...FALLBACK_ARTWORK] : [tile, ...FALLBACK_ARTWORK];
}

// "May 8, 1977" for the lock screen, which has room for the long form.
function lockScreenDate(iso: string | null | undefined): string | null {
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso) : null;
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  return match && month ? `${month} ${Number(match[3])}, ${match[1]}` : iso ?? null;
}

function pageHidden(): boolean {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
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
  // Which segment of the current track the active element holds, and each
  // segment's file length as measured (for a segment that plays to its file's end).
  const segmentRef = useRef(0);
  const measuredRef = useRef<(number | undefined)[]>([]);
  // A time in the active file to go to once its metadata loads: a restored
  // position, or the start of a song that begins partway into its file.
  const pendingSeekRef = useRef<number | null>(null);
  const [loop, setLoop] = useState<PlayerLoop>(NO_LOOP);
  const loopRef = useRef(loop);
  loopRef.current = loop;
  // Where the loop check last saw playback, to tell crossing the end from a seek.
  const loopLastRef = useRef(0);

  function currentTrackNow(): PlayerTrack | undefined {
    const current = stateRef.current;
    return current.queue[current.index];
  }

  // The song's clock for the active element.
  function songPosition(element: HTMLAudioElement): number {
    const track = currentTrackNow();
    return track ? songTime(track, segmentRef.current, element.currentTime, measuredRef.current) : element.currentTime;
  }

  // Jump back to the loop's start when playback crosses its end. A move of
  // more than a moment is a seek, the visitor's own choice, and is left alone.
  function checkLoop(element: HTMLAudioElement) {
    const { start, end } = loopRef.current;
    const now = songPosition(element);
    const last = loopLastRef.current;
    if (start != null && end != null && last < end && now >= end && now - last < LOOP_SEEK_SECONDS) {
      seekSong(start);
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

  // The active element, holding the current segment's file: a restored track
  // waits for its source until the page knows what is saved on the device,
  // and a play in that moment loads it here.
  function withSource(): HTMLAudioElement {
    const element = audio();
    const track = currentTrackNow();
    if (track && !element.getAttribute("src")) {
      const segment = trackSegments(track)[segmentRef.current] ?? trackSegments(track)[0];
      element.src = offlineSource(segment.url);
    }
    return element;
  }

  // The spare already holds this file and loaded it without an error.
  function spareHolds(url: string): boolean {
    const element = spareRef.current;
    return Boolean(element && element.getAttribute("src") === offlineSource(url) && !element.error);
  }

  // Start loading the next file into the spare element: the current song's
  // next segment, else the queue's next track.
  function preloadNext() {
    const current = stateRef.current;
    const track = current.queue[current.index];
    const nextSegment = track ? trackSegments(track)[segmentRef.current + 1] : undefined;
    const nextTrack = current.queue[current.index + 1];
    const url = nextSegment?.url ?? (nextTrack ? trackSegments(nextTrack)[0].url : null);
    // A hidden page plays the next file from the same element; loading it
    // into the spare would only spend the visitor's data.
    const source = url ? offlineSource(url) : null;
    if (!source || pageHidden() || audio().getAttribute("src") === source || spare().getAttribute("src") === source) return;
    spare().src = source;
    spare().load();
  }

  // Put one segment of a track in the active element at a time in its file.
  // With the page hidden (the phone locked, the car playing), the file loads
  // into the element already playing: a phone lets the playing element go on
  // to a new file, but may refuse to start a different one without a tap,
  // which would stop the show between songs.
  function loadSegment(track: PlayerTrack, index: number, fileTime: number, play: boolean) {
    const segment = trackSegments(track)[index];
    segmentRef.current = index;
    let element = audio();
    const source = offlineSource(segment.url);
    let fresh = true;
    if (element.getAttribute("src") === source && !element.error) {
      // The same file (a second window of it): only the place moves.
      fresh = false;
    } else if (!pageHidden() && spareHolds(segment.url)) {
      // The spare loaded this file ahead of time: it becomes the player, and
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
      element.src = source;
    }
    applyRate(element);
    if (!fresh || element.readyState >= 1) {
      pendingSeekRef.current = null;
      element.currentTime = fileTime;
    } else {
      element.currentTime = 0;
      pendingSeekRef.current = fileTime > 0 ? fileTime : null;
    }
    loopLastRef.current = songTime(track, index, fileTime, measuredRef.current);
    if (play) element.play().catch(onPlayRejected);
  }

  const loadTrack = useCallback((track: PlayerTrack, queue: PlayerTrack[], index: number) => {
    setLoop(NO_LOOP);
    measuredRef.current = [];
    fallbackRef.current = { trackId: track.id };
    setState({ queue, index, status: "loading", position: 0, duration: stateDuration(track) });
    stateRef.current = { queue, index, status: "loading", position: 0, duration: stateDuration(track) };
    loadSegment(track, 0, trackSegments(track)[0].start, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The current song is over: a loop whose end is the song's end goes round
  // again, else the queue moves on, else the player stops at the end.
  function finishTrack(element: HTMLAudioElement) {
    const { start, end } = loopRef.current;
    if (start != null && end != null) {
      seekSong(start);
      element.play().catch(onPlayRejected);
      return;
    }
    const current = stateRef.current;
    const nextIndex = current.index + 1;
    const track = current.queue[nextIndex];
    if (track) loadTrack(track, current.queue, nextIndex);
    else {
      element.pause();
      setState((previous) => ({ ...previous, status: "paused", position: previous.duration || previous.position }));
    }
  }

  // The active segment is done: on to the song's next segment, or the song is over.
  function finishSegment(element: HTMLAudioElement) {
    const track = currentTrackNow();
    const next = segmentRef.current + 1;
    if (track && next < trackSegments(track).length) {
      loadSegment(track, next, trackSegments(track)[next].start, true);
      return;
    }
    finishTrack(element);
  }

  // A segment with an end inside its file stops there (the next song starts after it).
  function pastSegmentEnd(element: HTMLAudioElement): boolean {
    const track = currentTrackNow();
    const segment = track ? trackSegments(track)[segmentRef.current] : undefined;
    return Boolean(segment && segment.end != null && pendingSeekRef.current == null && element.currentTime >= segment.end);
  }

  // Move to a moment of the current song, loading another of its files when it falls there.
  function seekSong(seconds: number) {
    const track = currentTrackNow();
    const element = audio();
    if (!track) return;
    const { segment, fileTime } = locate(track, seconds, measuredRef.current);
    if (segment === segmentRef.current && element.getAttribute("src")) {
      element.currentTime = fileTime;
      // A restored file still loading would otherwise move to its saved place after this seek.
      pendingSeekRef.current = null;
    } else {
      const status = stateRef.current.status;
      loadSegment(track, segment, fileTime, status === "playing" || status === "loading");
    }
    loopLastRef.current = seconds;
  }

  useEffect(() => {
    // Both elements carry the listeners; only the active one's events count.
    const elements = [audio(), spare()];
    const active = (handler: (element: HTMLAudioElement) => void) => (event: Event) => {
      const current = audioRef.current;
      if (current && event.target === current) handler(current);
    };
    const onTimeUpdate = active((element) => {
      if (pastSegmentEnd(element)) return finishSegment(element);
      // The frame watcher below stops in a background tab or on a locked
      // phone; time updates keep the loop going there.
      checkLoop(element);
      setState((previous) => ({ ...previous, position: songPosition(element) }));
      const track = currentTrackNow();
      const segment = track ? trackSegments(track)[segmentRef.current] : undefined;
      const fileEnd =
        segment?.end ??
        (Number.isFinite(element.duration) ? element.duration : track && !segmented(track) ? track.durationSeconds ?? null : null);
      if (fileEnd != null && fileEnd - element.currentTime <= PRELOAD_LEAD_SECONDS) preloadNext();
    });
    const onLoadedMetadata = active((element) => {
      if (Number.isFinite(element.duration)) measuredRef.current[segmentRef.current] = element.duration;
      const seekTo = pendingSeekRef.current;
      if (seekTo != null) {
        pendingSeekRef.current = null;
        if (!Number.isFinite(element.duration) || seekTo < element.duration) element.currentTime = seekTo;
      }
      const track = currentTrackNow();
      // A whole-file song is as long as its file; a segmented one keeps its stated length.
      if (track && !segmented(track) && Number.isFinite(element.duration)) setState((previous) => ({ ...previous, duration: element.duration }));
    });
    const onPlaying = active(() => setState((previous) => ({ ...previous, status: "playing" })));
    const onPause = active(() => setState((previous) => (previous.status === "error" ? previous : { ...previous, status: "paused" })));
    const onWaiting = active(() => setState((previous) => ({ ...previous, status: "loading" })));
    const markError = () => setState((previous) => ({ ...previous, status: "error" }));
    const tryNextSource = (fallback: { urls?: string[] }) => {
      const url = fallback.urls?.shift();
      if (!url) return markError();
      const element = audio();
      const track = currentTrackNow();
      const start = track ? trackSegments(track)[segmentRef.current]?.start ?? 0 : 0;
      element.src = url;
      pendingSeekRef.current = start > 0 ? start : null;
      element.play().catch(onPlayRejected);
    };
    const onErrorEvent = active(() => {
      const fallback = fallbackRef.current;
      const track = currentTrackNow();
      if (!fallback || !track || fallback.trackId !== track.id) return markError();
      if (fallback.urls) return tryNextSource(fallback);
      fallback.urls = [];
      const segment = trackSegments(track)[segmentRef.current] ?? trackSegments(track)[0];
      void archiveFallbackUrls(segment.url).then((urls) => {
        // A newer load replaced this one while the lookup ran.
        if (fallbackRef.current !== fallback) return;
        fallback.urls = urls;
        tryNextSource(fallback);
      });
    });
    const onEnded = active((element) => finishSegment(element));
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

    // A restored queue loads its track paused, ready to resume, at the saved
    // moment of the song (in whichever of its files that falls).
    const restored = currentTrackNow();
    if (restored && !audio().getAttribute("src")) {
      fallbackRef.current = { trackId: restored.id };
      const { segment, fileTime } = locate(restored, stateRef.current.position);
      segmentRef.current = segment;
      pendingSeekRef.current = fileTime > 0 ? fileTime : null;
      // First learn which songs are on the device, so a saved track loads
      // from there and a phone without a signal never asks the network for it.
      void loadSavedTracks().then(() => {
        if (currentTrackNow()?.id === restored.id) withSource();
      });
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
        withSource().play().catch(onPlayRejected);
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
    const now = songPosition(audio());
    // A start after the end begins a new loop from here.
    setLoop((previous) => ({ start: now, end: previous.end != null && previous.end > now ? previous.end : null }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setLoopEnd = useCallback(() => {
    const now = songPosition(audio());
    // Playback is at the end already: the next check goes straight back to
    // the start, so the visitor hears the loop right away.
    loopLastRef.current = now - 0.001;
    // An end before the start (or with no start) loops from the top.
    setLoop((previous) => ({ start: previous.start != null && previous.start < now ? previous.start : 0, end: now }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clearLoop = useCallback(() => setLoop(NO_LOOP), []);

  // While a loop plays on screen, or a song that stops partway into its file,
  // check every frame (timeupdate comes only about four times a second), so
  // the jump back lands right at the loop's end and the next song is not heard.
  const loopActive = loop.start != null && loop.end != null;
  const playing = state.status === "playing";
  const current = state.queue[state.index];
  const windowed = Boolean(current && trackSegments(current).some((segment) => segment.end != null));
  useEffect(() => {
    if ((!loopActive && !windowed) || !playing) return;
    let frame = 0;
    const watch = () => {
      const element = audio();
      if (pastSegmentEnd(element)) finishSegment(element);
      else checkLoop(element);
      frame = requestAnimationFrame(watch);
    };
    frame = requestAnimationFrame(watch);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loopActive, windowed, playing]);

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
      withSource().play().catch(onPlayRejected);
    }
  }, []);

  const seek = useCallback((seconds: number) => {
    seekSong(seconds);
    setState((previous) => ({ ...previous, position: seconds }));
    // Keep the lock screen's scrubber where the visitor moved it.
    const session = mediaSession();
    const duration = stateRef.current.duration;
    if (session && typeof session.setPositionState === "function" && duration > 0) {
      try {
        session.setPositionState({ duration, playbackRate: rateRef.current, position: Math.min(Math.max(seconds, 0), duration) });
      } catch {
        // A position the browser rejects; the lock screen keeps its last one.
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    const seen = new Set(current.queue.flatMap((track) => [track.id, trackKey(track)]));
    const added = tracks.filter((track) => {
      if (seen.has(track.id) || seen.has(trackKey(track))) return false;
      seen.add(track.id).add(trackKey(track));
      return true;
    });
    if (added.length === 0) return;
    if (current.index < 0) {
      const element = audio();
      pendingSeekRef.current = null;
      fallbackRef.current = { trackId: added[0].id };
      const first = trackSegments(added[0])[0];
      segmentRef.current = 0;
      measuredRef.current = [];
      element.src = offlineSource(first.url);
      pendingSeekRef.current = first.start > 0 ? first.start : null;
      setState({ queue: added, index: 0, status: "paused", position: 0, duration: stateDuration(added[0]) });
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

  const move = useCallback((from: number, to: number) => {
    setState((previous) => {
      const last = previous.queue.length - 1;
      if (from === to || from < 0 || to < 0 || from > last || to > last) return previous;
      const currentId = previous.queue[previous.index]?.id;
      const queue = previous.queue.slice();
      const [track] = queue.splice(from, 1);
      queue.splice(to, 0, track);
      return { ...previous, queue, index: queue.findIndex((item) => item.id === currentId) };
    });
  }, []);

  const replaceQueue = useCallback((tracks: PlayerTrack[]) => {
    setState((previous) => {
      const currentId = previous.queue[previous.index]?.id;
      const index = tracks.findIndex((track) => track.id === currentId);
      return index < 0 ? previous : { ...previous, queue: tracks.slice(), index };
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
        if (current.queue[current.index]) withSource().play().catch(onPlayRejected);
      }],
      ["pause", () => audio().pause()],
      ["previoustrack", () => {
        // Like a CD player: the first press goes back to the top of the track.
        if (songPosition(audio()) > RESTART_THRESHOLD_SECONDS || stateRef.current.index <= 0) seek(0);
        else previous();
      }],
      ["nexttrack", () => next()],
      ["seekto", (details) => {
        if (details.seekTime != null) seek(details.seekTime);
      }]
    ];
    // No seekbackward or seekforward: with those registered, a phone's lock
    // screen and a car's screen show ±10 s buttons in place of previous and
    // next track, and a steering wheel's next button skips 10 s instead of to
    // the next song. The scrubber still seeks (seekto).
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
      artwork: lockScreenArtwork(currentTrack)
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
      session.setPositionState({ duration: sessionDuration, playbackRate: rate, position: Math.min(songPosition(audio()) || state.position, sessionDuration) });
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
      jumpTo,
      move,
      replaceQueue
    }),
    [state, currentTrack, play, pause, toggle, seek, next, previous, retry, rate, setRate, loop, setLoopStart, setLoopEnd, clearLoop, enqueue, playNext, remove, jumpTo, move, replaceQueue]
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
