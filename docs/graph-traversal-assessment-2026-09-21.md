# Graph traversal assessment (2026-09-21)

A read-only review of how Deadbot retrieves and traverses connected domain
data: show → venue → setlist → performance → song → recording, show → guest →
person, song → performances → shows → eras, release → tracks → performances.
This is about the knowledge graph in Postgres and the tools over it, not the
LangGraph agent workflow. No code was changed for this review.

**Verdict: generally sound with specific inefficiencies.** The tool surface is
entity-shaped and returns real subgraphs; hydration is ID-grounded; batching
and a per-request query cache exist; no observed access pattern needs more
than three fixed hops. The inefficiencies are concentrated and cheap: two tools
dump whole tables, performance-level hydration is N+1, parallel tool calls
serialize on one database connection, a long song history cannot be sampled or
filtered, and one whole question family (frequency by year/era/venue) has no
tool at all. A graph database is not justified.

## How to pick this up

- Numbers below marked **measured** come from
  `scripts/measure_traversal_queries.py`, which loads the real canonical CSVs
  into the sqlite DB-API shim from `tests/test_postgres_store.py` and counts
  every SQL statement `PostgresCanonicalStore` issues. The SQL text is the
  production adapter's, so the counts are exact; latency is not measured. Run
  it before and after any change:

  ```bash
  PYTHONPATH=. .venv/bin/python scripts/measure_traversal_queries.py
  ```

- Numbers marked **estimate** are model-turn counts inferred from the prompt
  and tools. Seconds cited are from traces run 2026-09-08 against production
  Postgres, before streaming shipped, and are stale.
- Nothing in the repo records production latency, statement counts or token
  usage per tool call. `scripts/trace_stream.py` times only the client-visible
  stream. Every latency claim here is inference until the instrumentation in
  the plan below exists.
- Recommendations are ordered smallest first. Items 1–6 change no schema.

## 1. Current traversal architecture

### Storage

Every relationship is a plain foreign-key table in Postgres, imported from
`data/canonical/*.csv` by `schema/postgres.sql`. There is no graph database, no
recursive query, no view, and no materialized aggregate. `derived_observations`
(schema line 637) exists for precomputed facts; nothing in `deadbot/` reads it.

| Relationship | Table | Rows (2026-09-21) |
| --- | --- | --- |
| show → venue | `shows.venue_id` | 2,358 shows, 595 venues |
| show → setlist → song | `performances` (set, position, segue) | 39,774 |
| show → performer / guest | `show_performers` (540 guest rows, 145 guest people, 233 shows) | 26,265 |
| performance → guest (song-level) | `performance_performers` | 18 |
| show → recording → track | `recordings`, `performance_recordings` | 17,977 / 26,481 |
| performance → listen URL | `performance_links`, `show_links` | 26,473 / 3,875 |
| release → track → performance or song | `official_release_tracks`; `release_shows` and `official_release_track_performances` exist but no tool reads them | 10,492 |
| entity → lore | `resource_songs/shows/performances` → `resources` | 1,661 / 639 / 22 → 3,588 |
| person → band tenure | `band_memberships` | 13 |
| critic / fan picks | `selection_evidence` (JSON payload) | 78 |

Indexes cover every foreign key the tools use (schema lines 737–767).
Song → performances → shows is a two-hop indexed join.

### Access layer

`deadbot/postgres.py` fetches a bounded projection per entity, one query per
relation table, then hands the rows to the CSV-era shaping code in
`deadbot/data.py`:

- `show_context` (postgres.py 726–765): 13 queries.
- `song_context` (660–681): 9 queries.
- `performance_context` (767–798): 11 queries.
- `song_performance_profile` (683–693): 4 queries, one of which fetches every
  performance of every show the song was played at (8,232 rows for Eyes of
  the World) to compute set neighbors.
- `rows(table)` (336) is an unfiltered `SELECT *`.

A per-request cache keyed on SQL text plus parameters (postgres.py 26–51,
271–279) dedupes repeats. `deadbot/api.py` 239–319 carries one cache dict
across every stream step and into plan hydration.

The store holds a single psycopg connection (postgres.py 211–227). psycopg's
`Cursor.execute` takes the connection lock, so LangGraph's parallel tool
execution serializes at the database.

### Tools that traverse the graph (`deadbot/tools.py`)

| Tool | Line | Traversal |
| --- | --- | --- |
| `search_entities` | 385 | phrase → IDs across songs, people, venues, equipment, releases, shows; one query per table; pathways attached |
| `search_guest_musicians` | 475 | person → guest shows → venues → song credits; **reads seven whole tables** (488–496, 553) |
| `search_stored_resources` | 637 | text → resources → linked entities; **reads four whole tables** (664, 669) |
| `get_song` | 720 | song → writers, releases (cap 20), resources, arrangements, performance summary |
| `list_song_performances` | 774 | song → performances (paged 24, max 48) → show dates, listen URLs |
| `get_song_performance_profile` | 935 | song → count, endpoints, set neighbors |
| `get_song_notable_versions` | 1067 | song → performances → releases + selections (4 batched reads) |
| `get_album` | 844 | release → tracks → songs → live legacy per song (batched, 874–932) |
| `get_show` | 1294 | show → venue, setlist with listen URLs, performers, lineup, equipment, recording IDs, releases, resources, links |
| `get_performance` | 1518 | performance → song, show, credits, releases, links, recording tracks |
| `get_recording_reviews` | 1380 | show → recordings → archive.org ratings (one batched HTTP call, cap 8 identifiers) + reviews (one HTTP call) |
| `get_selections_for`, `get_show_selections`, `get_selection_signals` | 1093, 1317, 1331 | selection evidence → shows, performances |

### Query flow

```
question ──▶ model ──▶ search_entities ──▶ get_show / get_song / ... (≤8 rounds, config.py:80)
                │                                 │  JSON payloads (3–4k tokens each)
                └──── finish_response(plan of IDs) ──▶ finish.resolve_* ──▶ store.*_context (re-fetch)
                                                             └──▶ composition.* ──▶ blocks ──▶ browser
```

One model owns the turn (`deadbot/graph.py`). It researches with tools, then
calls `finish_response` with semantic units by ID. `deadbot/finish.py` checks
each ID appeared in this turn's tool output, re-fetches the entity, and
`deadbot/composition.py` hydrates the card. Grounding is by ID, so the plan
costs few tokens.

Division of labor: the database joins one hop at a time; Python does the
shaping and the second hop; the model chooses which entities to open, the
order of tool calls, and carries IDs between calls. Deterministic traversal
already done without the model: listen paths joined onto every performance
(data.py 348), pathways attached to every entity (pathways.py 194), one
rendition per year for a song unit (composition.py 262), notable versions per
song, live legacy per album track.

## 2. Evidence from representative questions

### "What shows did Branford Marsalis play with the Dead?"

Path: `search_entities` (17 queries, ~834 tokens) or `search_guest_musicians`
(10 queries, ~1,256 tokens) → `get_show` ×5 as the prompt instructs
(18/15/15/14/13 queries; 12–16k chars each, ~17k tokens total) →
`finish_response` with five `show_unit`s → hydration 15 queries with a warm
cache. **Measured**: ~90 SQL statements, 0 HTTP. **Estimate**: 2–3 model
turns. Sep 8 trace: 21s, 3 calls.

Notes: `search_guest_musicians` pulls 69,798 rows to answer this. The
full-sentence `search_entities` returns Branford as the 11th of 20 matches,
behind ten songs matched on "with" and "what". Hydrating five `show_unit`s
the model never opened with `get_show` costs 76 queries.

### "How did Eyes of the World evolve over the decades?"

Path: `search_entities` (16) → `get_song` (19 queries, ~3,839 tokens;
resources 7.9k chars and releases 5.7k chars are most of it) →
`get_song_notable_versions` (3 more, ~2,254 tokens; 66 versions, all from
official releases) → optionally `list_song_performances` (382 renditions =
16 pages at 24, 8 at 48; ~2k tokens each) → `get_performance` ×3–6 (9–10
queries each) → plan with `song_overview` (history facet) + `era_unit`s.
**Measured**: 60–180 SQL depending on route; four `era_unit`s of three
performances cost 119 hydration queries. **Estimate**: 4–6 model turns. Sep 8
analogue (Franklin's Tower): 47s, 5 calls.

Notes: the "evolution" traversal is not one operation. The model cannot see
all 382 renditions in 8 rounds, so its decade judgment rests on the summary,
the 66 released versions, and whatever `get_performance` calls it spends. The
server then picks one rendition per year deterministically, after the model
has already argued. Data gap seen in passing: `song_writers` has no row for
Eyes of the World (296 of 436 songs have writers), so a credits facet renders
empty.

### "Show me the setlist and best recording for 3/9/81."

Path: `get_show("1981-03-09")` (18 queries, ~3,092 tokens; 21 performances
with archive URLs are 6.9k of 12.4k chars) → `get_recording_reviews`
(2 queries + 2 archive.org HTTP calls) → one `show_unit` → ~5 hydration
queries. **Measured**: ~25 SQL, 2 HTTP. **Estimate**: 2–3 turns.

Notes: the best-served question. `get_show` returns recordings as a count plus
IDs, so "best" forces the review round trip, which is correct. The 8-identifier
cap in `site_search.py:322` means five of this show's 13 recordings are never
rated.

### "Which songs were most frequently played in 1977?"

Path: `search_entities` returns one song, one person and zero shows, because
the query is split on whitespace (tools.py 397) and the last token is `1977?`;
`1977` alone matches 60 shows. Even fixed, no tool counts performances by
year, era, tour or venue. The honest path is 60 `get_show` calls (~900
queries, ~200k tokens), which the 8-round bound forbids. **Outcome**: a gap
answer or an answer from model memory. This question family is unanswerable
today.

### "What guest performers appeared most often, and at which shows?"

Path: `search_guest_musicians("")` returns all 139 guests with every
appearance, sorted by count. **Measured**: 10 queries, 88,575 chars, ~22,000
tokens, above the 20k hard ceiling in `docs/architecture.md`. Then
`person_roster`s (hydration 3 batched queries). **Estimate**: 2 turns.

Notes: one call answers it by dumping the subgraph rather than aggregating.
The model cannot ask for "top 15 by count, then the shows for these three".

### Measured table

| Call | Queries | Full-table scans | Payload chars | ~tokens |
| --- | --- | --- | --- | --- |
| `search_entities` (full question) | 13–17 | 1–2 | 1,000–4,150 | 250–1,040 |
| `search_guest_musicians("Branford Marsalis")` | 10 | 8 | 5,025 | 1,256 |
| `search_guest_musicians("")` | 10 | 8 | 88,575 | 22,143 |
| `search_stored_resources("Eyes of the World")` | 4 | 4 | 17,111 | 4,277 |
| `get_show` (one show) | 13–18 | 1–2 | 11,258–16,460 | 2,814–4,115 |
| `get_song("Eyes of the World")` | 19 | 1 | 15,358 | 3,839 |
| `list_song_performances` page (warm / cold) | 1 / 10 | 0 | ~8,100 | ~2,030 |
| `get_song_notable_versions` (warm) | 3 | 1 | 9,018 | 2,254 |
| `get_performance` | 8–10 | 0 | 3,500–4,000 | ~900 |
| Hydrate 5 `show_unit`s (warm / cold) | 15 / 76 | | | |
| Hydrate `song_overview`, all facets (warm / cold) | 1 / 11 | | | |
| Hydrate 4 `era_unit`s × 3 performances | 119 | | | |
| Hydrate 3 `performance_unit`s | 38 | | | |
| Hydrate `person_roster` of 40 | 3 | | | |
| Fixed prefix: all tool schemas | | | 50,425 (finish_response 33,522) | ~12,600 |

## 3. Findings

### What works well (confirmed)

Entity tools return subgraphs, not table rows. Listen paths are pre-joined
onto every performance. Pathways are batched across a whole result set.
`get_song_notable_versions` and `get_album` live legacy are the graph-shaped
responses the design asks for. The per-request query cache, the response
cache, ID-level grounding with server hydration, and the "well-worn routes"
paragraph in the prompt (graph.py 62–71) all reduce model-mediated traversal.
The September 8 batching (search 191 → 6 queries, paging 825 → 1) is pinned by
`tests/test_latency_batching.py`.

### Issues, ranked

Format: severity / latency impact / token impact / effort / confidence.

1. **No aggregate or analytic traversal.** "Most played in 1977", "how often
   did X open a set", "which venues hosted the most guests" have no tool. The
   model must enumerate shows (impossible in 8 rounds) or guess. High / n.a. /
   n.a. / medium / confirmed (tools.py 1702–1729 is the full list).
2. **Two tools full-scan the largest tables per call.** `search_guest_musicians`
   reads people, shows, venues, songs, performances, performance_performers,
   show_performers whole (69,798 rows) every call; `search_stored_resources`
   reads four whole tables. High / high / low / low / confirmed.
3. **Parallel tool calls serialize on one connection.** Single psycopg
   connection (postgres.py 211–227); `Cursor.execute` locks it. The prompt's
   "request independent lookups together so they run in parallel" holds for
   HTTP tools only. Medium / medium-high / none / low / code confirmed,
   latency effect inferred.
4. **Performance-level hydration is N+1.** `era_unit` and `performance_unit`
   call `performance_context` per performance, 9–11 queries each, no batching
   (finish.py 701–725); `_set_neighbors` adds a filtered fetch plus a
   `store.one` per neighbor (composition.py 314, 331); `_show_lineup` one
   `store.one("people")` per performer row (897); `_song_overview` one per
   writer (1028). Measured: 119 queries for 12 performances. Medium / medium /
   none / low / confirmed.
5. **Cache misses between research and hydration are structural.**
   `show_context` fetches people with `IN (...)`, hydration with `= %s`, so
   identical rows miss the request cache; `_show_recordings` (972) re-queries.
   Low-medium / low / none / low / confirmed.
6. **Payload token cost.** `get_show` is 3–4k tokens, 55% of it performance
   entries carrying archive URLs the server re-hydrates anyway; five show
   units ≈ 17k tokens before the model writes a word; guest directory 22k;
   `get_song` spends 7.9k chars on resource metadata; fixed prefix ~12.6k
   tokens. Medium / medium / high / medium / measured.
7. **The model must know the schema and call order.** `search_entities`
   first; `get_show` before a `show_unit` or pay 76 queries;
   `list_song_performances` before naming representatives; `get_media_links`
   takes `'show'|'performance'`. The prompt spends ~40 lines on this.
   Medium / low / medium / medium / confirmed.
8. **`search_entities` ranking and tokenization.** Punctuation not stripped;
   matches truncated at 20 in fixed table order, so common-word songs push the
   person to position 11 and can push shows out (tools.py 397–456). Medium /
   low / low / very low / confirmed.
9. **Paging cannot reach a long song's history.** 382 renditions at 24 per
   page is 16 rounds against an 8-round budget; no filter by year, era or
   listen availability (tools.py 774). Medium / medium / medium / low /
   confirmed.
10. **`song_performance_profile` over-fetches.** 8,232 performance rows for
    Eyes to compute two neighbor counts (postgres.py 683–693). Low / medium
    for big songs / none / low / measured.
11. **No instrumentation.** No per-tool timing, statement count, bytes,
    payload size or token usage logged. Medium / n.a. / n.a. / low /
    confirmed.
12. **Unused relationship tables.** `release_shows` and
    `official_release_track_performances` are never read, so "which release is
    the complete show" is answered only through the legacy per-track
    `performance_id`. Low / none / none / low / confirmed.

## 4. Recommended improvements

Smallest first. Items 1–6 change no schema.

1. **Fix `search_entities` tokenization and ranking.** Strip punctuation
   before splitting; reserve at least two slots per entity type before
   filling by table order. `"…played in 1977?"` → phrase `1977` → 20 shows.
   Tradeoff none.
2. **Stop full-table scans in the two search tools.**
   `search_guest_musicians`: `WHERE role='guest'` (540 rows) then `rows_in`
   for the people, shows, venues and credits those rows name; for a named
   guest, resolve the person first and fetch only their assignments.
   `search_stored_resources`: push the match into SQL as `matching_rows_any`
   already does. Example: `search_guest_musicians("Branford")` → ~5 queries,
   ~30 rows instead of 10 queries, 69,798 rows. Tradeoff none; a
   `guest_appearances` view is optional.
3. **Aggregate mode for the guest tool.** `detail="summary"` returns
   `[{person_id, name, guest_show_count, first_year, last_year,
   instruments}]` for all 139 guests in ~3k tokens; `detail="appearances"`
   for a named guest keeps today's shape. Removes the 22k-token dump.
4. **Batch hydration.** Add `performance_contexts(ids)` to the store (one `IN`
   per relation, as `_album_live_legacy` does); use it for `era_unit`,
   `performance_unit`, `song_overview` representatives; replace per-row
   `store.one` in `_show_lineup`, `_set_neighbors`, `_song_overview` credits
   with `rows_in`; make `show_context` and hydration issue the same SQL shape
   so the request cache hits. Expected 119 → ~12 queries for four era units;
   76 → ~30 for five cold show units. Tradeoff none.
5. **Connection pool.** `psycopg_pool.ConnectionPool(min_size=1, max_size=4)`
   in the store's DSN factory path, or a connection per thread, so parallel
   tool calls are parallel at the database. Keep the pool small and lazy on
   Vercel; use the pooled Neon DSN. Tradeoff: more connections.
6. **Filters on `list_song_performances`.** Add `year_from`, `year_to`,
   `sample="per_year"|"all"`, `with_listen_only`. Example:
   `list_song_performances("song-eyes-of-the-world", sample="per_year")` →
   22 renditions, one per year, each with a listen URL, ~2k tokens, one call.
   This is the `get_song_performance_history(song_id, filters)` hypothesis,
   and the code supports it: `_song_history` already computes it after the
   model has finished. Tradeoff: one more parameter to teach.
7. **One analytic tool: `count_performances(group_by, filters)`.**
   `group_by ∈ {song, year, era, venue, tour, set_position}`; filters on year
   range, song, venue, guest present, set number; returns counts with
   denominators. Example input `count_performances(group_by="song",
   year_from=1977, year_to=1977, limit=25)`; output
   `{"denominator": {"shows": 60, "performances": N}, "rows": [{"song_id",
   "title", "count", "share_of_shows"}]}` from one `GROUP BY`, ~1k tokens.
   The only query-shaped tool recommended, because the question family is
   real, deterministic, and impossible today. Keep the enums closed. Schema:
   no; a `performance_facts` view (performance × show year, era, venue, tour)
   makes it one line of SQL. Do not build `query_connected_entities`: nothing
   observed needs arbitrary path expressions and its output would be the
   table dump the design already avoids.
8. **Trim `get_show` and `get_song` payloads.** Return each performance as
   `{performance_id, song_id, title, set, pos, segue, listen: ["archive",
   "spotify"]}` with URLs left to hydration; move `band_memberships` behind
   the `lineup` facet; cap `get_song` resources at 5 with a count. Expected
   `get_show` 12.4k → ~6k chars; five shows save ~8k tokens per turn.
   Tradeoff: the model cannot paste an archive URL into `chat_answer` without
   `get_performance`; check the evals for how often it does.
9. **Precompute song profiles.** Per-song count, first/last, per-year counts
   and top set neighbors in a `song_profiles` materialized view refreshed at
   import, or in `derived_observations`, which was built for this. `get_song`
   19 → ~10 queries and never fetches 8,232 rows. Schema: a view or
   observation rows; no canonical change.
10. **On the hypothesised tools.** `get_show` already is `get_show_context`.
    `get_guest_appearances` is `search_guest_musicians`. A batched
    `get_performances(ids)` (item 4 exposed as a tool) is the honest form of
    `compare_performances`: the data has no per-performance tempo or duration
    except on release and recording tracks, so "compare" would return
    contexts side by side and nothing more.

## 5. Prioritized plan

**Immediate (days, no schema change):** items 1, 2, 3, 4, 5. Removes the
69,798-row scan, the 22k-token dump, ~100 hydration queries on a song-history
page, and lets parallel tool calls run in parallel.

**Near-term (a sprint):** items 6, 7, 8, 9. Filters and `count_performances`
move the two deterministic traversals the model mediates by hand (sampling a
song's history, ranking by frequency) into SQL. Payload trimming and the
song-profile view cut per-turn tokens and the largest remaining fetch.

**Instrumentation to validate:** wrap `PostgresCanonicalStore._execute` to
record statement count, rows, bytes and milliseconds per tool call; record
each tool's payload chars; capture `usage_metadata` per model call; emit one
JSON line per request with those plus wall time to first answer and to
response. Check the architecture doc's own targets (p95 packet under 10k
tokens, ceiling 20k) against the eval suites in `evals/`. Rerun
`scripts/measure_traversal_queries.py` after each change; add its key counts
to `tests/test_latency_batching.py` as they improve.

**When a graph database would become worthwhile:** only if the question mix
shifts toward variable-length or pattern paths Postgres handles poorly
("segue chains of three or more across the 1973 tour", "songs within two
positions of Dark Star in any second set", setlist-shape similarity across
shows) and those become a large share of traffic. Try a recursive CTE over
`performances (show_id, set_number, position_in_set)` first; the table is
40k rows and fully indexed. The other trigger is `count_performances`
sprawling into an open-ended query language. Neither condition is present.

## Not verified

- Production latency per query and per tool call.
- How often the live model follows the `get_show`-before-`show_unit` route.
- Whether Vercel sets `DEADBOT_OPENAI_REASONING_EFFORT`.
