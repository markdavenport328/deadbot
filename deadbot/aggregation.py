"""Pure logic for the model-selected data-aggregation tool.

This module defines what dataset/group_by/measure/filter combinations are
legal, their display labels and scope notes, and how already-grouped rows
from a store become a verified, shaped result (zero-fill, sort, limit,
totals). It contains no SQL and touches no store; ``deadbot/data.py`` and
``deadbot/postgres.py`` both import and call into it so their outputs are
provably identical.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


def stable_aggregation_id(request: AggregationRequest) -> str:
    normalized = request.model_dump(mode="json")
    normalized["sort"] = request.effective_sort
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()
    return f"agg:{digest[:16]}"


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
