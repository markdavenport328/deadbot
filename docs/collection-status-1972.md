# 1972 collection status

Updated 2026-08-25.

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
| Song composition credits | 59 / 80 | MusicBrainz + Dead.net | Role-level credits normalized where the title/source match is strong |
| Ordered performances | 2,229 / 2,229 | gdshowsdb | Set number, position, and segue flag retained |
| Recording index rows | 362 | Internet Archive | Metadata-only item index; all 86 canonical shows have at least one indexed item |
| Full recording metadata | 86 | Internet Archive | One representative item per canonical show; raw metadata is preserved |

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

1. **Recording detail:** 276 of 362 canonical recording rows remain search-index records. One representative item per show now has full item metadata; the remaining indexed items still need selective enrichment.
2. **Performance-recording links:** only Veneta's 20 performances are mapped to recording tracks. The other 2,209 performances have no track/timestamp mapping.
3. **Lineups:** performer assignments exist only for Veneta. The 85 other shows need source-reviewed band and guest rows; gdshowsdb does not provide them.
4. **Song-source gaps:** 26 songs still lack a resolved Dead.net song page in this pass; 21 songs have no canonical credit rows, and four title/source matches remain explicitly held for review (Caution, Mind Left Body Jam, Nobody's Fault But Mine, and Space).
5. **Lyric-source scope:** 51 songs have external lyric-page links. The remaining songs are instrumentals, jams, unresolved pages, or otherwise need a better source match; no full lyrics are copied into the knowledge base.
6. **Show review:** JerryBase review data exists only for 1972-08-27. The remaining 85 shows need low-volume review or conflict checks before treating venue/setlist values as cross-source reconciled.
7. **Resources and media:** contextual resources, official-release mappings, and performance-specific media are concentrated on Veneta. The new song-page links are a metadata/source-link pass, not a full song-history or lyrics-text pass.
8. **Source reconciliation:** the Internet Archive index contains two dates absent from gdshowsdb (1972-01-01 and 1972-03-01). They remain outside the canonical show set until independently reviewed.
9. **Venue enrichment:** coordinates and richer location history are still blank.

The next safe collection batch is to reconcile the 86 preserved representative
item descriptions to canonical performances, adding track-level mappings only
where the source description and set order agree. Do not infer performers,
songwriting credits, or performance timestamps from the recording index alone.
