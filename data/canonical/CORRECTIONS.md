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
- **Not changed:** 28 other shows have a small first set but no tape note
  either way (for example 1983-10-09 Saint Stephen, 1994-12-11 Saint Stephen,
  1995-03-22 Watchin' the Wheels, 1995-06-24 Into the Mystic). They need a
  second source before anything moves.
