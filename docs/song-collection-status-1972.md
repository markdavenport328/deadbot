# 1972 song collection status

Updated 2026-08-25.

The 1972 set contains 80 canonical song labels drawn from the normalized
gdshowsdb show baseline. This pass added two source layers:

- Dead.net song pages: 54 of 80 pages resolved; 51 expose lyric-page content
  and 52 expose credit fields. The canonical graph stores external page links,
  page availability, and concise source notes. It does not store full lyric
  text.
- MusicBrainz work search: 80 compact query records preserved in the original
  1972 pass. The later 1970–1971 pass added overlapping source evidence; the
  shared canonical 1972 slice now has 62 songs with canonical role-level
  credit rows.

## Canonical outputs

- `data/canonical/songs.csv`: the shared graph's 174 songs, including the 80
  labels performed in 1972, with source-link and gap notes.
- `data/canonical/song_writers.csv`: role-level `lyrics`, `music`, and
  `writer` rows where source matching was strong.
- `data/canonical/people.csv`: people introduced by the accepted credit rows.
- `data/canonical/resources.csv` and `data/canonical/resource_songs.csv`:
  external Dead.net song-page resources and typed lyric/credit relationships,
  including one MusicBrainz work-search resource per title.
- `data/raw/songs/deadnet-song-credits-1972.jsonl`: compact page/credit/
  availability records; no page body or lyric text.
- `data/raw/songs/musicbrainz-song-works-1972.jsonl`: compact work-search
  records with stable source identifiers and credit relations.

The 1972 song slice currently links 148 resources through 158 typed
song-resource links. The shared canonical song layer contains 293 resources
and 299 typed links across 1970–1972. The app can link both lyric pages and
composition-credit searches; it does not display full lyric text.

## Remaining song gaps

Twenty-six titles did not resolve to a Dead.net song page in this run. Eighteen
songs have no canonical credit rows because the available evidence was
missing, traditional, instrumental, or too ambiguous to promote. Ambiguous
title/source matches remain held for review.

The next useful batch is targeted source review for those 26 page gaps and 18
credit gaps, followed by original-artist and first/last-known-performance
fields. Lyric text should remain an external, attributed source link rather
than a copied repository field.
