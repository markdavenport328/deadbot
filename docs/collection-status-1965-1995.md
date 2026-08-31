# Full show and setlist baseline status

Updated 2026-08-26.

The complete `gdshowsdb` year range represented by this project is now
preserved under `data/raw/shows/gdshowsdb-<year>.jsonl` and normalized into the
canonical CSV knowledge graph. Each raw record retains the GitHub blob SHA,
retrieval timestamp, source URL, and original base64-encoded YAML response.

## Coverage

“Shows with setlist” counts shows for which the source supplied at least one
song performance. Early-year source coverage is visibly partial; those shows
remain in the graph with zero performances rather than being dropped.

| Year | Shows | Shows with setlist | Performances | Song labels |
| ---: | ---: | ---: | ---: | ---: |
| 1965 | 12 | 2 | 2 | 2 |
| 1966 | 113 | 32 | 228 | 68 |
| 1967 | 139 | 41 | 201 | 38 |
| 1968 | 126 | 69 | 529 | 32 |
| 1969 | 149 | 124 | 1,527 | 78 |
| 1970 | 145 | 135 | 2,078 | 123 |
| 1971 | 81 | 80 | 1,793 | 89 |
| 1972 | 86 | 86 | 2,229 | 80 |
| 1973 | 72 | 72 | 1,884 | 80 |
| 1974 | 40 | 40 | 1,059 | 81 |
| 1975 | 4 | 4 | 54 | 28 |
| 1976 | 41 | 41 | 941 | 67 |
| 1977 | 60 | 60 | 1,233 | 81 |
| 1978 | 81 | 81 | 1,584 | 84 |
| 1979 | 75 | 75 | 1,597 | 93 |
| 1980 | 87 | 87 | 2,103 | 107 |
| 1981 | 83 | 83 | 1,841 | 109 |
| 1982 | 61 | 61 | 1,312 | 108 |
| 1983 | 66 | 66 | 1,357 | 112 |
| 1984 | 64 | 64 | 1,281 | 124 |
| 1985 | 71 | 71 | 1,402 | 132 |
| 1986 | 46 | 46 | 879 | 126 |
| 1987 | 85 | 85 | 1,693 | 128 |
| 1988 | 80 | 80 | 1,563 | 131 |
| 1989 | 73 | 73 | 1,449 | 137 |
| 1990 | 74 | 74 | 1,489 | 143 |
| 1991 | 77 | 77 | 1,463 | 138 |
| 1992 | 55 | 55 | 1,011 | 134 |
| 1993 | 81 | 81 | 1,544 | 146 |
| 1994 | 84 | 84 | 1,584 | 151 |
| 1995 | 47 | 47 | 864 | 149 |
| **Total** | **2,358** | **2,156** | **39,774** | **436** |

## Normalization safeguards

The year normalizer preserves same-day source sequences in stable show IDs
while storing a valid ISO calendar date. Null venue, city, state, and country
values become explicit blanks. Empty-set source records remain as shows with
an explanatory note and no fabricated performances.

The resulting graph has unique IDs and complete performance → show,
performance → song, and show → venue relationships. Lineups, performance
timestamps, and source-reviewed corrections remain separate enrichment work;
performer enrichment is summarized below.

## Performer enrichment

JerryBase performer snapshots now cover all 31 canonical years. They contain
2,268 of 2,358 canonical shows, yielding 26,265 normalized show-performer
assignments across 276 people: 25,725 performer rows and 540 guest rows. Exact
source instrument strings are retained in raw JSONL and assignment notes.

The remaining 90 shows are held in year-specific `.coverage.json` reports,
mostly because JerryBase omits an event date, uses an approximate date, or
does not expose a unique event page. They are not represented as covered
lineups.

## Recording metadata enrichment

The metadata-only Internet Archive pass preserved 18,325 unique recording
index items across the 31 years. 17,977 items were linked to 1,910 canonical
shows; 136 dates had no canonical show match and 27 dates were intentionally
held because the source date corresponded to multiple same-day shows.

One representative item per linked show was then retrieved through the Archive
metadata endpoint. All 1,910 representative requests returned metadata, and
the canonical recording rows now include source type, source description,
taper, transferer, lineage where supplied, and Archive links. Full item
payloads remain in year-specific raw JSONL files; audio and binaries were not
downloaded.

The representative file metadata also supports 16,487 new
performance-recording links, for 16,507 total canonical links including the
20 previously curated Veneta links. Each accepted link retains the source
track title and metadata duration. No playback timestamps were inferred.
Another 895 representatives were held in
`data/raw/recordings/internet-archive-track-mapping-review.jsonl` because the
track sequence was incomplete, contradictory, ambiguous, untitled, or had no
canonical setlist match.
