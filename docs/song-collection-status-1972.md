# 1972 song collection status

Updated 2026-08-25.

The 1972 set contains 80 canonical song labels drawn from the normalized
gdshowsdb show baseline. This pass added two source layers:

- Dead.net song pages: 54 of 80 pages resolved; 51 expose lyric-page content
  and 52 expose credit fields. The canonical graph stores external page links,
  page availability, and concise source notes. It does not store full lyric
  text.
- MusicBrainz work search: 80 compact query records preserved; 60 responses
  were available, with 52 exact-title matches. Strong exact matches and a
  small set of high-confidence Dead.net fallbacks produced 59 songs with
  canonical role-level credit rows.

## Canonical outputs

- `data/canonical/songs.csv`: all 80 songs, with source-link and gap notes.
- `data/canonical/song_writers.csv`: role-level `lyrics`, `music`, and
  `writer` rows where source matching was strong.
- `data/canonical/people.csv`: people introduced by the accepted credit rows.
- `data/canonical/resources.csv` and `data/canonical/resource_songs.csv`:
  external Dead.net song-page resources and typed lyric/credit relationships.
- `data/raw/songs/deadnet-song-credits-1972.jsonl`: compact page/credit/
  availability records; no page body or lyric text.
- `data/raw/songs/musicbrainz-song-works-1972.jsonl`: compact work-search
  records with stable source identifiers and credit relations.

## Remaining song gaps

Twenty-six titles did not resolve to a Dead.net song page in this run. Twenty-
one songs have no canonical credit rows because the available evidence was
missing, traditional, instrumental, or too ambiguous to promote. Four cases
are explicitly held for review: `Caution`, `Mind Left Body Jam`, `Nobody's
Fault But Mine`, and `Space`.

The next useful batch is targeted source review for those 26 page gaps and 21
credit gaps, followed by original-artist and first/last-known-performance
fields. Lyric text should remain an external, attributed source link rather
than a copied repository field.
