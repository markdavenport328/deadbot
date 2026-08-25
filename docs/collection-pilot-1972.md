# 1972 collection pilot

## Scope

1972 is the first bounded collection year. The pilot begins with a deliberately small test of the source-to-raw layer, using one representative event and one representative recording source. It is not a bulk scrape and it creates no canonical records yet.

## Collected raw records

- `data/raw/shows/jerrybase-1972-08-27.jsonl` preserves a JerryBase event record for 27 August 1972.
- `data/raw/recordings/internet-archive-1972-search.jsonl` preserves a 1972 Internet Archive search response (five returned records from a result set of 364).
- `data/raw/recordings/internet-archive-gd1972-08-27-4682.jsonl` preserves Internet Archive item metadata for one 27 August 1972 recording source.
- `data/raw/shows/gdshowsdb-1972.jsonl` preserves the complete, unparsed `gdshowsdb` 1972 YAML response, pinned to GitHub blob `1e87342c36d49e8c5818a1d22060442cad8e329f`.

No audio, binaries, or HTML snapshots were added. The sampled 27 August event was normalized separately; the bulk gdshowsdb capture adds raw source data only.

The pinned gdshowsdb source contains 86 show records, 2,229 ordered song occurrences, 80 distinct source song labels, and 51 distinct source venue strings. These are source-level counts, not yet-reconciled canonical counts.

## What the pilot establishes

JerryBase is provisionally the 1972 source of record for show date, venue, set order, and performers. Internet Archive item metadata is provisionally the source of record for recording identifiers, lineage, taper/transfer values, and source-supplied track descriptions.

The two raw records agree on the date and venue name for the sampled event. They retain source-specific title and setlist notation rather than attempting to normalize it in the raw layer.

## Next gated step

The sampled event has now been normalized end-to-end. The next collection step is to preserve gdshowsdb's committed 1972 year file as raw data, pinned to its GitHub blob SHA. It is the licensed bulk baseline for shows and performances; JerryBase remains a review source rather than an automated bulk target.
