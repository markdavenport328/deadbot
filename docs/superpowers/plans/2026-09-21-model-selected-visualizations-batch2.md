# Model-selected data visualizations — Batch 2: finish schema, grounding, hydration

## Context

Batch 1 (merged: see `docs/superpowers/plans/2026-09-21-model-selected-visualizations-batch1.md`)
added `deadbot/aggregation.py` (a constrained, server-validated
dataset/group_by/measure/filter contract) and matching `aggregate()` methods
on both canonical stores, exposed as the read-only `aggregate_data` tool.
Calling it returns a JSON payload shaped by `AggregationResult.to_payload()`:

```json
{
  "aggregation_id": "agg:<hash>",
  "query": {"dataset": "...", "group_by": "...", "measure": "...", "filters": {...}, "limit": 20, "fill_missing": false},
  "columns": [{"key": "year", "label": "Year", "type": "temporal"}, {"key": "value", "label": "Known performances", "type": "quantitative"}],
  "rows": [{"year": 1972, "value": 27}, ...],
  "metric_label": "Known performances",
  "scope_note": "Based on performances represented in Deadbot",
  "total": 227,
  "excluded_count": 0,
  "date_range": {"from": 1968, "to": 1995},
  "empty_reason": "No performances match these filters."
}
```

`columns` always has exactly two entries in this batch: one dimension column
(`key` is `"year"` for a temporal group_by, `"label"` for a categorical one)
and one `"value"` column. There is no series dimension yet — Batch 1
deliberately shipped no `series_by` (see its plan's "Optional bar selection
is explicitly deferred" and the stacked-bar row/series-cap notes).

Batch 2's job: let the model reference an `aggregation_id` from this turn's
tool output as a new `data_chart` semantic unit inside `finish_response`,
hydrated server-side into a browser-safe `DataChartBlock` using **only** the
verified payload above. No frontend rendering happens in this batch (that's
Batch 3) — Batch 2 ends at a validated, hydrated `ExperienceBlock` your test
suite can construct and assert on directly.

Research into the current architecture (conducted before this plan was
written) found two names in the original outcome document that don't
actually exist in this codebase, corrected here:

- There is no `resolve_body()`. The two functions that do this job are
  `resolve_items()` (resolves one group's items) and `resolve_groups()`
  (resolves `plan.groups`, calling `resolve_items()` per group) — both in
  `deadbot/finish.py`.
- There is no `LayoutSection`. Group layout is carried entirely by
  `ExperienceGroup.block_indexes` (an index list into the flat `blocks`
  array) — there is no nested section type to extend.

Both tasks below use the *actual* names.

## Global constraints

- **Every number in a `DataChartBlock` comes from the exact `aggregate_data`
  payload found this turn — never recomputed, never re-derived.** The model
  chooses which aggregation to reference and how to frame/plot it
  (title/note/chart/orientation/field mapping); the server supplies every
  row, total, and label verbatim from that payload.
- **An invalid or malformed chart request is dropped, exactly like every
  other unresolvable reference in this codebase** — `_resolve_reference`
  returns `(None, [])`, `resolve_items` logs it at `INFO` and continues. Do
  not invent a new "broken chart" block variant or raise a new error type.
  This applies to: an `aggregation_id` that never appeared in this turn's
  tool output, a `chart`/`orientation` combination that doesn't match the
  aggregation's dimension type, an `x_field`/`y_field` that isn't one of the
  payload's actual column keys, a `series_field` (never valid in this
  batch — see below), and any row whose `value` isn't a finite number.
- **A genuinely empty but well-formed aggregation still hydrates.** `rows ==
  []` with `empty_reason` set is a *valid* result (the aggregation ran
  correctly and found nothing) — this is different from a malformed
  request, and it must still produce a `DataChartBlock` so Batch 3's
  renderer can show the empty-state note. Do not conflate "empty" with
  "invalid."
- **`stacked_bar` and any `series_field` are always rejected (dropped) in
  this batch.** Batch 1's aggregation contract never returns more than the
  two fixed columns (dimension + value) — there is no series dimension for
  a stacked bar to plot yet. The schema keeps `chart: Literal["bar",
  "stacked_bar"]` and an optional `series_field` so a future batch can add
  `series_by` without a breaking schema change, but hydration in *this*
  batch must never construct a stacked-bar block — do not fake one from a
  single series.
- **`chart` is exactly `Literal["bar", "stacked_bar"]` — never `"line"` or
  anything else.** Pydantic's `Literal` validation is the rejection
  mechanism for an out-of-vocabulary chart type: a `finish_response` call
  naming `chart="line"` fails schema validation before any hydration logic
  runs. No additional runtime check is needed for this specific rule.
- **No `role`/`emphasis` field on `DataChartRef`.** `UnitRole` (`finish.py`)
  is explicitly marked deprecated scaffolding in this codebase, kept for one
  release of backward compatibility, and the live `Emphasis` field
  (`primary`/`supporting`/`mention`) is only declared on the four "unit"
  ref types (`ShowUnitRef`, `PerformanceUnitRef`, `AlbumUnitRef`,
  `SongOverviewRef`). A chart is a standalone component — like
  `arrangement_search`, `media_link`, and `resource_list`, none of which
  have an emphasis field either — not a graded unit. Ruling: omit both.
- `deadbot/experience.py` has zero imports from backend/business-logic
  modules (`aggregation.py`, `data.py`, `postgres.py`, `tools.py`) — it is
  the pure, standalone browser contract. `DataChartColumn`'s `type` literal
  (`"temporal" | "categorical" | "quantitative"`) is re-declared here, not
  imported from `aggregation.py`, preserving that independence.
  `deadbot/composition.py` may import `deadbot.experience` (it already
  does) but should not need anything from `deadbot.aggregation` either — it
  only re-shapes an already-JSON-decoded payload dict, it never constructs
  or inspects an `AggregationResult`/`AggregationRequest` object directly.
- Every new Pydantic model uses `model_config = ConfigDict(extra="forbid")`
  (via `ExperienceModel` in `experience.py`, or the existing `_Ref` base in
  `finish.py` — do not redeclare it if a base class already sets it).
- Explicitly out of scope for this batch: any frontend file under `web/src/`
  except the one generated-type alias in `web/src/types.ts` (Task 4), any
  React rendering, and any change to `deadbot/aggregation.py`, `data.py`,
  `postgres.py`, or `tools.py` (Batch 1 is closed; Batch 2 only consumes its
  output).
- Tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q <files>`
  per task, full suite before the final task completes. The one pre-existing
  `tests/test_evaluations.py::test_evaluate_cli_exits_non_zero_when_a_case_fails`
  failure (needs `DEADBOT_DATABASE_URL`) is expected and unrelated.
- Never push; never bare `git stash`. Commit trailer:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Task 1 — `deadbot/experience.py`: `DataChartBlock` browser schema

1. Add, near the other block definitions (a good neighbor is
   `ArrangementSearchBlock` — similar shape: title + a coverage/scope note +
   a bounded item/row list):

   ```python
   class DataChartColumn(ExperienceModel):
       key: str
       label: str
       type: Literal["temporal", "categorical", "quantitative"]


   class DataChartBlock(ExperienceModel):
       """A model-selected chart, hydrated entirely from one verified
       aggregate_data result.

       Every number here is server-computed from that exact result; the
       model chose only which aggregation to reference, how to frame it
       (title/note), and how to plot it (chart/orientation/field mapping).
       """

       type: Literal["data_chart"]
       aggregation_id: str
       title: str
       note: str | None = None
       chart: Literal["bar", "stacked_bar"]
       orientation: Literal["vertical", "horizontal"]
       x_field: str
       y_field: str
       x_label: str | None = None
       y_label: str | None = None
       columns: list[DataChartColumn] = Field(min_length=2, max_length=2)
       rows: list[dict[str, object]] = Field(default_factory=list, max_length=200)
       metric_label: str
       scope_note: str
       total: int
       excluded_count: int
       date_range: dict[str, int] | None = None
       empty_reason: str | None = None
   ```

   `rows` stays a loose `list[dict[str, object]]` deliberately — it mirrors
   `AggregationResult.rows` verbatim (either `{"year": int, "value": int}`
   or `{"id": str, "label": str, "value": int}` per row) rather than
   inventing a second row schema that duplicates Batch 1's. `date_range`
   stays a plain `dict[str, int] | None` (not a nested model) specifically
   to avoid aliasing the reserved-word-adjacent keys `"from"`/`"to"` as
   Pydantic field names.

2. Add `DataChartBlock` to the `ExperienceBlock` discriminated union
   (`Annotated[... | DataChartBlock | ..., Field(discriminator="type")]`) —
   put it near `ArrangementSearchBlock`/`ResourceListBlock` for readability,
   order doesn't affect behavior.

3. Tests, `tests/test_experience.py` (no `pytest.fixture` is used in this
   file — follow its existing plain-helper-function style):
   - a full valid `DataChartBlock` record validates (two columns, a few
     rows, all required fields present) — mirrors
     `test_album_unit_block_validates_a_full_record`'s style;
   - an unrecognized extra field is rejected (`extra="forbid"`) — mirrors
     `test_schema_rejects_an_unrecognized_browser_block`'s style, but
     targeted at `DataChartBlock` specifically (an extra field on an
     otherwise-valid record, not an unknown `type`);
   - `columns` with 1 entry or 3 entries both raise (min/max bound);
   - `rows` with 201 entries raises (max bound).

4. `tests/test_api_import.py`: add
   `assert "DataChartBlock" in schemas` and
   `assert "aggregation_id" in schemas["DataChartBlock"]["properties"]`,
   following `test_openapi_publishes_the_album_unit_block`'s exact pattern
   (no live DB; `Settings()`/`CanonicalStore()`/`object()` as the agent
   sentinel).

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_experience.py tests/test_api_import.py`

## Task 2 — `deadbot/composition.py`: the `_data_chart` builder

Depends on Task 1. This is the one place all of Global Constraints'
verification rules live — `finish.py` (Task 3) only checks whether the
`aggregation_id` was grounded and finds the payload; everything about
whether the *chart request itself* is well-formed is this function's job.

1. Add, near `_media_block` (the closest existing precedent: a small, pure,
   no-store-access builder that turns one already-shaped tool-payload record
   into a block or `None`):

   ```python
   import math
   # (add to composition.py's existing imports if not already present)

   def _data_chart(
       payload: dict[str, Any],
       *,
       chart: str,
       orientation: str,
       x_field: str,
       y_field: str,
       series_field: str | None,
       title: str | None,
       note: str | None,
       x_label: str | None,
       y_label: str | None,
   ) -> DataChartBlock | None:
       """Hydrate a data_chart block from a verified aggregate_data payload.

       ``payload`` is the exact JSON an aggregate_data tool call returned
       this turn; nothing here re-derives or re-computes a number. Returns
       None for any structurally invalid chart request (unknown/mismatched
       field names, an orientation that doesn't match the aggregation's
       dimension type, a still-unsupported stacked_bar/series request, or a
       non-finite value) so an invalid reference is dropped exactly like any
       other unresolvable reference. A genuinely empty but well-formed
       aggregation (rows == [], empty_reason set) still hydrates.
       """
       columns = payload.get("columns")
       rows = payload.get("rows")
       aggregation_id = payload.get("aggregation_id")
       metric_label = payload.get("metric_label")
       scope_note = payload.get("scope_note")
       total = payload.get("total")
       excluded_count = payload.get("excluded_count")
       if (
           not isinstance(aggregation_id, str)
           or not isinstance(columns, list)
           or len(columns) != 2
           or not isinstance(rows, list)
           or len(rows) > 200
           or not isinstance(metric_label, str)
           or not isinstance(scope_note, str)
           or not isinstance(total, int)
           or isinstance(total, bool)
           or not isinstance(excluded_count, int)
           or isinstance(excluded_count, bool)
       ):
           return None

       parsed_columns: list[DataChartColumn] = []
       for column in columns:
           if not isinstance(column, dict):
               return None
           try:
               parsed_columns.append(DataChartColumn(**column))
           except ValidationError:
               return None

       column_keys = {column.key for column in parsed_columns}
       if x_field not in column_keys or y_field not in column_keys or x_field == y_field:
           return None
       if series_field is not None:
           return None  # no series dimension exists in this batch's aggregation contract
       if chart == "stacked_bar":
           return None  # requires a series dimension the contract can't yet produce

       dimension_column = next((column for column in parsed_columns if column.key != "value"), None)
       if dimension_column is None:
           return None
       wants_vertical = dimension_column.type == "temporal"
       if wants_vertical and orientation != "vertical":
           return None
       if not wants_vertical and orientation != "horizontal":
           return None

       for row in rows:
           if not isinstance(row, dict):
               return None
           value = row.get("value")
           if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
               return None

       date_range = payload.get("date_range")
       if date_range is not None and not (
           isinstance(date_range, dict)
           and isinstance(date_range.get("from"), int)
           and isinstance(date_range.get("to"), int)
       ):
           return None
       empty_reason = payload.get("empty_reason")
       if empty_reason is not None and not isinstance(empty_reason, str):
           return None

       resolved_title = (title or "").strip() or metric_label
       return DataChartBlock(
           type="data_chart",
           aggregation_id=aggregation_id,
           title=resolved_title,
           note=note,
           chart=chart,
           orientation=orientation,
           x_field=x_field,
           y_field=y_field,
           x_label=x_label,
           y_label=y_label,
           columns=parsed_columns,
           rows=rows,
           metric_label=metric_label,
           scope_note=scope_note,
           total=total,
           excluded_count=excluded_count,
           date_range=date_range,
           empty_reason=empty_reason,
       )
   ```

   Check `composition.py`'s existing imports before adding `math`/
   `ValidationError` — add only what's actually missing, matching this
   file's existing import style/grouping.

2. Tests: append to `tests/test_finish.py` (this file already hosts the
   hydration tests for every other `composition.py` builder — there is no
   separate `tests/test_composition.py`; follow the existing convention
   rather than starting a new file). Use the real `aggregate_data` tool
   against a real `CanonicalStore()` for the happy-path payloads (matching
   this codebase's no-mocks convention), and hand-built payload dicts for
   the synthetic edge cases where a specific malformed shape is easier to
   construct directly than to coax out of the real tool:
   - a real `dataset="shows", group_by="year", measure="count"` payload with
     `chart="bar", orientation="vertical", x_field="year", y_field="value"`
     hydrates a `DataChartBlock` whose `rows`/`total`/`metric_label` match
     the payload exactly;
   - a real `dataset="performances", group_by="song", measure="count"`
     payload (categorical dimension) with `orientation="vertical"` (wrong —
     should be `"horizontal"` for a ranked category) returns `None`; the
     same payload with `orientation="horizontal"` hydrates;
   - the shows/year payload above with `orientation="horizontal"` (wrong —
     should be `"vertical"` for a year series) returns `None`;
   - `x_field`/`y_field` swapped to a value not in the payload's column keys
     (e.g. `x_field="not_a_real_column"`) returns `None`;
   - `chart="stacked_bar"` on an otherwise-valid payload returns `None`;
   - `series_field="anything"` on an otherwise-valid payload returns `None`;
   - a payload with `rows: []` and `empty_reason` set (get one from a real
     query with an impossible filter, e.g. a `year_from`/`year_to` range
     with no matches, mirroring Batch 1's own zero-match test pattern)
     still hydrates a `DataChartBlock` with `rows == []` and the
     `empty_reason` carried through;
   - a hand-built payload with one row's `"value"` set to a string, and
     separately one set to `float("nan")` via direct dict construction
     (not JSON, since `json.dumps`/`loads` can't round-trip NaN by
     default — construct the payload dict directly in the test), both
     return `None`;
   - a hand-built payload with 201 rows returns `None`;
   - `title=None` falls back to the payload's `metric_label`; a supplied
     `title` is kept as given.

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_finish.py tests/test_experience.py`

## Task 3 — `deadbot/finish.py`: `DataChartRef`, grounding, and hydration

Depends on Task 1 and Task 2.

1. Add `DataChartRef`, modeled on `ArrangementSearchRef`/`ResourceListRef`'s
   minimalism (no `role`/`emphasis` — see Global Constraints) plus `_Ref`'s
   inherited optional `title`:

   ```python
   class DataChartRef(_Ref):
       """A chart built from one aggregate_data result called this turn.

       Choose bar for any result today — stacked_bar is reserved for a
       future aggregation with more than one series and is always dropped
       until then. orientation must be vertical for a year-grouped result
       and horizontal for a ranked category (song, venue, city, guest).
       x_field/y_field must be exact column keys from that aggregate_data
       result's own columns list.
       """

       type: Literal["data_chart"]
       aggregation_id: str
       chart: Literal["bar", "stacked_bar"] = Field(
           description="bar for any result today; stacked_bar is not yet available and is always dropped."
       )
       orientation: Literal["vertical", "horizontal"] = Field(
           description="vertical for a year-grouped result, horizontal for a ranked category."
       )
       x_field: str = Field(description="One of the exact column keys this aggregate_data result returned.")
       y_field: str = Field(description="One of the exact column keys this aggregate_data result returned.")
       series_field: str | None = Field(default=None, description="Not yet supported; leave unset.")
       x_label: str | None = Field(default=None, description="Optional axis label overriding the column's default label.")
       y_label: str | None = Field(default=None, description="Optional axis label overriding the column's default label.")
       note: str | None = Field(default=None, description=_NOTE_DESCRIPTION)
   ```

   Read `_NOTE_DESCRIPTION`'s actual value first and reuse it verbatim (as
   every other unit ref does) rather than writing a new description string.

2. Add `DataChartRef` to the `BodyItem` union (a plain `|` append; the
   discriminator is `type`, `_BODY_ITEM_ADAPTER`/`validate_body_item()` need
   no changes since they operate generically over the union).

3. Add a lookup helper, placed next to `_find_in_payloads`/
   `_find_research_resource` (same idiom — the payload isn't a nested list
   under a well-known key here, it's matched by a top-level field, so this
   is closer to a single-purpose scan):

   ```python
   def _find_aggregation_payload(payloads: list[dict[str, Any]], aggregation_id: str) -> dict[str, Any] | None:
       for payload in payloads:
           if payload.get("aggregation_id") == aggregation_id:
               return payload
       return None
   ```

4. Add a `kind == "data_chart"` branch to `_resolve_reference`, following
   the same "return `(None, [])` on any failure" contract every other
   branch uses — no exception, no new error type:

   ```python
   if kind == "data_chart":
       if item.aggregation_id not in grounded.ids:
           return None, []
       payload = _find_aggregation_payload(payloads, item.aggregation_id)
       if payload is None:
           return None, []
       block = composition._data_chart(
           payload,
           chart=item.chart,
           orientation=item.orientation,
           x_field=item.x_field,
           y_field=item.y_field,
           series_field=item.series_field,
           title=item.title,
           note=item.note,
           x_label=item.x_label,
           y_label=item.y_label,
       )
       return (block, []) if block else (None, [])
   ```

   `grounded.ids` already contains a model-cited `aggregation_id` value
   whenever `aggregate_data` was actually called this turn — Batch 1's
   payload puts `"aggregation_id"` at the top level, and
   `grounded_context()`'s existing `_walk` heuristic
   (`key.endswith("_id")`) already picks up any `..._id`-suffixed key
   regardless of nesting. No change to `grounded_context`/`_walk` is needed
   or wanted for this. `data_chart` returns no `SourceReference` (a chart
   carries no external link), matching `guest_appearance_list`.

5. Update `FinishPlan.groups`'s field `description=` (the string that
   enumerates every standalone component by name) to add `data_chart` to
   the list, e.g. append "`, data_chart (a chart built from one
   aggregate_data result)`" — read the current exact string first and edit
   it in place rather than rewriting it wholesale.

6. Tests, append to `tests/test_finish.py`:
   - `FinishPlan` accepts a `DataChartRef` inside a group's `items` (schema
     acceptance, mirrors `test_finish_plan_accepts_semantic_units`);
   - constructing a `DataChartRef` with `chart="line"` raises
     `pydantic.ValidationError` (schema-level rejection, no hydration logic
     involved);
   - end-to-end hydration: call the real `aggregate_data` tool via
     `build_tools(store)` against a real `CanonicalStore()`, build a
     `GroupPlan`/`FinishPlan` referencing the returned `aggregation_id`
     with a valid `chart`/`orientation`/`x_field`/`y_field`, call
     `finish.resolve_items(...)`, assert the resolved block's `type ==
     "data_chart"` and `aggregation_id` matches — mirrors
     `test_resolve_body_resolves_guest_appearances_from_the_turn_payload`'s
     structure;
   - an `aggregation_id` that never appeared in `payloads`/`grounded.ids`
     (a made-up string) is dropped — `resolve_items(...)` returns no block
     for it — mirrors `test_an_ungrounded_release_id_is_dropped`;
   - an `aggregation_id` that *is* grounded (present in `grounded.ids`) but
     whose payload isn't actually found in `payloads` (construct this by
     passing a `grounded` built from one payload but an empty `payloads`
     list, or a mismatched pair) is also dropped, not an error;
   - a chart request with mismatched orientation (reusing Task 2's synthetic
     case, but now going through the full `_resolve_reference` path, not
     calling `composition._data_chart` directly) is dropped;
   - `resolve_groups` with a group containing a `DataChartRef` alongside an
     existing unit type (e.g. a `ShowUnitRef`) preserves reading order in
     `block_indexes` — mirrors
     `test_resolve_groups_preserves_order_criteria_and_truncates_judgments`;
   - a `DataChartBlock` has no `judgments` attribute, so `resolve_groups`'s
     `hasattr(block, "judgments")` truncation step is a no-op for it —
     assert this doesn't raise and the block passes through unchanged when
     mixed into a `comparison` group with `criteria` set.

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_finish.py tests/test_experience.py tests/test_api_import.py`

## Task 4 — `deadbot/graph.py` prompt guidance, contract regeneration

Depends on Tasks 1-3.

1. In `deadbot/graph.py`'s `SYSTEM_PROMPT`, `# COMPOSING THE EXPERIENCE`
   section, the paragraph that currently reads "Standalone components serve
   inventories that are not themselves the story: `equipment_list,
   show_selection, arrangement, arrangement_search, media_link and
   resource_list, guest_appearance_list ..., and person_roster ...`" — add
   `data_chart` to this enumerated list, with a short clause on when it
   applies, e.g.: "...and data_chart when a quantitative comparison,
   distribution, or change over time is the point — call aggregate_data
   first and reference its aggregation_id; prefer a chart to a long numeric
   list when the pattern matters more than any single number, and never
   estimate or restate its numbers from memory." Read the exact current
   paragraph text first and edit it in place; do not rewrite the whole
   section.

2. In the `## RESEARCH THE ACTUAL QUESTION` section, near the existing
   "Well-worn routes" paragraph, add a short new paragraph naming
   `aggregate_data` and when to reach for it: counts, rankings, or trends
   across many shows/performances/guests (not any single show or
   performance), and that it returns server-verified rows the model must
   quote exactly, never approximate. Distinguish performance frequency from
   listener popularity in this same paragraph (the aggregation only ever
   measures how often something was played/appeared, never how well-loved
   it was) — this is a specific, easy-to-get-wrong distinction worth stating
   explicitly rather than leaving implicit.

3. Tests, append to `tests/test_graph.py` (follow the existing
   normalized-whitespace substring-assertion style):
   - `"data_chart"` appears in `SYSTEM_PROMPT`;
   - `"aggregate_data"` appears in `SYSTEM_PROMPT`;
   - the new sentence(s) you actually wrote appear verbatim (assert the
     exact unwrapped substring, the way
     `test_prompt_teaches_semantic_units_and_grouping_by_meaning` asserts
     `"Group by meaning and referent, not by tool, source or data type."` —
     write the test against whatever exact wording you land on, don't
     invent a wording the test checks for and then write different prose).

   Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_graph.py`

4. Regenerate the published contracts:
   ```
   /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py
   npm run gen:types --prefix web
   ```
   This updates `web/openapi.json` and `web/src/generated/api.ts` to include
   `DataChartBlock`. Then update `web/src/types.ts` by hand (it is not
   itself generated):
   - add a `Require<...>` alias for `DataChartBlock` for whichever fields
     Pydantic's `default_factory`/optional-with-default treatment makes
     look optional in the generated type but the server always populates —
     check `rows` in particular (`default_factory=list`), following the
     exact pattern the file's own comment block (near the top of the file)
     documents for the other block types;
   - add that alias to the `ExperienceBlock` union export.

   Verify no drift: re-run both regeneration commands a second time and
   confirm `git status` shows no changes the second time (this is exactly
   what CI's drift gate checks). If `npm`/node modules aren't available in
   this environment, report that clearly as a concern rather than skipping
   the step silently — this is required for the batch to be complete, not
   optional polish.

5. Run the full suite:
   ```
   PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
   ```
   and, if the web toolchain is available:
   ```
   npm run build --prefix web
   ```
   Compare failures against the known pre-existing baseline; anything new
   is this batch's responsibility.
