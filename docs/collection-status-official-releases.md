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

---

# Collection status: studio releases (MusicBrainz pass)

Pass date: 2026-09-05 (collection), 2026-09-06 (normalization and the personnel
pass). Source: the same MusicBrainz web service, collected by
`scripts/collect/fetch_musicbrainz_studio_releases.py` into
`data/raw/releases/musicbrainz-studio-release-groups.jsonl` (62 release groups),
`musicbrainz-studio-releases.jsonl` (482 official releases) and
`musicbrainz-studio-releases.run.json`. A second, narrow pass
(`--artist-relations`) looks each promoted release up with
`inc=recordings+artist-rels+recording-level-rels` and writes
`musicbrainz-studio-release-credits.jsonl` (46 releases, 46 requests);
that file is the only source of per-person instrument credits.
`scripts/normalize_musicbrainz_studio_releases.py` promotes them, and logs every
decision to `data/raw/releases/musicbrainz-studio-release-review.jsonl`.

Scope, from the governing spec: the Grateful Dead studio albums plus the solo and
side-project records that first carried songs the band played. The collector
browsed the Dead, Jerry Garcia, Jerry Garcia Band, Bob Weir, New Riders of the
Purple Sage, Old & In the Way and Kingfish.

## Counts

| Item | Count |
| --- | --- |
| Release groups enumerated (primary type Album, no Live secondary type) | 62 |
| Release groups with at least one official release | 54 |
| Official releases fetched (all editions) | 482 |
| Release groups promoted to `official_releases.csv` as `studio` | 46 |
| Release groups held for review | 16 |
| Promoted albums by artist | New Riders 15, Grateful Dead 13, Jerry Garcia 9, Bob Weir 4, Kingfish 4, Jerry Garcia Band 1 |
| Promoted albums with a full `release_date` | 21 of 46 (25 have only a year or month in MusicBrainz; noted in `notes`) |
| Promoted albums with a `spotify_album_url` | 25 of 46 |
| Track rows written | 447 (all with `duration_seconds`) |
| Tracks resolved to a canonical `song_id` | 133 (29.8%) |
| Tracks left unresolved | 314 |
| Grateful Dead album tracks resolved | 92 of 102 (90.2%) |
| Albums with every track resolved / no track resolved | 6 / 14 |
| Distinct `songs.csv` songs linked to a studio album | 129 |
| `release_personnel` rows written | 205, on 28 of the 46 albums, for 17 people |
| Personnel credits held rather than written | 486 (419 `person_not_in_people_csv`, 67 `no_instrument`) |
| Live-pass and hand-curated rows left untouched | 294 releases, 10,045 tracks |

Held release groups and reasons:

| Reason | Count | Release groups |
| --- | --- | --- |
| `manually_held_not_a_studio_album` | 6 | `Move Me Brightly` (the filmed Garcia tribute concert), `Double Dose` x2 (a Kingfish concert set of covers, entered twice in MusicBrainz), `The Pizza Tapes` (an informally taped Garcia/Grisman/Rice jam session), `So What` (a posthumous compilation of alternate takes), `Blue Incantation` (a Sanjay Mishra album Garcia guests on) |
| `no_official_release_fetched` | 5 | `Mason's Children`, `Standing On The Corner`, `Playin' Acoustic`, `Pirates of the Deep South`, `50 Shades of Black & White With a Touch of Grey (Volume 2)` |
| `suspected_live_material_in_title` | 4 | `1985-09-07 - Red Rocks Amphitheatre` (date and a `venues.csv` venue), `Pacific High Studio, San Francisco, CA 06-02-72` (date), `To The Sky: Jerry Garcia's Final Show` (`final show`), `Alive in Eighty Five` (`alive`) |
| `suspected_compilation_in_title` | 1 | `The Very Best Of New Riders` (`very best`) |

The three holds added on 2026-09-06 are scope decisions against the governing
sentence — the Dead's studio albums plus the solo and side-project records that
*first carried* songs the band played:

- `The Pizza Tapes` (2000) is an informally taped Garcia/Grisman/Rice jam
  session issued archivally. It first carried nothing, five of its tracks are
  fragments titled `Appetizer`, and promoting it attached `song-so-what` and
  `song-knockin-on-heaven-s-door` to a jam tape.
- `So What` (1998) is a posthumous Garcia/Grisman compilation of alternate
  takes. Its three tracks all titled `So What` all resolved to `song-so-what`,
  which was the only duplicate `(release_id, song_id)` pair in the studio set;
  there is now none.
- `Blue Incantation` is a Sanjay Mishra record that Garcia guests on. A guest
  appearance is neither a solo nor a side-project record.

Nothing else was pruned. `Been All Around This World`, `Not for Kids Only`,
`Shady Grove` and `Jerry Garcia / David Grisman` stay promoted, and promotion is
deliberately *not* gated on how many tracks resolve to a song: an album that
resolves none attaches nothing to anything, and such a rule would silently
change the catalog every time `songs.csv` widens.

## Studio-album rule

MusicBrainz never tagged the concert and bootleg material in this catalog with a
`Live` secondary type, so the collector — which is fail-closed and will not
reject on a title guess — passes it through. Filtering is the normalizer's job:

- **Title signals.** A calendar date in the title (the live pass's
  `extract_dates`), a `venues.csv` venue name of twelve characters or more
  appearing in the title, an explicit live phrase (`live`, `alive`,
  `in concert`, `unplugged`, `on stage`, `bootleg`, `final show`, `last show`,
  `farewell show`, `recorded live`, `soundboard`), or a hits-package phrase
  (`very best`, `best of`, `greatest hits`, `anthology`, `essential`,
  `retrospective`, `collection`).
- **Track signals.** A third or more of the chosen release's tracks carrying a
  MusicBrainz `live` recording disambiguation or a `(live` track title.
- **`MANUAL_HOLDS`.** A short list in the script, each entry a release-group
  MBID with a written reason, for records the signals cannot see. Adding an
  entry is preferred to loosening a regex, which would start holding real
  albums.

Holding errs deliberately toward exclusion: a studio album held by mistake is
visible in the review log and cheap to promote by hand, while a bootleg shipped
as `release_type='studio'` attaches a wrong record to real songs.

Which release represents a group: single-disc editions first (anniversary boxes
add live bonus discs), then the edition closest to the group's modal single-disc
track count, then CD/digital before vinyl, then the earliest date, then the
lowest MBID.

`release_date` is the release group's first-release date when MusicBrainz gives a
full one. When it gives only a year or a month, an edition's own full date is
used only if it falls inside that partial value; otherwise the field is blank
with the partial value in `notes`. Without that guard a 2005 remaster would be
published as the release date of a 1972 album.

`release_id` is `release-<kebab-case album title>`
(`release-american-beauty`, `release-ace`, `release-workingmans-dead`). Two
groups sharing a title are disambiguated by artist when the artists differ and
by release-group year when they do not; the two Kingfish albums both titled
`Kingfish` became `release-kingfish-1976` and `release-kingfish-1985`. An
eight-character MBID suffix is the last resort. Reruns reuse the id already
recorded for the same release or release-group MBID, so ids never renumber.

## Song-resolution rule

A track title is folded (apostrophes dropped, `&` read as `and`, every other run
of punctuation collapsed to a space) and looked up against every `songs.csv`
title and slug plus the alias table reviewed for the live pass, which is
imported from `normalize_musicbrainz_live_releases.py` rather than copied. Two
aliases were added in the same spirit: `The Golden Road (to Unlimited Devotion)`
→ `Golden Road To Unlimited Devotion` (article variant) and
`All New Minglewood Blues` → `Minglewood Blues` (a third documented variant of a
title the table already carried twice).

A title that does not match leaves `song_id` blank with the reason in `notes`.
Nothing is inferred from track order, so the 314 unresolved tracks are honest
gaps, not guesses. Most are songs the Dead never played, which is why
`songs.csv` does not carry them: 14 of the 46 albums resolve no track at all and
they are almost all New Riders, Kingfish and Garcia/Grisman records whose
material never entered the Dead's repertoire. The Grateful Dead's own albums
resolve 92 of 102 tracks; the ten that do not are suites and studio-only
pieces (`That's It for the Other One`, `Weather Report Suite: Prelude / Part 1 /
Part 2: Let It Grow`, `Blues for Allah / Sand Castles and Glass Camels /
Unusual Occurrences in the Desert`, `Help on the Way / Slipknot!`,
`King Solomon's Marbles`, `Terrapin Station, Part 1`, `Pride of Cucamonga`,
`Antwerp's Placebo (The Plumber)`, `France`, `Serengetti`).

`performance_id` is always blank on a studio track: a studio recording is not a
live performance. No live-pass track gained a `song_id` in this pass.

## Personnel

`artist-credits` — what the original browse requested — is the album's *billed*
artist ("Jerry Garcia & David Grisman"), not a performer list. Instrument
credits are MusicBrainz *relations*, and for this catalog most of them hang off
the recording rather than the release. So the collector gained `artist-rels` and
a narrow `--artist-relations` pass that looks up only the promoted releases with
`inc=recordings+artist-rels+recording-level-rels` — 46 requests, one per album,
at the same one-per-second pace, same User-Agent, same 429/503 backoff, resuming
from its `.partial` file.

That yields 205 rows on 28 of the 46 albums for 17 people. `role` follows
`show_performers`' vocabulary: an `instrument` or `vocal` relation is a
`performer`, and the relation's attribute is the instrument (`guitar`,
`lead vocals`, `drums (drum set)`). A person credited on many recordings of one
album is one row per instrument, since `release_personnel` has no track column;
`notes` says how many credits it stands for.

486 credits are held rather than written, all of them in the review log:

- 419 `person_not_in_people_csv` — 224 distinct names, mostly engineers,
  producers and session players (`Bob Matthews`, `Betty Cantor‐Jackson`,
  `John Kahn`, `Dan Healy`) who have no `people.csv` row. A person is never
  invented; adding them to `people.csv` would convert these on the next run.
- 67 `no_instrument` — real credits that the schema cannot store, because
  `instrument` is part of the primary key (mirroring `show_performers`).
  **Only a performing relation yields an instrument.** MusicBrainz hangs
  attributes on other relation types too, and they are qualifiers, not
  instruments: `producer` carries `executive`, `additional`, `assistant`.
  Reading those as instruments would file "Bob Weir, producer, executive" in the
  column that says what he played, so producer, engineer, mix, mastering,
  arranger and artwork credits are held.

18 albums get no personnel at all: MusicBrainz simply carries no artist
relations for them (`Brujo` returned zero). That is a coverage gap in the
source, not a gap this pass may fill.

## Row ownership and reruns

Rows written by this pass carry `MusicBrainz release <mbid>` for provenance and
the phrase `studio release-group pass` in `notes`. The second marker is what
identifies ownership, and **both** passes have to respect it. The live pass kept
"every row whose notes lack `MusicBrainz release `", which every studio row's
notes begins with, so a live run after a studio run would have deleted all 46
studio releases and their 447 track rows. Ownership is now a named function in
each script — `owns_row` — and they are mirrors: the studio pass owns rows
carrying `studio release-group pass`, the live pass owns rows carrying the MBID
marker *without* it, and neither owns the hand-curated Veneta row. Track rows
follow their release in both scripts (the track filter tests `release_id`
membership), so no track row is orphaned either way. The two passes can now run
in either order, repeatedly.

Two consecutive studio runs produce byte-identical `official_releases.csv`,
`official_release_tracks.csv`, `release_personnel.csv` and review log. Running
the live pass after the studio pass was verified to leave every release row and
every track row identical field for field; it does move the studio block ahead
of the live block in the file, because each script writes the rows it kept and
then appends its own.

## Verification

- The normalizer validates before writing: unique `release_id`; every
  `release_type` in the `studio`/`live`/`compilation`/`single` vocabulary;
  non-blank `title` and `source_url`; ISO `release_date`; unique positive
  `(release_id, track_number)`; non-negative durations; non-blank `track_title`;
  every `song_id` present in `songs.csv` and every `performance_id` present in
  `performances.csv`; unique `release_personnel` keys with a non-blank
  instrument and a `people.csv` person; CSV headers unchanged.
- `deadbot.postgres_import.read_canonical_table` converts all three tables with
  the importer's `TableSpec`s: 340 releases, 10,492 tracks, 205 personnel rows.
- `python -m pytest`: 235 passed, 1 failed. The failure,
  `tests/test_evaluations.py::test_evaluate_cli_exits_non_zero_when_a_case_fails`,
  needs `DEADBOT_DATABASE_URL` and fails identically on a clean tree.
- `tests/test_normalize_musicbrainz_studio_releases.py` pins the two behaviours
  that matter beyond title folding: that neither pass claims the other's rows
  (a regression test for the bug above, which fails against the pre-fix live
  normalizer), and that a release or release-group MBID keeps the `release_id`
  it was already given instead of being renumbered.

## Open questions

1. **Held groups worth a hand decision.** `Mason's Children` and
   `Standing On The Corner` are early Dead studio material that MusicBrainz has
   no official release for; if a real official issue exists they belong in the
   catalog and can be added by hand.
2. **The six manual holds** are held on a reading of the records rather than on
   anything in the MusicBrainz metadata: `Move Me Brightly`, `Double Dose` (x2),
   `The Pizza Tapes`, `So What` and `Blue Incantation`. Each is worth an owner
   check, and `Double Dose` is entered twice upstream.
3. **Suites need the segment bridge.** `Terrapin Station, Part 1`,
   `Weather Report Suite`, `That's It for the Other One` and
   `Help on the Way / Slipknot!` name more than one canonical song or a part of
   one. A studio-side equivalent of `official_release_track_performances` would
   let them carry several `song_id`s instead of none.
4. **Songs that only ever existed in the studio.** `Pride of Cucamonga`,
   `France`, `Serengetti` and `Antwerp's Placebo (The Plumber)` have no
   `songs.csv` row. Each is either a genuine repertoire gap or a song the band
   never performed; the distinction should come from the setlist baseline, not
   from this pass.
5. **New Riders, Kingfish and Garcia/Grisman repertoire.** 14 albums resolve no
   track. Adding those compositions to `songs.csv` would connect the side-project
   catalog, but `songs.csv` is currently the Dead's performed repertoire and
   widening it is an owner decision.
6. **224 credited people have no `people.csv` row**, which is why 419 credits
   are held. Most are engineers and producers (`Bob Matthews`, `Dan Healy`,
   `Betty Cantor‐Jackson`) whose credits would still be held for
   `no_instrument`, but session players such as `John Kahn` would become rows
   the moment they exist in `people.csv`. Adding them is an owner decision about
   who belongs in the people table, not something this pass may do.
7. **Track-level Spotify URLs.** No studio track has one: MusicBrainz carries
   recording-level streaming relationships for very little of this catalog,
   though 25 of 46 albums do have an album URL.
