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
- **Left as is:** the other five soundcheck rows (`-1-1` through `-1-5`) stay
  in Set 1, because recordings and links point at them. Labelling them as a
  soundcheck rather than a set is open work.
