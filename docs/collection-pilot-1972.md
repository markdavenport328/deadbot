# 1972 collection pilot

## Scope

1972 is the first bounded collection year. It began with a deliberately small
test of the source-to-raw layer, using one representative event and one
representative recording source, and then expanded through reviewable bulk and
enrichment passes. The repeatable workflow is documented in
`docs/collection-methodology.md`.

## Collected raw records

- `data/raw/shows/jerrybase-1972-08-27.jsonl` preserves a JerryBase event record for 27 August 1972.
- `data/raw/recordings/internet-archive-1972-search.jsonl` preserves a 1972 Internet Archive search response (five returned records from a result set of 364).
- `data/raw/recordings/internet-archive-gd1972-08-27-4682.jsonl` preserves Internet Archive item metadata for one 27 August 1972 recording source.
- `data/raw/recordings/internet-archive-1972-search-all.jsonl` preserves the complete 364-item Internet Archive metadata index for 1972.
- `data/raw/shows/gdshowsdb-1972.jsonl` preserves the complete, unparsed `gdshowsdb` 1972 YAML response, pinned to GitHub blob `1e87342c36d49e8c5818a1d22060442cad8e329f`.
- `data/raw/songs/deadnet-song-credits-1972.jsonl` preserves compact Dead.net
  page status and displayed credit metadata for the 80-song set.
- `data/raw/songs/musicbrainz-song-works-1972.jsonl` preserves compact
  MusicBrainz work-search results and candidate credit relations for the same
  set.

No audio, binaries, full lyrics, or HTML snapshots were added. The sampled 27
August event was normalized separately; later passes normalized the bulk
gdshowsdb capture and selected song-source metadata into canonical data.

The pinned gdshowsdb source contains 86 show records, 2,229 ordered song occurrences, 80 distinct source song labels, and 50 distinct source venue strings (51 venue/name-city instances). These are source-level counts before canonical enrichment.

## What the pilot establishes

JerryBase is provisionally the 1972 source of record for show date, venue, set order, and performers. Internet Archive item metadata is provisionally the source of record for recording identifiers, lineage, taper/transfer values, and source-supplied track descriptions.

The two raw records agree on the date and venue name for the sampled event. They
retain source-specific title and setlist notation rather than attempting to
normalize it in the raw layer. The song pass demonstrated that title-only
catalog matches require context review: exact matches can refer to unrelated
works, so held candidates remain raw evidence rather than canonical credits.

## Current state and next gated step

The sampled event has been normalized end-to-end, and the pinned gdshowsdb year
file has now been normalized into 86 canonical shows and 2,229 performances.
The Internet Archive search index adds 362 recording rows across those shows,
and one full item-metadata record per show is preserved separately. JerryBase
remains a review source rather than an automated bulk target. See
`docs/collection-status-1972.md` for the remaining gaps and the next bounded
track-mapping batch.
