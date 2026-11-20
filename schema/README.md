# Schema

`sqlite.sql` is the one definition of the catalog: its tables, indexes,
integrity triggers and the views the `look_up` tool reads. It uses stable text
identifiers so database keys match the reviewable CSV files directly. Every
file in `data/canonical` has a same-named table whose columns match the CSV
header; the builder does not invent database-only values for those tables.

`deadbot/sqlite_build.py` executes this file into a new SQLite database on
every deploy and on a local run whenever the inputs change, then loads the
CSVs into it. There are no migrations: a schema change is an edit to
`sqlite.sql`, and the next build produces a database in the new shape.
`deadbot_schema_metadata` records the builder's `SQLITE_SCHEMA_VERSION`, the
build time, and the input fingerprint: a digest of every CSV, the
selection-evidence file and `sqlite.sql` itself. A local run compares that
fingerprint with the checked-out inputs and rebuilds when anything changed,
this file included.

## Notes on particular tables

`official_releases` constrains `release_type` to `studio`, `live`,
`compilation` or `single`, and `official_release_tracks` carries a nullable
`song_id` so a track can name its composition. A live track identifies a
performance; a studio track has no performance, because a performance is a
song played at a show. A track may carry both, one, or neither — an intro,
tuning or banter segment carries neither. `release_personnel` records one row
per person's role-and-instrument credit on a release, shaped like
`show_performers`.

`official_releases.release_date` is text. MusicBrainz sometimes knows only a
year (`"1972"`) or a year-month (`"1972-05"`) for a release; the column stores
exactly what is known, at whatever precision that is. ISO 8601 date strings of
mixed precision still sort and compare correctly as plain text.

`band_memberships` holds one row per person's role and tenure in a named act
(`grateful-dead` for now), so "who was the keyboardist in 1978" or "when did
Brent join" does not require scanning all of `show_performers`. `act` is a
stable text identifier, not a foreign key, because the catalog does not yet
model bands as entities in their own right. A non-contiguous tenure (Mickey
Hart leaving in 1971 and rejoining in 1975) carries one row per contiguous
span.

`performance_performers` holds one row per person's role-and-instrument credit
on one performance, shaped like `show_performers`. `show_performers` says who
was onstage at a show; this table says which songs they played on, when a
source pins it down. It is sparse by design. A guest with a show-level credit
and no rows here is known at the show level only. See
`docs/collection-status-guest-song-credits.md`.

`selection_lists`, `selection_entries` and `selection_evidence` hold curator,
critic and dated fan-choice signals. They have no CSV: the builder fills them
from `data/editorial/selection-evidence-review.json`, and adds each list's
source to `resources`.

## Load order

The builder loads the canonical files in the order of `TABLE_SPECS` in
`deadbot/canonical_import.py`:

1. `people.csv`
2. `band_memberships.csv`
3. `songs.csv`
4. `venues.csv`
5. `equipment.csv`
6. `shows.csv`
7. `song_writers.csv`
8. `resources.csv`
9. `resource_songs.csv`
10. `resource_shows.csv`
11. `show_performers.csv`
12. `performances.csv`
13. `performance_performers.csv`
14. `resource_performances.csv`
15. `show_links.csv`
16. `performance_links.csv`
17. `official_releases.csv`
18. `official_release_tracks.csv`
19. `release_personnel.csv`
20. `song_arrangements.csv`
21. `arrangement_chord_sections.csv`
22. `recordings.csv`
23. `performance_recordings.csv`
24. `show_equipment.csv`

The builder validates CSV formatting, required values, dates, numbers and
booleans before it opens the database. SQLite's `CHECK` constraints and
triggers then guard every insert (a performance is mapped only to a recording
of the same show, for one), and one foreign-key check after loading reports
every broken reference. CSV empty fields become SQL `NULL` only for nullable
columns. Booleans are stored as the CSV's `true`/`false` text and dates as ISO
text.

This is the order for loading already-generated CSVs. Regenerating
`official_release_tracks.csv` itself from raw sources has a separate, earlier
ordering that this list does not cover: run
`scripts/normalize_musicbrainz_live_releases.py`, then
`scripts/normalize_musicbrainz_studio_releases.py`, then
`scripts/normalize_release_track_songs.py` last. The live normalizer rewrites
every row it owns from raw data on each run and never sets `song_id` itself, so
if it runs after the song_id backfill, the backfilled column is silently wiped
back to blank on every live track. The round trip is exact — rerunning the
backfill restores the same values — so no data is lost, but the ordering is a
real dependency, not a suggestion. See
`docs/collection-status-studio-releases.md` for the counts this affects.
