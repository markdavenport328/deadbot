// The artwork a show gets when no real cover exists: one of a small set of
// tie-dye tiles (web/public/icons/tiles, drawn by web/scripts/make-show-tiles.mjs).
// The show's date picks the tile: its era chooses the palette and the day
// chooses the composition, so the same show always gets the same tile, and
// neighbouring nights, or the same night in neighbouring years, get different
// ones. They are plain image files at fixed addresses, so the lock screen and
// a car's display can show them as they would a record's cover.

// The first year of each era after the first; a year's era is how many it has reached.
const ERA_STARTS = [1968, 1971, 1973, 1975, 1980, 1987];
const COMPOSITIONS = 4;

export const TILE_SIZE = 512;

function hash(text: string): number {
  let value = 0;
  for (let index = 0; index < text.length; index += 1) value = (value * 31 + text.charCodeAt(index)) >>> 0;
  return value;
}

// `seed` stands in when there is no date (a lone tape named only by its file).
export function showTile(showDate?: string | null, seed?: string | null): string {
  const match = showDate ? /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(showDate) : null;
  if (match) {
    const year = Number(match[1]);
    const era = ERA_STARTS.filter((start) => year >= start).length;
    const day = Number(match[2] ?? 0) * 31 + Number(match[3] ?? 0);
    return `/icons/tiles/e${era}v${(day + year) % COMPOSITIONS}.jpg`;
  }
  const value = hash(seed || "deadbot");
  return `/icons/tiles/e${value % (ERA_STARTS.length + 1)}v${Math.floor(value / 7) % COMPOSITIONS}.jpg`;
}

// The Internet Archive's picture for a tape is a drawing of its sound wave,
// not artwork. Queues saved before the tiles still carry its address.
function isWaveform(url: string): boolean {
  return /^https?:\/\/(?:www\.)?archive\.org\/services\/img\//.test(url);
}

type Pictured = { id: string; showDate?: string | null; thumbnailUrl?: string | null };

// A real cover the track came with, if it has one.
export function trackCover(track: Pictured): string | null {
  return track.thumbnailUrl && !isWaveform(track.thumbnailUrl) ? track.thumbnailUrl : null;
}

export function trackTile(track: Pictured): string {
  return showTile(track.showDate, track.id);
}
