// Deadbot's service worker: it lets a phone listen without a signal.
//
// - Songs the visitor saved for offline (src/player/offline.ts) are whole
//   audio files in the "deadbot-offline-audio-v1" cache. The player loads a
//   saved song from /offline-audio?src=<its Internet Archive URL>; this
//   worker answers from the stored file, including the byte ranges an audio
//   element asks for, and falls back to the network if the file is gone.
// - The app itself (its page, scripts, fonts and icons) is kept as it loads,
//   so Deadbot still opens with no signal and its player can resume the
//   saved queue. Questions still need the network.
// Every other request, including all streaming audio, passes through
// untouched.

const AUDIO_CACHE = "deadbot-offline-audio-v1";
const SHELL_CACHE = "deadbot-shell-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => name.startsWith("deadbot-shell-") && name !== SHELL_CACHE).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === "/offline-audio") {
    event.respondWith(savedAudio(request, url.searchParams.get("src") || ""));
  } else if (request.mode === "navigate") {
    // Every page of the app is the same page; keep one copy.
    event.respondWith(networkFirst(request, "/"));
  } else if (/^\/(assets|fonts)\//.test(url.pathname)) {
    event.respondWith(keptFile(request));
  } else if (url.pathname.startsWith("/icons/") || url.pathname === "/manifest.webmanifest") {
    event.respondWith(networkFirst(request, request));
  }
});

// A saved song, whole or the byte range asked for.
async function savedAudio(request, src) {
  const stored = src ? await caches.open(AUDIO_CACHE).then((cache) => cache.match(src)) : undefined;
  if (!stored) return fetch(src);
  const body = await stored.blob();
  const type = stored.headers.get("Content-Type") || "audio/mpeg";
  const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get("Range") || "");
  if (!range || (range[1] === "" && range[2] === "")) {
    return new Response(body, { status: 200, headers: { "Content-Type": type, "Content-Length": String(body.size), "Accept-Ranges": "bytes" } });
  }
  let start;
  let end;
  if (range[1] === "") {
    // "bytes=-500": the last 500 bytes.
    start = Math.max(0, body.size - Number(range[2]));
    end = body.size - 1;
  } else {
    start = Number(range[1]);
    end = range[2] === "" ? body.size - 1 : Math.min(Number(range[2]), body.size - 1);
  }
  if (start >= body.size || start > end) {
    return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${body.size}` } });
  }
  return new Response(body.slice(start, end + 1, type), {
    status: 206,
    headers: {
      "Content-Type": type,
      "Content-Length": String(end - start + 1),
      "Content-Range": `bytes ${start}-${end}/${body.size}`,
      "Accept-Ranges": "bytes"
    }
  });
}

// From the network when there is one, else the last copy kept.
async function networkFirst(request, key) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(key, response.clone());
    return response;
  } catch (error) {
    const kept = await cache.match(key);
    if (kept) return kept;
    throw error;
  }
}

// Scripts, styles and fonts have fixed names per build: keep each as
// it first loads and answer from the copy after.
async function keptFile(request) {
  const cache = await caches.open(SHELL_CACHE);
  const kept = await cache.match(request);
  if (kept) return kept;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}
