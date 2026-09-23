# Summaries first, catalog queries for sets: design

Date: 2026-09-23. Status: approved in conversation. Written for the owner's review.
Branch: `claude/tool-detail-levels`, stacked on `claude/neon-sqlite-migration-da5cee` ([markdavenport328/deadbot#58](https://github.com/markdavenport328/deadbot/pull/58)). This design needs the SQLite store from that branch.

## The problem

Asking "Which official releases cover 1972?" locally on 2026-09-23 took 50 seconds before the model wrote a word. A reworded rerun then failed on OpenAI's rate limit. The trace:

- 0–30 s: about 20 `search_entities` calls over five rounds, because the model had no way to ask about a *set* of releases.
- 30 s: eight `get_album` calls in one round. `get_album` always returns every track with a per-song stage history attached. *Europe '72: The Complete Recordings* is about 33,000 tokens (578 tracks), *Complete Road Trips* 27,000 and *Enjoying the Ride* 23,000. The median release is about 1,400.
- 30–50 s: one round took 20 seconds.
- 51 s: the next model call requested **374,000 input tokens**, because every round resends everything read so far. It exceeded the organization's 500,000 tokens-per-minute limit.

The question was about albums. It never needed a tracklist.

The graph-traversal assessment ([docs/graph-traversal-assessment-2026-09-21.md](../../graph-traversal-assessment-2026-09-21.md), [markdavenport328/deadbot#56](https://github.com/markdavenport328/deadbot/pull/56)) reached the same diagnosis from other questions:
- tools return whole subgraphs when a summary would do (the guest lookup at 22,000 tokens, `get_show` at 3–4k);
- no tool can find or count across a set ("most played in 1977" is unanswerable today);
- nothing enforces the architecture doc's packet ceiling ("measured p95 below 10,000 tokens and a hard ceiling of 20,000 tokens").

## Principle

The answer is to equip the model, not to script it. The project's rules (AGENTS.md) say to give the model clear context and rich tools and let it decide, rather than encoding question-specific choices in code. So this design gives the model two general capabilities and one general habit:

1. **Summaries first, detail on request.** A lookup returns what a thing is and what is available about it. The model asks for heavy parts by name when its answer will use them.
2. **Find and count by querying.** Questions about sets ("which", "how many", "most") go to a read-only query tool over simplified catalog tables, not through opening entities one by one.
3. **One general line in the persona:** survey first, then open detail only on the items the answer will use.

Code enforces only structure: default shapes, a size ceiling that says what it cut, and query guardrails. Code never decides content based on the question.

## Scope

In this round:
- Album lookup: summary and detail.
- A catalog query tool with simplified tables.
- A size ceiling on every tool result.
- The persona line.
- Per-turn measurement.
- Evaluations.

Next round, informed by these measurements: the same summary and detail pattern for `get_show`, `get_song`, `get_performance` and `search_guest_musicians`, plus the other traversal-assessment fixes.

Out of scope:
- Frontend changes.
- Postgres support for the query tool. Postgres is being retired (plan Task 7 of the SQLite migration). The query tool is registered only when the store supports it.
- A bespoke release-list tool or `count_performances` tool. The query tool replaces both.

## Design

### 1. `get_album`: summary by default, detail on request

New signature: `get_album(release_id_or_title: str, include: list[str] | None = None, show: str | None = None)`.

**Summary (no `include`).** The result carries:
- `release`: title, artist, release date, type, links and notes, as today.
- `track_count` and `total_duration_seconds` (where durations exist).
- `contents`:
  - **Live release:** `shows`, one entry per show the release's tracks come from, in date order: `show_id`, `show_date`, `venue_name`, `city`, `track_count`. Tracks that name no performance (intros, tuning) are counted under `unattributed_track_count`.
  - **Studio release:** `songs`, one entry per distinct song in track order: `song_id` and `title`.
- `personnel`, as today (short).
- `pathways`, as today.
- `available`, one entry per detail not included, each saying what it is, how big it is, and how to ask for it. For example:
  ```json
  "available": {
    "tracks": {"count": 578, "ask": "include=[\"tracks\"]; narrow to one show with show=\"1972-05-26\""},
    "live_legacy": {"songs": 61, "ask": "include=[\"live_legacy\"]: each song's stage history and most-released performances"}
  }
  ```

The summary's IDs (`release_id`, `show_id`, `song_id`) are enough for the model to place album, show and song units on the page: [finish.py](../../../deadbot/finish.py) grounds plan references on IDs that appeared in this turn's tool output. `performance_id`s appear only with `tracks`.

**Details.**
- `include=["tracks"]` adds today's `tracks` list (track number, title, song, performance, duration, Spotify link). With `show="<show id or date>"`, it contains only that show's tracks. The show is resolved with `store.resolve_show`, and an unresolved show returns an error naming the release's shows.
- `include=["live_legacy"]` adds each track's `live_legacy` exactly as `_album_live_legacy` computes it today. This is now opt-in. It was attached to every album.
- Unknown `include` values return an error listing the valid ones. Details can be combined.

**Sizes (measured 2026-09-23 as `album_context` JSON ÷ 4).** *Europe '72: The Complete Recordings* drops from about 33,000 tokens to an estimated 1,500 (22 show rows). Studio albums shrink modestly, since their song lists stay.

### 2. `query_catalog`: read-only queries over simplified tables

**The tool.** `query_catalog(sql: str)` runs one read-only `SELECT` against the canonical SQLite database. It returns:
```json
{"columns": [...], "rows": [[...], ...], "row_count": 37, "truncated": false}
```
At most **200 rows** are returned. When more exist, `truncated` is true with a note to aggregate, filter or add a `LIMIT`.

**Simplified tables.** These are views, created in `schema/sqlite.sql` at build time. Each one pre-joins what questions usually need, so most queries are one table with a `WHERE`, `GROUP BY` and `ORDER BY`.
- `show_facts`: `show_id, show_date, year, venue_id, venue_name, city, state_region, country, tour_name, event_name, song_count`.
- `performance_facts`: `performance_id, song_id, song_title, show_id, show_date, year, venue_id, venue_name, city, tour_name, set_number, set_label, position_in_set, encore, segue_into_next`.
- `release_track_facts`: `release_id, release_title, release_type, release_date, track_number, track_title, song_id, song_title, performance_id, show_id, show_date, year, venue_id, venue_name, city`. Studio tracks have no show, so the show columns are NULL for them.
- `guest_appearances`: `show_id, show_date, year, person_id, person_name, role, instrument, venue_name, city`, from `show_performers` where `role = 'guest'` (540 rows; the only other role is `performer`).

`year` is the integer year of `show_date`. The base tables stay queryable for anything the views don't cover.

**The model's guide.** The tool description carries a compact guide, targeted under 2,500 characters because it is re-read on every model call:
- each view and its columns, one line each;
- the gotchas:
  - `release_date` may be partial ("1972" or "1972-05") and is text;
  - booleans are the text `'true'`/`'false'`;
  - dates are ISO text, so compare with strings or use `year`;
  - count shows with `COUNT(DISTINCT show_id)` when the question is about shows;
- two example queries: releases covering a year, and the most-played songs in a year;
- when to use it: "Use this to find or count things across the catalog. Then use the lookup tools for depth on the few items your answer will feature."

**Guardrails** (structural integrity only, never content):
- A dedicated connection opened `?mode=ro&immutable=1`, the same as the store.
- An authorizer that permits only reading: `SELECT`, `READ` and ordinary functions. `ATTACH`, `PRAGMA`, writes, `load_extension` and every other action are denied.
- One statement per call. SQLite's `execute` already rejects multiple statements.
- A progress handler that aborts after **1.5 seconds**.
- The 200-row cap, via `fetchmany(201)`.
- Errors (syntax, a denied action, a timeout, an unknown column) come back as `{"error": "<SQLite message>", "hint": "<one line>"}`, so the model can correct itself in one round.

**Placement.** `SqliteCanonicalStore.run_catalog_query(sql) -> dict` owns the connection and guardrails, reusing the store's path. [tools.py](../../../deadbot/tools.py) registers `query_catalog` only when the store has `run_catalog_query`. The CSV store, the Postgres store and test doubles do not get it.

Grounding needs no change. Query results that include IDs make those IDs available to the plan, because `grounded_context` collects every ID in tool output.

### 3. A size ceiling on every tool result

`_json` in tools.py enforces the architecture doc's hard ceiling: **80,000 characters**, about 20,000 tokens. When a serialized result exceeds it, the largest list in the payload is shortened, repeatedly, until the result fits. A `_truncated` entry is added naming each list's path, how many items were kept, the original total, and "narrow the request (a filter, a detail option, a smaller page or a query) to see the rest". Results under the ceiling are untouched.

This is transport integrity: it prevents another 374,000-token call. With sections 1 and 2 in place it should rarely fire, and the measurement in section 5 records every time it does.

### 4. Persona and tool descriptions

[graph.py](../../../deadbot/graph.py), `## RESEARCH THE ACTUAL QUESTION`. The additions are written as what to do, per the owner's prompt style:
- **Add:** "Work like a researcher. Lookups return a summary and list what more is available; open a detail only when your answer will use it. To find or count things across the catalog (which releases, how many times, the most), query it with query_catalog; to understand one thing deeply or put it on the page, look it up."
- **Update the well-worn route** "For a record's life on stage, get_album carries each track's live legacy" to name `include=["live_legacy"]`.
- **Add a well-worn route:** "For releases, shows or songs by year, venue or tour, query_catalog first, then get_album or get_show for the few you will feature."

The `get_album` docstring describes the summary, `available`, `include` and `show`.

### 5. Measurement

**Per-turn metrics.** The streaming endpoint (`_stream_events` in [api.py](../../../deadbot/api.py)) logs one JSON line per turn under the logger `deadbot.turn_metrics`:
- question;
- model call count;
- each call's input and output tokens (from `usage_metadata` where the provider supplies it);
- each tool call's name and result size in characters, plus whether the ceiling fired;
- seconds to the first answer text and to the final response;
- any error.

No request data beyond the question is logged. The API contract does not change.

**`scripts/measure_turns.py`.** Runs a question list in-process through `create_app` with the configured model and the response cache off. It captures the metrics lines and prints one row per question: rounds, peak input tokens, total input tokens, largest tool result, time to first answer, time to finish, and errors. The default question list:
- the 15 opening questions from `scripts/warm_answers.py`;
- four set questions:
  - "Which songs did they play most in 1977?"
  - "Which guest musicians sat in most often?"
  - "How often did Scarlet Begonias open the second set in the 1980s?"
  - "What live albums came from Winterland?"

**Baseline first.** The plan runs the script on the branch before any tool change, and saves the table to `docs/measurements/2026-09-23-baseline.md`. It runs it again after each step.

### 6. Evaluations

- **Deterministic cases** (new suite `evals/catalog-v1.json`, same format as `veneta-v1.json`):
  - `get_album` summary shape for *Europe '72: The Complete Recordings*: has `contents.shows` and `available.tracks`, has no `tracks`;
  - `include=["tracks"]` with `show` narrows the tracks;
  - `query_catalog` for releases covering 1972 contains the Europe '72 release ID;
  - `query_catalog` for the most-played songs in 1977 returns the same top song as an independent computation in the test;
  - a write attempt returns an error;
  - a runaway cross join returns a timeout error.
- **Model evaluations** (`deadbot evaluate --model`) on the set questions and a sample of opening questions, reviewed by reading the traces:
  - Did the model query instead of enumerating?
  - Were its numbers right? Check them against a hand-written query.
  - Did answer quality hold against the baseline?

## Success criteria

These are measured with `scripts/measure_turns.py`, not imposed as rules on the model:
1. "Which official releases cover 1972?" completes without a rate-limit error, with peak input under **60,000 tokens** per call and the first answer text sooner than baseline.
2. Across the question list, no tool result exceeds the ceiling unless it is recorded as truncated, and no call exceeds 100,000 input tokens.
3. The four set questions are answered with numbers that match a hand-written query.
4. Opening-question answers keep their quality on review: the same key facts, listening paths and cards as baseline.
5. All existing tests pass, and the new deterministic evaluation cases pass.

## Risks

- **Plausible but wrong queries.** The views and the guide exist to make the easy query the right one. The set-question checks in criterion 3 will show whether they're enough. If they aren't, improve the guide or the views, not question-specific code.
- **Guide cost.** The guide adds up to 2,500 characters to every call. That's measured and small next to the savings. If it grows, move the full guide behind an error hint and keep only the view list in the description.
- **The model over-queries**, running many small queries where one would do. The metrics record query counts per turn. Address it in the guide's examples if it appears.
- **Stacked branch.** This work merges after #58. If #58 changes before merge, rebase.
