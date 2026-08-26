# 1970–1971 collection status

Updated 2026-08-25.

This pass followed `docs/collection-methodology.md`: pinned `gdshowsdb`
snapshots were preserved as raw source records, then normalized into the
shared show, venue, song, and ordered-performance graph. Song-source
collection preserved compact Dead.net and MusicBrainz metadata only; lyric
text and audio were not copied.

## Coverage

| Area | 1970 | 1971 | Primary source |
| --- | ---: | ---: | --- |
| Shows | 145 | 81 | gdshowsdb |
| Ordered performances | 2,078 | 1,793 | gdshowsdb |
| Song labels | 123 | 89 | gdshowsdb |
| Venue instances | 67 | 50 | gdshowsdb |
| Dead.net song records | 123 | 89 | Dead.net |
| Dead.net pages resolved | 73 | 60 | Dead.net |
| Dead.net records with credits | 70 | 57 | Dead.net |
| Dead.net records with lyric content | 70 | 57 | Dead.net |
| MusicBrainz work records | 123 | 89 | MusicBrainz |
| MusicBrainz HTTP-success responses | 117 | 87 | MusicBrainz |
| MusicBrainz exact-title candidates | 104 | 77 | MusicBrainz |

The raw show snapshots are:

- `data/raw/shows/gdshowsdb-1970.jsonl` — blob
  `69e4795b435a96ff441a5cea0273c4cdbb7ab0d7`
- `data/raw/shows/gdshowsdb-1971.jsonl` — blob
  `90b6fe5895ea8e909f204791d50c62e2b8c5f4a8`

The 1970 and 1971 song-source records are in
`data/raw/songs/deadnet-song-credits-{1970,1971}.jsonl` and
`data/raw/songs/musicbrainz-song-works-{1970,1971}.jsonl`.

## Validation and boundaries

The merged canonical graph contains 312 shows, 6,100 ordered performances,
174 song labels, and 152 venues. The merged song layer has 133 songs with
promoted canonical credits, 101 resolved Dead.net pages, and 97 linked lyric
pages. IDs are unique, and all performance → show,
performance → song, and show → venue foreign-key checks passed.

MusicBrainz title searches are retained as source evidence. Exact-title
matches were promoted only under the existing conservative normalization
rules; ambiguous, traditional, instrumental, and unresolved cases remain
unpromoted. Network errors remain represented in the raw records rather than
being interpreted as source absence.

The broader recording pass now includes metadata-only Internet Archive
inventories and representative item metadata for 1970–1971. It adds 442
performance-recording links across those years, retaining source track titles
and durations where the ordered alignment was high confidence. Playback start
timestamps, lineups, and cross-source show review remain separate fact types.
