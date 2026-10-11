"""Grids: two lists of library things and the fact where each pair meets.

A grid's rows and columns are both library entities: songs across years,
nights across songs, records across songs, guests across years. The model
chooses the lists, their order and what to say about them; every cell here is
read from the store, so one spec always draws the same grid. Builds read only
rows_in, one and aggregate, which every store already implements identically.
"""

from __future__ import annotations

import calendar
import difflib
import hashlib
import json
import logging
import re
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
    ("release", "song"): "minutes",
    ("guest", "year"): "shows",
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
    tracks_without_song: dict[str, tuple[int, int]] = field(default_factory=dict)  # release: (tracks, tracks naming no song)
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
            "rows": [
                {
                    "id": row.id,
                    "label": row.label,
                    **({"sub": row.sub} if row.sub else {}),
                    **({"total": row.total} if row.total is not None else {}),
                }
                for row in self.rows
            ],
            "columns": [{"id": column.id, "label": column.label} for column in self.columns],
            "cells": {"columns": ["row", "column", "value", "passes", "state"], "rows": table},
        }


GRID_NOTE = (
    "A grid in finish_response draws these rows and columns with every cell filled by the library. "
    "Choose the rows to show and their order, how many open before Show all, the cells worth pointing at "
    "with a short note each, and what the visitor should know about gaps."
)


def tool_payload(data: GridData) -> dict[str, Any]:
    """The model's view of a built grid: the filled cells, coverage facts and the spec to rebuild it."""

    compact = data.to_compact()
    lengths = {"release": 0, "tape": 0, "mixed": 0, "none": 0}
    for cell in data.cells.values():
        if cell.state == "value" and cell.length_source:
            lengths[cell.length_source] += 1
        elif cell.state == "no_length":
            lengths["none"] += 1
    coverage: dict[str, Any] = {}
    if data.measure == "minutes":
        coverage["lengths"] = lengths
    if data.coverage_by_year:
        coverage["setlists_by_year"] = [
            {"year": year, "shows_on_record": on_record, "shows_with_setlist": with_setlist}
            for year, (on_record, with_setlist) in sorted(data.coverage_by_year.items())
            if with_setlist < on_record
        ]
    unnamed = [
        {"release_id": release_id, "tracks": tracks, "without_song": blank}
        for release_id, (tracks, blank) in data.tracks_without_song.items()
        if blank
    ]
    if unnamed:
        coverage["tracks_without_song"] = unnamed
    return {
        "grid_id": grid_id(data.spec),
        "rows_are": data.spec.row_kind,
        "columns_are": data.spec.column_kind,
        "measure": data.measure,
        "on_the_page": GRID_NOTE,
        "rows": compact["rows"],
        "columns": compact["columns"],
        "cells": compact["cells"],
        "coverage": coverage,
        "column_suggestions": data.suggestions,
        "spec": data.spec.to_json(),
    }


def build(store: CanonicalStore, spec: GridSpec) -> GridData:
    return _BUILDERS[(spec.row_kind, spec.column_kind)](store, spec)


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


def _year_counts(
    store: CanonicalStore, year_from: int, year_to: int, *, dataset: str = "performances", **ids: str
) -> aggregation.AggregationResult:
    filters: dict[str, Any] = {"year_from": year_from, "year_to": year_to, **ids}
    request = aggregation.parse_request(
        {
            "dataset": dataset,
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
    baseline = _year_counts(store, year_from, year_to)
    coverage = {
        int(entry["year"]): (int(entry["shows_on_record"]), int(entry["shows_with_setlist"]))
        for entry in (baseline.setlist_coverage or {}).get("by_year", [])
    }
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for song_id in row_ids:
        result = _year_counts(store, year_from, year_to, song_id=song_id)
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
    return GridData(spec=spec, rows=rows, columns=_year_columns(years), cells=cells, coverage_by_year=coverage)


def _year_columns(years: list[int]) -> list[Axis]:
    return [Axis(id=year_id(year), label=f"'{str(year)[2:]}", sub=str(year)) for year in years]


# --- guest × year ------------------------------------------------------------


def _guest_by_year(store: CanonicalStore, spec: GridSpec) -> GridData:
    """Shows each guest sat in on, year by year, counted as aggregate_data counts them."""

    years = [year for year in (parse_year(value) for value in spec.column_ids) if year is not None]
    people = {row["person_id"]: row for row in store.rows_in("people", "person_id", spec.row_ids)}
    row_ids = [person_id for person_id in spec.row_ids if person_id in people]
    if not years or not row_ids:
        return GridData(spec=spec, rows=[], columns=[], cells={})
    year_from, year_to = min(years), max(years)
    cells: dict[tuple[str, str], Cell] = {}
    rows = []
    for person_id in row_ids:
        result = _year_counts(store, year_from, year_to, dataset="guest_appearances", guest_id=person_id)
        by_year = {int(row["year"]): int(row["value"] or 0) for row in result.rows}
        total = 0
        for year in years:
            value = by_year.get(year, 0)
            total += value
            cells[(person_id, year_id(year))] = Cell(state="value", value=value) if value else Cell(state="none")
        rows.append(Axis(id=person_id, label=people[person_id].get("name") or person_id, total=total))
    return GridData(spec=spec, rows=rows, columns=_year_columns(years), cells=cells)


# --- release × song ----------------------------------------------------------

_VOLUME = re.compile(r"(?<=[^\W\d_]), Vol(?:ume|\.) (\d+)$")
_SERIES_PARENTHESIS = re.compile(r"^(.*, Vol(?:ume|\.) \d+) \((.+)\)$")


def release_label(title: str) -> tuple[str, str | None]:
    """A record's row name and sub line, cut from its own title and nothing else.

    "Dick's Picks, Volume 36: The Spectrum, Philadelphia, PA 9/21/72" reads as
    "Dick's Picks 36" over "The Spectrum, Philadelphia, PA 9/21/72". A volume
    number joins a series name only where the name ends in a word, so
    "Europe '72, Vol. 01" keeps its own words.
    """

    title = str(title or "").strip()
    head, sub = title, None
    if ": " in title:
        head, sub = (part.strip() for part in title.split(": ", 1))
    elif match := _SERIES_PARENTHESIS.match(title):
        head, sub = match.group(1), match.group(2).strip()
    return _VOLUME.sub(r" \1", head), sub or None


_DASHES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-"})


def _plain(text: str) -> str:
    return " ".join(str(text or "").translate(_DASHES).casefold().split())


def _mentions(track_title: str, song_title: str) -> bool:
    """Whether a track's own title names the song as a whole word or phrase."""

    needle = _plain(song_title)
    return bool(needle) and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", _plain(track_title)) is not None


def resolve_release(store: CanonicalStore, identifier: str) -> dict[str, str] | None:
    """A record by ID, title, or the short name its grid row carries ("Dick's Picks 36")."""

    found = store.resolve_release(identifier)
    if found:
        return found
    needle = _plain(identifier)
    if not needle:
        return None
    releases = store.rows("official_releases")
    names = [(row, _plain(row.get("title", "")), _plain(release_label(row.get("title", ""))[0])) for row in releases]
    exact = [row for row, title, label in names if needle in (title, label)]
    if exact:
        return exact[0] if len(exact) == 1 else None
    partial = [row for row, title, label in names if needle in title or needle in label]
    return partial[0] if len(partial) == 1 else None


def closest_releases(store: CanonicalStore, identifier: str, limit: int = 5) -> list[dict[str, str]]:
    """The records whose names are nearest a name that did not resolve, so the model can retry by ID."""

    by_name: dict[str, dict[str, str]] = {}
    for row in store.rows("official_releases"):
        by_name.setdefault(_plain(release_label(row.get("title", ""))[0]), row)
        by_name.setdefault(_plain(row.get("title", "")), row)
    chosen: dict[str, dict[str, str]] = {}
    for name in difflib.get_close_matches(_plain(identifier), list(by_name), n=limit * 2, cutoff=0.5):
        row = by_name[name]
        chosen.setdefault(row["release_id"], {"release_id": row["release_id"], "title": row.get("title", "")})
    return list(chosen.values())[:limit]


def _number(value: str) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 10**9


def _release_by_song(store: CanonicalStore, spec: GridSpec) -> GridData:
    """Minutes each song takes up on each record, from the record's own track lengths."""

    releases = {row["release_id"]: row for row in store.rows_in("official_releases", "release_id", spec.row_ids)}
    row_ids = [release_id for release_id in spec.row_ids if release_id in releases]
    by_release: dict[str, list[dict[str, str]]] = defaultdict(list)
    for track in store.rows_in("official_release_tracks", "release_id", row_ids):
        by_release[track["release_id"]].append(track)
    for tracks in by_release.values():
        tracks.sort(key=lambda track: (_number(track.get("track_number", "")), track.get("track_title", "")))

    song_ids = {t.get("song_id", "") for tracks in by_release.values() for t in tracks} - {""} | set(spec.column_ids)
    songs = {row["song_id"]: row for row in store.rows_in("songs", "song_id", song_ids)}
    column_ids = [song_id for song_id in spec.column_ids if song_id in songs]
    column_set = set(column_ids)
    title = lambda song_id: songs.get(song_id, {}).get("title") or song_id  # noqa: E731

    wanted = [
        t["performance_id"]
        for tracks in by_release.values()
        for t in tracks
        if t.get("song_id") in column_set and t.get("performance_id", "").strip()
    ]
    tape = _archive_tracks(store, wanted)
    set_labels = {row["performance_id"]: row.get("set_label", "") for row in store.rows_in("performances", "performance_id", wanted)}

    cells: dict[tuple[str, str], Cell] = {}
    seconds_by_cell: dict[tuple[str, str], int] = defaultdict(int)
    for release_id in row_ids:
        tracks = by_release.get(release_id, [])
        for track in tracks:
            song_id = track.get("song_id", "")
            if song_id not in column_set:
                continue
            key = (release_id, song_id)
            cell = cells.setdefault(key, Cell(state="no_length"))
            cell.passes += 1
            performance_id = track.get("performance_id", "").strip()
            if performance_id:
                cell.performance_ids = (*cell.performance_ids, performance_id)
                if (found := tape.get(performance_id)) is not None:
                    cell.tracks = (*cell.tracks, (performance_id, set_labels.get(performance_id, ""), found))
            seconds = str(track.get("duration_seconds") or "").strip()
            if seconds.isdigit() and int(seconds) > 0:
                seconds_by_cell[key] += int(seconds)
                cell.length_source = "release"
        # A track naming no song keeps a song it mentions an open question, not an absence.
        unnamed = [t.get("track_title", "") for t in tracks if not t.get("song_id", "").strip()]
        for song_id in column_ids:
            if (release_id, song_id) not in cells and any(_mentions(name, title(song_id)) for name in unnamed):
                cells[(release_id, song_id)] = Cell(state="unknown")
    for key, cell in cells.items():
        if seconds_by_cell.get(key):
            cell.state = "value"
            cell.value = round(seconds_by_cell[key] / 60)

    rows = []
    for release_id in row_ids:
        label, sub = release_label(releases[release_id].get("title") or release_id)
        rows.append(Axis(id=release_id, label=label, sub=sub, setlist=[_track_entry(t) for t in by_release.get(release_id, [])]))
    columns = [Axis(id=song_id, label=title(song_id)) for song_id in column_ids]
    # Songs on the most of these records that are not yet columns: the "Add a column" menu.
    counts: dict[str, int] = defaultdict(int)
    for release_id in row_ids:
        for song_id in {t.get("song_id", "") for t in by_release.get(release_id, [])} - {""} - column_set:
            counts[song_id] += 1
    suggestions = [
        {"id": song_id, "label": title(song_id), "rows_with": count}
        for song_id, count in sorted(counts.items(), key=lambda item: (-item[1], title(item[0])))[:12]
    ]
    blanks = {
        release_id: (len(tracks := by_release.get(release_id, [])), sum(1 for t in tracks if not t.get("song_id", "").strip()))
        for release_id in row_ids
    }
    return GridData(spec=spec, rows=rows, columns=columns, cells=cells, tracks_without_song=blanks, suggestions=suggestions)


def _track_entry(track: dict[str, str]) -> dict[str, Any]:
    """One line of a record's tracklist for the row's drawer, read from the track row."""

    name = str(track.get("track_title") or "").strip()
    segue = name.endswith(">")
    disc = re.match(r"disc (\d+) track", str(track.get("notes") or ""), re.IGNORECASE)
    return {
        "song_id": track.get("song_id", "").strip(),
        "title": name[:-1].rstrip() if segue else name,
        "set_label": f"Disc {disc.group(1)}" if disc else "",
        "segue": segue,
    }


_BUILDERS = {
    ("song", "year"): _song_by_year,
    ("show", "song"): _show_by_song,
    ("release", "song"): _release_by_song,
    ("guest", "year"): _guest_by_year,
}


def grid_block(
    store: CanonicalStore,
    payload: dict[str, Any],
    *,
    row_ids: list[str] | None,
    open_rows: int | None,
    highlights: list[dict[str, Any]],
    title: str | None,
    note: str | None,
    coverage: str | None,
    follow_ups: list[Any],
) -> Any:
    """Hydrate a model-planned grid from the spec in this turn's get_grid result, or None."""

    from deadbot.experience import (
        GridBlock,
        GridCell,
        GridColumn,
        GridRow,
        GridSetlistEntry,
        GridSpecModel,
        GridSuggestion,
        PlayableTrack,
    )

    spec = GridSpec.from_json(payload.get("spec"))
    if spec is None or payload.get("grid_id") != grid_id(spec):
        return None
    data = build(store, spec)
    if not data.rows or not data.columns:
        return None
    by_id = {row.id: row for row in data.rows}
    chosen = [row_id for row_id in dict.fromkeys(row_ids or []) if row_id in by_id]
    chosen_set = set(chosen)
    ordered = [by_id[row_id] for row_id in chosen] + [row for row in data.rows if row.id not in chosen_set]
    notes = {
        (str(h.get("row_id")), str(h.get("column_id"))): (str(h.get("note") or "").strip() or None)
        for h in highlights
        if isinstance(h, dict)
    }
    column_titles = {column.id: column.label for column in data.columns}

    def cell_model(row: Axis, column: Axis) -> GridCell:
        cell = data.cell(row.id, column.id)
        key = (row.id, column.id)
        return GridCell(
            state=cell.state,
            value=cell.value,
            passes=cell.passes,
            set_label=cell.set_label,
            segue_from=cell.segue_from,
            segue_into=cell.segue_into,
            length_source=cell.length_source,
            of_shows=cell.of_shows,
            tracks=[
                PlayableTrack(
                    performance_id=performance_id,
                    title=column_titles.get(column.id, column.id),
                    audio_url=track.url,
                    duration_seconds=track.duration_seconds,
                    set_label=set_label or None,
                )
                for performance_id, set_label, track in cell.tracks
            ],
            highlight=key in notes,
            note=notes.get(key),
        )

    return GridBlock(
        type="grid",
        grid_id=grid_id(spec),
        title=(title or "").strip() or None,
        note=(note or "").strip() or None,
        coverage=(coverage or "").strip() or None,
        row_kind=spec.row_kind,
        column_kind=spec.column_kind,
        measure=spec.measure,
        columns=[GridColumn(id=c.id, label=c.label, sub=c.sub) for c in data.columns],
        rows=[
            GridRow(
                id=row.id,
                label=row.label,
                sub=row.sub,
                total=row.total,
                cells=[cell_model(row, column) for column in data.columns],
                setlist=[GridSetlistEntry(**entry) for entry in row.setlist],
            )
            for row in fit(ordered, "grid rows")
        ],
        open_rows=open_rows if open_rows and 0 < open_rows < len(ordered) else None,
        max_value=data.max_value(),
        suggestions=[GridSuggestion(**s) for s in data.suggestions],
        follow_ups=list(follow_ups),
        spec=GridSpecModel(**spec.to_json()),
    )
