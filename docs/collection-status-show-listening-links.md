# Whole-show listening links status

Updated 2026-09-01.

Goal: give every canonical Grateful Dead show at least one resolvable
whole-show listening link so Deadbot can always hand a listener off to the
music. Before this pass `data/canonical/show_links.csv` held one row (the
Veneta YouTube upload). It now holds 3,874 rows across 1,964 shows.

## What was done

1. `scripts/collect/fetch_relisten_years.py` fetched the public Relisten API
   year endpoint `GET /api/v2/artists/grateful-dead/years/<year>` once per year
   for 1965–1995 (31 requests, one per second, User-Agent
   `Deadbot/0.1 (historical-show-context)`). Each year is one raw JSONL record
   in `data/raw/recordings/relisten-years.jsonl` with `source`,
   `source_record_id`, `retrieved_at`, `source_url`, `status`, `error`, and a
   compact `raw_payload`: the year summary (show count, source count, average
   rating) and, per show, `display_date`, `date`, `source_count`,
   `avg_rating`, soundboard/FLAC flags, UUID, and venue name/location. Track
   lists, per-source records, and popularity windows are not stored. The
   collector refuses to overwrite the raw file without `--force`.
2. `scripts/normalize_show_listening_links.py` appended two link families to
   `show_links.csv`, matching on `(show_id, url)` so reruns are idempotent and
   the existing YouTube row is preserved:
   - `relisten` / `streaming-show-page` →
     `https://relisten.net/grateful-dead/YYYY/MM/DD` for every canonical show
     whose `show_date` appears as a Relisten `display_date`.
   - `archive` / `recording-index` →
     `https://archive.org/details/GratefulDead?query=date%3AYYYY-MM-DD` for
     every canonical show with at least one row in `recordings.csv`.
   Both are date-level URLs. `show_links` is unique on
   `(show_id, platform, url)`, not on `url`, so same-date early/late shows each
   receive the link and the ambiguity is written into `notes` and into
   `data/raw/recordings/show-listening-links-review.jsonl`. Nothing was held.
   The file is sorted by `show_link_id`; the header is unchanged.

Rerunning the normalizer produced byte-identical CSV and review output.

## Counts

| Measure | Count |
| --- | ---: |
| Canonical shows (`shows.csv`) | 2,358 |
| Relisten year requests / HTTP 200 | 31 / 31 |
| Relisten Grateful Dead shows (distinct `display_date`) | 2,080 |
| Canonical shows whose date is on Relisten | 1,963 |
| Canonical shows not on Relisten | 395 |
| Relisten dates with no canonical show | 144 |
| Canonical shows with ≥1 `recordings.csv` row | 1,910 |
| `relisten` rows written | 1,963 |
| `archive` rows written | 1,910 |
| Existing rows kept | 1 |
| Total `show_links.csv` rows | 3,874 |
| Rows held for review | 0 |
| Relisten rows sharing a date-level URL with another show | 54 (27 dates) |
| Archive rows sharing a URL with another show | 0 |
| Canonical shows with at least one listening link | 1,964 |
| Canonical shows with no listening link | 394 |

The 395 shows absent from Relisten are concentrated in the early spine: 1965
(12), 1966 (91), 1967 (119), 1968 (95), 1969 (32), 1970 (40), 1971 (5), 1978
(1). Relisten lists a show only when Archive.org holds a recording for it,
while the gdshowsdb spine includes shows with no known tape, so this gap is
expected rather than a collection failure. 394 of those 395 also have no
`recordings.csv` row; only `gd-1967-01-01` has Archive recordings without a
Relisten date match (Relisten's 1967 listing has no 1967-01-01 entry, so its
date handling for that item differs from the Archive index).

No archive row is ambiguous because the earlier Internet Archive index pass
deliberately held items whose date matched more than one canonical show, so
same-date shows currently have no `recordings.csv` rows.

## Sample URL verification

Internet Archive listing candidates, checked 2026-09-01 with `curl` for
1972-08-27, 1977-05-08, 1969-02-27, 1989-07-07, and 1965-05-05:

| Pattern | Result |
| --- | --- |
| `https://archive.org/details/GratefulDead?query=date%3A<date>` (chosen) | HTTP 200 for all 5 |
| `https://archive.org/search?query=collection%3AGratefulDead+AND+date%3A<date>` | HTTP 200 for all 5 |
| `https://archive.org/details/GratefulDead?and%5B%5D=date%3A<date>` | HTTP 200 for all 5 |

Caveat: both archive.org page patterns are JavaScript search shells and also
return HTTP 200 for a date with no items (`date:1901-01-01` was tested). A 200
therefore does not prove that recordings exist, which is why archive rows are
only written for shows that already have `recordings.csv` rows. The
`advancedsearch.php` JSON endpoint confirmed `numFound: 7` for
`collection:GratefulDead AND date:1972-08-27`, matching the 7 canonical
recording rows for Veneta.

Relisten show pages, checked the same day: `/grateful-dead/1972/08/27`,
`/1977/05/08`, `/1969/02/27`, `/1989/07/07`, `/1965/11/01`, and `/1970/02/14`
(a two-show date) all returned HTTP 200; `/grateful-dead/1972/08/28`, a date
with no show, returned 404. Relisten's page pattern therefore does
discriminate between real and non-existent show dates.

## Relisten acceptable use and attribution

Findings from https://relisten.net/about and https://github.com/RelistenNet,
reviewed 2026-09-01:

- Relisten describes itself as a completely free, non-commercial, open-source
  platform for recorded live concerts that is powered by Archive.org (plus
  Phish.in and The Phish Spreadsheet for Phish). It does not accept donations
  and asks that donations go to Archive.org or The Mockingbird Foundation.
- The about page states that the site complies with Archive.org's policy and
  reproduces the Grateful Dead's taping/digital-distribution stipulations: no
  commercial gain from sites offering the music, respect for the copyrights of
  performers, writers, and publishers, and the band's reserved right to
  withdraw sanction.
- The API server (`RelistenNet/RelistenApi`) is MIT licensed; the web client
  (`RelistenNet/relisten-web`) is AGPL-3.0. No published API terms of service,
  rate limit, or usage policy were found in the about page, the repository
  READMEs, or the repository `docs/` folder. The API documentation page
  referenced in the server README is a local-development URL; the public
  `https://api.relisten.net/api-docs` returned 403/404.
- Contact paths offered on the about page: the project Discord, GitHub issues,
  and an email address for the Relisten team (Daniel Saewitz and Alec Gorge).

How Deadbot uses Relisten in this pass, consistent with those findings:

- Metadata only: year listings, never audio, never track lists.
- 31 requests total at one request per second with a descriptive User-Agent.
- Links point listeners to Relisten's own show pages; nothing is embedded or
  re-hosted. Each row's `notes` cites the API URL and retrieval date, and the
  underlying media remains Archive.org's non-commercial Grateful Dead
  collection.
- Recommended attribution in the product: name Relisten as the player and the
  Internet Archive as the recording source, and keep Deadbot non-commercial
  with respect to this material.
- Before any higher-volume use (per-show source pulls for 2,080 shows, or
  scheduled refreshes), ask the Relisten team through GitHub or Discord, since
  no written policy covers automated clients.

## Open questions

1. Same-date shows: 27 dates carry two canonical shows and one Relisten
   date-level URL each (54 rows). Relisten itself lists one show per date, so
   the ambiguity is on Relisten's side too. If a per-show link is wanted, the
   show endpoint (`/years/<year>/<display_date>`) would need to be reviewed for
   early/late source labelling.
2. 144 Relisten dates have no canonical show. Some are placeholders
   (`1966-11-XX`, `1966-XX-XX`), and 21 are in 1975, when the spine has 4 shows
   and Relisten has 25 (likely rehearsals, studio sessions, or misdated
   items). These are candidates for a spine reconciliation pass, not for
   automatic show creation.
3. 394 canonical shows still have no listening link; nearly all are 1965–1970
   shows for which no recording is known. Only a source that documents lost
   shows could change that, and the absence should stay visible.
4. Two existing tests in `tests/test_data.py` fail against the enlarged
   `show_links.csv` and were not changed because tests are outside this pass's
   scope:
   - `test_show_media_lookup_resolves_a_date_to_the_canonical_show` asserts
     that `links[0]` for Veneta is the `full-show-video` row; rows are now
     sorted by `show_link_id`, so `archive-index` sorts first. The assertion
     should look up the YouTube row by `link_type` or `platform`.
   - `test_show_tool_payload_is_compact_enough_for_local_model_context` caps
     the Veneta `get_show` payload at 11,000 characters; it is now 11,253.
     Without the two new rows the payload is 10,255 characters, and the row
     fields alone (before any notes) add about 650, so no note wording fits.
     Either the budget or the amount of link detail `get_show` inlines needs
     an owner decision.
5. Documentation owned by other passes still needs updating: the Relisten
   entry in `docs/data-sources.md` (still "no Relisten record has yet been
   collected"; usage considerations "TBD") and `scripts/README.md` (new
   collector and normalizer).
6. `link_type` values `streaming-show-page` and `recording-index` and platform
   value `archive` are new; the schema imposes no vocabulary, but
   `deadbot/composition.py` and the media-link tooling should be checked for
   any assumptions about `full-show-video`.
