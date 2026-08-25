# Schema

`postgres.sql` defines the operational PostgreSQL representation of the canonical CSV model. It uses stable text identifiers so database keys match the reviewable files directly.

Load canonical files in foreign-key dependency order:

1. `people.csv`
2. `songs.csv`
3. `venues.csv`
4. `shows.csv`
5. `song_writers.csv`
6. `show_performers.csv`
7. `performances.csv`
8. `show_links.csv`
9. `performance_links.csv`
10. `official_releases.csv`
11. `official_release_tracks.csv`
12. `resources.csv`
13. `resource_songs.csv`
14. `resource_shows.csv`
15. `resource_performances.csv`
16. `song_arrangements.csv`
17. `arrangement_chord_sections.csv`
18. `recordings.csv`
19. `performance_recordings.csv`

The final table is also checked to ensure a performance is mapped only to a recording of the same show. A future importer should validate CSV formatting, required values, date formats, booleans, ranges, and cross-file IDs before loading.
