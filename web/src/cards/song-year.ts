// The year lookup behind "See all": one song's performances in one year,
// fetched once per song and year and kept for the session. Library facts do
// not change between deploys, so a kept answer never goes stale.
import type { SongYearDetail } from "./song-timeline-types";

export type FetchYear = (songId: string, year: number) => Promise<SongYearDetail>;

const kept = new Map<string, Promise<SongYearDetail>>();

export function songYearUrl(songId: string, year: number): string {
  return `/api/songs/${encodeURIComponent(songId)}/years/${year}`;
}

export const fetchSongYear: FetchYear = (songId, year) => {
  const key = `${songId}:${year}`;
  let pending = kept.get(key);
  if (!pending) {
    pending = fetch(songYearUrl(songId, year)).then(async (response) => {
      if (!response.ok) throw new Error(`The ${year} list could not load (${response.status}).`);
      return (await response.json()) as SongYearDetail;
    });
    // A failed lookup is forgotten so the visitor's retry asks again.
    pending.catch(() => kept.delete(key));
    kept.set(key, pending);
  }
  return pending;
};

export function forgetSongYears(): void {
  kept.clear();
}
