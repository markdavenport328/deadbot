# Future scripts

This directory reserves a deliberately small pipeline surface:

```text
collect/
    source-specific ingestion

normalize/
    entity matching
    stable ID creation
    cleanup and reconciliation

import/
    validation
    canonical CSV → PostgreSQL
```

Collectors preserve raw source records; normalizers make matching and
corrections reviewable; and importers should validate all canonical CSV
headers, data types, IDs, foreign keys, and cross-show recording mappings
before loading PostgreSQL.

## Year-baseline collector

`collect/fetch_gdshowsdb_year.py` retrieves one public, committed year file from the MIT-licensed `jefmsmit/gdshowsdb` repository through GitHub's Contents API and stores the unparsed API response as one JSONL raw record. It fetches metadata only, never audio, and refuses to overwrite an existing record without `--force`.

`normalize_gdshowsdb_1972.py` accepts a target year argument despite its
historical filename, for example `.venv/bin/python
scripts/normalize_gdshowsdb_1972.py 1970`. It retains canonical rows from
previous years while adding the selected year.

The song collectors accept the same year argument and derive their bounded
song set from the normalized performances. MusicBrainz collection checkpoints
each result in a partial JSONL file so an interrupted run can resume without
discarding completed lookups.

The full show/setlist baseline currently covers 1965–1995. See
`docs/collection-status-1965-1995.md` for year-level coverage and known
partial-setlist boundaries.

`collect/fetch_internet_archive_year.py` preserves year-level recording
indexes using month-bounded metadata queries. `collect/fetch_internet_archive_representatives.py`
selects one SBD/AUD-preferred item per canonical show for full metadata-only
enrichment; `normalize_internet_archive_1972_index.py` and
`normalize_internet_archive_1972_metadata.py` retain their historical names
but process all preserved years. `normalize_internet_archive_tracks.py` maps
only uniquely ordered source tracks to canonical performances and writes held
alignment decisions to a review JSONL; it does not infer playback start times
or download audio.

`collect/fetch_jerrybase_performers.py` collects source-reviewed musicians,
guests, and instrument strings for canonical Grateful Dead shows. Run it for a
year or use `--all` for 1965–1995; batch mode continues past held years and
writes a `.coverage.json` report when the source omits or ambiguously dates a
canonical show. Then run `normalize_jerrybase_performers.py` for the same year
or with `--all`. The normalizer preserves named instrument details supplied by
the source and holds uncertain or unidentified people out of canonical
assignments.

`collect/fetch_jerry_guitar_history.py` fetches the cited, photo/video-based
Jerry Garcia instrument-history source and materializes its explicit named
guitar claims into `equipment.csv` and `show_equipment.csv`. It records whether
each link comes from a date range or a specific-show claim and does not fill
uncovered dates by era-based inference.
