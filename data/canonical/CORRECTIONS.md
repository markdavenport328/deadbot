# Manual corrections

Each entry records a hand correction to the canonical CSVs: what changed,
why, and the evidence. See `README.md` and `docs/provenance-policy.md`.

## 2026-11-15 — 1974-02-22 Winterland: no Estimated Prophet

- **Removed:** `performances.csv` row `gd-1974-02-22-estimated-prophet-1-6`
  (song `song-estimated-prophet`, Set 1 position 6; gdshowsdb song UUID
  0b8389fb-a55b-4130-ab91-70309b0ac38e).
- **Why:** Estimated Prophet was first played on 1977-02-26 (Swing
  Auditorium). The gdshowsdb "Set 1" for 1974-02-22 is the pre-show
  soundcheck. On the representative Charlie Miller soundboard
  (archive.org `gd1974-02-22.114556.sbd.miller.flac16`), tracks 1–7 are
  Let It Grow, They Love Each Other, U.S. Blues (twice), Attics of My Life,
  It Must Have Been the Roses, and track 7 "Estimated Prophet Jam", a
  soundcheck jam on the riff, not the song. No recording track was ever
  mapped to this row (`data/raw/recordings/internet-archive-track-mapping-review.jsonl`
  lists track 7 as `not_a_setlist_song`). The show's official release,
  *Dave's Picks, Bonus Disc 2022*, opens with U.S. Blues, matching gdshowsdb
  Set 2.
- **Follow-up (2026-11-16):** the other five soundcheck rows were removed with
  the soundcheck sets below.

## 2026-11-16 — Soundchecks imported as "Set 1" (16 shows)

- **Removed:** Set 1 of 16 shows, 39 `performances.csv` rows, and the 10
  `performance_recordings.csv` / `performance_links.csv` rows pointing at them.
  The remaining sets of those shows are numbered from 1; performance IDs are
  unchanged. Every removed row is saved in
  `data/raw/corrections/soundcheck-sets-removed.jsonl`.
- **Why:** gdshowsdb has no set labels, so a soundcheck taped before a show
  arrived as an unnamed first set. That put soundcheck takes into play counts,
  debuts and bust-out gaps (Unbroken Chain's "debut" became the 3/17/95
  soundcheck; It's a Man's World's 6/30/95 soundcheck read as a 24-year
  comeback).
- **Evidence:** for each show, archive.org tape notes name the first set as a
  soundcheck, or (1973-10-23) Wang Dang Doodle as the last file after the
  encore and absent from the taper's setlist. The per-show note is in
  `scripts/remove_soundcheck_sets.py`, which made the change.
- **Not changed then:** 28 other shows had a small first set but no tape note
  either way. They were checked the same day; see the next entry.

## 2026-11-16 — Soundchecks imported as "Set 1" (36 more shows)

- **Removed:** Set 1 of 36 more shows (85 `performances.csv` rows), with the
  rows pointing at them, by the same script. Fifteen songs heard only in
  soundchecks leave the catalog with them (for example Into the Mystic, Watchin'
  the Wheels, Whiskey in the Jar, Like a Rolling Stone, Start Me Up). Two
  side-project album tracks keep their rows and titles with no song link,
  as tracks of songs the Dead never played already do: Young Blood (Kingfish)
  and Whiskey in the Jar (Shady Grove). Every change is saved in
  `data/raw/corrections/soundcheck-sets-removed.jsonl`.
- **Evidence:** the 28 shows held back above are each labeled "Soundcheck"
  (or "Partial Soundcheck") on JerryBase (jerrybase.com/events/<date>), most
  with a named eyewitness, taper or tape; 1994-12-11 lists no Saint Stephen at
  all, and none of its tapes has one. A set-count scan found 8 more shows
  whose extra opening set archive.org tape notes call a soundcheck or
  rehearsal (1973-12-12, 1976-07-12, 1993-03-17, 1993-03-31, 1994-02-25,
  1994-09-16, 1995-05-24, 1995-07-02). The per-show note is in
  `scripts/remove_soundcheck_sets.py`.
- **Not changed:** 1987-12-28 has an extra four-song first set (Sitting On
  Top Of The World, Hey Pocky Way, Eyes Of The World, Louie Louie) that no
  tape of the show contains and no note explains; it needs a source.
  1982-12-31's four sets are the real New Year's show.
