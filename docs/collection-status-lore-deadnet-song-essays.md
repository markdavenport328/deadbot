# Collection status: Dead.net "Greatest Stories Ever Told" song essays (2026-09-08)

Indexes David Dodd's per-song essay series on `www.dead.net` as metadata-only
stored resources, plus the official `/song/<slug>` page for each target song,
and maps both to canonical songs. Plan:
`docs/superpowers/plans/2026-09-08-lore-collection-targeted.md` (Task A);
global constraints inherited from
`docs/superpowers/plans/2026-09-08-lore-collection-blog-index.md`.

- Collector: `scripts/collect/collect_deadnet_song_essays.py`
- Normalizer: `scripts/normalize/normalize_song_guide_resources.py` (shared
  with the Deadhead High pass; see
  `docs/collection-status-lore-deadheadhigh.md`)
- Raw: `data/raw/resources/deadnet-greatest-stories.jsonl` (first line is the
  pass metadata, one line per essay and per song page after it)
- Held queue: `data/editorial/lore-mapping-held-deadnet.jsonl`
- Registry: `deadnet-editorial` was already reviewed and approved; this pass
  adds no registry entry for Dead.net.

This pass changes raw files, the held queue and docs only. **No canonical CSV
was written.** The normalizer was run with `--out-dir` pointing at a scratch
directory; the row counts below are what it will append when the controller
runs it against `data/canonical`. Production PostgreSQL is loaded by the
owner's import step (`deadbot/postgres_import.py`); nothing here writes to a
database.

## What is stored, and what is not

A stored record keeps the page URL, its title, at most 200 characters of the
page's own meta description, the byline, the posting date, the HTTP status and
the retrieval time. No essay text, lyric quotation or comment is written to any
file. The canonical `notes` field carries a sentence naming the series and the
retention boundary; Dead.net's own meta description is the same site-wide
boilerplate ("Official Site Of The Grateful Dead") on every page, so it is not
copied into `notes`.

Dead.net serves `<meta name="robots" content="noimageai,noai">` on these pages.
That signal is about training and generation, not about linking: this pass
stores a title, a byline, a date and a link, reads no page text into any file,
and the runtime tools read a page at request time without storing it. The
boundary is the same one `docs/provenance-policy.md` sets for lyrics — link and
scope metadata, never a copied work.

## Requests

38 requests in total, one at a time, at least two seconds apart, with
`User-Agent: Deadbot/0.1 (metadata index; contact via repository)`:

| Step | Requests |
| --- | --- |
| `https://www.dead.net/robots.txt` | 1 |
| `https://www.dead.net/sitemap.xml` | 1 |
| Series index, `/taxonomy/term/4424?page=0..10` | 11 |
| Candidate essay URLs for targets missing from the index | 11 |
| `/song/<slug>` for each of the 14 target songs | 14 |

robots.txt answered HTTP 200 with the standard Drupal group for `*`, which
permits `/features/greatest-stories-ever-told/` and `/song/` and disallows
`/core/`, `/profiles/`, `/admin/`, `/comment/reply/`, `/search/`, `/user/*` and
`/media/oembed`; no `Crawl-delay`. Nothing this pass requested is disallowed.

### Discovery: why the series index, not the sitemap

The plan's first choice was the sitemap. `https://www.dead.net/sitemap.xml`
answers HTTP 200 and lists **seven** URLs — the home page, `/archives`,
`/features/news`, `/band`, `/forum`, `/mailing-list` and `/deadcast`. It has no
sitemap index and no essay. That finding is recorded in the raw file rather
than treated as "the essays do not exist".

The series' landing page (`/features/greatest-stories-ever-told`) renders one
essay plus its comments and links to no others. The essays are enumerated in
one place only: the taxonomy term Dead.net files each of them under,
`/taxonomy/term/4424` ("Greatest Stories Ever Told"), ten teasers per page.
Each teaser carries the essay's URL, its title, the "By David Dodd" byline and
the node's posting date, so eleven requests yielded 95 essays' metadata with no
per-essay request at all. The collector walks the pager until a page holds no
essay teaser (page 10 was empty) and aborts the whole pass if any page returns
a non-200.

Dead.net's path builder drops Drupal's stopwords and apostrophes, so the essay
slugs are not the song slugs: `attics-my-life`, `friend-devil`, `blues-allah`,
`looks-rain`, `hes-gone`, `eyes-world`. Where a path was already taken it
appends a counter: Dodd's "Box Of Rain" essay lives at
`greatest-stories-ever-told-box-rain-0`. Both spellings are handled by the
match key described below.

## What was collected

| Records | Count |
| --- | --- |
| Essays discovered through the series index | 95 |
| Essays confirmed by a candidate URL | 0 |
| Candidate URLs tried (all HTTP 404) | 11 |
| `/song/<slug>` pages that exist | 8 of 14 targets |
| `/song/<slug>` pages that answered HTTP 404 | 6 |

Every essay carries the byline "David Dodd" except
`greatest-stories-ever-told-just-little-light` ("Just A Little Light"), whose
teaser has no byline; its `creator` is blank rather than assumed. Posting dates
run 2013-01-22 to 2015-01-15.

## What the normalizer will write

| Rows | Count |
| --- | --- |
| `resources.csv` | 98 (94 `song-history-essay`, 4 `catalog-song-page`) |
| `resource_songs.csv` | 97 (93 from essays, 4 from song pages) |
| Distinct songs reached | 94 |
| Already cataloged, left untouched | 5 |
| Held for review | 5 |
| Unmapped | 0 |

Resource ids: `resource-deadnet-gset-<url slug>` for an essay,
`resource-deadnet-song-<slug>` for a song page. `resource_type` is
`song-history-essay` for an essay; a song page is typed `catalog-song-page`,
matching the eight existing rows of that kind, because this pass confirms the
page exists and reads its title but does not check whether lyrics are displayed
(the type `lyrics-and-credits` asserts that). `source_name` is
`Grateful Dead / Dead.net`, `relationship_type` is `about`, and `notes` on each
relationship states the basis: "The page slug names the song.", "The page title
names the song." or "Dead.net song page for this song."

Five records were skipped because a reviewed row already carries their URL, and
those rows keep their own type, creator and notes:
`greatest-stories-ever-told-dark-star` (stored as
`resource-deadnet-greatest-stories-dark-star`, whose URL differs only by
`?page=1`), and the `/song/` pages for Candyman, Bertha, Cold Rain and Snow and
In the Midnight Hour (three `lyrics-and-credits` rows and one
`catalog-song-page` row).

## The 14 target songs

"found" is a row this pass will write or confirm; "already cataloged" is a page
Deadbot already stored, left exactly as it is; "not found at source" is a
reviewed absence — the constructed URL answered HTTP 404 and the slug appears
in neither the series index nor the site's `/song/` index.

| Song | Greatest Stories essay | Dead.net song page |
| --- | --- | --- |
| Box Of Rain | found (`box-rain-0`) | not found at source |
| Attics Of My Life | found (`attics-my-life`) | not found at source |
| Candyman | found | already cataloged |
| Slipknot! | found (in the "Help on the Way"/"Slipknot" essay) | found |
| Throwing Stones | found | found |
| Touch Of Grey | not found at source | not found at source |
| Feel Like A Stranger | found (`feel-stranger`) | not found at source |
| Cold Rain And Snow | not found at source | already cataloged |
| Bertha | found | already cataloged |
| Goin' Down The Road Feelin' Bad | not found at source | not found at source |
| Black Queen | not found at source | found |
| Midnight Hour | not found at source | already cataloged |
| Quinn The Eskimo | not found at source | not found at source |
| They Love Each Other | found | found |

Eight of the 14 gain a Dead.net essay; eleven of the 14 gain or already have a
first-party Dead.net page of some kind. Three — Touch Of Grey, Goin' Down The
Road Feelin' Bad and Quinn The Eskimo — have neither, at any of the URL
spellings tried:

| Song | URLs tried |
| --- | --- |
| Touch Of Grey | `…-touch-of-grey`, `…-touch-grey`, `/song/touch-of-grey` |
| Goin' Down The Road Feelin' Bad | `…-goin-down-the-road-feelin-bad`, `…-goin-down-road-feelin-bad`, `/song/goin-down-the-road-feelin-bad` |
| Quinn The Eskimo | `…-quinn-the-eskimo`, `…-quinn-eskimo`, `/song/quinn-the-eskimo` |

All eleven candidate attempts (for these three plus Slipknot!, Cold Rain and
Snow, Black Queen and Midnight Hour) are recorded in the raw file's pass
metadata with their HTTP status, and every `/song/` read is recorded with the
adapter's state and message, so "not collected" and "reviewed and absent" stay
distinguishable.

## Mapping rules as implemented

The match key. A title or a URL slug is reduced to a tuple of words:
apostrophes are removed rather than splitting a word ("He's Gone" and
`hes-gone` agree), `&` reads as "and", punctuation is a separator, a lone
contraction remnant rejoins the word before it (`it-s-all-over` is "its all
over"), Drupal's pathauto stopwords are dropped from both sides (plus "like",
which Dead.net also drops: `looks-rain`), a trailing `-ing` is read as `-in'`
("Feelin'" and "Feeling" agree), and a trailing duplicate-path counter (`-0`)
is not part of a song's name. Across the 436 canonical songs this key has no
collisions, so a match is unambiguous where it exists.

1. **Slug first.** The essay slug, or the slug minus its path counter, matches
   exactly one canonical song → that song, "The page slug names the song."
2. **Two songs → hold.** A slug matching more than one canonical song is held
   with both candidates.
3. **Then the quoted title.** With no slug match, each song name the page title
   quotes is tried. This is how the four paired essays map to both their songs:
   "Help on the Way"/"Slipknot", "Lazy Lightning/Supplication", "Lost Sailor" &
   "Saint Of Circumstance", "Sugar Magnolia/Sunshine Daydream" — eight rows
   that would otherwise have been eight holds, and the only path by which
   Slipknot! (a target) reaches an essay.
4. **Neither → hold with candidates.** The songs sharing the most words with
   the unmatched key are recorded for review.
5. **A song page maps to its own target.** The collector asked for
   `/song/<slug>` by canonical slug, so the record carries the song id.

## Held for review — 5 essays

Written to `data/editorial/lore-mapping-held-deadnet.jsonl` with
`resource_id`, `source`, `url`, `title`, `reason` and `candidates`. Each still
gets a resource row; only the relationship is withheld.

| Essay title | Reason | Candidates offered |
| --- | --- | --- |
| "Lady With A Fan" | No canonical song of that name | `song-foxy-lady-jam` |
| "Pride of Cucamonga" | No canonical song of that name | none |
| "The Stranger" | No canonical song of that name | `song-feel-like-a-stranger` |
| "Terrapin Station Suite" | No canonical song of that name | `song-terrapin-station`, `song-weather-report-suite-part-1`, `song-weather-report-suite-prelude` |
| "Weather Report Suite" | No canonical song of that name | `song-weather-report-suite-part-1`, `song-weather-report-suite-prelude` |

All five are the same editorial fact: Dodd writes about a suite or a movement
that the canonical song set records under different labels. "Lady With A Fan"
is the first movement of Terrapin Station; "Weather Report Suite" is carried as
`Weather Report Suite Prelude` and `Weather Report Suite Part 1`; "Pride of
Cucamonga" is a *From the Mars Hotel* track the canonical performance universe
has no row for. A reviewer can map each of these by hand; the pass will not
guess which movement an essay is "really" about.

## Known limitations

- **The series index is not provably complete.** It holds 95 essays. Dodd's
  "Deal" essay exists (it is already cataloged as
  `resource-deadnet-greatest-stories-deal`) but is not filed under the taxonomy
  term, so the walk did not find it. Where the series has essays that are
  neither tagged nor at a slug this pass constructed, they remain uncollected —
  which is why every target was also probed directly.
- **No published date beyond the node's posting date.** Dead.net shows the
  node's created date, which for these essays is the week Dodd posted them; it
  is stored as `published_date` and is not a claim about the song.
- **A song page is a link, not a credit.** These four new
  `catalog-song-page` rows say the official page exists and what it is titled.
  Composition credits stay with the existing MusicBrainz and reviewed Dead.net
  credit work.
- **`?page=` variants are not followed.** Long essays paginate their comments.
  The stored URL is the page-1 form without a query, which serves the whole
  essay.

## Spot checks

Ten mappings judged from the page title and URL slug alone; no page text was
read. Three drawn at random from the essay rows, the two rules that could go
wrong deliberately included (a paired essay, a path counter), one song page,
and three from the Deadhead High side of the same normalizer.

| # | Page | Mapped to | Verdict |
| --- | --- | --- | --- |
| 1 | `…-fire-mountain` — 'Greatest Stories Ever Told - "Fire On The Mountain"' | `song-fire-on-the-mountain` | pass |
| 2 | `…-doin-rag` — 'Greatest Stories Ever Told - "Doin\' That Rag"' | `song-doin-that-rag` | pass |
| 3 | `…-lazy-lightningsupplication` — 'Lazy Lightning/Supplication' | `song-lazy-lightning` + `song-supplication` | pass (both named) |
| 4 | `…-help-wayslipknot` — '"Help on the Way"/"Slipknot"' | `song-help-on-the-way` + `song-slipknot` | pass (both named) |
| 5 | `…-box-rain-0` — 'Greatest Stories Ever Told - "Box Of Rain"' | `song-box-of-rain` | pass (counter ignored) |
| 6 | `/song/slipknot` — 'Slipknot \| Grateful Dead' | `song-slipknot` | pass |
| 7 | `deadheadhigh.com/songs/gangster-of-love` | `song-gangster-of-love` | pass |
| 8 | `deadheadhigh.com/songs/unidentified-19660312-02-blues-instrumental` | `song-unidentified-19660312-02-blues-instrumental` | pass |
| 9 | `deadheadhigh.com/songs/revolutionary-hamstrung-blues` | `song-revolutionary-hamstrung-blues` | pass |
| 10 | `deadheadhigh.com/shows/1978-04-12` | `gd-1978-04-12` | pass |

No check failed, so no rule was changed after the checks; the two rules the
checks exercise (paired titles, path counters) were both added *because* the
first real run showed Box Of Rain and Slipknot! reported absent when their
essays existed.

## Landing the rows

```
PYTHONPATH=. .venv/bin/python scripts/normalize/normalize_song_guide_resources.py \
    --canonical-dir data/canonical --out-dir data/canonical
```

One command lands both sources of this pass (Dead.net and Deadhead High): 512
rows into `data/canonical/resources.csv`, 447 into `resource_songs.csv`, 19
into `resource_shows.csv`, every existing row untouched, and the two held
queues rewritten. A rerun over unchanged raw files adds nothing.
