# Model-selected data visualizations — Batch 4: review fixes and evals

## Context

Batches 1-3 live on branch `claude/model-selected-data-visualizations-c8b239`
(PR #57, still open). **Do this work on that branch**, in its worktree
`.claude/worktrees/model-selected-data-visualizations-c8b239`; this plan file
was written from a review worktree and should be copied into that branch's
`docs/superpowers/plans/` with the first commit.

An Opus review found the architecture sound but several decisions that work
against AGENTS.md's "keep the model in charge" rules, plus two
data-correctness bugs. This batch fixes them in three tasks:

- **Task A — the tool** (`aggregate_data` and both stores): give the model the
  setlist-coverage facts it currently can't see, make `total` correct, make
  the Postgres and CSV stores agree on missing records, cut dead options, and
  drop the fixed caveat copy.
- **Task B — the chart contract** (`DataChartRef` → `DataChartBlock` →
  `DataChart.tsx`): the model supplies only the aggregation, a title and a
  note; the server derives everything structural; the renderer drops the
  caveat line and follows the colour system.
- **Task C — evals**: a new suite of representative chart questions, so the
  prompt and tools are tuned against evidence rather than one example.

Order: **A first. Then B and C in parallel** (B touches finish/composition/
experience/web; C touches only `evals/` and at most `tests/test_evaluations.py`).

### Measured facts this batch is built on

Run against `data/canonical` on 2026-09-22:

| Year | Shows on record | Shows with at least one performance row |
|---|---|---|
| 1965 | 12 | 2 |
| 1966 | 113 | 32 |
| 1967 | 139 | 41 |
| 1968 | 126 | 69 |
| 1969 | 149 | 124 |
| 1970 | 145 | 135 |
| 1971 onward | — | equal to shows on record |

So every performance count before 1971 describes surviving setlists, not
everything played — and that is exactly the Dark Star peak. Today the model
cannot see this. Meanwhile every chart carries a generic "Based on
performances represented in Deadbot" line that tells the visitor nothing.

`performances` grouped by `year` with `measure=distinct_songs` currently
returns `total: 3099` because `total` is the sum of the rows; the catalogue has
a few hundred songs. The sum is only meaningful for some measure/group
combinations.

## Global constraints (unchanged from Batches 1-3 unless stated)

- Read AGENTS.md before starting. Deterministic code does transport and
  structural integrity only. The model decides relevance, framing and what to
  say about coverage; code supplies the facts.
- Prompt and tool-description text is written as what to do, never as a
  "do not" list (owner's rule: negative rules give the model ideas).
- No model-authored SQL or identifiers reach the database. Table/column names
  come from literal spec tables through `_identifier()` / `_qualified_table()`;
  every value is a bound `%s` parameter.
- Both stores (`deadbot/data.py` `CanonicalStore.aggregate`, and
  `deadbot/postgres.py` `PostgresCanonicalStore.aggregate`) must return
  identical payloads for identical requests. Parity tests in
  `tests/test_postgres_store.py` (sqlite-backed) prove it.
- Tools never raise; errors return `_json({"error": ..., "detail": ...})`.
- After any `deadbot/experience.py` change:
  `/Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py`
  then `npm run gen:types --prefix web`. CI fails on a stale
  `web/src/generated/api.ts`.
- Tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`
  (full suite before each task's final commit); web: `npm test --prefix web`
  and `npm run build --prefix web`.
- **The worktree has an uncommitted `web/package-lock.json` diff that predates
  this batch.** Do not stage it. Stage files by name; never `git add -A` / `.`.
  Report it in your final message.
- Never push. Never run bare `git stash`.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Keep commits scoped to the task. No drive-by refactors.

---

## Task A — the tool

Files: `deadbot/aggregation.py`, `deadbot/data.py`, `deadbot/postgres.py`,
`deadbot/tools.py`, `deadbot/progress.py`, `deadbot/graph.py`,
`deadbot/composition.py` (one-line change, A5), `tests/test_aggregation.py`,
`tests/test_postgres_store.py`, `tests/test_research_tools.py`,
`tests/test_progress.py`.

### A1. Remove dead options

- Remove `"average_duration"` from `Measure` and delete its validator branch.
  Leave one plain code comment (not model-facing) in `aggregation.py` saying
  duration is not offered because recording-derived duration covers 66.5% of
  performances, so the reasoning isn't lost.
- Remove the `performance_id` filter everywhere: `AggregationFilters`,
  `_DATASET_FILTERS`, the `provided` tuple, `_AGGREGATE_FILTER_COLUMNS`,
  the CSV loop, the `aggregate_data` signature and docstring. (Filtering
  performances to one performance always counts 1.)
- Update tests that referenced either.

### A2. Make `total` correct

`total` becomes **the measure computed over the whole filtered set**, not the
sum of rows: `count` → number of facts; `distinct_shows` → distinct shows
across all groups; `distinct_songs` → distinct songs across all groups.

- It covers exactly the facts that entered a group (for `group_by="year"`,
  facts with no derivable year are excluded from both groups and total), and
  it is computed before `limit`.
- `assemble_result(request, raw_rows, date_range, total)` takes `total` from
  the store instead of summing.
- CSV store: compute from the grouped facts.
- Postgres store: one extra query,
  `SELECT {measure_sql} AS total FROM {from_sql} {join_sql} {where_sql}` using
  the same `where_sql` / params as the grouped query (so it sees the same rows).
- Tests: `distinct_songs` by year has `total` equal to the number of distinct
  songs in the fixture, strictly less than the row sum; `distinct_shows` by
  song likewise; `count` totals unchanged. Parity test for each.
- In the tool docstring, one sentence: `total` is the measure across the whole
  filtered set (for example distinct songs across every year), including rows
  beyond `limit`.

### A3. Make the stores agree on missing records

Postgres uses inner joins to `venues`, `songs`, `people`, so a fact whose
dimension record is missing disappears; the CSV store keeps it. Rule for both:

- `LEFT JOIN` the dimension table.
- Label fallback: the record's name/title → the id → `"Unknown"` when the id
  is blank. (`_query` returns SQL NULL as `""`; the CSV reader also gives `""`
  for a blank cell, so treat `""` as blank in both.)
- City keeps its existing `COALESCE(NULLIF(city,''),'Unknown')`, now over the
  LEFT JOIN.
- Add parity fixtures: a show whose `venue_id` is not in `venues`; a show with
  a blank `venue_id`; a performance whose `song_id` is not in `songs`; a guest
  row whose `person_id` is not in `people`. Assert both stores return the same
  rows and totals for venue, city, song and guest grouping.

### A4. Give the model setlist coverage

Add a `setlist_coverage` object to every `performances` result (only that
dataset; lineup coverage for `guest_appearances` is a different question and
out of scope):

```json
"setlist_coverage": {
  "shows_on_record": 2358,
  "shows_with_setlist": 2076,
  "by_year": [{"year": 1966, "shows_on_record": 113, "shows_with_setlist": 32}]
}
```

- Computed over shows that match the **show-level** filters only (`venue_id`,
  `year`, `year_from`, `year_to`); `song_id`/`show_id` don't change whether a
  setlist survives.
- `shows_with_setlist` = shows with at least one `performances` row.
- `by_year` lists every year in range, chronological, no filtering or
  thresholding — the model decides what matters.
- Shared shaping lives in `aggregation.py`; each store supplies the counts
  (CSV loop; Postgres one grouped query over `shows` LEFT JOIN a
  `SELECT DISTINCT show_id FROM performances` subquery). Parity test.
- `setlist_coverage` is tool output for the model. It is **not** copied into
  `DataChartBlock` (Task B does not add it).

### A5. Drop the fixed caveat copy

- Delete `_SCOPE_NOTES`, and `scope_note` from `AggregationSpec`,
  `AggregationResult` and `to_payload()`.
- Metric labels become plain nouns:

  | (dataset, measure) | label |
  |---|---|
  | shows, count | Shows |
  | performances, count | Performances |
  | performances, distinct_shows | Shows |
  | performances, distinct_songs | Songs |
  | guest_appearances, count | Guest appearances |
  | guest_appearances, distinct_shows | Shows with a guest |

- `progress.py` labels: drop "known" ("Counting performances", etc.).
- Task B removes `DataChartBlock.scope_note`. Until then,
  `composition._data_chart` would return `None` for a payload with no
  `scope_note`. In Task A make the minimal change there to stop requiring it
  (pass `scope_note=""`) so the full suite stays green.

### A6. Tell the model what the coverage means

In `deadbot/graph.py`'s "Cross-show patterns" paragraph, add (adjust wording
to fit; keep it affirmative and short):

> Performance results also carry setlist_coverage: how many shows are on
> record each year and how many have a surviving setlist. Read the counts
> against it. Where many shows lack a setlist, the count describes the
> surviving setlists, and saying so in plain words keeps the pattern honest.

Mirror one sentence in the `aggregate_data` docstring describing the field.

Commit A as one or two commits. Report the before/after `total` for
`performances`/`year`/`distinct_songs` on real data.

---

## Task B — the chart contract

Files: `deadbot/finish.py`, `deadbot/composition.py`, `deadbot/experience.py`,
`deadbot/graph.py`, `web/openapi.json`, `web/src/generated/api.ts`,
`web/src/DataChart.tsx`, `web/src/DataChart.test.tsx`, `web/src/styles.css`,
`web/src/visual-fixtures.ts`, `tests/test_finish.py`, `tests/test_experience.py`.

### B1. The model supplies only what is editorial

`DataChartRef` keeps: `type`, `aggregation_id`, `title` (inherited from
`_Ref`), `note`. Remove `chart`, `orientation`, `x_field`, `y_field`,
`series_field`, `x_label`, `y_label`.

Rewrite its docstring affirmatively, roughly:

> A chart of one aggregate_data result from this turn. The server draws it:
> bars over time for a year result, ranked bars for a song, venue, city or
> guest result. Your title names the pattern; your note says what it means.

Title description: name the pattern the visitor should see ("Dark Star's
1969 peak"), not the metric.

### B2. The server derives what is structural

`composition._data_chart(payload, *, title, note)`:

- `orientation` = `"vertical"` when the dimension column is temporal, else
  `"horizontal"`.
- The renderer finds the dimension column itself (the one whose key isn't
  `"value"`), so `x_field` / `y_field` leave the block entirely.
- Keep the payload shape and finite-number checks (they guard transport).
  Drop the checks that existed only to reject model field choices.

`DataChartBlock`: remove `scope_note`, `x_field`, `y_field`, `x_label`,
`y_label`; `chart` becomes `Literal["bar"]`. Keep `orientation`, `columns`,
`rows`, `metric_label`, `total`, `excluded_count`, `date_range`,
`empty_reason`, `title`, `note`, `aggregation_id`.

Update the `graph.py` palette sentence about `data_chart` if it mentions the
removed fields. Regenerate `openapi.json` and generated types.

### B3. Renderer

In `DataChart.tsx`:

- Remove the `stacked_bar` guard, the `x_field`/`y_field` guards, the
  `scope_note` paragraph and axis-label props. Use the dimension column's key
  and `"value"` directly.
- `chartDescription` drops the scope sentence.
- `CoverageDetail` ("Top 10 of 24 venues") stays; it is how a sighted reader
  learns rows were left out.
- **Colour (owner approved 2026-09-22):** bars use `var(--muted)`
  instead of `var(--violet)`. The design system reserves colour for actions
  (gold listens, rose reads, blue asks); a bar is none of those. Hover cursor
  stays `var(--hair)`.
- **Corners:** `radius` uses 2px at the data end (`[2, 2, 0, 0]` vertical,
  `[0, 2, 2, 0]` horizontal), matching `--r`.

Update `visual-fixtures.ts` and `DataChart.test.tsx` for the new shape
(delete tests for removed guards; keep tests for empty state, table, tooltip,
truncation, excluded-count copy). Update Python tests for the new Ref/Block.

Verify: `npm test`, `npm run build`, full pytest, and the fixture renders
(the `?fixture=` name Batch 3 added) — the controller checks it in the browser.

---

## Task C — evals

Files: new `evals/data-charts-v1.json`; `tests/test_evaluations.py` only if
it needs to load the new suite.

Follow the existing suite format (`evals/veneta-v1.json`): every case has
`id`, `category`, `question`, `tool`, `arguments`, `expected`
(`equals` / `contains`), and `failure_conditions`. The `tool`/`arguments` are
the call a good answer would make; the deterministic runner checks that call's
output, and `--model` runs the question for manual review.

Cases (compute the current values from real data and pin them; say in the
suite `description` that pinned counts move when data passes add setlists):

1. `dark-star-by-year` — "How often did they play Dark Star each year?"
   `performances`/`year`/`count`, `song_id: song-dark-star`. Expect rows
   contain `{"year": 1969}`, `metric_label == "Performances"`,
   `setlist_coverage.by_year` contains `{"year": 1968, "shows_with_setlist": 69}`.
   Failure conditions: no `data_chart` in the body; numbers in the answer
   differ from the chart; presents 1966-1968 as complete counts without
   saying how few setlists survive.
2. `top-venues` — "Which venues did the Dead play most often?"
   `shows`/`venue`/`count`, `limit: 10`. Pin the first row's label and value
   and `excluded_count`. Failure: invents counts; chart and prose disagree.
3. `song-variety-over-time` — "How did the number of different songs they
   played change over the years?" `performances`/`year`/`distinct_songs`.
   Pin `total` (post-A2 value). Failure: states the row sum as the number of
   songs; ignores the thin early setlists.
4. `dark-star-vs-pitb` — "Compare Dark Star and Playing in the Band over
   time." Tool call for Dark Star as in case 1 (the model will need two).
   Failure: fabricates numbers for either song; shows one song only without
   saying so. (Measures the missing multi-series capability.)
5. `veneta-no-chart` — "What happened at the Veneta show?" (negative control)
   `search_entities` `{"query": "1972-08-27"}`, expect match `gd-1972-08-27`.
   Failure: adds a `data_chart` to a single-show answer.

Run the deterministic suite:
`PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m deadbot.cli evaluate --suite evals/data-charts-v1.json`
— all must pass.

Then attempt the model run:
`PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m deadbot.cli evaluate --suite evals/data-charts-v1.json --model --output <scratch>/data-charts-model.json`.
If it can't reach a model (keys, network), stop and report that; do not
fake results. If it runs, report per case: tool calls made, body block types,
and your read of each failure condition. Don't change prompts or code in
response — the controller decides what to tune.

Commit the suite (not the model output).

---

## Final review (controller)

One Opus review of the whole branch diff against this plan and AGENTS.md,
one fix wave, then a browser check of the fixture and one live question. Then
the owner pushes and PR #57 is updated.
