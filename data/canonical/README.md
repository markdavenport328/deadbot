# Canonical data

These CSV files hold normalized Deadbot entities and relationships. They are initially Git-tracked, reviewable source material from which PostgreSQL can be reconstructed.

Stable IDs are important: use lowercase kebab-case identifiers and do not replace an established ID merely because a display name changes. During normalization, external spelling variants and source identifiers should be matched to a canonical entity rather than copied as new entities.

Canonical edits should ideally be produced by a documented normalization process. A carefully documented manual correction is acceptable when necessary. In either case, preserve the reason and source evidence as the project grows.

Provenance will become increasingly important as multiple Dead datasets are reconciled. We will likely add provenance tables or columns once conflicting source assertions need to be represented explicitly.

Files began header-only. Canonical rows are added only after a documented normalization pass; they do not contain fabricated records.

For `show_performers.csv`, enter one row per person's role-and-instrument assignment at a show. A performer with multiple instruments or vocal duties therefore has multiple rows with the same show and person IDs.

Resources are generic, source-specific references. `resources.csv` holds a link and descriptive metadata; `resource_songs.csv`, `resource_shows.csv`, and `resource_performances.csv` attach it to the entities it addresses. This lets a future model find interviews, reviews, lessons, tabs, and videos for a song, show, or performance before opening the original link. `song_arrangements.csv` records the version, key, and scope that a music resource describes; `arrangement_chord_sections.csv` records its chord progression by section. Do not treat a chart for one recording or transposition as an authoritative chart for every performance.
