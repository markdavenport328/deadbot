# Model-selected data visualizations — Batch 1: aggregation domain and tool

## Context

Deadbot is gaining an optional `data_chart` semantic unit: the model decides
whether a quantitative pattern matters, calls one constrained aggregation
tool, interprets the verified result, and places the chart in the same
ordered group grammar as narrative and entity units. This is Batch 1 of 4:
the read-only aggregation domain and tool only. No `finish.py`,
`experience.py`, or frontend changes happen in this batch — those are
Batches 2-3. The full architectural plan (spec authority for this batch) is
in the conversation that produced it; the parts binding this batch are
reproduced in Global Constraints below.

Guardrail from that plan, load-bearing for every task here: no model-authored
SQL, SQL fragments, column names, or arbitrary configuration ever reaches the
database. The model supplies a dataset/group_by/measure/filters *request*;
application code owns every SQL string. Canonical ID filters (`song_id`,
`venue_id`, `guest_id`, `show_id`, `performance_id`) are IDs only — the model
resolves names to IDs with the existing `search_entities` /
`search_guest_musicians` tools first, exactly as every other tool already
requires.

Data-quality finding this batch must honor: recording-derived duration
covers 66.5% of performances overall and only 50.7% for Dark Star
specifically. `average_duration` is a reserved-but-rejected measure name in
this batch, not an accepted one — see Task 1.

## Global constraints

- Two canonical stores implement the identical contract: `deadbot/data.py`
  (`CanonicalStore`, CSV-backed, in-memory Python) and `deadbot/postgres.py`
  (`PostgresCanonicalStore`, subclasses `CanonicalStore`, DB-API backed). Any
  new store method must exist on both and return identical shapes for
  identical requests — verified by parity tests, the established pattern in
  `tests/test_postgres_store.py`.
- SQL injection rule (already enforced elsewhere in `postgres.py` via
  `_identifier`): table and column names that get string-interpolated into
  SQL must come from an internal, literal, hand-written spec table — never
  from a request field's raw string value — and must be passed through
  `_identifier()`. Actual data values (IDs, years, limits, the literal
  `'guest'` role filter) are always bound as `%s` DB-API parameters, never
  interpolated. Task 3 spells out the exact spec tables to use; do not
  invent a different mechanism.
- All new Pydantic models use `model_config = ConfigDict(extra="forbid")` so
  an unrecognized field from a model-authored tool call is rejected, not
  silently dropped.
- Tools never raise. Every existing tool in `deadbot/tools.py` catches its
  domain errors and returns `_json({"error": "...", ...})`; the new
  `aggregate_data` tool follows the same convention (Task 4).
- JSON encoding: use the existing `_json()` helper in `tools.py` (strips
  `None`/`""` recursively, keeps `0`/`False`). Do not hand-roll `json.dumps`
  in the tool.
- Existing repo conventions to match, not reinvent: `CanonicalStore.rows()`,
  `.by_id`, `.rows_in()`, `.filtered_rows()` for the CSV store;
  `PostgresCanonicalStore._query()`, `._identifier()`, `._qualified_table()`
  for the Postgres store; `@tool`-decorated nested functions inside
  `build_tools()` for tools; the `if name == "...": return "..."` chain in
  `deadbot/progress.py::describe_tool_call`.
- Prompt guidance, `finish.py`/`experience.py` wiring, and the frontend are
  explicitly out of scope for this batch — do not touch `deadbot/graph.py`,
  `deadbot/finish.py`, `deadbot/experience.py`, or anything under `web/`.
- Tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q <files>`
  per task, and the full suite before the final task completes. A
  pre-existing failure in `tests/test_evaluations.py` unrelated to this work
  is expected and may be ignored if present before your change; do not let
  it mask a new failure.
- Never push (agents in this repo cannot push); never run bare `git stash`.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Task 1 — `deadbot/aggregation.py`: contract, compatibility matrix, shaping

Create `deadbot/aggregation.py`. This module is pure logic shared by both
stores: it defines what dataset/group_by/measure/filter combinations are
legal, their labels and scope notes, and how already-grouped rows become a
verified, shaped result (zero-fill, sort, limit, totals). It contains no SQL
and touches no store.

1. Enums and the allowed-combination tables. Use these exact literal values
   and structures — they are the full accepted vocabulary for this batch:

   ```python
   from typing import Literal

   Dataset = Literal["shows", "performances", "guest_appearances"]
   GroupBy = Literal["year", "song", "venue", "city", "guest"]
   Measure = Literal["count", "distinct_shows", "distinct_songs", "average_duration"]
   Sort = Literal["chronological", "value_desc", "value_asc", "label"]

   _DATASET_GROUP_BYS: dict[Dataset, frozenset[GroupBy]] = {
       "shows": frozenset({"year", "venue", "city"}),
       "performances": frozenset({"year", "song", "venue", "city"}),
       "guest_appearances": frozenset({"year", "venue", "city", "guest"}),
   }

   _MEASURES_BY_COMBO: dict[tuple[Dataset, GroupBy], frozenset[Measure]] = {
       ("shows", "year"): frozenset({"count"}),
       ("shows", "venue"): frozenset({"count"}),
       ("shows", "city"): frozenset({"count"}),
       ("performances", "year"): frozenset({"count", "distinct_shows", "distinct_songs"}),
       ("performances", "venue"): frozenset({"count", "distinct_shows", "distinct_songs"}),
       ("performances", "city"): frozenset({"count", "distinct_shows", "distinct_songs"}),
       ("performances", "song"): frozenset({"count", "distinct_shows"}),
       ("guest_appearances", "year"): frozenset({"count", "distinct_shows"}),
       ("guest_appearances", "venue"): frozenset({"count", "distinct_shows"}),
       ("guest_appearances", "city"): frozenset({"count", "distinct_shows"}),
       ("guest_appearances", "guest"): frozenset({"count"}),
   }

   _DATASET_FILTERS: dict[Dataset, frozenset[str]] = {
       "shows": frozenset({"venue_id", "year", "year_from", "year_to"}),
       "performances": frozenset({"song_id", "venue_id", "show_id", "performance_id", "year", "year_from", "year_to"}),
       "guest_appearances": frozenset({"guest_id", "venue_id", "show_id", "year", "year_from", "year_to"}),
   }

   _METRIC_LABELS: dict[tuple[Dataset, Measure], str] = {
       ("shows", "count"): "Known shows",
       ("performances", "count"): "Known performances",
       ("performances", "distinct_shows"): "Shows with a known performance",
       ("performances", "distinct_songs"): "Distinct songs performed",
       ("guest_appearances", "count"): "Guest appearances",
       ("guest_appearances", "distinct_shows"): "Shows with a guest appearance",
   }

   _SCOPE_NOTES: dict[Dataset, str] = {
       "shows": "Based on shows represented in Deadbot",
       "performances": "Based on performances represented in Deadbot",
       "guest_appearances": "Based on guest appearances represented in Deadbot",
   }

   _DATASET_LABELS: dict[Dataset, str] = {
       "shows": "shows",
       "performances": "performances",
       "guest_appearances": "guest appearances",
   }

   _GROUP_BY_LABELS: dict[GroupBy, str] = {
       "year": "Year", "song": "Song", "venue": "Venue", "city": "City", "guest": "Guest",
   }
   ```

   `average_duration` is intentionally in the `Measure` literal (so a request
   naming it gets a specific, explanatory rejection — see step 2) but never
   appears as a value in `_MEASURES_BY_COMBO` or `_METRIC_LABELS`, so it can
   never validate.

2. `AggregationFilters` and `AggregationRequest` (Pydantic, `extra="forbid"`):

   ```python
   from pydantic import BaseModel, ConfigDict, Field, model_validator

   class AggregationFilters(BaseModel):
       model_config = ConfigDict(extra="forbid")
       song_id: str | None = None
       venue_id: str | None = None
       guest_id: str | None = None
       show_id: str | None = None
       performance_id: str | None = None
       year: int | None = None
       year_from: int | None = None
       year_to: int | None = None

       @model_validator(mode="after")
       def _check_year_bounds(self) -> "AggregationFilters":
           if self.year is not None and (self.year_from is not None or self.year_to is not None):
               raise ValueError("year cannot be combined with year_from/year_to")
           if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
               raise ValueError("year_from must be <= year_to")
           return self

   class AggregationRequest(BaseModel):
       model_config = ConfigDict(extra="forbid")
       dataset: Dataset
       group_by: GroupBy
       measure: Measure
       filters: AggregationFilters = Field(default_factory=AggregationFilters)
       sort: Sort | None = None
       limit: int = Field(default=20, ge=1, le=50)
       fill_missing: bool = False

       @model_validator(mode="after")
       def _check_combination(self) -> "AggregationRequest":
           if self.measure == "average_duration":
               raise ValueError(
                   "average_duration is not available yet: recording-derived "
                   "duration covers 66.5% of performances overall (50.7% for "
                   "some songs), not enough for a reliable aggregate. It will "
                   "return once a documented duration source and a minimum-"
                   "completeness policy are in place."
               )
           allowed_group_bys = _DATASET_GROUP_BYS.get(self.dataset, frozenset())
           if self.group_by not in allowed_group_bys:
               raise ValueError(f"dataset {self.dataset!r} does not support group_by {self.group_by!r}")
           allowed_measures = _MEASURES_BY_COMBO.get((self.dataset, self.group_by), frozenset())
           if self.measure not in allowed_measures:
               raise ValueError(
                   f"dataset {self.dataset!r} grouped by {self.group_by!r} does not support measure {self.measure!r}"
               )
           provided = {
               name for name in
               ("song_id", "venue_id", "guest_id", "show_id", "performance_id", "year", "year_from", "year_to")
               if getattr(self.filters, name) is not None
           }
           allowed_filters = _DATASET_FILTERS.get(self.dataset, frozenset())
           invalid = provided - allowed_filters
           if invalid:
               raise ValueError(f"dataset {self.dataset!r} does not support filters {sorted(invalid)}")
           if self.fill_missing and self.group_by != "year":
               raise ValueError("fill_missing is only valid when group_by is 'year'")
           if self.sort is not None:
               if self.group_by == "year" and self.sort not in ("chronological", "value_desc", "value_asc"):
                   raise ValueError(f"sort {self.sort!r} is not valid when group_by is 'year'")
               if self.group_by != "year" and self.sort not in ("value_desc", "value_asc", "label"):
                   raise ValueError(f"sort {self.sort!r} is not valid when group_by is {self.group_by!r}")
           return self

       @property
       def effective_sort(self) -> Sort:
           if self.sort is not None:
               return self.sort
           return "chronological" if self.group_by == "year" else "value_desc"

   def parse_request(payload: dict[str, object]) -> AggregationRequest:
       """Validate an externally-supplied (model-authored) aggregation request.

       Raises pydantic.ValidationError on anything outside the accepted
       contract. Callers (the aggregate_data tool) catch this and return a
       plain JSON error rather than letting it propagate.
       """
       return AggregationRequest.model_validate(payload)
   ```

3. `AggregationSpec` / `resolve_spec` — the per-request bundle of display
   text, derived only from already-validated `dataset`/`group_by`/`measure`:

   ```python
   from dataclasses import dataclass

   @dataclass(frozen=True)
   class AggregationSpec:
       metric_label: str
       scope_note: str
       empty_reason: str
       dimension_key: str            # "year" or "label"
       dimension_label: str          # column display label, e.g. "Song"
       dimension_type: Literal["temporal", "categorical"]

   def resolve_spec(request: AggregationRequest) -> AggregationSpec:
       metric_label = _METRIC_LABELS[(request.dataset, request.measure)]
       dimension_key = "year" if request.group_by == "year" else "label"
       return AggregationSpec(
           metric_label=metric_label,
           scope_note=_SCOPE_NOTES[request.dataset],
           empty_reason=f"No {_DATASET_LABELS[request.dataset]} match these filters.",
           dimension_key=dimension_key,
           dimension_label=_GROUP_BY_LABELS[request.group_by],
           dimension_type="temporal" if request.group_by == "year" else "categorical",
       )
   ```

4. `stable_aggregation_id` — normalizes `sort` to `effective_sort` so two
   requests that differ only in an explicit-vs-default sort collapse to the
   same id:

   ```python
   import hashlib
   import json

   def stable_aggregation_id(request: AggregationRequest) -> str:
       normalized = request.model_dump(mode="json")
       normalized["sort"] = request.effective_sort
       digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()
       return f"agg:{digest[:16]}"
   ```

5. Row shaping types and functions — the shared bridge between a store's raw
   grouped output and the final payload:

   ```python
   @dataclass
   class AggregationRow:
       """One grouped, already-counted row before zero-fill/sort/limit."""
       value: int
       year: int | None = None
       id: str | None = None
       label: str | None = None

   def zero_fill_years(rows: list[AggregationRow], filters: AggregationFilters) -> list[AggregationRow]:
       if filters.year_from is not None or filters.year_to is not None:
           start = filters.year_from if filters.year_from is not None else min(r.year for r in rows)
           end = filters.year_to if filters.year_to is not None else max(r.year for r in rows)
       elif rows:
           start = min(r.year for r in rows)
           end = max(r.year for r in rows)
       else:
           return rows
       present = {r.year: r for r in rows}
       return [present.get(year, AggregationRow(year=year, value=0)) for year in range(start, end + 1)]

   def sort_rows(rows: list[AggregationRow], request: AggregationRequest) -> list[AggregationRow]:
       sort = request.effective_sort
       if sort == "chronological":
           return sorted(rows, key=lambda r: r.year)
       if sort == "label":
           return sorted(rows, key=lambda r: ((r.label or "").casefold(), r.id or ""))
       if sort == "value_desc":
           return sorted(rows, key=lambda r: (-r.value, (r.label or "").casefold(), r.id or ""))
       return sorted(rows, key=lambda r: (r.value, (r.label or "").casefold(), r.id or ""))  # value_asc

   def apply_limit(rows: list[AggregationRow], limit: int) -> tuple[list[AggregationRow], int]:
       if len(rows) <= limit:
           return rows, 0
       return rows[:limit], len(rows) - limit
   ```

6. `AggregationColumn`, `AggregationResult`, and `assemble_result` — the
   single place both stores hand off to for identical final shaping:

   ```python
   @dataclass
   class AggregationColumn:
       key: str
       label: str
       type: Literal["temporal", "categorical", "quantitative"]

   @dataclass
   class AggregationResult:
       aggregation_id: str
       request: AggregationRequest
       columns: list[AggregationColumn]
       rows: list[dict[str, object]]
       metric_label: str
       scope_note: str
       date_range: dict[str, int] | None
       total: int
       excluded_count: int
       empty_reason: str | None

       def to_payload(self) -> dict[str, object]:
           payload: dict[str, object] = {
               "aggregation_id": self.aggregation_id,
               "query": self.request.model_dump(mode="json", exclude_none=True),
               "columns": [column.__dict__ for column in self.columns],
               "rows": self.rows,
               "metric_label": self.metric_label,
               "scope_note": self.scope_note,
               "total": self.total,
               "excluded_count": self.excluded_count,
           }
           if self.date_range is not None:
               payload["date_range"] = self.date_range
           if self.empty_reason is not None:
               payload["empty_reason"] = self.empty_reason
           return payload

   def assemble_result(
       request: AggregationRequest,
       raw_rows: list[AggregationRow],
       date_range: dict[str, int] | None,
   ) -> AggregationResult:
       """Shape a store's raw grouped rows into a verified result.

       ``raw_rows`` is exactly one row per group, unfilled and unsorted —
       stores supply it from their own grouping logic (Python loop or SQL
       GROUP BY). Zero-fill, sort, limit, totals, and empty-state text all
       happen here so both stores produce identical shaped output.
       """
       spec = resolve_spec(request)
       total = sum(r.value for r in raw_rows)
       rows = zero_fill_years(raw_rows, request.filters) if request.fill_missing else raw_rows
       rows = sort_rows(rows, request)
       limited, excluded_count = apply_limit(rows, request.limit)
       columns = [
           AggregationColumn(key=spec.dimension_key, label=spec.dimension_label, type=spec.dimension_type),
           AggregationColumn(key="value", label=spec.metric_label, type="quantitative"),
       ]
       shaped_rows: list[dict[str, object]] = []
       for row in limited:
           if spec.dimension_key == "year":
               shaped_rows.append({"year": row.year, "value": row.value})
           else:
               shaped_rows.append({"id": row.id, "label": row.label, "value": row.value})
       return AggregationResult(
           aggregation_id=stable_aggregation_id(request),
           request=request,
           columns=columns,
           rows=shaped_rows,
           metric_label=spec.metric_label,
           scope_note=spec.scope_note,
           date_range=date_range,
           total=total,
           excluded_count=excluded_count,
           empty_reason=spec.empty_reason if not raw_rows else None,
       )
   ```

7. Tests: create `tests/test_aggregation.py`. Cover, at minimum:
   - every entry in `_MEASURES_BY_COMBO` validates via `parse_request`, and a
     handful of invalid combinations (e.g. `dataset="shows", group_by="song"`;
     `dataset="performances", group_by="song", measure="distinct_songs"`;
     `dataset="guest_appearances", group_by="guest", measure="distinct_shows"`)
     raise `pydantic.ValidationError`;
   - `measure="average_duration"` is rejected and the error message contains
     "66.5%" (or otherwise clearly names the coverage reason, not a generic
     enum error);
   - an unknown top-level field and an unknown `filters` field both raise
     (`extra="forbid"`);
   - a filter not valid for the dataset (e.g. `song_id` with `dataset="shows"`)
     raises;
   - `year` combined with `year_from` raises; `year_from > year_to` raises;
   - `fill_missing=True` with `group_by="venue"` raises;
   - `sort="label"` with `group_by="year"` raises, and `sort="chronological"`
     with `group_by="venue"` raises;
   - `limit=0` and `limit=51` both raise (Pydantic `Field` bounds);
   - two requests built from the same logical payload but one with an
     explicit `sort` equal to the default and one with `sort` omitted
     produce the same `stable_aggregation_id`; a request that differs only
     in `limit` produces a different id;
   - `zero_fill_years` with `year_from=1965, year_to=1968` and one input row
     for 1966 produces exactly rows for 1965-1968 with the 1966 row's real
     value and zero elsewhere;
   - `zero_fill_years` with no bounds and no rows returns `[]` unchanged;
   - `sort_rows` orders `value_desc` by value descending with a stable
     casefolded-label tiebreak (construct two equal-value rows with
     different labels and assert order);
   - `apply_limit` returns the correct `excluded_count`;
   - `assemble_result` on an empty `raw_rows` list produces `empty_reason`
     set and `total == 0`, `date_range` passed through unchanged, and
     `rows == []`.

   Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_aggregation.py`

## Task 2 — `deadbot/data.py`: CSV reference implementation

Depends on Task 1. Add one method to `CanonicalStore`:

```python
def aggregate(self, request: "aggregation.AggregationRequest") -> "aggregation.AggregationResult":
    """Compute a constrained aggregation entirely from loaded canonical rows.

    Mirrors PostgresCanonicalStore.aggregate's grouping/measure semantics so
    both stores return identical shaped rows for the same request; only the
    fetch strategy (Python loop vs SQL GROUP BY) differs.
    """
    from deadbot import aggregation

    filters = request.filters
    shows_by_id = self.by_id.get("shows", {})
    venues_by_id = self.by_id.get("venues", {})
    songs_by_id = self.by_id.get("songs", {})
    people_by_id = self.by_id.get("people", {})

    def show_year(show: dict[str, str] | None) -> int | None:
        date = (show or {}).get("show_date", "")
        return int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None

    def show_matches(show: dict[str, str] | None) -> bool:
        if show is None:
            return False
        if filters.venue_id is not None and show.get("venue_id") != filters.venue_id:
            return False
        year = show_year(show)
        if filters.year is not None and year != filters.year:
            return False
        if filters.year_from is not None and (year is None or year < filters.year_from):
            return False
        if filters.year_to is not None and (year is None or year > filters.year_to):
            return False
        return True

    facts: list[dict[str, object]] = []
    if request.dataset == "shows":
        for show in self.rows("shows"):
            if not show_matches(show):
                continue
            facts.append({"show_id": show["show_id"], "year": show_year(show), "venue_id": show.get("venue_id")})
    elif request.dataset == "performances":
        for performance in self.rows("performances"):
            if filters.song_id is not None and performance.get("song_id") != filters.song_id:
                continue
            if filters.show_id is not None and performance.get("show_id") != filters.show_id:
                continue
            if filters.performance_id is not None and performance.get("performance_id") != filters.performance_id:
                continue
            show = shows_by_id.get(performance.get("show_id", ""))
            if not show_matches(show):
                continue
            facts.append({
                "show_id": performance["show_id"],
                "year": show_year(show),
                "venue_id": show.get("venue_id"),
                "song_id": performance.get("song_id"),
            })
    else:  # guest_appearances
        seen: set[tuple[str, str]] = set()
        for assignment in self.rows("show_performers"):
            if assignment.get("role") != "guest":
                continue
            pair = (assignment.get("show_id", ""), assignment.get("person_id", ""))
            if pair in seen:
                continue
            if filters.guest_id is not None and assignment.get("person_id") != filters.guest_id:
                continue
            if filters.show_id is not None and assignment.get("show_id") != filters.show_id:
                continue
            show = shows_by_id.get(assignment.get("show_id", ""))
            if not show_matches(show):
                continue
            seen.add(pair)
            facts.append({
                "show_id": assignment["show_id"],
                "year": show_year(show),
                "venue_id": show.get("venue_id"),
                "person_id": assignment.get("person_id"),
            })

    years = [fact["year"] for fact in facts if fact["year"] is not None]
    date_range = {"from": min(years), "to": max(years)} if years else None

    def dimension(fact: dict[str, object]) -> tuple[str, str]:
        if request.group_by == "year":
            return (str(fact["year"]), str(fact["year"]))
        if request.group_by == "venue":
            venue = venues_by_id.get(fact["venue_id"], {})
            return (fact["venue_id"], venue.get("name") or fact["venue_id"])
        if request.group_by == "city":
            venue = venues_by_id.get(fact["venue_id"], {})
            city = venue.get("city") or "Unknown"
            return (city, city)
        if request.group_by == "song":
            song = songs_by_id.get(fact["song_id"], {})
            return (fact["song_id"], song.get("title") or fact["song_id"])
        person = people_by_id.get(fact["person_id"], {})
        return (fact["person_id"], person.get("name") or fact["person_id"])

    groups: dict[str, dict[str, object]] = {}
    for fact in facts:
        dim_id, dim_label = dimension(fact)
        group = groups.setdefault(dim_id, {"label": dim_label, "show_ids": set(), "song_ids": set(), "count": 0})
        group["count"] += 1
        group["show_ids"].add(fact["show_id"])
        if fact.get("song_id"):
            group["song_ids"].add(fact["song_id"])

    raw_rows = []
    for dim_id, group in groups.items():
        if request.measure == "count":
            value = group["count"]
        elif request.measure == "distinct_shows":
            value = len(group["show_ids"])
        else:  # distinct_songs
            value = len(group["song_ids"])
        if request.group_by == "year":
            raw_rows.append(aggregation.AggregationRow(year=int(dim_id), value=value))
        else:
            raw_rows.append(aggregation.AggregationRow(id=dim_id, label=group["label"], value=value))

    return aggregation.assemble_result(request, raw_rows, date_range)
```

Add `from deadbot import aggregation` as a top-of-function import (inside the
method, as shown) rather than a module-level import, matching this file's
existing avoidance of a circular import with any module that might import
`data.py` — check whether `aggregation.py` imports anything from `data.py`
(it should not; if it doesn't, a module-level import is fine and preferred —
use your judgment, but keep the import path acyclic).

Tests (append to `tests/test_aggregation.py`), using the real on-disk
`CanonicalStore()` (matching the existing convention in
`tests/test_research_tools.py`/`tests/test_data.py` — no fixture CSVs
exist, tests read the actual `data/canonical/*.csv`):

- `performances` grouped by `year`, `measure="count"`, filtered to
  `song_id="song-dark-star"` — assert every row's `value` is a positive int,
  years are ascending, and `total` equals the sum of all rows' values;
- the same query with `fill_missing=True` and no explicit year bounds —
  assert the row years form a contiguous range with no gaps, and any filled
  year has `value == 0`;
- `shows` grouped by `year`, `measure="count"` — assert `date_range` spans
  a multi-decade range consistent with the catalog (first year <= 1970,
  last year >= 1990 is a safe bound given 31 years of coverage);
- `performances` grouped by `song`, `measure="count"`, `sort="value_desc"`,
  `limit=5` — assert exactly 5 rows, values non-increasing, and
  `excluded_count > 0`;
- `performances` grouped by `venue`, `measure="distinct_shows"` — assert
  every row's `id` is a real `venue_id` and matches a venue name lookup
  (cross-check a couple of ids against `store.one("venues", id)`);
- `guest_appearances` grouped by `guest`, `measure="count"` — assert
  `person-jack-casady` appears with `value >= 1` (real data: Jack Casady
  guests at `gd-1966-07-16`, role `guest`);
- `guest_appearances` grouped by `year`, `measure="distinct_shows"`,
  filtered to `guest_id="person-jack-casady"` — assert it returns rows only
  for years in which that guest appears;
- an impossible filter (e.g. `performances` filtered to
  `song_id="song-dark-star", show_id="gd-1900-01-01"` — a show_id that
  cannot exist) returns `rows == []`, `total == 0`,
  `empty_reason` set, `date_range is None`;
- `dataset="performances", group_by="song", measure="count"` grouped without
  a song filter, `limit=1`, `sort="value_desc"` — assert the single returned
  row's `id` is `song-dark-star`'s or a comparably-performed song's id (do
  not hardcode which song wins; assert the returned `value` is at least as
  large as Dark Star's own count computed via a second, filtered query in
  the same test — this proves ranking is correct without hand-picking the
  top song).

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_aggregation.py`

## Task 3 — `deadbot/postgres.py`: SQL implementation and parity tests

Depends on Task 1 and Task 2 (parity tests call both).

### SQL design

Add internal, literal (never request-derived) spec tables at module scope in
`postgres.py`, alongside the existing `_IDENTIFIER`/`_identifier`:

```python
# filter name -> (table alias in the aggregate query, column name)
_AGGREGATE_FILTER_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "shows": {"venue_id": ("s", "venue_id")},
    "performances": {
        "song_id": ("p", "song_id"),
        "show_id": ("p", "show_id"),
        "performance_id": ("p", "performance_id"),
        "venue_id": ("s", "venue_id"),
    },
    "guest_appearances": {
        "guest_id": ("g", "person_id"),
        "show_id": ("g", "show_id"),
        "venue_id": ("s", "venue_id"),
    },
}

# measure -> SQL aggregate expression (table aliases match the FROM clauses below)
_AGGREGATE_MEASURE_SQL: dict[str, str] = {
    "count": "COUNT(*)",
    "distinct_shows": 'COUNT(DISTINCT s."show_id")',
    "distinct_songs": 'COUNT(DISTINCT p."song_id")',
}
```

`_aggregate_from_clause(self, dataset)` returns `(from_sql, base_params)`:

```python
def _aggregate_from_clause(self, dataset: str) -> tuple[str, list[Any]]:
    shows = self._qualified_table("shows")
    if dataset == "shows":
        return f"{shows} s", []
    if dataset == "performances":
        performances = self._qualified_table("performances")
        return f'{performances} p JOIN {shows} s ON s."show_id" = p."show_id"', []
    show_performers = self._qualified_table("show_performers")
    return (
        f'(SELECT DISTINCT "show_id", "person_id" FROM {show_performers} WHERE "role" = %s) g '
        f'JOIN {shows} s ON s."show_id" = g."show_id"',
        ["guest"],
    )
```

`_aggregate_dimension_sql(self, dataset, group_by)` returns
`(id_sql, label_sql, group_by_sql, join_sql)`:

```python
def _aggregate_dimension_sql(self, dataset: str, group_by: str) -> tuple[str, str, str, str]:
    if group_by == "year":
        expr = 'EXTRACT(YEAR FROM s."show_date")::int'
        return expr, expr, expr, ""
    if group_by == "venue":
        venues = self._qualified_table("venues")
        return 's."venue_id"', 'v."name"', 's."venue_id", v."name"', f'JOIN {venues} v ON v."venue_id" = s."venue_id"'
    if group_by == "city":
        venues = self._qualified_table("venues")
        # venues.city is nullable; COALESCE to match CanonicalStore.aggregate's
        # `venue.get("city") or "Unknown"` in data.py exactly, or the
        # CSV/Postgres parity test in Task 3 will fail on any blank city.
        city_expr = "COALESCE(NULLIF(v.\"city\", ''), 'Unknown')"
        return city_expr, city_expr, city_expr, f'JOIN {venues} v ON v."venue_id" = s."venue_id"'
    if group_by == "song":
        songs = self._qualified_table("songs")
        return 'p."song_id"', 'so."title"', 'p."song_id", so."title"', f'JOIN {songs} so ON so."song_id" = p."song_id"'
    people = self._qualified_table("people")
    return 'g."person_id"', 'pe."name"', 'g."person_id", pe."name"', f'JOIN {people} pe ON pe."person_id" = g."person_id"'
```

`_aggregate_predicates(self, dataset, filters)` returns `(predicate_sql_list, params)`,
**without** any null-date predicate (callers add that where needed):

```python
def _aggregate_predicates(self, dataset: str, filters: "aggregation.AggregationFilters") -> tuple[list[str], list[Any]]:
    predicates: list[str] = []
    params: list[Any] = []
    filter_columns = _AGGREGATE_FILTER_COLUMNS[dataset]
    for name in ("song_id", "venue_id", "guest_id", "show_id", "performance_id"):
        value = getattr(filters, name)
        if value is None or name not in filter_columns:
            continue
        alias, column = filter_columns[name]
        predicates.append(f"{alias}.{_identifier(column)} = %s")
        params.append(value)
    if filters.year is not None:
        predicates.append('EXTRACT(YEAR FROM s."show_date")::int = %s')
        params.append(filters.year)
    if filters.year_from is not None:
        predicates.append('EXTRACT(YEAR FROM s."show_date")::int >= %s')
        params.append(filters.year_from)
    if filters.year_to is not None:
        predicates.append('EXTRACT(YEAR FROM s."show_date")::int <= %s')
        params.append(filters.year_to)
    return predicates, params
```

`aggregate(self, request)` — assembles and runs two queries: the grouped
aggregate, and a lightweight date-range query over the same FROM/filters
(always excluding null-date rows, regardless of `group_by`):

```python
def aggregate(self, request: "aggregation.AggregationRequest") -> "aggregation.AggregationResult":
    from deadbot import aggregation

    dataset, group_by = request.dataset, request.group_by
    from_sql, base_params = self._aggregate_from_clause(dataset)
    dim_id_sql, dim_label_sql, dim_group_sql, join_sql = self._aggregate_dimension_sql(dataset, group_by)
    measure_sql = _AGGREGATE_MEASURE_SQL[request.measure]
    predicates, filter_params = self._aggregate_predicates(dataset, request.filters)

    grouped_predicates = list(predicates)
    if group_by == "year":
        grouped_predicates.append('s."show_date" IS NOT NULL')
    where_sql = f"WHERE {' AND '.join(grouped_predicates)}" if grouped_predicates else ""
    sql = (
        f"SELECT {dim_id_sql} AS dim_id, {dim_label_sql} AS dim_label, {measure_sql} AS value "
        f"FROM {from_sql} {join_sql} {where_sql} GROUP BY {dim_group_sql}"
    )
    grouped = self._query(sql, tuple(base_params + filter_params))

    range_predicates = list(predicates) + ['s."show_date" IS NOT NULL']
    range_where_sql = f"WHERE {' AND '.join(range_predicates)}"
    range_sql = (
        'SELECT MIN(EXTRACT(YEAR FROM s."show_date"))::int AS min_year, '
        'MAX(EXTRACT(YEAR FROM s."show_date"))::int AS max_year '
        f"FROM {from_sql} {range_where_sql}"
    )
    range_rows = self._query(range_sql, tuple(base_params + filter_params))
    min_year = range_rows[0].get("min_year") if range_rows else None
    max_year = range_rows[0].get("max_year") if range_rows else None
    date_range = {"from": int(min_year), "to": int(max_year)} if min_year is not None and max_year is not None else None

    raw_rows = []
    for row in grouped:
        value = int(row["value"] or 0)
        if group_by == "year":
            raw_rows.append(aggregation.AggregationRow(year=int(row["dim_id"]), value=value))
        else:
            raw_rows.append(aggregation.AggregationRow(id=row["dim_id"], label=row["dim_label"] or row["dim_id"], value=value))

    return aggregation.assemble_result(request, raw_rows, date_range)
```

Notes:
- Every table/column name reaching SQL comes from `_qualified_table`,
  `_identifier`, or one of the two literal dicts above — never from
  `request` directly. Every value from `request.filters` (or the literal
  `"guest"` role) is bound as a `%s` parameter. If you find yourself
  f-string-interpolating anything from `request.filters` or
  `request.group_by`/`request.dataset` directly into SQL text (as opposed to
  looking it up in `_AGGREGATE_FILTER_COLUMNS`/`_aggregate_dimension_sql`
  first), stop — that violates the Global Constraints injection rule.
- `_query`'s row values come back as strings via `_string_value` in some
  DB-API paths (see existing `coverage_summary`) — cast with `int(...)`
  defensively as shown, matching the existing `coverage_summary` pattern.
- This method does not sort, zero-fill, or limit — `aggregation.assemble_result`
  does that identically for both stores. Do not duplicate that logic here.

### Parity tests (append to `tests/test_postgres_store.py`)

Use the existing `store`/`csv_store` fixtures (toy SQLite-backed
`Connection`/`TABLES`) for a first quick pass, and — because the toy `TABLES`
fixture is thin (verify what group_by/dataset combinations it can actually
exercise; extend `TABLES` minimally, consistent with its existing row
shapes, if a combination has no matching toy rows at all) — the
session-scoped `real_connection`/`real_tables` fixtures for full-coverage
parity against production data:

```python
@pytest.fixture
def real_store(real_connection):
    return PostgresCanonicalStore(real_connection, schema="canonical")

@pytest.fixture
def real_csv_store(real_tables):
    result = CanonicalStore()
    result.__dict__["tables"] = real_tables
    return result
```

For every valid `(dataset, group_by, measure)` triple in
`aggregation._MEASURES_BY_COMBO` (import and iterate it directly — do not
hand-copy the list, so this test can't drift from Task 1's table), build one
representative `AggregationRequest` (no filters, `limit=50`,
`fill_missing=True` only when `group_by == "year"`) and assert
`real_store.aggregate(request).to_payload() == real_csv_store.aggregate(request).to_payload()`.
This is the test that actually proves the hand-written SQL above is correct
against the real ~40k-row dataset — treat any mismatch it finds as a bug in
the SQL, not in the CSV path (the CSV path was already covered by Task 2's
own tests).

Also add filtered-request parity cases (canonical IDs from the real data,
safe to hardcode): `song_id="song-dark-star"` with
`(performances, year, count, fill_missing=True)`; `guest_id="person-jack-casady"`
with `(guest_appearances, year, distinct_shows)`; a `year_from`/`year_to`
range with `(shows, year, count)`.

Run:
```
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_postgres_store.py tests/test_aggregation.py
```

If any of these tests need a live PostgreSQL connection rather than the
SQLite-compatibility fixtures to be meaningful, check how the rest of
`test_postgres_store.py` handles that (it doesn't — the toy `Connection`
class is SQLite underneath and is treated as sufficient); do not introduce a
new PostgreSQL dependency for this batch. Note in your report if any SQL
construct you used (e.g. `EXTRACT(YEAR FROM ...)`) behaves identically in
SQLite and PostgreSQL — if it does not, flag it rather than silently
adjusting the query only for the test to pass.

## Task 4 — `deadbot/tools.py` and `deadbot/progress.py`: the `aggregate_data` tool

Depends on Tasks 1-3.

1. In `deadbot/tools.py`, add `from pydantic import ValidationError` (check
   it is not already imported under a different name) and
   `from deadbot import aggregation` near the existing imports. Inside
   `build_tools`, add a new nested `@tool`-decorated function following the
   existing pattern (see `search_guest_musicians` for the closure-over-`store`
   and docstring-as-tool-description conventions):

   ```python
   @tool
   def aggregate_data(
       dataset: str,
       group_by: str,
       measure: str,
       song_id: str | None = None,
       venue_id: str | None = None,
       guest_id: str | None = None,
       show_id: str | None = None,
       performance_id: str | None = None,
       year: int | None = None,
       year_from: int | None = None,
       year_to: int | None = None,
       sort: str | None = None,
       limit: int = 20,
       fill_missing: bool = False,
   ) -> str:
       """Count or group canonical Deadbot rows with a constrained, verified aggregation.

       dataset is one of "shows", "performances", "guest_appearances".
       group_by is one of "year", "song", "venue", "city", "guest" — only
       some combinations are valid per dataset (an invalid combination
       returns an error naming what's wrong, not a guess). measure is one of
       "count", "distinct_shows", "distinct_songs" (also only valid for some
       combinations); "average_duration" is reserved but not yet available —
       expect a rejection explaining why if you try it.

       Every ID filter (song_id, venue_id, guest_id, show_id,
       performance_id) takes a canonical ID only, never a name — resolve a
       name to an ID with search_entities or search_guest_musicians first.
       year, year_from, year_to filter by show year.

       The response's rows and metric_label are the actual computed
       aggregate: never estimate, extrapolate, or restate these numbers from
       memory. aggregation_id grounds a data_chart reference in
       finish_response — call this tool once per distinct question and reuse
       its aggregation_id rather than calling again with the same
       parameters.
       """
       filters = {
           "song_id": song_id, "venue_id": venue_id, "guest_id": guest_id,
           "show_id": show_id, "performance_id": performance_id,
           "year": year, "year_from": year_from, "year_to": year_to,
       }
       payload: dict[str, Any] = {
           "dataset": dataset,
           "group_by": group_by,
           "measure": measure,
           "filters": {key: value for key, value in filters.items() if value is not None},
           "limit": limit,
           "fill_missing": fill_missing,
       }
       if sort is not None:
           payload["sort"] = sort
       try:
           request = aggregation.parse_request(payload)
       except ValidationError as error:
           return _json({"error": "Invalid aggregation request", "detail": str(error)})
       result = store.aggregate(request)
       return _json(result.to_payload())
   ```

   Append `aggregate_data` to the list `build_tools` returns (after the
   existing entries, matching the existing style — one name per line).

2. In `deadbot/progress.py`, inside `describe_tool_call`, add a branch before
   the final fallback:

   ```python
   if name == "aggregate_data":
       dataset = (args or {}).get("dataset")
       measure = (args or {}).get("measure")
       labels = {
           ("shows", "count"): "Counting known shows",
           ("performances", "count"): "Counting known performances",
           ("performances", "distinct_shows"): "Counting shows with a known performance",
           ("performances", "distinct_songs"): "Counting distinct songs performed",
           ("guest_appearances", "count"): "Counting guest appearances",
           ("guest_appearances", "distinct_shows"): "Counting shows with a guest appearance",
       }
       return labels.get((dataset, measure), "Counting the catalog")
   ```

3. Tests (append to `tests/test_research_tools.py`, using the real on-disk
   `CanonicalStore()` and `_tool_by_name` helper already in that file):
   - `aggregate_data.invoke({...})` with a valid performances/year/count
     request for Dark Star returns parseable JSON with a non-empty `rows`
     list and `metric_label == "Known performances"`;
   - an invalid combination (e.g. `dataset="shows", group_by="song",
     measure="count"`) returns `{"error": "Invalid aggregation request", ...}`
     rather than raising;
   - an unresolvable extra field (e.g. `dataset="performances", group_by="year",
     measure="count", song_id="Dark Star"` — a title, not an ID) still
     "succeeds" at the schema level (aggregate_data doesn't resolve names) but
     returns an empty result — assert `rows == []` and `empty_reason` is set,
     documenting that name resolution is the caller's job, not this tool's;
   - `aggregate_data` appears in the list returned by `build_tools(store)`.

   Add one test to `tests/test_progress.py` (find its existing pattern first
   — likely a direct call to `describe_tool_call`):
   `describe_tool_call("aggregate_data", {"dataset": "performances", "measure": "count"}) == "Counting known performances"`,
   and one for an unmapped combination falling through to
   `"Counting the catalog"`.

   Run:
   ```
   PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_research_tools.py tests/test_progress.py
   ```

4. Run the full suite before completing this task:
   ```
   PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
   ```
   Compare failures against the pre-existing baseline noted in Global
   Constraints; anything new is this batch's responsibility to fix.
