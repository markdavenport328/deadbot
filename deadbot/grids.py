"""Grids: two lists of library things and the fact where each pair meets.

A grid's rows and columns are both library entities: songs across years,
nights across songs. The model chooses the lists, their order and what to say
about them; every cell here is read from the store, so one spec always draws
the same grid. Reads use only rows_in, one and aggregate, which every store
already implements identically.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from deadbot import aggregation
from deadbot.data import CanonicalStore
from deadbot.experience import fit
from deadbot.sequences import Track, _archive_tracks

logger = logging.getLogger(__name__)

GRID_ROW_CEILING = 60
GRID_COLUMN_CEILING = 40
YEAR_PREFIX = "year:"

SUPPORTED_PAIRS: dict[tuple[str, str], str] = {
    ("song", "year"): "shows",
    ("show", "song"): "minutes",
}

CellState = Literal["value", "none", "no_length", "unknown"]


def year_id(year: int) -> str:
    return f"{YEAR_PREFIX}{year}"


def parse_year(value: str) -> int | None:
    text = str(value).removeprefix(YEAR_PREFIX)
    return int(text) if text.isascii() and text.isdigit() and len(text) == 4 else None


def _trim(items: list[str], ceiling: int, what: str) -> list[str]:
    items = list(dict.fromkeys(fit(items, what)))
    if len(items) > ceiling:
        logger.warning("Truncated %d %s to the grid ceiling of %d", len(items), what, ceiling)
        items = items[:ceiling]
    return items


@dataclass(frozen=True)
class GridSpec:
    row_kind: str
    row_ids: tuple[str, ...]
    column_kind: str
    column_ids: tuple[str, ...]

    @property
    def measure(self) -> str:
        return SUPPORTED_PAIRS[(self.row_kind, self.column_kind)]

    def to_json(self) -> dict[str, Any]:
        return {
            "row_kind": self.row_kind,
            "row_ids": list(self.row_ids),
            "column_kind": self.column_kind,
            "column_ids": list(self.column_ids),
        }

    @classmethod
    def from_json(cls, value: Any) -> "GridSpec | None":
        if not isinstance(value, dict):
            return None
        row_kind, column_kind = value.get("row_kind"), value.get("column_kind")
        if (row_kind, column_kind) not in SUPPORTED_PAIRS:
            return None
        rows = [str(item) for item in value.get("row_ids") or [] if str(item).strip()]
        columns = [str(item) for item in value.get("column_ids") or [] if str(item).strip()]
        if column_kind == "year":
            columns = [year_id(year) if (year := parse_year(item)) is not None else item for item in columns]
        if not rows or not columns:
            return None
        return cls(
            row_kind,
            tuple(_trim(rows, GRID_ROW_CEILING, "grid rows")),
            column_kind,
            tuple(_trim(columns, GRID_COLUMN_CEILING, "grid columns")),
        )


def grid_id(spec: GridSpec) -> str:
    digest = hashlib.sha1(json.dumps(spec.to_json(), sort_keys=True).encode()).hexdigest()[:12]
    return f"grid:{digest}"


@dataclass
class Cell:
    state: CellState
    value: int | None = None
    passes: int = 0
    performance_ids: tuple[str, ...] = ()
    set_label: str | None = None
    segue_from: str | None = None
    segue_into: str | None = None
    length_source: Literal["release", "tape", "mixed"] | None = None
    tracks: tuple[tuple[str, str, Track], ...] = ()  # (performance_id, set_label, tape track) per pass
    of_shows: int | None = None


@dataclass
class Axis:
    id: str
    label: str
    sub: str | None = None
    total: int | None = None
    setlist: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GridData:
    spec: GridSpec
    rows: list[Axis]
    columns: list[Axis]
    cells: dict[tuple[str, str], Cell]
    coverage_by_year: dict[int, tuple[int, int]] = field(default_factory=dict)
    suggestions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def measure(self) -> str:
        return self.spec.measure

    def row(self, row_id: str) -> Axis:
        return next(row for row in self.rows if row.id == row_id)

    def cell(self, row_id: str, column_id: str) -> Cell:
        return self.cells.get((row_id, column_id), Cell(state="none"))

    def max_value(self) -> int:
        return max((cell.value or 0 for cell in self.cells.values()), default=0)

    def to_compact(self) -> dict[str, Any]:
        """The model's view: filled cells as one table, no URLs."""

        table = [
            [row.id, column.id, cell.value, cell.passes, cell.state]
            for row in self.rows
            for column in self.columns
            if (cell := self.cell(row.id, column.id)).state != "none"
        ]
        return {
            "rows": [{"id": row.id, "label": row.label, **({"total": row.total} if row.total is not None else {})} for row in self.rows],
            "columns": [{"id": column.id, "label": column.label} for column in self.columns],
            "cells": {"columns": ["row", "column", "value", "passes", "state"], "rows": table},
        }


def build(store: CanonicalStore, spec: GridSpec) -> GridData:
    if spec.measure == "minutes":
        return _show_by_song(store, spec)
    return _song_by_year(store, spec)


# --- show × song -------------------------------------------------------------


def _long_date(show_date: str) -> str:
    """``1972-05-11`` as ``May 11, 1972``; anything else as stored."""

    parts = str(show_date or "").split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts) and 1 <= int(parts[1]) <= 12:
        return f"{calendar.month_name[int(parts[1])]} {int(parts[2])}, {parts[0]}"
    return str(show_date or "")


def _release_seconds(store: CanonicalStore, performance_ids: list[str]) -> dict[str, int]:
    """Each performance's longest official release track, the curated whole-song length."""

    seconds: dict[str, int] = {}
    for row in store.rows_in("official_release_tracks", "performance_id", performance_ids):
        text = str(row.get("duration_seconds") or "").strip()
        if text.isdigit() and int(text) > 0:
            seconds[row["performance_id"]] = max(seconds.get(row["performance_id"], 0), int(text))
    return seconds


def _show_by_song(store: CanonicalStore, spec: GridSpec) -> GridData:
    shows = {row["show_id"]: row for row in store.rows_in("shows", "show_id", spec.row_ids)}
    row_ids = [show_id for show_id in spec.row_ids if show_id in shows]
    venues = {row["venue_id"]: row for row in store.rows_in("venues", "venue_id", {s.get("venue_id", "") for s in shows.values()})}
    performances = store.rows_in("performances", "show_id", row_ids)
    by_show: dict[str, list[dict[str, str]]] = defaultdict(list)
    for performance in performances:
        by_show[performance["show_id"]].append(performance)
    for rows in by_show.values():
        # Blank set or position sorts last, as the store orders a night elsewhere.
        rows.sort(key=lambda row: (
            int(row["set_number"]) if row.get("set_number", "").isdigit() else 10**9,
            int(row["position_in_set"]) if row.get("position_in_set", "").isdigit() else 10**9,
            row.get("performance_id", ""),
        ))

    song_ids = {performance["song_id"] for performance in performances} | set(spec.column_ids)
    songs = {row["song_id"]: row for row in store.rows_in("songs", "song_id", song_ids)}
    column_ids = [song_id for song_id in spec.column_ids if song_id in songs]
    column_set = set(column_ids)
    title = lambda song_id: songs.get(song_id, {}).get("title") or song_id  # noqa: E731

    wanted = [p["performance_id"] for p in performances if p["song_id"] in column_set]
    release = _release_seconds(store, wanted)
    tape = _archive_tracks(store, wanted)

    cells: dict[tuple[str, str], Cell] = {}
    seconds_by_cell: dict[tuple[str, str], int] = defaultdict(int)
    for show_id in row_ids:
        night = by_show.get(show_id, [])
        for index, performance in enumerate(night):
            song_id = performance["song_id"]
            if song_id not in column_set:
                continue
            key = (show_id, song_id)
            cell = cells.setdefault(key, Cell(state="no_length"))
            set_number = performance.get("set_number")
            previous = night[index - 1] if index > 0 else None
            following = night[index + 1] if index + 1 < len(night) else None
            if cell.passes == 0:
                cell.set_label = performance.get("set_label") or None
                if previous and previous.get("set_number") == set_number and previous.get("segue_into_next") == "true":
                    cell.segue_from = title(previous["song_id"])
            if following and following.get("set_number") == set_number and performance.get("segue_into_next") == "true":
                cell.segue_into = title(following["song_id"])
            performance_id = performance["performance_id"]
            track = tape.get(performance_id)
            seconds = release.get(performance_id)
            source: Literal["release", "tape"] | None = "release" if seconds else None
            if not seconds and track is not None and track.duration_seconds:
                seconds, source = track.duration_seconds, "tape"
            cell.passes += 1
            cell.performance_ids = (*cell.performance_ids, performance_id)
            if track is not None:
                cell.tracks = (*cell.tracks, (performance_id, performance.get("set_label", ""), track))
            if seconds:
                seconds_by_cell[key] += seconds
                if cell.length_source not in (None, source):
                    cell.length_source = "mixed"
                else:
                    cell.length_source = source
    # A cell keeps state "no_length" only when no pass has a length.
    for key, cell in cells.items():
        if seconds_by_cell.get(key):
            cell.state = "value"
            cell.value = round(seconds_by_cell[key] / 60)

    rows = []
    for show_id in row_ids:
        show = shows[show_id]
        venue = venues.get(show.get("venue_id", ""), {})
        city = venue.get("city") or ""
        rows.append(
            Axis(
                id=show_id,
                label=f"{_long_date(show.get('show_date', ''))} · {city}".strip(" ·"),
                sub=venue.get("name") or None,
                setlist=[
                    {
                        "song_id": p["song_id"],
                        "title": title(p["song_id"]),
                        "set_label": p.get("set_label", ""),
                        "segue": p.get("segue_into_next") == "true",
                    }
                    for p in by_show.get(show_id, [])
                ],
            )
        )
    columns = [Axis(id=song_id, label=title(song_id)) for song_id in column_ids]
    # Songs played most on these nights that are not yet columns: the "Add a column" menu.
    counts: dict[str, int] = defaultdict(int)
    for show_id in row_ids:
        for song_id in {p["song_id"] for p in by_show.get(show_id, [])}:
            if song_id not in column_set:
                counts[song_id] += 1
    suggestions = [
        {"id": song_id, "label": title(song_id), "rows_with": count}
        for song_id, count in sorted(counts.items(), key=lambda item: (-item[1], title(item[0])))[:12]
    ]
    return GridData(spec=spec, rows=rows, columns=columns, cells=cells, suggestions=suggestions)


# --- song × year -------------------------------------------------------------


def _year_counts(store: CanonicalStore, song_id: str | None, year_from: int, year_to: int) -> aggregation.AggregationResult:
    filters: dict[str, Any] = {"year_from": year_from, "year_to": year_to}
    if song_id:
        filters["song_id"] = song_id
    request = aggregation.parse_request(
        {
            "dataset": "performances",
            "group_by": "year",
            "measure": "distinct_shows",
            "filters": filters,
            "fill_missing": True,
            "limit": 50,
        }
    )
    return store.aggregate(request)


def _song_by_year(store: CanonicalStore, spec: GridSpec) -> GridData:
    years = [year for year in (parse_year(value) for value in spec.column_ids) if year is not None]
    songs = {row["song_id"]: row for row in store.rows_in("songs", "song_id", spec.row_ids)}
    row_ids = [song_id for song_id in spec.row_ids if song_id in songs]
    if not years or not row_ids:
        return GridData(spec=spec, rows=[], columns=[], cells={})
    year_from, year_to = min(years), max(years)
    baseline = _year_counts(store, None, year_from, year_to)
    coverage = {
        int(entry["year"]): (int(entry["shows_on_record"]), int(entry["shows_with_setlist"]))
        for entry in (baseline.setlist_coverage or {}).get("by_year", [])
    }
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for song_id in row_ids:
        result = _year_counts(store, song_id, year_from, year_to)
        by_year = {int(row["year"]): int(row["value"] or 0) for row in result.rows}
        total = 0
        for year in years:
            value = by_year.get(year, 0)
            total += value
            of_shows = coverage.get(year, (0, 0))[1] or None
            cells[(song_id, year_id(year))] = (
                Cell(state="value", value=value, of_shows=of_shows) if value else Cell(state="none", of_shows=of_shows)
            )
        rows.append(Axis(id=song_id, label=songs[song_id].get("title") or song_id, total=total))
    columns = [Axis(id=year_id(year), label=f"'{str(year)[2:]}", sub=str(year)) for year in years]
    return GridData(spec=spec, rows=rows, columns=columns, cells=cells, coverage_by_year=coverage)
