# 1972 collection status

Updated 2026-08-25.

The repeatable collection workflow and lessons from this pass are documented
in `docs/collection-methodology.md`.

## What is now collected

The pinned `gdshowsdb` 1972 source is preserved at
`data/raw/shows/gdshowsdb-1972.jsonl` and has been normalized into the
canonical show/performance layer:

| Area | Coverage | Primary source | Notes |
| --- | ---: | --- | --- |
| Shows | 86 / 86 | gdshowsdb | One record per source date; no duplicate dates in the baseline |
| Venue instances | 51 | gdshowsdb | 50 distinct source venue strings; same venue name can occur in multiple cities |
| Song labels | 80 | gdshowsdb | Source labels normalized to stable song IDs |
| Song lyric/credit pages | 51 lyric pages / 54 song pages | Dead.net | External links and concise page metadata retained; full lyric text is not stored |
| Song composition credits | 62 / 80 | MusicBrainz + Dead.net | Role-level credits normalized where the title/source match is strong |
| Song source links | 148 resources / 158 typed links | Dead.net + MusicBrainz | 1972 slice; shared canonical files also contain 1970–1971 song evidence |
| Ordered performances | 2,229 / 2,229 | gdshowsdb | Set number, position, and segue flag retained |
| Recording index rows | 362 | Internet Archive | Metadata-only item index; all 86 canonical shows have at least one indexed item |
| Full recording metadata | 86 | Internet Archive | One representative item per canonical show; raw metadata is preserved |
| Performance-recording links | 875 | Internet Archive + curated Veneta mapping | Source track title/order aligned to the canonical setlist; durations are metadata-only |
| Source-reviewed performer assignments | 938 | JerryBase | 86 / 86 canonical shows; 927 performers and 11 guest role/instrument rows |

The bulk normalization is reproducible with
`scripts/normalize_gdshowsdb_1972.py`. The complete Internet Archive search
index is preserved at `data/raw/recordings/internet-archive-1972-search-all.jsonl`
and is normalized by `scripts/normalize_internet_archive_1972_index.py`.

## What was already present before this pass

The Veneta vertical slice remains the enriched part of the dataset:

- 1 show, 20 performances, 1 venue, 7 people, and 10 show-performer role rows.
- 1 fully described recording with 20 performance-recording mappings.
- 1 official release with 21 release tracks, including the intro.
- 22 contextual resources, with typed song/show/performance links.
- 1 full-show YouTube link, 1 performance-specific YouTube link, and 1 source-specific Sugaree chord arrangement.

Existing Veneta IDs and enriched notes were retained during normalization.

## Remaining gaps

These are real coverage gaps, not inferred missing facts:

1. **Recording detail:** 276 of 362 canonical recording rows remain search-index records. One representative item per show has full item metadata; the remaining indexed items still need selective enrichment.
2. **Performance-recording links:** 875 links now connect source tracks to canonical performances. The remaining performances have no accepted track mapping, and the links do not claim playback start timestamps.
3. **Lineups:** the 1972 performer pass covers all 86 canonical shows from JerryBase, including five shows with named guests. The same collector now covers 2,268 of 2,358 canonical shows across 1965–1995; 90 held dates remain listed in coverage reports. The source supplies musical roles and instrument strings, but not a complete per-show guitar-model history; named instruments are retained when a source explicitly supplies them.
4. **Song-source gaps:** 26 songs still lack a resolved Dead.net song page in this pass; 18 songs have no canonical credit rows, and ambiguous title/source matches remain explicitly held for review.
5. **Lyric-source scope:** 51 songs have external lyric-page links. The remaining songs are instrumentals, jams, unresolved pages, or otherwise need a better source match; no full lyrics are copied into the knowledge base.
6. **Show review:** JerryBase review data exists only for 1972-08-27. The remaining 85 shows need low-volume review or conflict checks before treating venue/setlist values as cross-source reconciled.
7. **Resources and media:** contextual resources, official-release mappings, and performance-specific media are concentrated on Veneta. The new song-page links are a metadata/source-link pass, not a full song-history or lyrics-text pass.
8. **Source reconciliation:** the Internet Archive index contains two dates absent from gdshowsdb (1972-01-01 and 1972-03-01). They remain outside the canonical show set until independently reviewed.
9. **Venue enrichment:** coordinates and richer location history are still blank.

Track-level mapping decisions are reproducible with
`scripts/normalize_internet_archive_tracks.py`; held cases remain in the raw
review JSONL. Do not infer performers, songwriting credits, or playback start
timestamps from the recording index alone.
