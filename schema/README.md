# Schema

`postgres.sql` defines the operational PostgreSQL representation of the canonical CSV model. It uses stable text identifiers so database keys match the reviewable files directly. Every file currently in `data/canonical` has a same-named table whose columns match the CSV header; the importer does not need to invent database-only values for those tables.

`deadbot_schema_metadata` records the installed schema version. The importer
bootstraps an empty database, applies the checked-in forward migrations it
understands, and fails clearly for a partial or newer schema. Schema changes
require an explicit migration or a deliberate rebuild; table existence alone is
never treated as proof that the database shape is current.

Schema version 3 adds `source_registry`, a reviewed acquisition contract with
host and operation allowlists plus authority, access, rights, review,
retention, rate, and adapter-version policy. `source_snapshots` records each
normalized URL retrieval (including blocked or failed attempts) with status,
timestamp, content hash, metadata, and adapter version. Snapshots are
append-only evidence and do not grant network access; adapters must enforce the
registry contract before performing an operation.

Each successful canonical import first creates a content-addressed snapshot
manifest in `canonical_snapshots`. Its stable `sha256:...` ID identifies the
exact CSV bytes and validated row count for every imported canonical file.
`canonical_imports` is an append-only import ledger with table-level row
results and an explicit mode: `bootstrap`, `rebuild`, or non-destructive
`merge`. Only bootstrap and rebuild operations represent clean projection
events; a merge deliberately does not claim that the operational data exactly
matches the named snapshot.

Schema version 5 adds studio albums to the release catalog. `official_releases`
now constrains `release_type` to `studio`, `live`, `compilation` or `single`,
and `official_release_tracks` carries a nullable `song_id` so a track can name
its composition. A live track identifies a performance; a studio track has no
performance, because a performance is a song played at a show. A track may
carry both, one, or neither — an intro, tuning or banter segment carries
neither. `release_personnel` records one row per person's role-and-instrument
credit on a release, shaped like `show_performers`.

Schema version 6 widens `official_releases.release_date` from `DATE` to
`TEXT`. MusicBrainz sometimes knows only a year (`"1972"`) or a year-month
(`"1972-05"`) for a release, which a SQL date column cannot hold without
inventing a day; `release_date` now stores exactly what is known, at whatever
precision that is. ISO 8601 date strings of mixed precision still sort and
compare correctly as plain text, so nothing else about the column changes.

Schema version 9 adds `band_memberships`: one row per person's role and
tenure in a named act (`grateful-dead` for this pass), so "who was the
keyboardist in 1978" or "when did Brent join" no longer requires scanning all
of `show_performers`. `act` is a stable text identifier, not a foreign key,
because the catalog does not yet model bands as entities in their own right.
A non-contiguous tenure (Mickey Hart leaving in 1971 and rejoining in 1975)
carries one row per contiguous span. `end_date` is nullable so a currently
active tenure in a future act need not invent an end, but every row from this
pass carries an explicit end date rather than leaving it blank.

Load canonical files in foreign-key dependency order:

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
13. `resource_performances.csv`
14. `show_links.csv`
15. `performance_links.csv`
16. `official_releases.csv`
17. `official_release_tracks.csv`
18. `release_personnel.csv`
19. `song_arrangements.csv`
20. `arrangement_chord_sections.csv`
21. `recordings.csv`
22. `performance_recordings.csv`
23. `show_equipment.csv`

`performance_recordings` is checked to ensure a performance is mapped only to
a recording of the same show. The importer validates CSV formatting, required
values, dates, numbers, and booleans before opening the transaction; PostgreSQL
then enforces ranges, uniqueness, foreign keys, and cross-show rules before
commit. CSV empty fields become SQL `NULL` only for nullable columns.

This is the load order for importing already-generated CSVs into PostgreSQL.
Regenerating `official_release_tracks.csv` itself from raw sources has a
separate, earlier ordering that this list does not cover: run
`scripts/normalize_musicbrainz_live_releases.py`, then
`scripts/normalize_musicbrainz_studio_releases.py`, then
`scripts/normalize_release_track_songs.py` last. The live normalizer rewrites
every row it owns from raw data on each run and never sets `song_id` itself, so
if it runs after the song_id backfill, the backfilled column is silently wiped
back to blank on every live track. The round trip is exact — rerunning the
backfill restores the same values — so no data is lost, but the ordering is a
real dependency, not a suggestion. See
`docs/collection-status-studio-releases.md` for the counts this affects.

## Enrichment and observations

The schema also provides normalized operational tables for the next collection layers. They do not yet have canonical CSV files:

- `release_shows` records whether a release covers a show completely, partially, or only through represented performances.
- `official_release_track_performances` maps multiple ordered performance segments to one release track and allows one performance to span tracks. Load `release_shows` before these mappings so the coverage guard can validate each performance's show.
- `selection_lists` and `selection_entries` retain curator, critic, and dated fan-choice signals independently. Each list must point to the source `resource` that supports it.
- `claims` and `claim_entities` keep attributed prose assertions separate from canonical facts and attach each claim to typed, foreign-key-checked entities.
- `derived_observations`, `observation_entities`, and `observation_resources` store versioned structured calculation results, their coverage boundary, supporting entities, and sources. They do not store the final model-written response.

Load these in parent-first order: release/show rows before release track segments; selection lists before entries; claims before claim entities; and derived observations before their entity and resource relationships. When an observation supersedes an older observation, insert older versions first and clear their `is_current` flag before marking the replacement current.

`calculation_version` identifies the algorithm, while `input_revision` is a
foreign-keyed canonical snapshot ID. Recomputing after either changes creates a
new observation version; the partial unique index permits only one current row
for an `observation_key`. The v1 → v2 migration keeps historical observation
rows valid while requiring a known snapshot for every newly written row.

References from these enrichment tables back to canonical entities are deferred until transaction commit. A canonical rebuild can therefore delete and restore the same stable IDs without cascading away curated evidence. If an import actually drops or changes a referenced ID, commit fails instead of silently deleting the enrichment relationship.
