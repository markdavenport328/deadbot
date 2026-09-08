# Collection status: Deadhead High song and listener guides (2026-09-08)

Indexes `deadheadhigh.com` — a per-song listening guide, a per-show page and a
set of editorial listener guides — as metadata-only stored resources, mapped to
canonical songs and shows. Plan:
`docs/superpowers/plans/2026-09-08-lore-collection-targeted.md` (Task A);
global constraints inherited from
`docs/superpowers/plans/2026-09-08-lore-collection-blog-index.md`.

- Collector: `scripts/collect/collect_deadheadhigh_index.py`
- Normalizer: `scripts/normalize/normalize_song_guide_resources.py` (shared
  with the Dead.net pass; see
  `docs/collection-status-lore-deadnet-song-essays.md` for the match key and
  the mapping rules in full)
- Raw: `data/raw/resources/deadheadhigh-index.jsonl` (first line is the pass
  metadata, one line per kept page after it)
- Held queue: `data/editorial/lore-mapping-held-deadheadhigh.jsonl` (empty:
  nothing was held)
- Registry: `deadheadhigh-guides` added to `data/source_registry.json` as a
  reviewed metadata-only source with `allowed_operations`
  `["search", "read"]`.

This pass changes raw files, the held queue, the registry and docs only. **No
canonical CSV was written.** The normalizer was run with `--out-dir` pointing
at a scratch directory; the row counts below are what it will append when the
controller runs it against `data/canonical`. Production PostgreSQL is loaded by
the owner's import step (`deadbot/postgres_import.py`); nothing here writes to
a database.

## What is stored, and what is not

A stored record keeps the page URL, its title, at most 200 characters of the
page's own meta description, the HTTP status and the retrieval time. No guide
text is written to any file. These pages carry no byline and no publication
date, so `creator` and `published_date` are blank rather than assumed.

Deadhead High's meta description is written per page and says what the page
covers ("Explore 156 Grateful Dead performances of Box of Rain from 1970-1995,
with first and last dates, venues, setlists, and listening links."), so it is
kept in the canonical `notes` field, capped at 200 characters, with the
retention sentence after it.

## Requests

416 requests in total, one at a time, at least two seconds apart, with
`User-Agent: Deadbot/0.1 (metadata index; contact via repository)`:

| Step | Requests |
| --- | --- |
| `https://deadheadhigh.com/robots.txt` | 1 |
| `https://deadheadhigh.com/sitemap.xml` | 1 |
| One metadata request per kept page | 414 |

robots.txt answered HTTP 200 with `User-agent: *` / `Allow: /` and a `Sitemap:`
directive pointing at `/sitemap.xml`; no `Crawl-delay`, nothing disallowed.
The site has no search, so the sitemap is the index: one file, HTTP 200, 2,828
page URLs, no sitemap index to follow.

### What the walk kept, and what it left alone

| Section | URLs in sitemap | Requested | Why |
| --- | --- | --- | --- |
| `/songs/` | 351 (350 pages + the section index) | 350 | the pass's subject |
| `/shows/` | 1,925 | 19 | slug is a target or featured show date |
| `/guides/` | 17 (16 + index) | 16 | the site's editorial writing |
| `/paths/` | 30 (29 + index) | 29 | curated listening paths, same character |
| `/venues/` | 500 | 0 | this pass has no venue mapping rule |
| site pages (`/`, `/privacy`, `/terms`, `/support`, `/editorial-standards`) | 5 | 0 | not about a song or a show |

Keeping `/guides/` and `/paths/` whole is the plan's "broader coverage when it
costs only more requests at the same pace": 45 pages, 90 seconds of politeness,
and it is the part of the site a person actually reads ("What Grateful Dead
Show Should You Listen to First?", "Audience Tape, Soundboard, Matrix, or
Official Release? How Grateful Dead Recordings Work"). The 500 venue pages were
left alone deliberately: nothing in this pass maps a resource to a venue, so
requesting them would have been traffic without a use. They can be added later
from the same sitemap walk.

## What the normalizer will write

| Rows | Count |
| --- | --- |
| `resources.csv` | 414 (350 `listening-guide`, 64 `listener-guide`) |
| `resource_songs.csv` | 350 (350 distinct songs) |
| `resource_shows.csv` | 19 (19 distinct shows) |
| Unmapped (a resource, no relationship) | 45 |
| Held for review | 0 |

Resource ids are `resource-deadheadhigh-<path slug>`:
`resource-deadheadhigh-songs-box-of-rain`,
`resource-deadheadhigh-shows-1982-07-27`,
`resource-deadheadhigh-guides-best-grateful-dead-shows-for-beginners`.
`resource_type` is `listening-guide` for a `/songs/` page and `listener-guide`
for everything else, as the plan specifies. `source_name` is `Deadhead High`,
`relationship_type` is `about`, and `notes` states the basis: "The page slug
names the song." or "The page slug names the show date."

All 350 song slugs matched exactly one canonical song, including the awkward
ones — `i-know-it-s-a-sin`, `a-mind-to-give-up-livin`,
`unidentified-19660312-02-blues-instrumental`, `hey-jude-reprise` — because the
site derives its song list from the same gdshowsdb baseline the canonical set
came from. Nothing was ambiguous, so the held queue is empty. The 45 unmapped
rows are the guide and path pages, which are about listening in general rather
than one song or one show; they are searchable by title and description through
`search_stored_resources`.

### The show-date rule, applied here

The plan states the date rule for archive items. Deadhead High names its show
pages by date (`/shows/1982-07-27`), so the same rule is what lets them map: a
slug that is one full date maps to the show on that date when exactly one
canonical show sits there; two shows on that date would be a hold, and a date
with no canonical show is left unmapped. All 19 kept show pages matched exactly
one show, so none was held.

## The 14 target songs

Every target song has a Deadhead High listening guide. "found" is a row this
pass will write.

| Song | Deadhead High song page |
| --- | --- |
| Box Of Rain | found (`/songs/box-of-rain`) |
| Attics Of My Life | found (`/songs/attics-of-my-life`) |
| Candyman | found (`/songs/candyman`) |
| Slipknot! | found (`/songs/slipknot`) |
| Throwing Stones | found (`/songs/throwing-stones`) |
| Touch Of Grey | found (`/songs/touch-of-grey`) |
| Feel Like A Stranger | found (`/songs/feel-like-a-stranger`) |
| Cold Rain And Snow | found (`/songs/cold-rain-and-snow`) |
| Bertha | found (`/songs/bertha`) |
| Goin' Down The Road Feelin' Bad | found (`/songs/goin-down-the-road-feelin-bad`) |
| Black Queen | found (`/songs/black-queen`) |
| Midnight Hour | found (`/songs/midnight-hour`) |
| Quinn The Eskimo | found (`/songs/quinn-the-eskimo`) |
| They Love Each Other | found (`/songs/they-love-each-other`) |

That closes the gap for all three songs Dead.net has nothing for — Touch Of
Grey, Goin' Down The Road Feelin' Bad and Quinn The Eskimo — so after this pass
each of the 14 target songs has at least one non-catalog lore resource.

## The 11 target shows

The show side of the target list belongs to Task B (GDAO), but the same
Deadhead High walk covers it, so the outcome is recorded here.

| Show | Deadhead High show page |
| --- | --- |
| gd-1970-05-08 (Farrell Hall, SUNY) | not found at source |
| gd-1972-04-08 (Empire Pool) | found |
| gd-1973-11-11 (Winterland) | found |
| gd-1974-06-18 (Freedom Hall) | found |
| gd-1977-05-22 (Sportatorium) | found |
| gd-1978-04-12 (Cameron Indoor Stadium) | found |
| gd-1980-11-30 (Fox Theatre) | found |
| gd-1981-03-09 (Madison Square Garden) | found |
| gd-1982-07-27 (Red Rocks) | found |
| gd-1987-09-18 (Madison Square Garden) | found |
| gd-1989-07-17 (Alpine Valley) | found |

1970-05-08 is absent from the site's sitemap, so no request was made for it;
that is a reviewed absence, not a failed request. The nine other featured shows
(1969-02-27, 1972-05-26, 1972-08-27, 1972-09-21, 1973-02-09, 1974-02-24,
1977-05-08, 1990-03-29, 1991-09-10) all have a page and all nine mapped.

## Known limitations

- **A secondary compilation, not an authority.** These pages are generated from
  a setlist database: "156 performances of Box of Rain from 1970-1995". The
  stored row is a link and a description, and the registry entry says plainly
  that a guide page is not a setlist or performance-count authority. Nothing in
  this pass promotes a count from these pages into canonical data.
- **A show page is about the show, not about its songs.** A `/shows/<date>`
  page lists a setlist, but the row says only that it is about that show. Songs
  reach it through the show, not through 20 guessed song rows.
- **Titles carry the site's own phrasing.** A stored title reads "Grateful Dead
  Box of Rain Live Versions (156 Shows)" as the page's `<title>` has it, minus
  the "| Deadhead High" suffix. The count in the title will drift if the site
  recomputes it; the raw file records the retrieval time.
- **No byline.** The site publishes an editorial-standards page but no per-page
  author, so `creator` is blank on all 414 rows.
- **Venues and the remaining 1,906 show pages are uncollected.** They are one
  sitemap walk away when a pass has a rule for them.

## Spot checks

Four of the ten spot checks for this pass fall on this source; they are listed
in full, with the six Dead.net checks, in
`docs/collection-status-lore-deadnet-song-essays.md`. All four passed, judged
from the page title and URL slug alone:
`/songs/gangster-of-love` → `song-gangster-of-love`,
`/songs/unidentified-19660312-02-blues-instrumental` →
`song-unidentified-19660312-02-blues-instrumental`,
`/songs/revolutionary-hamstrung-blues` → `song-revolutionary-hamstrung-blues`,
`/shows/1978-04-12` → `gd-1978-04-12`.

## Coverage after this pass (Task A only)

| Measure | Before | After Task A |
| --- | --- | --- |
| Resources | 2,040 | 2,552 |
| Songs with any resource | 200 | 374 |
| Songs with a non-catalog resource | 70 | 361 |
| Shows with any resource | 422 | 432 (of 2,358) |

"Non-catalog" excludes `catalog-work-search`, `lyrics-and-credits` and
`catalog-song-page`. Task B's GDAO rows are counted separately in
`docs/collection-status-lore-gdao.md`.

## Landing the rows

```
PYTHONPATH=. .venv/bin/python scripts/normalize/normalize_song_guide_resources.py \
    --canonical-dir data/canonical --out-dir data/canonical
```

One command lands both sources of this pass (Dead.net and Deadhead High): 512
rows into `data/canonical/resources.csv`, 447 into `resource_songs.csv`, 19
into `resource_shows.csv`, every existing row untouched, and the two held
queues rewritten. A rerun over unchanged raw files adds nothing.
