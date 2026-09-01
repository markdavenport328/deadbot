# Performance track-link status (Internet Archive)

Updated 2026-09-01.

This pass gives every mapped song performance a resolvable per-track playback
URL on archive.org, so Deadbot can point a listener at "this version of this
song" rather than only at the whole show. It followed
`docs/collection-methodology.md`: no new source requests were needed for the
data itself, the URLs were derived offline from the already-preserved
representative item metadata, and the URL pattern was verified with a small
rate-limited sample before the canonical file was written.

## What was done

- Added `scripts/normalize_internet_archive_track_links.py` (stdlib only,
  deterministic, rerunnable, idempotent). For each
  `data/canonical/performance_recordings.csv` row it looks up the recording's
  `archive_identifier`, finds the preserved representative record in
  `data/raw/recordings/internet-archive-{year}-representatives.jsonl`, and
  selects the file that carries the mapped track number and whose title
  normalizes to the canonical song title with the same `normalized_title`
  alias rules used by `normalize_internet_archive_tracks.py`. A derivative
  file that carries no title of its own inherits title and track number from
  the lossless original named in its `original` field. The URL is
  `https://archive.org/details/{identifier}/{file_name}` (file name
  percent-encoded), which opens the archive.org web player on that track.
- File preference: a single `VBR MP3` file for the track, because the web
  player streams MP3. When more than one MP3 exists for the track and every
  candidate derives from the same lossless original (the `d1t03.mp3` /
  `d1t03_vbr.mp3` pattern), the shortest name is chosen deterministically and
  counted separately; any other multiplicity is held. When no MP3 matches, the
  lossless original chosen by the track-mapping rules is used if its title
  matches; otherwise the row is held.
- Appended rows to `data/canonical/performance_links.csv` with
  `performance_link_id = performance-link-{performance_id}-archive-track`,
  `platform = archive`, `link_type = recording-track`, the source track title,
  blank `start_seconds`, `duration_seconds` copied from
  `performance_recordings`, `is_official = false`, and a note naming the track
  number, item, recording ID, and file. The existing YouTube row was kept. The
  file is sorted by `performance_link_id`; reruns match on `url` and add
  nothing.
- Held rows are written to
  `data/raw/recordings/internet-archive-track-link-review.jsonl` with the
  reason, the mapped and canonical titles, and every file title seen for the
  track. Nothing was guessed.

`schema/postgres.sql` places no vocabulary constraint on `platform` or
`link_type`; the relevant constraints are the primary key, `UNIQUE
(performance_id, platform, url)`, and non-negative seconds, all of which the
output satisfies.

## Counts

| Measure | Count |
| --- | ---: |
| `performance_recordings` rows | 16,507 |
| Distinct recordings with mapped tracks | 1,016 |
| Representative records available for those recordings | 1,016 (all) |
| Matched: single `VBR MP3` file | 16,301 |
| Matched: MP3 chosen by same-original tie-break | 199 |
| Matched: lossless original (no MP3 with matching title) | 5 |
| Written to `performance_links.csv` | 16,505 |
| Held for review | 2 |
| `performance_links.csv` rows after the pass | 16,506 (1 existing + 16,505) |
| Rows carrying `duration_seconds` | 16,487 |

Held rows, both from the hand-curated Veneta mapping on
`gd1972-08-27.sbd.latvala-eaton-lutch-dankseed.4682.shnf`:

| Performance | Track | Source file title | Canonical title | Reason |
| --- | ---: | --- | --- | --- |
| `gd-1972-08-27-casey-jones` | 19 | `E1: Casey Jones` | Casey Jones | `file_title_does_not_match_canonical_song` |
| `gd-1972-08-27-one-more-saturday-night` | 20 | `E2: Saturday Night` | One More Saturday Night | `file_title_does_not_match_canonical_song` |

The encore prefix is not covered by the shared alias list, and the second
title also uses a shortened song name. Both are correct tracks on inspection
but were not promoted because the rule is title agreement, not judgment.

## Sample URL verification

Before writing, the script requested 10 sample URLs with HTTP GET (headers
only), one per second, `User-Agent: Deadbot/0.1 (historical-show-context)`.
Samples were spread across the sorted output and deliberately included one
percent-encoded file name with spaces and one lossless `.flac` fallback.

| Status | URL |
| ---: | --- |
| 200 | `https://archive.org/details/gd1966-01-08.sbd.bershaw.5410.shnf/Acid1_05.mp3` |
| 200 | `https://archive.org/details/gd72-11-19.sbd.winters.17705.sbeok.shnf/gd72-11-19d1t01.mp3` |
| 200 | `https://archive.org/details/gd1977-05-07.148736.SBD.Betty.Anon.Noel.t-flac2448/gd.77-05-07.s1t16.mp3` |
| 200 | `https://archive.org/details/gd1979-02-11.155704.aud.remaster.acetboy.flac16/Grateful%20Dead%201979-02-11%20aud%2007.mp3` |
| 200 | `https://archive.org/details/gd1980-10-29.140899.sbd.aud.flac1644/gd1980-10-29-s1t11.mp3` |
| 200 | `https://archive.org/details/gd1982-07-25.137191.nak300.schley.flac2448/gd1982-07-25s1t07.mp3` |
| 200 | `https://archive.org/details/gd1984-07-21.136717.sbd.GEMS.flac16/gd84-07-21s2t08.mp3` |
| 200 | `https://archive.org/details/gd1987-08-13.sbd.unknown.7992.sbeok.shnf/gd87-08-13d1t10.mp3` |
| 200 | `https://archive.org/details/gd1991-05-10.149670.sbd.pearson-healy.miller.flac2496/05%20Stagger%20Lee.mp3` |
| 200 | `https://archive.org/details/gd1969-08-16.139807.sbd.gastwirt.miller.sirmick.flac1644/gd1969-08-16t07.flac` |

All 10 returned 200, so the canonical file was written. Only these 10
requests were made; no item metadata was re-fetched and no audio was
retrieved.

## Validation

- `performance_link_id` values are unique and the file is sorted by them.
- Every `performance_id` exists in `performances.csv`.
- No duplicate `url`; `(performance_id, platform, url)` is unique.
- CSV header unchanged; `deadbot.postgres_import.read_canonical_table` (the
  importer's strict header/type validator, run without a database) accepted
  all 16,506 rows.
- Idempotency: a second run without network produced byte-identical
  `performance_links.csv` and review JSONL (same SHA-256).
- Tests: `pytest tests/test_data.py tests/test_provenance.py
  tests/test_postgres_import.py -q` gave 50 passed, 2 failed
  (`test_show_tool_payload_is_compact_enough_for_local_model_context`,
  `test_show_media_lookup_resolves_a_date_to_the_canonical_show`). Both
  failures were isolated with scratch copies of `data/canonical/`: they
  reproduce with this pass's `performance_links.csv` reverted to HEAD and
  disappear when the concurrently modified `show_links.csv` is reverted to
  HEAD. They belong to the separate show-listening-links work in this
  worktree, not to this pass. `test_postgres_import.py` ran fully against its
  fake connection; no live database was needed.

## Source and rights notes

- Source: Internet Archive item metadata already preserved in
  `data/raw/recordings/internet-archive-{year}-representatives.jsonl`
  (retrieved 2026-08-24/25). This pass stores file names, track numbers,
  titles, durations, and resolvable URLs only. No audio, artwork, or
  long-form text was copied.
- The links point at archive.org's own player pages for community-uploaded
  Grateful Dead recordings held in the `GratefulDead`/`etree` collections
  under the band's taping and stream-only policies. Rows are
  `is_official = false`; the note attributes each link to its item and file.
- The representative item is one metadata-selected SBD/AUD-preferred source
  per show. A track link therefore identifies one version of the performance
  on one source, not the best or only recording of it.

## Open questions

1. Should the shared alias list (in `normalize_internet_archive_tracks.py`)
   learn to strip encore prefixes such as `E1:` and map `Saturday Night` to
   `One More Saturday Night`? That would promote the two held Veneta encore
   rows, and Veneta is the vertical-slice show. It was left alone here to keep
   this pass from changing the track-mapping normalizer.
2. The same-original tie-break for duplicate MP3 encodes (199 rows) is a
   policy choice. It selects a file by name length rather than by any source
   field describing the encode. If reviewers prefer, those rows can be held
   instead by removing the branch; they are counted separately so the change
   is auditable.
3. The 5 lossless fallbacks resolve (sample verified), but the player streams
   a derivative behind them. If a stream-format URL is required for every
   row, these five could be held instead.
4. `deadbot/composition.py` maps `platform` to an embed kind. `archive` is a
   new platform value for `performance_links`; confirm the media block treats
   it as a plain external link (it should fall back to a non-embedded link)
   and decide whether the UI wants a dedicated label.
5. `start_seconds` is blank everywhere because the source gives per-file
   durations only. Per-track pages make offsets unnecessary for playback, but
   a future pass could derive cumulative offsets for whole-show players if
   the product needs them.
6. `performance_recordings` currently maps each performance to exactly one
   recording, so the `-archive-track` ID suffix is collision-free. If a later
   pass maps performances to additional sources, the ID scheme will need a
   recording-specific component.
