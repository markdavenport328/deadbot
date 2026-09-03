# Collection status: official live releases (MusicBrainz pass)

Pass date: 2026-09-01. Source: MusicBrainz web service (JSON, one request per
second, User-Agent `DeadBot/0.1 (local official-release collection; contact
unavailable)`).

## What was done

1. `scripts/collect/fetch_musicbrainz_live_releases.py` resolved the Grateful
   Dead artist MBID by search (`6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6`, score
   100, type Group; the other hits were a UK act and a tribute band), browsed
   every release group with primary type Album and secondary type Live, then
   browsed the artist's official Album+Live releases with
   `inc=recordings+url-rels+release-groups+recording-level-rels`. Browsing
   releases by artist returned the complete official catalog in 37 paged
   requests, so no per-release-group lookups were needed; the normalizer picks
   one release per group. Compact raw records (MBIDs, titles, dates,
   disambiguations, statuses, medium titles, track titles and lengths,
   recording disambiguations, URL relationships; no cover art, no annotation
   text) are in `data/raw/releases/musicbrainz-release-groups.jsonl` and
   `data/raw/releases/musicbrainz-releases.jsonl`. The run summary and request
   log are in `data/raw/releases/musicbrainz-live-releases.run.json`. The
   collector checkpoints after every page and resumes from
   `musicbrainz-live-releases.checkpoint.json` if interrupted; the cap of 300
   release requests was not approached.
2. `scripts/normalize_musicbrainz_live_releases.py` resolved each release
   group to canonical shows, wrote `data/canonical/official_releases.csv` and
   `data/canonical/official_release_tracks.csv`, and logged every decision to
   `data/raw/releases/musicbrainz-release-review.jsonl`. Rows it manages carry
   `MusicBrainz release <mbid>` in `notes`; reruns replace only those rows,
   reuse the `release_id` previously assigned to the same release or
   release-group MBID, and leave the hand-curated Veneta row and its 21 tracks
   untouched. Two consecutive runs produce byte-identical output.

## Counts

| Item | Count |
| --- | --- |
| HTTP requests (1 artist search, 10 release-group pages, 37 release pages) | 48, all HTTP 200 |
| Album+Live release groups enumerated | 991 |
| Release groups with at least one official release | 327 |
| Release groups with no official release (bootleg-only or artist credited only on tracks) | 664, held |
| Official releases fetched (all editions) | 572 |
| Release groups promoted to `official_releases.csv` | 293 (157 single-show, 136 spanning more than one show) |
| Release groups skipped as a likely duplicate of the curated Veneta row | 1 (`Sunshine Daydream: Veneta, Oregon, August 27, 1972`) |
| Release groups held for review (official release, not promoted) | 33 |
| Promoted releases with a full `release_date` | 244 of 293 (49 have only a month or year in MusicBrainz; noted in `notes`) |
| Track rows written | 10,024 |
| Tracks mapped to a canonical performance | 7,026 (70.1%) |
| Tracks left without `performance_id` | 2,998 |
| Releases with every track mapped / some / none | 82 / 187 / 24 |
| Distinct canonical shows attributed to a promoted release | 648 |
| Distinct canonical shows with at least one mapped track | 529 |
| Tracks with `duration_seconds` | 9,790 |

Held release groups and reasons:

| Reason | Count | Examples |
| --- | --- | --- |
| `no_show_date_in_metadata` | 23 | Without a Net, Steal Your Face, Dylan & the Dead, Infrared Roses, Nightfall of Diamonds, Dozin' at the Knick, Vintage Dead, Historic Dead, View From the Vault I–IV, Road Trips 4.2 April Fools' '88, Road Trips 3.4 Penn State–Cornell '80, Dave's Picks bonus discs 2021 and 2025 |
| `multi_show_without_track_attribution` | 8 | Dick's Picks 4, 20, 25, 29 (two dates in the title, no per-track dates), Download Series 9, Dave's Picks 30 (1/2/70 and 1/3/70 each have two canonical shows), RFK July 12 & 13 1989, Fare Thee Well (2015, outside the canonical span) |
| `date_matches_multiple_canonical_shows` | 2 | Fillmore East 2-11-69, Dave's Picks Bonus Disc 2019 (early and late shows on the same date) |
| `possible_duplicate_of_curated_release` | 1 | Sunshine Daydream (same show and release year as the curated Veneta row) |

Unmapped-track reasons (all recorded per row in `notes`; sums to 2,998):

| Reason | Tracks |
| --- | --- |
| Release order contradicts the canonical setlist, whole show group held | 1,153 |
| Multi-show release and the track has no per-track date in MusicBrainz | 1,058 |
| Title not in the show's canonical setlist (intro, tuning, banter, source-only segment; `Rhythm Devils` is now aliased to `Drums`, see open question 9) | 376 |
| No release title for that show matched any canonical title (mostly `A / B` medley tracks on 30 Days of Dead compilations) | 223 |
| Track date resolves to two canonical shows (early/late) | 81 |
| Title fits more than one setlist position after all consistent alignments are compared | 46 |
| Track date not in `shows.csv` | 49 |
| Track combines more than one canonical performance (medley) | 11 |
| More than one date in the track's own metadata | 1 |

(Refreshed 2026-09-02 from a fresh run of `scripts/normalize_musicbrainz_live_releases.py` against a scratch copy of `data/`, printed-summary and committed-CSV counts alike: the run is byte-identical to the committed `official_releases.csv` and `official_release_tracks.csv`, confirmed by SHA-256, so the CSVs were not rewritten, only this table. The prior table's 6,993/3,031/409/10,081 figures predated the `Rhythm Devils` → `Drums` alias resolved in open question 9 below; the "releases with every track mapped / some / none" row was independently stale and is corrected here from the same committed tracks table. The unmapped-reasons table now sums to the stated 2,998 total.)

## Show-resolution rule

Dates are extracted from four title-level fields (release-group title and
disambiguation, chosen release title and disambiguation) and three track-level
fields (recording disambiguation, which MusicBrainz editors write as
`live, YYYY-MM-DD: venue`; medium title; track title). Recognized forms:
`YYYY-MM-DD`, `M/D/YY`, `M/D/YYYY`, `M-D-YY`, `M.D.YY`, same-month day ranges
and lists (`2/13-14/70`, `4/2&3/89`), two-date lists (`10/1/77 & 10/2/77`),
and `Month D, YYYY` including `July 12 & 13, 1989`. Unicode hyphens are
normalized first. Two-digit years 65–99 map to the 1900s. Month-only strings
(`September 1974`, `April 1978`) are not dates.

- If the union of title-level and track-level dates is exactly one date, the
  release is a **single-show release** and every track is attributed to that
  show. It is promoted only when the date matches exactly one row in
  `shows.csv`; a date with two canonical shows (early/late) or none is held.
- If more than one date is present, the release **spans more than one show**.
  Each track is attributed only by its own track-level date, and only when that
  date matches exactly one canonical show. Tracks without a track-level date
  are never attributed, even when the title names one main show (bonus tracks
  are the usual reason for a second date). The release is promoted when at
  least one track is attributed; `notes` lists the attributed shows.
- If no date is found anywhere, the release is held.

Which release represents a group: the official release with the best format
rank (CD/digital before other formats, vinyl last, because vinyl sides split and
reorder long tracks), then the most tracks, then the earliest date, then the
lowest MBID. `release_date` is the release group's first-release date when it
is a full date, otherwise the earliest fully dated release in the group,
otherwise blank with the partial value in `notes`.

`release_id` is `release-<title before the first colon, dates removed>-<show
date>` for a release that names one show date (`release-dicks-picks-volume-8-1970-05-02`),
and `release-<full title, dates removed>-<release year>` for a compilation
without a single title date (`release-europe-72-1972`,
`release-30-days-of-dead-nov-2015`). One collision (`RFK Stadium, Washington
D.C. 6/10/73` and `June 10 1973 (RFK Stadium, Washington, D.C.)`, two MusicBrainz
release groups issued the same day) received an eight-character MBID suffix.

## Track-mapping rule

For each attributed show, the release's tracks (in disc and track order) are
aligned with the show's canonical setlist using `normalized_title` from
`scripts/normalize_internet_archive_tracks.py`, extended with a documented
alias table (contractions such as `Goin' Down the Road Feeling Bad`,
abbreviations such as `St. Stephen`, and full or alternate titles such as
`New Minglewood Blues`, `Mississippi Half-Step Uptown Toodeloo`, `Caution (Do
Not Stop on Tracks)`, `The Stranger (Two Souls in Communion)`; every alias
target is an existing `songs.csv` title). Parentheticals that contain a date
(`Dark Star (1969-06-05: Fillmore West)`) are stripped before matching.

A track gets a `performance_id` only when every monotonic alignment of the
show group agrees on its setlist position. Titles absent from the setlist are
skipped as intro/tuning/banter/source-only material. A title that appears in
the setlist but only earlier than the alignment has reached kills that
alignment; when no alignment survives, the whole show group is held. This is
deliberate: it is what stops an undated bonus track from another show (for
example the 11/2/77 filler on Dick's Picks 34, or the 5/25/93 tracks on Road
Trips 2.4) from being absorbed into a gap in the main show's setlist. Suites
and medleys (`That's It for the Other One`, `Weather Report Suite`, `China Cat
Sunflower / I Know You Rider`) and segment names that are not song titles
(`Rhythm Devils`) stay unmapped; `official_release_track_performances` is the
place for those segments.

## Spotify URL coverage

Spotify links come only from MusicBrainz URL relationships (`streaming` /
`free streaming`). 65 of 293 promoted releases (22%) have a
`spotify_album_url` (35 single-show, 30 multi-show); the URL may come from any
edition in the release group and `notes` says which release supplied it when it
differs from the represented release. 399 tracks have a `spotify_track_url`
from recording-level relationships. Most Dick's Picks, Dave's Picks, Road Trips
and Download Series entries have no Spotify relationship in MusicBrainz even
where the album is streamable, so this is a lower bound on availability, not a
statement that the album is missing from Spotify.

## MusicBrainz attribution and terms

- MusicBrainz core data (the entities, titles, dates, relationships and URLs
  used here) is released under CC0. Supplementary data such as annotations and
  cover art carry other licenses and were not collected.
- The web service asks for one request per second and a descriptive
  User-Agent; the collector enforces both and backs off on HTTP 429/503.
- Rows cite MusicBrainz by release and release-group MBID in `notes` and by
  `source_url = https://musicbrainz.org/release/<mbid>`. Keep the "source:
  MusicBrainz" credit in any user-facing surface that displays these fields.
- Track order, titles and dates in MusicBrainz are contributor-entered.
  Recording disambiguation dates were treated as source evidence for show
  attribution, never as a canonical show fact; a date that does not match
  `shows.csv` is held rather than used to create a show.

## Verification

- `scripts/normalize_musicbrainz_live_releases.py` validates before writing:
  unique `release_id`; non-blank `title` and `source_url`; ISO `release_date`;
  unique positive `(release_id, track_number)` (the `official_release_tracks`
  primary key); non-negative durations; every `performance_id` exists in
  `performances.csv` and belongs to the show the track was attributed to;
  CSV headers unchanged.
- `deadbot.postgres_import.read_canonical_table` converts both tables with the
  importer's `TableSpec`s without error (294 releases, 10,045 tracks including
  the curated Veneta rows).
- `pytest tests/test_data.py tests/test_provenance.py tests/test_postgres_import.py`:
  50 passed, 2 failed. `test_show_media_lookup_resolves_a_date_to_the_canonical_show`
  fails because of the concurrent `show_links.csv` work in this worktree
  (`recording-index` links now sort first), not because of this pass.
  `test_show_tool_payload_is_compact_enough_for_local_model_context` asserts the
  Veneta `get_show` payload is under 11,000 characters; it is 11,253 with the
  new `show_links` rows and the original release files, and 11,709 with the
  four additional releases that now reference Veneta performances. The
  threshold needs an owner decision.

## Open questions

1. **Spotify/Apple Music coverage.** 78% of promoted releases have no album
   URL from MusicBrainz. A Spotify Web API search (artist + album title, then
   track-count and duration cross-check) or an Apple Music lookup would fill
   most of the Dick's Picks / Dave's Picks gaps; both need credentials and a
   rights review, and matches should be verified against track lists before
   promotion.
2. **Per-track show attribution for two-show releases.** Dick's Picks 4, 20,
   25, 29 and Download Series 9 name two dates but their MusicBrainz recordings
   carry no dates. Dead.net track listings or the release booklets could supply
   disc-level attribution; until then they stay in the review file.
3. **Early/late shows.** 1970-05-15, 1970-01-02/03, 1969-02-11, 1970-02-11/13/14
   and similar dates have two canonical shows. Attributing these needs a
   set-level source (or a decision to use early/late labels from recording
   disambiguations when MusicBrainz provides them).
4. **Undated bonus material.** About 1,150 tracks sit on releases whose order
   contradicts the canonical setlist. Most are single-date titles with undated
   filler from a neighbouring show; a second pass with per-track dates would
   recover the main-show tracks safely.
5. **Segment bridge.** Suites, medleys and split tracks (`Good Lovin' I/II`,
   `Dark Star…/…Dark Star`) need `official_release_track_performances` rows
   rather than the legacy single `performance_id`.
6. **Release/show coverage table.** Releases with zero mapped tracks (24) are
   not reachable from the show tool today because `show_context` finds releases
   through mapped tracks only. Populating `release_shows` from the `notes`
   attribution would make coverage queryable independently of track mapping.
7. **Canonical gaps surfaced by release dates.** Track dates such as
   1971-09-09, 1968-01-23, 1969-01-23 and 1993-02-18 are absent from
   `shows.csv`. Each is either a MusicBrainz error or a baseline gap and should
   be checked against the gdshowsdb source before either side is changed.
8. **Duplicate release groups in MusicBrainz.** The two RFK 6/10/73 groups
   look like one product entered twice; if confirmed, one should be folded into
   the other upstream or marked in the review file.
9. Resolved 2026-09-01: `Rhythm Devils` is the drummers' own name for the
   segment that `songs.csv` calls `Drums`, so the normalizer now treats it as
   an alias of `Drums`. 33 of the 40 `Rhythm Devils` tracks map to a canonical
   `Drums` performance; the remaining 7 sit on releases whose show attribution
   or alignment is still held for the reasons above.
