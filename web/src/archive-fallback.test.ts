import { describe, expect, it, vi } from "vitest";
import { archiveFallbackUrls } from "./archive-fallback";

const ITEM = "gd1971-02-21.sbd.cantor-crouch-diebert-gmb.87134.sbeok.flac16";
const URL = `https://archive.org/download/${ITEM}/gd1971-02-21d1t10.mp3`;

function respond(body: unknown, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => body }) as Response);
}

describe("archiveFallbackUrls", () => {
  it("points at the item's primary servers", async () => {
    const fetcher = respond({ d1: "ia601509.us.archive.org", d2: "ia801509.us.archive.org", dir: `/11/items/${ITEM}` });
    await expect(archiveFallbackUrls(URL, fetcher)).resolves.toEqual([
      `https://ia601509.us.archive.org/11/items/${ITEM}/gd1971-02-21d1t10.mp3`,
      `https://ia801509.us.archive.org/11/items/${ITEM}/gd1971-02-21d1t10.mp3`
    ]);
    expect(fetcher).toHaveBeenCalledWith(`https://archive.org/metadata/${ITEM}`);
  });

  it("offers nothing for links that are not archive.org downloads", async () => {
    const fetcher = respond({});
    await expect(archiveFallbackUrls("https://example.com/a.mp3", fetcher)).resolves.toEqual([]);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("offers nothing when the metadata lookup fails", async () => {
    await expect(archiveFallbackUrls(URL, respond({}, false))).resolves.toEqual([]);
    await expect(archiveFallbackUrls(URL, vi.fn(async () => Promise.reject(new Error("offline"))))).resolves.toEqual([]);
    await expect(archiveFallbackUrls(URL, respond({ d1: "ia601509.us.archive.org" }))).resolves.toEqual([]);
  });
});
