# Collection status: research-blog post index (2026-09-08)

Indexes the five Blogger research sites in `data/research_sites.json` as
metadata-only stored resources and maps them, conservatively, to canonical
songs and shows. Plan:
`docs/superpowers/plans/2026-09-08-lore-collection-blog-index.md`.

- Collector: `scripts/collect/collect_blog_post_index.py`
- Normalizer: `scripts/normalize/normalize_blog_post_resources.py`
- Raw: `data/raw/resources/blog-post-index-{host}.jsonl` (first line is the
  pass metadata, one line per post after it)
- Held queue: `data/editorial/blog-post-mapping-held.jsonl`
- Canonical: appended rows in `data/canonical/resources.csv`,
  `resource_songs.csv`, `resource_shows.csv`

This pass changes CSVs, raw files and docs only. Production PostgreSQL is
loaded by the owner's import step (`deadbot/postgres_import.py`); nothing here
writes to a database.

## What is stored, and what is not

A stored record keeps the post title, its URL, the published and updated
timestamps, the post labels, the feed's author name, the request URL, the HTTP
status and the retrieval time. No post body, summary or excerpt is written to
any file. The canonical `notes` field carries the post's own labels and the
retention sentence; nothing else from the site is retained.

## Requests

29 requests in total: one `robots.txt` per host, then 24 feed pages. One
request at a time, at least two seconds apart, with
`User-Agent: Deadbot/0.1 (metadata index; contact via repository)`.

Two decisions worth naming:

- **The summary feed.** The collector walks `/feeds/posts/summary` rather than
  `/feeds/posts/default`. Both carry the same post metadata, and neither post
  bodies nor summaries are stored either way, but one page of Lost Live Dead is
  95 KB from the summary feed against 2.4 MB from the full feed. Pass
  `--feed-path /feeds/posts/default` for the full feed; the path used is
  recorded in each raw file's pass metadata.
- **Pagination by entries returned.** Blogger answers with as many entries as
  fit its own response budget, not with the requested `max-results`: Lost Live
  Dead returned 36 entries for `max-results=150`, then 54, then 92, then 116.
  So the walk advances `start-index` by the number of entries a page actually
  returned and stops on an empty page or once the feed's reported total is
  reached. Every host's collected entry count equals the total its feed
  reports, so no host is partially indexed.

## Per host

Every host serves the standard Blogger `robots.txt`, HTTP 200, with the group
that applies to this collector reading `Disallow: /search`,
`Disallow: /share-widget`, `Allow: /`, and no `Crawl-delay`. The feed path is
allowed on all five; no host was skipped or aborted.

| Site | Host | robots | Pages | Entries (feed total) | Resources | Song rows (distinct songs) | Show rows (distinct shows) | Unmapped | Held |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lost Live Dead | lostlivedead.blogspot.com | 200, feed allowed | 4 | 298 (298) | 298 | 0 (0) | 71 (69) | 194 | 33 |
| Hooterollin' Around | hooterollin.blogspot.com | 200, feed allowed | 3 | 133 (133) | 133 | 5 (4) | 11 (11) | 115 | 4 |
| Grateful Dead Guide (Deadessays) | deadessays.blogspot.com | 200, feed allowed | 7 | 184 (184) | 184 | 44 (33) | 12 (12) | 130 | 1 |
| Dead Sources | deadsources.blogspot.com | 200, feed allowed | 5 | 575 (575) | 575 | 4 (4) | 241 (189) | 251 | 79 |
| Grateful Seconds | gratefulseconds.blogspot.com | 200, feed allowed | 5 | 550 (550) | 550 | 80 (43) | 231 (219) | 206 | 94 |
| **Total** | | | **24** | **1,740** | **1,740** | **133 (63)** | **566 (419)** | **896** | **211** |

`resource_type` by host: Lost Live Dead → `show-history-post`; Deadessays and
Hooterollin' → `editorial-blog-post`; Dead Sources → `press-transcription`;
Grateful Seconds → `statistics-post`. `creator` is the feed's byline
(`Corry342`, `Dr. Jeff` and `The Yellow Shark` on Lost Live Dead,
`Light Into Ashes` on Deadessays and Dead Sources, `Grateful Seconds` on
Grateful Seconds). `relationship_type` is `about` on every row, and `notes`
states the basis: "Title names the show date.", "A post label names the show
date.", "Title names the song.", "Title names the song and a post label names
it too.", "Title begins with the song title."

Grateful Seconds publishes on `gratefulseconds.com`, whose feed advertises
`http://` links and which answers nothing on port 443. Those 550 rows store
`https://gratefulseconds.blogspot.com/<path>` — the blog's own https address
for the same post, which Blogger redirects to the custom domain — and each row
records the feed's own URL in its notes. Without that, the rows would be
invisible to `search_stored_resources`, which only returns https resources.

## Coverage before and after

| Measure | Before | After |
| --- | --- | --- |
| Resources | 300 | 2,040 |
| Songs with any resource | 174 | 200 |
| Songs with a non-catalog resource | 17 | 70 |
| Shows with any resource | 6 | 422 (of 2,358) |

"Non-catalog" excludes `catalog-work-search`, `lyrics-and-credits` and
`catalog-song-page` rows — the MusicBrainz work entries and Dead.net lyric
pages that made up 267 of the 300 pre-existing resources.

## Held for review — 211 posts

Held posts are written to `data/editorial/blog-post-mapping-held.jsonl` with
`resource_id`, `host`, `url`, `title`, `reason` and `candidates`. Each still
has a resource row; only the relationship is withheld.

| Reason | Posts |
| --- | --- |
| The title names more than one date (a run, or two dates) | 112 |
| The post labels name more than one date | 57 |
| One date carries two canonical shows (early/late, or two venues) | 42 |

The 42 two-show holds concentrate in 1967–1970, where the canonical set records
two shows on a date: 1970-03-21 four times, then 1967-01-14, 1967-06-16,
1967-08-05, 1968-04-14, 1968-06-14, 1969-06-21, 1969-09-27, 1970-01-02 and
1970-10-11 twice each, and twenty other dates once each.

## Unmapped — 896 posts

A post naming neither one show date nor a song is still a resource; it is not
held. These are the essays, tour itineraries, personnel lists, statistics
round-ups and obituaries that carry no single canonical anchor: "The Grateful
Dead in Upstate and Central New York 1969-79", "Jerry Garcia Band Personnel
1975-1995", "Grateful Dead Touring Revenues, 1965-1995". They are searchable by
title and labels through `search_stored_resources`.

A further 158 posts name a date the collector parsed that matches no canonical
show — Jerry Garcia Band, New Riders and Kingfish dates, Fare Thee Well 2015,
and a handful of real Dead dates the canonical set does not carry
(1978-11-25 in New Haven, for one). These are counted separately and left
unmapped rather than attached to a neighbouring date.

## Mapping rules as implemented

Show: the title, or failing that a post label, names exactly one date in
`YYYY-MM-DD`, `M/D/YY`, `M/D/YYYY` or `Month D, YYYY` form (abbreviated month
names and `Month D-D, YYYY` / `Month D - Month D, YYYY` runs included), and
exactly one canonical show sits on that date. A title date beats a label date.
Two dates, or a date carrying two shows, is a hold. A two-digit year is read as
19YY only for 65–99; an impossible date (13/45/72, 2/30/70) is not a date.

Song: the title contains a canonical song title as a whole phrase, matched
case-insensitively, with curly and straight apostrophes alike, `&` read as
`and`, and a comma, colon or dash between words read as the space it stands in
for — so `"It's All Over Now, Baby Blue"` matches the song whose canonical
title has no comma. A shorter title matched inside a longer one (Playing In The
Band inside its Reprise) is dropped as the same reference. More than three
matches is a hold.

Three readings of the plan are worth recording:

1. **One-word titles are always short.** The plan's gate is "at least two words
   or at least six letters", but its own examples of titles needing help —
   `Deal`, `Ripple`, `Truckin'`, `Bertha`, `Cassidy` — are all one word and
   four are six letters or more. So a one-word title always needs support, and
   so does a two-word title of fewer than six letters.
2. **Seven titles these blogs write for another reason** need the same
   support: `The Seven`, `The Eleven`, `The Main Ten`, `Maybe You Know` and
   `So Many Roads` read as ordinary prose ("The Eleven Longest Jerry Bands
   Songs", "The Seven And Only Seven Terrapin Encores", "Maybe You Know Brent
   Got Wasted", "South Bay Landmark Guide (So Many Roads I)"). The cost is
   real — two genuine `Dark Star > The Eleven` posts go unmapped — and
   accepted, because a wrong row would have Deadbot say a post covers a song it
   never mentions.
3. **A song named after a city gets no label path.** `New Orleans`,
   `Kansas City`, `Salt Lake City` and `El Paso` matched venue lines ("The
   Warehouse, New Orleans", "Terrace Ballroom, Salt Lake City, UT"), and these
   sites label posts by place, so a `Kansas City` label is the venue's city as
   often as the song. Only a Deadessays title that begins with the song title
   maps these.

Label support is exact: the label must be the song title, not merely contain it
("Top-31 Jam Segment" does not name `Jam`).

## Known limitations

- **A date is not a subject.** Twelve Dead Sources rows are interviews or press
  items dated on a show day ("November 23, 1970: Band Interview",
  "March 20, 1981: Jerry Garcia Interview"). The row says the post's title
  names that date, which is true and useful for that date's context; it does not
  claim the post reviews the show.
- **Side-project posts on a Dead show date.** Lost Live Dead and Hooterollin'
  cover the whole bill: "December 31, 1977 Winterland: New Riders of The Purple
  Sage with Spencer Dryden" maps to the Dead's show that night because the post
  is about that event.
- **Partly spelled date lists.** "Guest Flute Players with The Grateful Dead:
  June 13, August 3 and August 21, 1969" names three dates but spells only one
  with its year, so it maps to that one instead of being held.
- **Song coverage is thin by nature.** 63 songs against 419 shows: these blogs
  title posts by date and venue far more often than by song. Deadessays, the
  song-by-song site, produced 33 of the 63.

## Spot checks

Twenty mappings drawn at random from the 699 relationship rows and judged from
the post title alone; no post page was read.

| # | Host | Mapped to | Title | Verdict |
| --- | --- | --- | --- | --- |
| 1 | Grateful Seconds | song-i-need-a-miracle | The East-Coast Only I Need A Miracle Sing-A-Long | pass |
| 2 | Grateful Seconds | song-foolish-heart | Post 3.5 Bruuuce and Jerry Play In The Garden Prior To A Foolish Heart 1991-09-24 | pass |
| 3 | Grateful Seconds | song-if-i-had-the-world-to-give | Jam>Jack-A-Roe and Playin>Shakedown>If I Had the World to Give>Playin Highlight Weirdest Show of Year in Cleveland, November 20, 1978 | pass |
| 4 | Deadessays | song-franklin-s-tower | Help on the Way > Slipknot > Franklin's Tower: The Early Years (Guest Post) | pass |
| 5 | Grateful Seconds | song-estimated-prophet | "If You Can't Handle LSD, Don't Take It" Bobby and The True Story of Estimated Prophet | pass |
| 6 | Grateful Seconds | song-tennessee-jed | I Was A Magnet for Second-Set Tennessee Jed, 1976-1995 | pass |
| 7 | Grateful Seconds | song-stir-it-up | Reggae Dead Day : From Stir It Up Jam to Struggling Man | pass |
| 8 | Deadessays | song-mind-left-body-jam | The Mind Left Body Jam | pass |
| 9 | Dead Sources | song-i-know-you-rider | I Know You Rider Lyric Variations | pass |
| 10 | Grateful Seconds | song-samson-and-delilah | Two Double Reverse Ax Handles in Boston and Cedar Rapids with Eyes of the World and Samson & Delilah | pass (`&` read as `and`) |
| 11 | Dead Sources | gd-1971-10-27 | October 27, 1971: Onondoga War Memorial, Syracuse, NY | pass |
| 12 | Lost Live Dead | gd-1969-08-21 | August 21, 1969 Aqua Theatre, Seattle, WA (Revisited) | pass |
| 13 | Dead Sources | gd-1970-10-17 | October 17, 1970: Music Hall, Cleveland OH | pass |
| 14 | Grateful Seconds | gd-1969-04-11 | We're Gonna Be Here For A Long Time, And Just Play Any Old Thing Show, April 11, 1969 Tucson | pass |
| 15 | Grateful Seconds | gd-1976-12-31 | Stroke of Midnight, First Show of 1977: December 31, 1976 at the Cow Palace | pass |
| 16 | Dead Sources | gd-1971-03-13 | March 13, 1971: Michigan State University, East Lansing, MI | pass |
| 17 | Dead Sources | gd-1981-03-20 | March 20, 1981: Jerry Garcia Interview | overreach: an interview dated on a show day, kept with the basis stated and disclosed above |
| 18 | Grateful Seconds | gd-1980-12-12 | The Grateful Dead Is Still Worth Taking A Chance On Estimated>He's Gone>Eyes of the World Show, San Bernardino, December 12, 1980 | pass |
| 19 | Grateful Seconds | gd-1993-08-22 | 25 Years Ago: Best Days Between, August 22, 1993 Autzen | pass |
| 20 | Grateful Seconds | gd-1979-05-05 | Disco Dancing Dead (and The Four Sandwiches) — label `1979-05-05` | pass (label basis) |

19 of 20 pass; one is the disclosed "date is not a subject" case.

An earlier round of twenty checks against the first run found and fixed four
rules: city names matching venue lines (`New Orleans`, `Kansas City`,
`Salt Lake City`), `The Eleven` reading as a count, `"It's All Over Now, Baby
Blue"` matching the shorter song because of its comma, and a run spanning two
months ("February 27-March 2, 1969") mapping only its last date instead of
being held.

## Validation

- Foreign keys: every appended `song_id`, `show_id` and `resource_id` resolves;
  no duplicate resource id, source URL or `(resource_id, entity_id,
  relationship_type)` triple; every stored URL is https.
- Idempotency: rerunning the normalizer over the same raw files leaves all
  three CSVs and the held queue byte-identical, and the diff against the
  previous canonical files is insertions only — no existing row was modified or
  reordered.
- Tests: `tests/test_collect_blog_post_index.py` (27) and
  `tests/test_normalize_blog_post_resources.py` (36), both fixture-only.
