// Songs kept on the device for listening without a signal (in the car, on a
// plane). Each saved track's audio file sits whole in the browser's cache
// under its Internet Archive URL; the service worker (public/sw.js) serves it
// to the player from /offline-audio, answering the player's byte-range
// requests from the stored file. The player asks offlineSource() which URL
// to load, so a saved track plays from the device and any other from the
// network.
import { useEffect, useState, useSyncExternalStore } from "react";

export const OFFLINE_AUDIO_CACHE = "deadbot-offline-audio-v1";
const OFFLINE_ROUTE = "/offline-audio";

// Archive.org's MP3s run near 200 kbps: about 1.5 MB a minute.
const BYTES_PER_SECOND = 25_000;
// A track with no known length is sized as an eight-minute song.
const UNKNOWN_SECONDS = 480;

type Progress = { done: number; total: number; failed: number };

let saved = new Set<string>();
let progress: Progress | null = null;
let loaded: Promise<void> | null = null;
const listeners = new Set<() => void>();
// The store's snapshot: a new object whenever the saved set or progress changes.
let snapshot: { saved: Set<string>; progress: Progress | null } = { saved, progress };

function changed() {
  snapshot = { saved, progress };
  for (const listener of listeners) listener();
}

export function offlineSupported(): boolean {
  return typeof window !== "undefined" && "caches" in window && "serviceWorker" in navigator;
}

// Read which tracks are already saved; once per page, and again after a change.
export function loadSavedTracks(): Promise<void> {
  if (!offlineSupported()) return Promise.resolve();
  if (!loaded) {
    loaded = caches
      .open(OFFLINE_AUDIO_CACHE)
      .then((cache) => cache.keys())
      .then((requests) => {
        saved = new Set(requests.map((request) => request.url));
        changed();
      })
      .catch(() => undefined);
  }
  return loaded;
}

// The URL the player loads for a track: the device's copy when the track is
// saved and the service worker is there to serve it, else the network's.
export function offlineSource(url: string): string {
  if (!saved.has(url) || typeof navigator === "undefined" || !navigator.serviceWorker?.controller) return url;
  return `${OFFLINE_ROUTE}?src=${encodeURIComponent(url)}`;
}

export function estimateBytes(tracks: { durationSeconds?: number | null }[]): number {
  return tracks.reduce((sum, track) => sum + (track.durationSeconds ?? UNKNOWN_SECONDS) * BYTES_PER_SECOND, 0);
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

// Save each track not saved yet, one at a time, reporting progress. A track
// that fails is counted and skipped; the rest still save.
export async function saveTracks(urls: string[]): Promise<void> {
  if (!offlineSupported() || progress) return;
  await loadSavedTracks();
  const missing = [...new Set(urls)].filter((url) => !saved.has(url));
  if (missing.length === 0) return;
  // Ask the browser to keep these files rather than clear them under pressure.
  void navigator.storage?.persist?.().catch(() => false);
  progress = { done: 0, total: missing.length, failed: 0 };
  changed();
  const cache = await caches.open(OFFLINE_AUDIO_CACHE);
  for (const url of missing) {
    try {
      const response = await fetch(url, { mode: "cors" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.blob();
      await cache.put(
        url,
        new Response(body, { headers: { "Content-Type": body.type || "audio/mpeg", "Content-Length": String(body.size) } })
      );
      saved = new Set(saved).add(url);
      progress = { ...progress, done: progress.done + 1 };
    } catch {
      progress = { ...progress, done: progress.done + 1, failed: progress.failed + 1 };
    }
    changed();
  }
  const failed = progress.failed;
  progress = null;
  lastFailed = failed;
  changed();
}

let lastFailed = 0;

export function lastSaveFailures(): number {
  return lastFailed;
}

export async function removeTracks(urls: string[]): Promise<void> {
  if (!offlineSupported()) return;
  const cache = await caches.open(OFFLINE_AUDIO_CACHE);
  await Promise.all(urls.map((url) => cache.delete(url)));
  const next = new Set(saved);
  for (const url of urls) next.delete(url);
  saved = next;
  lastFailed = 0;
  changed();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// Which of these tracks are on the device, and a save in progress.
export function useOffline(urls: string[]) {
  const state = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void loadSavedTracks().then(() => live && setReady(true));
    return () => {
      live = false;
    };
  }, []);
  const unsaved = urls.filter((url) => !state.saved.has(url));
  return { ready, savedCount: urls.length - unsaved.length, unsaved, progress: state.progress };
}

// For tests: forget what this page has read.
export function resetOfflineState() {
  saved = new Set();
  progress = null;
  loaded = null;
  lastFailed = 0;
  changed();
}
