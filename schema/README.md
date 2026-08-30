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

Load canonical files in foreign-key dependency order:

1. `people.csv`
2. `songs.csv`
3. `venues.csv`
4. `equipment.csv`
5. `shows.csv`
6. `song_writers.csv`
7. `resources.csv`
8. `resource_songs.csv`
9. `resource_shows.csv`
10. `show_performers.csv`
11. `performances.csv`
12. `resource_performances.csv`
13. `show_links.csv`
14. `performance_links.csv`
15. `official_releases.csv`
16. `official_release_tracks.csv`
17. `song_arrangements.csv`
18. `arrangement_chord_sections.csv`
19. `recordings.csv`
20. `performance_recordings.csv`
21. `show_equipment.csv`

`performance_recordings` is checked to ensure a performance is mapped only to
a recording of the same show. The importer validates CSV formatting, required
values, dates, numbers, and booleans before opening the transaction; PostgreSQL
then enforces ranges, uniqueness, foreign keys, and cross-show rules before
commit. CSV empty fields become SQL `NULL` only for nullable columns.

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
