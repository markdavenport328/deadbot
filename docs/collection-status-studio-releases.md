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
| Promoted albums with a `release_date` | 46 of 46 (28 full dates, 7 year-month, 11 year only, after the 2026-09-06 Wikipedia sharpening pass below; MusicBrainz-only precision noted in `notes` was 21 full dates, 6 year-month, 19 year only) |
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

`release_date` is the release group's first-release date, stored at whatever
precision MusicBrainz gives it: a full ISO date, a year-month (`1972-05`), or a
year alone (`1972`). `official_releases.release_date` is `TEXT`, not a SQL
date, precisely so a partial value can be stored rather than blanked. An
edition's own full date is used in place of a partial value only if it falls
inside that partial value; otherwise a 2005 remaster would be published as the
release date of a 1972 album. The field is left blank only when MusicBrainz
gives no `first_release_date` that is a recognized year, year-month, or full
date.

## Wikipedia sharpening pass (2026-09-06)

The 25 studio rows above whose `release_date` was still year-only or
year-month after the MusicBrainz pass were checked against Wikipedia's
infobox `Released` field: `scripts/collect/fetch_wikipedia_album_dates.py`
(`data/raw/releases/wikipedia-album-dates.jsonl`, one raw record per album with
the chosen article, page id, revision id, and the raw `Released` string) and
`scripts/normalize_wikipedia_album_dates.py`
(`data/raw/releases/wikipedia-album-date-review.jsonl`). All 25 were matched to
a confident article and yielded a parseable field.

| Outcome | Count | Albums |
| --- | --- | --- |
| Upgraded (year → year-month or full; year-month → full) | 11 | `Ace` (1972-05→1972-05-01), `17 Pine Avenue` (2012-03→2012-03-06), `Reflections` (1976-02→1976-02-03), `Cats Under the Stars`, `Compliments of Garcia`, `Heaven Help the Fool`, `Jerry Garcia / David Grisman` (all year→full), `Gypsy Cowboy`, `New Riders of the Purple Sage`, `Powerglide`, `The Adventures of Panama Red` (all year→year-month) |
| Conflict: Wikipedia's year disagrees with the existing year, left untouched | 4 | `Hooteroll?` (existing 1970 vs Wikipedia 1971-11-01), `Feelin' All Right` (1980 vs 1981), `Marin County Line` (1993 vs 1977), `Midnight Moonlight` (1993 vs 1992-05-12) |
| Held: already at Wikipedia's own precision | 9 | `Before Time Began`, `Brujo`, `Keep On Keepin' On`, `Kingfish` (1976), `Kingfish` (1985), `New Riders`, `Oh, What a Mighty Time`, `Trident`, `Who Are Those Guys?` |
| Held: Wikipedia is less precise than the existing value | 1 | `Run for the Roses` (existing 1982-11; Wikipedia infobox gives only `1982`) |

A year conflict is logged as a review item and never resolved by picking a
side: the four conflicts above disagree on the *year*, which the governing
rule treats as more significant than any precision Wikipedia might otherwise
add. Every decision — including the article chosen and why, and the raw
`Released` string before parsing — is in the review log. Only the
`release_date` column of these 11 rows changed: the 294 live rows, every other
column, and row order were diffed field-for-field against the pre-pass commit
and are unchanged.

Two consecutive runs of `scripts/normalize_wikipedia_album_dates.py` produce a
byte-identical `official_releases.csv`. The review log is not expected to
match byte-for-byte across runs: it compares the raw Wikipedia record against
`official_releases.csv` as it stands when each run starts, so a row upgraded
by the first run reads `already_at_source_precision` on every run after,
which is the correct comparison against the now-updated CSV rather than a
sign of drift.

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

**This ownership guarantee is about *rows*, not about the `song_id` column.**
The live normalizer recomputes every row it owns from raw data on each run and
never writes `song_id` itself (it always leaves the column blank on its own
rows), so running the live pass after `scripts/normalize_release_track_songs.py`
has backfilled `song_id` onto live tracks silently drops that column back to
blank on every live row — from 9,380 tracks carrying a `song_id` down to the 153
that the studio pass alone had contributed. Nothing is lost: the backfill is
a deterministic recomputation from `performances.csv` and `songs.csv` and
reproduces the same 9,380 the moment it is rerun. But the three scripts have a
required order, and running them out of order looks like a regression until
the backfill runs again. See `schema/README.md` for the stated order.

## Verification

- The normalizer validates before writing: unique `release_id`; every
  `release_type` in the `studio`/`live`/`compilation`/`single` vocabulary;
  non-blank `title` and `source_url`; `release_date` blank or a recognized
  year, year-month, or full ISO date; unique positive
  `(release_id, track_number)`; non-negative durations; non-blank `track_title`;
  every `song_id` present in `songs.csv` and every `performance_id` present in
  `performances.csv`; unique `release_personnel` keys with a non-blank
  instrument and a `people.csv` person; CSV headers unchanged.
- `deadbot.postgres_import.read_canonical_table` converts all three tables with
  the importer's `TableSpec`s: 340 releases, 10,492 tracks, 205 personnel rows.
- `python -m pytest`: 272 passed, 1 failed. The failure,
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
8. **`source_key`/`source_record_id` provenance columns.** `shows.csv`,
   `performances.csv` and `show_performers.csv` carry real provenance columns
   (see `scripts/add_provenance_columns.py`); `official_releases.csv` and
   `official_release_tracks.csv` still rely on matching a marker substring in
   the free-text `notes` column (`owns_row` above) to tell the live and studio
   passes' rows apart. That has worked so far, but it is a weaker mechanism
   than a real column and is worth migrating to the same provenance pattern.
