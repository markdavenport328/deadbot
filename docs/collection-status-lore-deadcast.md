# Collection status: Good Ol' Grateful Deadcast episode index (2026-09-11)

Indexes every published episode of the official Good Ol' Grateful Deadcast
podcast as a metadata-only stored resource, and maps it, conservatively, to
canonical shows and songs.

- Collector: `scripts/collect/collect_deadcast_episode_index.py`
- Normalizer: `scripts/normalize/normalize_deadcast_episodes.py`
- Raw: `data/raw/resources/deadcast-episode-index.jsonl` (first line is the
  pass metadata, one line per episode after it)
- Held queue: `data/editorial/lore-mapping-held-deadcast.jsonl`
- Registry: `deadcast-metadata` in `data/source_registry.json`, extended to
  `-v2` to add `/deadcast-index` to its allowed read paths
- Canonical: appended rows in `data/canonical/resources.csv`,
  `resource_songs.csv`, `resource_shows.csv`

This pass changes CSVs, the raw file, the registry and docs only. Production
PostgreSQL is loaded by the owner's import step
(`deadbot/postgres_import.py`); nothing here writes to a database.

## What is stored, and what is not

A stored record keeps the episode's title, its URL, the season heading it is
filed under on the site's own archive listing, its publish date, the HTTP
status and the retrieval time. No transcript, episode description, guest
list or audio is read into any file. `notes` states the series and season and
the retention boundary; nothing else from the site is retained.

## Discovery: one page, not 130 requests

`https://www.dead.net/deadcast-index` is Dead.net's own unpaginated episode
archive: every episode published so far — 129 of them across 13 seasons — is
listed on this single page, each row carrying its URL, title and publish date
under an `<h3>Season N</h3>` heading. One request therefore yields the whole
catalog's title/URL/season/date fields; no per-episode request is needed to
discover them.

Two representative episode pages (`blues-allah-50-slipknot` and
`independence-ball-7366`) were fetched by hand during development to check
this was safe: each page's own `<title>` matched the index row's title text
exactly, and each page's meta description was the same site-wide boilerplate
("The Good Ol' Grateful Deadcast is the first official Grateful Dead
podcast...") rather than episode-specific text. A per-episode fetch would
therefore return no information beyond what the index row already carries, so
this pass makes two requests in total — `robots.txt` and `/deadcast-index` —
rather than 131. That finding, and the two URLs checked, are recorded in the
raw file's pass metadata (`per_episode_page_fetch_rationale`) rather than
assumed silently.

`robots.txt` (HTTP 200) permits both `/deadcast` and `/deadcast-index`, with
no `Crawl-delay`. The registry's `deadcast-metadata` entry only listed
`/deadcast` before this pass; it is extended to `-v2` to add
`/deadcast-index`, per the task's own instruction to extend
`operation_policies` only if an index or pagination path was needed. Its rate
policy (one request per ten seconds, descriptive User-Agent) is honored
regardless — this pass needed only the two requests above.

## What was collected and mapped

| Measure | Count |
| --- | --- |
| Episodes indexed | 129 |
| Seasons | 13 |
| Already cataloged (URL already in `resources.csv`) | 3 |
| New `resources.csv` rows | 126 |
| Mapped to a canonical show | 4 episodes (4 distinct shows) |
| Mapped to a canonical song | 36 episodes (37 `resource_songs` rows, 37 distinct songs) |
| Held for review | 1 |
| Unmapped (still a resource; no relationship) | 85 |

`resource_type` is `podcast-episode` for every new row, per the task's
instruction. The three already-cataloged URLs are the two Veneta episode
pages (`resource-deadcast-veneta-part-1`, `resource-deadcast-veneta-part-2`)
and the Sugar Magnolia episode page
(`resource-deadcast-american-beauty-sugar-magnolia`), all three added in an
earlier, manually-curated pass under different resource ids. Their rows and
relationships are left exactly as they were; this pass neither rewrites nor
duplicates them. (Three other pre-existing Deadcast rows —
`resource-deadcast-blues-for-allah-slipknot`, `resource-deadnet-ace-50`,
`resource-deadnet-bear-drops-la-66` — point at the site's separate transcript
pages, e.g. `https://www.dead.net/blues-allah-50-slipknot`, not the episode
player page `https://www.dead.net/deadcast/blues-allah-50-slipknot`; those are
different URLs for different pages, so this pass adds a second, distinct
resource row for the episode page alongside the existing transcript-page
row.)

`relationship_type` is `show-oral-history` for a show row and
`song-history-and-interview` for a song row, matching the relationship types
the six pre-existing Deadcast rows already use.

## Mapping rules as implemented

**Show.** The full episode title is scanned with the same date parser the
research-blog normalizer uses (`find_dates`): `YYYY-MM-DD`, `M/D/YY`,
`M/D/YYYY`, `Month D, YYYY`. Exactly one parsed date matching exactly one
canonical show maps, with the basis "The episode title names the show date."
Two parsed dates, or a date matching two canonical shows, is held. A title
giving only a month and year (Deadcast often does — "Friend Of the Devils:
Florida, 4/78", "In and Out Of The Garden: Madison Square Garden, 3/81") or
only a month and day with no year ("Here Comes Sunshine: RFK Stadium, 6/73")
yields no parsed date at all, so the episode is left unmapped rather than
guessed at — the task's own instruction not to map from a guess about the
episode's content. Four episodes mapped this way: Independence Ball
(`gd-1966-07-03`) and three of the five "Here Comes Sunshine" 1973 episodes
that spell a full date (Des Moines 5/13/73, Santa Barbara 5/20/73, Kezar
Stadium 5/26/73).

**Song.** The text after the title's *last* colon is read as the episode's
stated subject — "Blues For Allah 50: Slipknot!" → "Slipknot!"; a title with
no colon uses the whole title. That segment is compared to every canonical
song's `match_key` (shared with the Dead.net essay normalizer: apostrophes
removed, `&` read as "and", punctuation and stopwords dropped, `-ing`/`-in'`
treated alike). An exact match maps, with the basis "The episode title names
the song." A segment whose key matches more than one canonical song is held.
A segment containing "/" (e.g. "Till the Morning Comes / To Lay Me Down") is
also split on the slash and each part tried the same way, so a paired
reference maps to both songs — one episode, two `resource_songs` rows.
Finally, a segment that exactly *prefixes* one or more canonical song keys
without matching any of them whole is held with those candidates: "Wake Of
The Flood 50: Weather Report Suite" prefixes both `Weather Report Suite Part
1` and `Weather Report Suite Prelude`, the same ambiguity the Dead.net essay
pass held its own "Weather Report Suite" essay for. Anything else — a
segment naming no canonical song at all ("Ace 50", "Bobby 75", "Garcia",
"T.C.", "Enter Keith Godchaux", side/date names like "Side A" or "Prelude/
Tuesday Night Jam") — is left unmapped, not held, since there is no
song-shaped reference to flag.

## Held for review — 1 episode

Written to `data/editorial/lore-mapping-held-deadcast.jsonl`:

| Episode | URL | Reason | Candidates |
| --- | --- | --- | --- |
| Wake Of The Flood 50: Weather Report Suite | `/deadcast/wake-flood-50-weather-report-suite` | The episode title's subject matches more than one canonical song. | `song-weather-report-suite-part-1`, `song-weather-report-suite-prelude` |

## Known limitations

- **A segment that only partly names a canonical song stays unmapped.**
  "Blues For Allah 50: King Solomon's Marbles/Stronger Than Dirt or Milkin'
  The Turkey" splits into "King Solomon's Marbles" (no canonical song) and
  "Stronger Than Dirt or Milkin' The Turkey" (canonical `Stronger Than Dirt`
  plus trailing words the exact-match rule does not strip), so neither half
  maps even though the episode plainly covers `song-stronger-than-dirt`. This
  is the same conservative trade-off the blog-post and Dead.net essay passes
  made: an exact, reviewable rule over a fuzzier one that could attach a song
  an episode never actually centers on.
- **A bare month/year or month/day names no single show.** Five "Friend Of
  the Devils" episodes (Florida, Atlanta, Duke, Virginia, West Virginia, all
  "4/78"), three "Summer Magic 1985" episodes ("6/14-6/16", "6/27", "6/28",
  "6/30 & 7/1"), "In and Out Of The Garden" (MSG "3/81", "9/82", "10/83"), the
  Sufi Choir episode ("3/71") and one "Here Comes Sunshine" episode (RFK,
  "6/73") are each plainly about one specific show, but their titles do not
  spell a full date, so this pass leaves all of them unmapped rather than
  infer the missing day or year.
- **The archive listing is not provably complete going forward.** A future
  episode published after this pass's retrieval time is simply not in the
  raw file yet; rerunning the collector picks it up on the next pass, and the
  normalizer's URL-based idempotency means the rerun only adds what is new.

## Validation

- Foreign keys: every appended `song_id`, `show_id` and `resource_id`
  resolves; no duplicate resource id, source URL, or `(resource_id,
  entity_id, relationship_type)` triple.
- Idempotency: rerunning the collector and then the normalizer over
  unchanged input leaves all three CSVs and the held queue byte-identical
  (verified directly: a second normalizer run reports 0 new resources, 0 new
  relationship rows, and the same 1 held entry).
- Tests: `tests/test_collect_deadcast_episode_index.py` (2) and
  `tests/test_normalize_deadcast_episodes.py` (8), both fixture-only.
- `PYTHONPATH=. pytest -q` passes after this pass (one pre-existing,
  unrelated failure remains: `tests/test_evaluations.py::
  test_evaluate_cli_exits_non_zero_when_a_case_fails` requires
  `DEADBOT_DATABASE_URL`, which this worktree does not have configured).
