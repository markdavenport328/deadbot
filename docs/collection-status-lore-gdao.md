# Collection status: Grateful Dead Archive Online show items (2026-09-08)

Catalogs items from the Grateful Dead Archive Online (GDAO, `www.gdao.org`) —
UC Santa Cruz Library's Omeka S archive — as metadata-only stored resources
mapped to canonical shows. Plan:
`docs/superpowers/plans/2026-09-08-lore-collection-targeted.md` (Task B); its
global constraints come from
`docs/superpowers/plans/2026-09-08-lore-collection-blog-index.md`.

- Collector: `scripts/collect/collect_gdao_show_items.py`
- Normalizer: `scripts/normalize/normalize_gdao_show_resources.py`
- Raw: `data/raw/resources/gdao-show-items.jsonl` (first line is the pass
  metadata, one line per item after it)
- Held queue: `data/editorial/lore-mapping-held-gdao.jsonl`
- Canonical: **not written by this pass.** The normalizer reads
  `--canonical-dir` and writes `--out-dir`; it was run only into a scratch
  directory for review. The controller lands the rows with
  `--out-dir data/canonical` after review.

This pass changes raw files, the held queue and docs only. Production
PostgreSQL is loaded by the owner's import step (`deadbot/postgres_import.py`);
nothing here writes to a database.

## What is stored, and what is not

A stored record keeps the Omeka item id, the item title, the item type (the
Omeka resource-template label: `Poster`, `Ticket`, `Envelope`, `Fan Tape`,
`Image`, …), the item-set titles, the values of the item's three date fields,
its coverage lines, its creator, the item page URL, and the first 200
characters of its description with markup removed. No files, media,
thumbnails or `dcterms:tableOfContents` set lists are written to any file, and
the description is not copied into a canonical row — the canonical `notes`
field carries the item type, the item sets, the coverage lines and the
retention sentence, and nothing else.

## Robots and the API's own terms

- `https://www.gdao.org/robots.txt` answers **HTTP 404** (the archive serves no
  robots file), so `/api/items` is unrestricted. The finding is preserved in
  the raw file's pass metadata.
- `https://www.gdao.org/api` states its own terms: "This is the REST API root
  endpoint for this Omeka S installation. Below is a list of available API
  resources and links to their endpoints. Some resources and features require
  authentication." Nothing this pass reads requires authentication; every
  request is an anonymous GET of a public item list.
- GDAO's `dcterms:rights` statement on an item is a fair-use notice: the work
  is available from the UC Santa Cruz Library for research, teaching and
  private study, and use beyond fair use needs the copyright holder's
  permission. That is why this pass stores links and metadata and never a
  file, an image or a body of text.

## Requests

24 requests in the recorded pass: one `robots.txt`, one API root, two small
reference lists (`/api/resource_templates`, `/api/item_sets`), then one item
query per show date — 20 dates, each answered in a single page. A further
fifteen requests were made by hand while working out the API's shape and while
checking the absences reported below. One request at a time, at least two
seconds apart, with
`User-Agent: Deadbot/0.1 (metadata index; contact via repository)`.

Three decisions worth naming:

- **Query by property, not by full text.** `fulltext_search=1977-05-22`
  returns items that merely mention the string; a property query
  (`property[n][type]=sw`) against the date fields returns only items whose
  date field starts with that day. The stored values read
  `1989-07-17T00:00:00Z` or `1989-07-17`, so a full ISO date matches the day
  and nothing else.
- **All three date fields are queried, and all three are stored.** GDAO keeps
  a date in `dcterms:temporal` (property 41, Temporal Coverage — the date the
  item is *about*), `dcterms:date` (property 7 — the item's own date) and
  `gdao:sortableDate` (property 240 — the archive's sort key). A
  ticket-request envelope postmarked 1989-06-03 for the 1989-07-17 show
  carries the show date only in Temporal Coverage, so a pass that read one
  field would miss it or file it under the postmark.
- **A slow API is not an absence.** One property query over GDAO's 37,432
  items took 29 seconds to answer, so the collector waits 60 seconds and asks
  once more before it gives up; a transport failure or a 5xx aborts the pass
  and leaves the previous raw file untouched.

## What was found

| | Count |
| --- | --- |
| Show dates queried | 20 (11 target, 9 other featured) |
| Dates with at least one item at the source | 20 of 20 |
| Distinct items collected | 279 |
| Resources proposed | 279 (all `archive-artifact`) |
| `about` show relationships proposed | 162, across 20 distinct shows |
| Held for review | 117 items |
| Cataloged but unmapped | 0 |
| Skipped | 0 |
| `creator` filled from the source | 167 of 279 |
| `published_date` filled from the item's own Date field | 128 of 279 |

By item type: `Fan Tape` 134, `Envelope` 107, `Image` 30, `Timeline` 3,
`Laminate` 2, `Poster` 2, `T-Shirt` 1.

## Per target

`found` counts items the source returned for that date; `mapped` counts items
whose date field maps them to *that* show; `held` counts items whose date
reference is ambiguous. Every date is reported, including the ones where the
archive holds nothing.

| # | Show | Date | Group | Found | Mapped | Held | Item types mapped |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Farrell Hall, SUNY | 1970-05-08 | target | 2 | 1 | 1 | Fan Tape 1 |
| 2 | Empire Pool | 1972-04-08 | target | 5 | 4 | 1 | Fan Tape 4 |
| 3 | Winterland | 1973-11-11 | target | 5 | 5 | 0 | Fan Tape 5 |
| 4 | Freedom Hall | 1974-06-18 | target | 4 | 4 | 0 | Fan Tape 4 |
| 5 | Sportatorium | 1977-05-22 | target | 2 | 2 | 0 | Fan Tape 2 |
| 6 | Cameron Indoor Stadium, Duke | 1978-04-12 | target | 9 | 9 | 0 | Fan Tape 8, Image 1 |
| 7 | Fox Theatre | 1980-11-30 | target | 8 | 8 | 0 | Fan Tape 8 |
| 8 | Madison Square Garden | 1981-03-09 | target | 15 | 15 | 0 | Fan Tape 15 |
| 9 | Red Rocks Amphitheatre | 1982-07-27 | target | 5 | 5 | 0 | Fan Tape 5 |
| 10 | Madison Square Garden | 1987-09-18 | target | 36 | 15 | 21 | Fan Tape 12, Image 2, Envelope 1 |
| 11 | Alpine Valley Music Theatre | 1989-07-17 | target | 46 | 8 | 38 | Fan Tape 6, Image 1, Envelope 1 |
| 12 | Fillmore West | 1969-02-27 | featured | 23 | 21 | 2 | Image 18, Fan Tape 3 |
| 13 | Lyceum | 1972-05-26 | featured | 4 | 4 | 0 | Fan Tape 4 |
| 14 | Old Renaissance Faire Grounds | 1972-08-27 | featured | 8 | 8 | 0 | Fan Tape 7, Timeline 1 |
| 15 | Spectrum | 1972-09-21 | featured | 1 | 1 | 0 | Image 1 |
| 16 | Roscoe Maples Pavilion, Stanford | 1973-02-09 | featured | 4 | 4 | 0 | Fan Tape 4 |
| 17 | Winterland | 1974-02-24 | featured | 6 | 6 | 0 | Fan Tape 6 |
| 18 | Barton Hall, Cornell | 1977-05-08 | featured | 21 | 21 | 0 | Fan Tape 20, Timeline 1 |
| 19 | Nassau Veterans Memorial Coliseum | 1990-03-29 | featured | 39 | 10 | 29 | Fan Tape 10 |
| 20 | Madison Square Garden | 1991-09-10 | featured | 36 | 11 | 25 | Fan Tape 10, Envelope 1 |
| | **Total** | | | **279** (distinct) | **162** | **117** | |

All 11 target shows and all 20 featured shows gained at least one mapped GDAO
item. No date came back empty, so there is no "none at source" row: the
absences in this pass are absences of *kinds* of item, described below, not of
dates.

## Held for review — 117 items

| Reason | Items |
| --- | --- |
| The item's Temporal Coverage names more than one date | 116 |
| The item's Date field names more than one date | 1 |

By item type: `Envelope` 104, `Image` 7, `Laminate` 2, `Poster` 2,
`Timeline` 1, `T-Shirt` 1.

Almost every hold is the same shape and the same artifact: a fan's
ticket-request envelope for a multi-night stand. "Kip Francis" carries
Temporal Coverage `1990-03-28`, `1990-03-29`, `1990-03-30`; "Victoria
Crociata" carries five nights at Madison Square Garden in September 1987. The
envelope really is about every night it names, so the rule holds it rather
than pick one, and the held record lists each date with the canonical show id
it resolves to:

```json
{"reason":"The item's Temporal Coverage names more than one date.",
 "candidates":["1990-03-28 (gd-1990-03-28)","1990-03-29 (gd-1990-03-29)","1990-03-30 (gd-1990-03-30)"]}
```

**Recommendation for the controller.** These 117 holds are not
title-resolution guesses; every candidate is already a canonical show id. If
the owner decides a multi-night artifact may carry an `about` row for each
night it names, the whole queue can be promoted mechanically from the
candidates, which would add roughly 300 more show relationships and give the
run-mates of these 20 shows their first GDAO resource. That decision is
editorial, so this pass did not take it.

## Mapping rules as implemented

1. **Which date decides.** The three date fields are read in the order the
   archive means them — Temporal Coverage, then the item's own Date, then
   Sortable Date — and the first field that gives a day-precision date decides
   the mapping. `1977-00-00T00:00:00Z` is a year written into a date-shaped
   slot, not a day, so a zero month or day is not a date.
2. **One date, one show → map.** `relationship_type` is `about` and the note
   says which field carried it: "The item's Temporal Coverage names this show
   date (1989-07-17)."
3. **One date, two shows → hold.** Candidates are the show ids.
4. **More than one date in the deciding field → hold.** Candidates are each
   date with the show it resolves to.
5. **Only a partial date → hold.** Candidates are the raw field values, so a
   reviewer can see what the archive actually recorded.
6. **A full date no canonical show sits on → cataloged, unmapped.** Reviewed
   and absent is not ambiguous. (None occurred: every collected item was found
   by a query for a canonical show date.)
7. **No date at all → stored unmapped only if the title names the band or a
   canonical venue, else skipped.** (None occurred, because a date query only
   returns dated items. The rule is implemented and tested for a rerun over a
   wider raw file.)
8. **Resource type from the item type.** `Oral History`, `Story` and `Email`,
   and any item type or format naming an oral history, interview, letter,
   correspondence, recollection or memoir, are a `first-person-account`;
   posters, tickets, envelopes, photographs and an item type the source does
   not give are an `archive-artifact`.
9. **Resource ids** are `resource-gdao-item-<omeka-id>`. `source_name` is
   `Grateful Dead Archive Online / UC Santa Cruz Library`, matching the
   existing row in `resources.csv`. `creator` is the item's `dcterms:creator`
   when it has one. `published_date` is the item's own Date field when GDAO
   gives exactly one day-precision value there — never the show date, which
   belongs to the relationship, not to the artifact.

## Spot checks

Ten mapped rows, drawn at random from the 162 relationships with seed
20260908, checked against the item title and the item's date fields only —
no GDAO page was read.

| Item | Title | Deciding date | Mapped to | Correct? |
| --- | --- | --- | --- | --- |
| 34224 | Grateful Dead Live at Old Renaissance Faire Grounds on 1972-08-27 | temporal 1972-08-27 | gd-1972-08-27 (Veneta) | yes |
| 32949 | Grateful Dead Live at Red Rocks Amphitheatre on 1982-07-27 | temporal 1982-07-27 | gd-1982-07-27 | yes |
| 35078 | Grateful Dead Live at Red Rocks Amphitheatre on 1982-07-27 | temporal 1982-07-27 | gd-1982-07-27 | yes |
| 31321 | Grateful Dead Live at Madison Square Garden on 1987-09-18 | temporal 1987-09-18 | gd-1987-09-18 | yes |
| 98670 | Grateful Dead: Jerry Garcia, Phil Lesh and Bob Weir performing "Dark Star" | temporal 1969-02-27 | gd-1969-02-27 (Fillmore West) | yes |
| 36981 | Grateful Dead Live at Madison Square Garden on 1981-03-09 | temporal 1981-03-09 | gd-1981-03-09 | yes |
| 35077 | Grateful Dead Live at Red Rocks Ampitheatre on 1982-07-27 | temporal 1982-07-27 | gd-1982-07-27 | yes |
| 34226 | Grateful Dead Live at Old Renaissance Faire Grounds on 1972-08-27 | temporal 1972-08-27 | gd-1972-08-27 | yes |
| 28253 | Grateful Dead Live at Barton Hall - Cornell University on 1977-05-08 | temporal 1977-05-08 | gd-1977-05-08 | yes |
| 32865 | Grateful Dead Live at Madison Square Garden on 1981-03-09 | temporal 1981-03-09 | gd-1981-03-09 | yes |

Ten of ten agree, so no rule was changed. Because `Fan Tape` is 48% of the
collected items, a random ten drew eight of them, so six more rows were read
one per remaining item type — every one also agreed:

| Item type | Title | Deciding date | Mapped to |
| --- | --- | --- | --- |
| Image | Jerry Garcia: portrait | temporal 1987-09-18 | gd-1987-09-18 |
| Image | Jerry Garcia | temporal 1987-09-18 | gd-1987-09-18 |
| Timeline | Field Trip | date 1972-08-27 | gd-1972-08-27 |
| Timeline | Cornell '77 show | date 1977-05-08 | gd-1977-05-08 |
| Envelope | Hayato Yoshida (postmarked 1989-06-03) | temporal 1989-07-17 | gd-1989-07-17 |
| Envelope | Stacey L. Hogan (postmarked 1991-07-15) | temporal 1991-09-10 | gd-1991-09-10 |

The two envelopes are the case the field order was written for: the item's own
Date is the postmark, and Temporal Coverage is the show the fan was asking for.

## Known limitations

- **Nothing first-person was reachable by date.** Not one of the 279 items is
  a `first-person-account`, and that is a property of the archive rather than
  of the pass: GDAO holds 26 `Story` items and no `Oral History` items at all,
  and every `Story` item leaves all three date fields empty. A date-keyed pass
  cannot reach them. Catching them needs a different key — the item type plus
  a venue or band name in the title — which is a separate, small pass.
- **Fan tapes carry the coverage.** `Fan Tape` items are GDAO's mirror of
  Internet Archive tape metadata, and they are 134 of the 279 items and the
  only mapped item for 12 of the 20 shows: running the normalizer with
  `--skip-item-types "Fan Tape"` yields 145 resources but only 28
  relationships across 8 shows. They are genuine dated archive items with
  their own GDAO page, so they are kept, but a reviewer should know that for
  most of these shows the new GDAO "artifact" is a tape record duplicating
  what the Internet Archive pass already inventories, and that the human
  artifacts — envelopes, posters, laminates — are mostly in the held queue.
- **Envelope titles are people's names.** GDAO titles a ticket-request
  envelope with the fan's name ("Hayato Yoshida"), which reads oddly as a
  resource title. The source title is kept verbatim rather than invented, and
  the row's `notes` carry the item type and the coverage line
  ("Envelope … Alpine Valley Music Theatre - July 17, 1989") so the context is
  not lost.
- **Posters are mostly dated by year.** GDAO holds 663 `Poster` items, but
  their date fields commonly read `1997-00-00`, a year with no day. Under rule
  5 such an item is held, not mapped, which is why only two posters appeared
  for twenty shows.
- **Tickets exist but not for these dates.** GDAO holds 1,085 `Ticket` items,
  well dated in Temporal Coverage; none of them carries one of these 20 show
  dates. That is a reviewed absence, not a failed request.
- **One date, one page.** Every date was answered in a single 100-item page,
  so pagination was exercised only in the tests. A date with more than 100
  items would take a second page; the collector's ceiling is 25 pages.

## Validation

- `tests/test_collect_gdao_show_items.py` — 14 tests: robots and the API terms
  read before any item query, a missing robots file read as unrestricted, a
  robots disallow stopping the pass, pagination, an item matching two
  requested dates stored once, a failed page aborting without touching the raw
  file, a non-JSON page aborting, a date with no items recorded as
  none-at-source, metadata-only shaping (no files, media or set lists), markup
  stripped before the 200-character cap, a missing resource template, the raw
  file's shape, target dates ordered before the other featured shows, and one
  transport failure retried rather than read as an absence.
- `tests/test_normalize_gdao_show_resources.py` — 19 tests: a full date
  mapping, the item's own date used when it has no Temporal Coverage, Temporal
  Coverage outranking the item's own date, Sortable Date as the last resort,
  item type deciding the resource type, a date with two canonical shows held, a
  partial date held, a field naming two dates held, a full date with no
  canonical show cataloged but unmapped, an undated item stored by band name
  and by venue name and skipped otherwise, a byte-identical rerun, the
  canonical directory untouched when `--out-dir` is elsewhere, appending in
  place when it is not, a hand-cataloged URL keeping its own row, an
  incomplete pass not normalized, item types skippable by name, and a
  per-target outcome for every requested date.
- Rerunning the normalizer over the unchanged raw file reproduced
  byte-identical `resources.csv`, `resource_shows.csv` and held queue.
- `data/canonical` was not modified by this pass; `git status` shows no change
  under it.
- Registry: `gdao-archive` added to `data/source_registry.json` as a reviewed
  metadata-only source with `allowed_operations` `["search", "read"]`.

## Landing the rows

```
PYTHONPATH=. .venv/bin/python scripts/normalize/normalize_gdao_show_resources.py \
    --canonical-dir data/canonical --out-dir data/canonical
```

It appends 279 rows to `data/canonical/resources.csv` and 162 rows to
`data/canonical/resource_shows.csv`, leaves every existing row untouched, and
rewrites `data/editorial/lore-mapping-held-gdao.jsonl`. Add
`--skip-item-types "Fan Tape"` to land the human artifacts only (145
resources, 28 relationships, 8 shows).
