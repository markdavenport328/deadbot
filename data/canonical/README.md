# Canonical data

These CSV files hold normalized Deadbot entities and relationships. They are initially Git-tracked, reviewable source material from which PostgreSQL can be reconstructed.

Stable IDs are important: use lowercase kebab-case identifiers and do not replace an established ID merely because a display name changes. During normalization, external spelling variants and source identifiers should be matched to a canonical entity rather than copied as new entities.

Canonical edits should ideally be produced by a documented normalization process. A carefully documented manual correction is acceptable when necessary. In either case, preserve the reason and source evidence as the project grows.

For collection and normalization work, follow `docs/collection-methodology.md`.
In particular, do not promote a failed request, unresolved title match, or
source-specific display value without recording the decision and evidence.

Provenance will become increasingly important as multiple Dead datasets are reconciled. We will likely add provenance tables or columns once conflicting source assertions need to be represented explicitly.

`shows.csv`, `performances.csv`, and `show_performers.csv` each end with two
structured provenance columns, `source_key` and `source_record_id`, added by
`scripts/add_provenance_columns.py`. `source_key` names the source system
(`gdshowsdb`, `jerrybase`, or `manual`) and `source_record_id` is that
source's stable identifier for the row (a gdshowsdb show or song UUID, or a
JerryBase event id). These are derived, not hand-entered: the script parses
them deterministically from the same prose citation that has always lived in
`notes` / `performance_notes`, so that citation remains the source of truth
and continues to carry any additional detail (blob hashes, snapshot
filenames, instrument lists) the structured columns don't capture. Re-running
the script recomputes both columns from scratch; it never trusts a prior run.

The convention is fail-closed: a row whose `notes` doesn't match a known
citation format gets an empty `source_key` and `source_record_id` rather than
a guessed value, and the script's report lists every such row so it can be
reviewed instead of silently passing. `source_key = "manual"` is reserved for
rows confirmed by inspection to be hand-curated with no machine-parseable
citation (currently the 20 original Veneta, `gd-1972-08-27`, performances,
which predate the citation convention and have an empty `performance_notes`)
— it is never used as a default for an unparseable row.

Files began header-only. Canonical rows are added only after a documented normalization pass; they do not contain fabricated records.

For `show_performers.csv`, enter one row per person's role-and-instrument assignment at a show. A performer with multiple instruments or vocal duties therefore has multiple rows with the same show and person IDs.

Resources are generic, source-specific references. `resources.csv` holds a link and descriptive metadata; `resource_songs.csv`, `resource_shows.csv`, and `resource_performances.csv` attach it to the entities it addresses. This lets a future model find interviews, reviews, lessons, tabs, and videos for a song, show, or performance before opening the original link. `song_arrangements.csv` records the version, key, and scope that a music resource describes; `arrangement_chord_sections.csv` records its chord progression by section. Do not treat a chart for one recording or transposition as an authoritative chart for every performance.

Lyrics and other protected works follow the same resource boundary: canonical
data may retain a source URL, availability flags, attribution, and scope notes,
but not full lyric text, complete tabs, transcriptions, audio, or video.
