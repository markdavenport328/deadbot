# Grid Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `grid` block. Rows and columns are both library entities (songs across years, shows across songs), every cell is filled from the store, and the visitor can explore it in three ways: hovering shows facts instantly, clicking does instant code work (play, sort, open a night's setlist, add or remove a column), and asking sends a question about the clicked cells to the model.

**Architecture:** A new `deadbot/grids.py` builds a grid from a `GridSpec` (row kind, row IDs, column kind, column IDs) using existing store reads (`rows_in`, `one`, `aggregate`), so the three stores need no new SQL. The model calls a new `get_grid` tool, sees a compact table of cells, and places the grid with a `GridRef` in `finish_response`. `finish` rebuilds the full `GridBlock` from the store using the spec carried in that tool payload, the same way `version_strip` re-queries. The same builder backs a new code-only `POST /api/grid` endpoint, so reshaping a grid takes milliseconds and no model call. Asking about cells sends a new optional `focus` field with the question.

**Tech Stack:** Python 3 / FastAPI / Pydantic / LangGraph tools; SQLite, CSV and Postgres stores; React + TypeScript + Vite; vitest + jsdom.

**Spec:** the approved sketch at https://claude.ai/artifact/LCJhGyezR3VFRf5brG8YQQ (three grids on real data), this session's research notes on whereyouworkmatters.org, and `AGENTS.md`. The follow-up memory that makes "Ask" clicks fast is designed separately in `docs/superpowers/specs/2026-10-09-research-notebook-design.md`; Task 7 here defines the `focus` field that design consumes.

## Global Constraints

- Read `AGENTS.md` first. Code guards facts and transport; the model owns judgment. Every cell value, length, track, date and venue comes from the store. The model chooses the rows, columns, their order, how many rows open before "Show all", the headline, the note, the highlighted cells and their notes, and what to say about coverage.
- No code-written coverage prose. Coverage facts (setlists per year, where each length came from, unmatched cells) go to the model in the tool payload and to the visitor in hover cards; the model writes what the visitor should know in its own `note` or `coverage` field. (Same rule Batch 4 applied to charts.)
- Read the model's plan leniently: unknown keys ignored, an unknown row or highlight dropped, an ungrounded `grid_id` falls back to the model's own text via `model_text_block`. Never reject the block for one bad field.
- Ceilings trim and log through `experience.fit`; they never refuse. Grid ceilings: 60 rows, 40 columns (`GRID_ROW_CEILING`, `GRID_COLUMN_CEILING`).
- Prompt and tool-description text says what to do. No "do not" sentences (`tests/test_graph.py` asserts `"do not" not in prompt`).
- Color: cell strength is cream (`rgba(243,240,226,a)`). Gold appears only on the play control and on a selected cell that will play. Rose is for reading links, blue for anything that asks Deadbot. 2px corners.
- After any `deadbot/experience.py` change: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py` then `npm run gen:types --prefix web`. CI fails on drift in `web/openapi.json` or `web/src/generated/api.ts`.
- Python tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q` (full suite before each task's last commit). Web: `npm ci --prefix web` once (the worktree has no `node_modules`), then `npm test --prefix web` and `npm run build --prefix web`.
- Stage files by name. Never `git add -A`. Never bare `git stash`. Never push; give the owner the push command.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the model actually doing the work).
- Fixtures prove rendering; only live runs prove answers improved. Task 8 runs the owner's questions live.

## File Structure

| File | Responsibility |
|---|---|
| `deadbot/grids.py` (new) | `GridSpec`, IDs, cell building for each supported pair, the compact tool payload, the full block, suggestions. No model text except what the ref passes in. |
| `deadbot/tools.py` | `get_grid` tool. |
| `deadbot/progress.py` | Visitor status line for `get_grid`. |
| `deadbot/graph.py` | Two affirmative prompt sentences. |
| `deadbot/finish.py` | `GridRef`, `GridHighlightRef`, union entry, `_resolve_reference` branch. |
| `deadbot/experience.py` | `GridBlock` and parts, `GridRequest`, `AskFocus`, `ExperienceRequest.focus`. |
| `deadbot/api.py` | `POST /api/grid`; focus line in `_prepare`; focus IDs grounded. |
| `web/src/Grid.tsx`, `web/src/Grid.css` (new) | Rendering, fill scale, states, legend, Show all, keyboard movement. |
| `web/src/GridFacts.tsx` (new) | The facts for one cell or header, shared by hover card and detail bar. |
| `web/src/grid-actions.ts` (new) | Pure client actions (sort, column summary) and the two network actions (reshape, ask). |
| `web/src/types.ts`, `web/src/App.tsx` | Union entry; dispatch; `focus` on ask. |
| `web/src/visual-fixtures.ts`, `web/src/fixtures/grid-*.json` | Two fixtures exported from real data. |
| `tests/test_grids.py` (new), `tests/test_finish.py`, `tests/test_research_tools.py`, `tests/test_graph.py`, `tests/test_api_grid.py` (new) | Backend tests. |
| `web/src/Grid.test.tsx` (new) | Frontend tests. |
| `evals/grids-v1.json` (new) | Representative questions for the grid family. |

## Interaction model (what the visitor can do)

Three tiers, so most exploring is instant and the model is used for reasoning.

| Gesture | Speed | Who does it | What happens |
|---|---|---|---|
| Hover or keyboard focus on a cell | instant | client, data already in the block | Hover card: song, date, venue, set and position, what it came out of and went into, length with passes and where the length came from; for song × year, "on 67 of the 124 shows with a setlist that year"; the model's note if the cell is highlighted. |
| Hover a row or column header | instant | client | Row: total and span. Column: nights played, longest, shortest, computed in the browser. |
| Click or tap a cell | instant | client | Selects it. The detail bar under the grid shows the same facts plus a gold Play button (plays every pass in order through the shared player) and an "Ask about this" button. |
| Click a row header (show rows) | instant | client | Opens that night's full setlist under the row, the grid's songs lit, segues as arrows. Data ships in the block. |
| Click a column header | instant | client | Sort rows by that column (longest first), click again to restore the model's order. |
| Shift- or Cmd-click a second cell | instant | client | Two cells selected; the detail bar offers "Play both" and "Compare these". |
| "Add a column" menu | ~100 ms | code, `POST /api/grid` | Suggestions are songs played most on these rows' nights. Picking one re-hydrates the grid from the store. "Remove" on a column header does the same. The model's note stays, marked "Written for the original grid". |
| "Ask about this" / "Compare these" / "Ask about this grid" | model turn | model, with `focus` | Sends a visitor-readable question plus the clicked IDs and facts. The model decides whether it needs more research. |

On touch screens nothing depends on hover: a tap selects, and the detail bar carries everything the hover card shows.

---

### Task 1: Grid core (`deadbot/grids.py`)

**Files:**
- Create: `deadbot/grids.py`
- Test: `tests/test_grids.py`

**Interfaces:**
- Produces:
  - `GridSpec(row_kind: str, row_ids: tuple[str, ...], column_kind: str, column_ids: tuple[str, ...])`, `.measure -> str`, `.to_json() -> dict`, `GridSpec.from_json(dict) -> GridSpec | None`
  - `SUPPORTED_PAIRS: dict[tuple[str, str], str]` = `{("song", "year"): "shows", ("show", "song"): "minutes"}`
  - `grid_id(spec: GridSpec) -> str` (`"grid:<12 hex>"`)
  - `year_id(year: int) -> str` (`"year:1972"`), `parse_year(value: str) -> int | None`
  - `Cell` dataclass, `GridData` dataclass (below)
  - `build(store, spec: GridSpec) -> GridData`

- [ ] **Step 1: Write the failing tests**

```python
"""Grids: two lists of library things and the fact where each pair meets."""

import pytest

from deadbot import grids
from deadbot.data import CanonicalStore
from deadbot.sqlite_store import SqliteCanonicalStore

EUROPE_72 = [
    "gd-1972-04-07", "gd-1972-04-08", "gd-1972-04-11", "gd-1972-04-14", "gd-1972-04-16",
    "gd-1972-04-17", "gd-1972-04-21", "gd-1972-04-24", "gd-1972-04-26", "gd-1972-04-29",
    "gd-1972-05-03", "gd-1972-05-04", "gd-1972-05-07", "gd-1972-05-10", "gd-1972-05-11",
    "gd-1972-05-13", "gd-1972-05-16", "gd-1972-05-18", "gd-1972-05-23", "gd-1972-05-24",
    "gd-1972-05-25", "gd-1972-05-26",
]
DARK_STAR = "song-dark-star"
OTHER_ONE = "song-the-other-one"
PLAYING = "song-playing-in-the-band"


@pytest.fixture(scope="module")
def csv_store():
    return CanonicalStore()


@pytest.fixture
def sqlite_store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def europe_spec():
    return grids.GridSpec("show", tuple(EUROPE_72), "song", (DARK_STAR, OTHER_ONE, PLAYING))


def songs_by_year_spec():
    return grids.GridSpec("song", (DARK_STAR, PLAYING), "year", tuple(grids.year_id(y) for y in range(1967, 1996)))


def test_grid_id_is_stable_and_order_sensitive():
    spec = europe_spec()
    assert grids.grid_id(spec) == grids.grid_id(grids.GridSpec.from_json(spec.to_json()))
    reordered = grids.GridSpec("show", tuple(reversed(EUROPE_72)), "song", spec.column_ids)
    assert grids.grid_id(reordered) != grids.grid_id(spec)
    assert grids.grid_id(spec).startswith("grid:")


def test_unsupported_pair_is_rejected_by_from_json():
    assert grids.GridSpec.from_json({"row_kind": "venue", "row_ids": ["x"], "column_kind": "song", "column_ids": ["y"]}) is None


def test_show_by_song_cells(csv_store):
    data = grids.build(csv_store, europe_spec())
    assert data.measure == "minutes"
    assert [row.id for row in data.rows] == EUROPE_72
    rotterdam = data.cell("gd-1972-05-11", DARK_STAR)
    assert rotterdam.state == "value"
    assert rotterdam.passes == 2
    assert rotterdam.value >= 40  # 44 minutes across two passes on the official release
    assert rotterdam.length_source == "release"
    bickershaw = data.row("gd-1972-05-07")
    assert data.cell("gd-1972-05-07", DARK_STAR).state == "value"
    assert data.cell("gd-1972-05-07", OTHER_ONE).state == "value"
    assert bickershaw.setlist  # the whole night ships for the row's setlist drawer
    assert data.cell("gd-1972-04-08", OTHER_ONE).state == "none"
    assert data.cell("gd-1972-05-23", DARK_STAR).state in {"no_length", "value"}


def test_show_by_song_segue_neighbours(csv_store):
    data = grids.build(csv_store, europe_spec())
    frankfurt = data.cell("gd-1972-04-26", OTHER_ONE)
    assert frankfurt.segue_from == "Drums"
    assert frankfurt.segue_into == "Comes A Time"
    rotterdam = data.cell("gd-1972-05-11", DARK_STAR)
    assert rotterdam.segue_from is None  # Next Time You See Me ended before it
    assert rotterdam.segue_into == "Sugar Magnolia"  # from the second pass


def test_song_by_year_counts_and_setlist_coverage(csv_store):
    data = grids.build(csv_store, songs_by_year_spec())
    assert data.measure == "shows"
    assert data.cell(DARK_STAR, "year:1969").value == 67
    assert data.cell(DARK_STAR, "year:1976").state == "none"
    assert data.cell(PLAYING, "year:1972").value == 80
    assert data.coverage_by_year[1969] == (149, 124)
    assert data.cell(DARK_STAR, "year:1969").of_shows == 124


def test_unknown_ids_are_dropped_not_fatal(csv_store):
    spec = grids.GridSpec("show", ("gd-1972-05-11", "gd-nope"), "song", (DARK_STAR, "song-nope"))
    data = grids.build(csv_store, spec)
    assert [row.id for row in data.rows] == ["gd-1972-05-11"]
    assert [column.id for column in data.columns] == [DARK_STAR]


@pytest.mark.parametrize("spec_factory", [europe_spec, songs_by_year_spec])
def test_sqlite_matches_csv(csv_store, sqlite_store, spec_factory):
    left = grids.build(csv_store, spec_factory())
    right = grids.build(sqlite_store, spec_factory())
    assert left.to_compact() == right.to_compact()
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_grids.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'deadbot.grids'`.

- [ ] **Step 3: Implement `deadbot/grids.py`**

```python
"""Grids: two lists of library things and the fact where each pair meets.

A grid's rows and columns are both library entities: songs across years,
nights across songs. The model chooses the lists, their order and what to say
about them; every cell here is read from the store, so one spec always draws
the same grid. Reads use only rows_in, one and aggregate, which every store
already implements identically.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from deadbot import aggregation
from deadbot.data import CanonicalStore
from deadbot.experience import fit
from deadbot.sequences import Track, _archive_tracks

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
    return int(text) if text.isdigit() and len(text) == 4 else None


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
        if not rows or not columns:
            return None
        return cls(
            row_kind,
            tuple(dict.fromkeys(fit(rows, "grid rows")[:GRID_ROW_CEILING])),
            column_kind,
            tuple(dict.fromkeys(fit(columns, "grid columns")[:GRID_COLUMN_CEILING])),
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
    length_source: Literal["release", "tape"] | None = None
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


def _number(value: Any) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


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
        rows.sort(key=lambda row: (_number(row.get("set_number")), _number(row.get("position_in_set"))))

    song_ids = {performance["song_id"] for performance in performances} | set(spec.column_ids)
    songs = {row["song_id"]: row for row in store.rows_in("songs", "song_id", song_ids)}
    column_ids = [song_id for song_id in spec.column_ids if song_id in songs]
    title = lambda song_id: songs.get(song_id, {}).get("title") or song_id  # noqa: E731

    wanted = [p["performance_id"] for p in performances if p["song_id"] in set(column_ids)]
    release = _release_seconds(store, wanted)
    tape = _archive_tracks(store, wanted)

    cells: dict[tuple[str, str], Cell] = {}
    seconds_by_cell: dict[tuple[str, str], int] = defaultdict(int)
    for show_id in row_ids:
        night = by_show.get(show_id, [])
        for index, performance in enumerate(night):
            song_id = performance["song_id"]
            if song_id not in column_ids:
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
                cell.length_source = cell.length_source or source
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
                label=f"{show.get('show_date', '')} · {city}".strip(" ·"),
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
            if song_id not in column_ids:
                counts[song_id] += 1
    suggestions = [
        {"id": song_id, "label": title(song_id), "rows_with": count}
        for song_id, count in sorted(counts.items(), key=lambda item: (-item[1], title(item[0])))[:12]
    ]
    return GridData(spec=spec, rows=rows, columns=columns, cells=cells, suggestions=suggestions)
```

Lengths prefer the performance's official release track, the curated whole-song length, and fall back to the archive tape track. The tape track is what plays either way. Each cell records which source timed it; the hover card says so.

- [ ] **Step 4: Implement song × year**

```python
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
```

If `test_song_by_year_counts_and_setlist_coverage` fails on the 1969 numbers, print `baseline.setlist_coverage` and `result.rows` and correct the key names to what `AggregationResult` actually returns (`rows` entries carry `year` and `value`, confirmed in `evals/data-charts-v1.json`). Do not change the expected numbers: they were measured on 2026-10-09 against the canonical CSVs. If a data pass has since added setlists, re-measure and update the numbers with a comment giving the date.

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_grids.py -q`
Expected: all pass, including SQLite/CSV parity.

- [ ] **Step 6: Commit**

```bash
git add deadbot/grids.py tests/test_grids.py
git commit -m "Build grids of songs across years and nights across songs from the store"
```

---

### Task 2: The `get_grid` tool, status line and prompt

**Files:**
- Modify: `deadbot/grids.py` (add `tool_payload`)
- Modify: `deadbot/tools.py` (new tool near `get_segue_pairing`, and the tool list at ~2287)
- Modify: `deadbot/progress.py` (`describe_tool_call`)
- Modify: `deadbot/graph.py` (`SYSTEM_PROMPT`, next to the version_strip sentences at ~89 and ~242)
- Test: `tests/test_grids.py`, `tests/test_research_tools.py`, `tests/test_graph.py`

**Interfaces:**
- Consumes: `grids.build`, `grids.GridSpec`, `grids.grid_id`, `grids.year_id`
- Produces: `grids.tool_payload(data: GridData) -> dict` with keys in this order: `grid_id`, `rows_are`, `columns_are`, `measure`, `on_the_page`, `rows`, `columns`, `cells`, `coverage`, `column_suggestions`, `spec`. `spec` is `GridSpec.to_json()` and is what Task 3 rebuilds from.

- [ ] **Step 1: Failing tests**

In `tests/test_grids.py`:

```python
def test_tool_payload_order_and_spec(csv_store):
    data = grids.build(csv_store, europe_spec())
    payload = grids.tool_payload(data)
    assert list(payload)[:5] == ["grid_id", "rows_are", "columns_are", "measure", "on_the_page"]
    assert payload["grid_id"] == grids.grid_id(europe_spec())
    assert grids.GridSpec.from_json(payload["spec"]) == europe_spec()
    assert "archive.org" not in str(payload)  # tape URLs stay out of the model's view
    assert payload["coverage"]["lengths"]["release"] > 0
```

In `tests/test_research_tools.py`, following the `aggregate_data` registration test at ~156:

```python
def test_get_grid_is_registered_and_resolves_titles(csv_store):
    tools = {tool.name: tool for tool in build_tools(csv_store)}
    result = json.loads(tools["get_grid"].invoke({
        "row_kind": "song",
        "rows": ["Dark Star", "song-playing-in-the-band"],
        "column_kind": "year",
        "year_from": 1968,
        "year_to": 1974,
    }))
    assert result["grid_id"].startswith("grid:")
    assert [row["id"] for row in result["rows"]] == ["song-dark-star", "song-playing-in-the-band"]
    assert result["columns"][0]["id"] == "year:1968"


def test_get_grid_tour_selects_show_rows(csv_store):
    tools = {tool.name: tool for tool in build_tools(csv_store)}
    result = json.loads(tools["get_grid"].invoke({
        "row_kind": "show", "tour": "Europe 1972", "column_kind": "song", "columns": ["Dark Star", "The Other One"],
    }))
    assert len(result["rows"]) == 22
```

(Use whatever store fixture `tests/test_research_tools.py` already defines; rename `csv_store` to match.)

In `tests/test_graph.py`:

```python
def test_prompt_teaches_grid_and_get_grid():
    prompt = " ".join(graph.SYSTEM_PROMPT.split())
    assert "get_grid" in prompt
    assert "a grid in finish_response" in prompt
```

- [ ] **Step 2: Run, expect failures** (`AttributeError: tool_payload`, `KeyError: 'get_grid'`, prompt assertion).

- [ ] **Step 3: Implement `tool_payload`**

```python
GRID_NOTE = (
    "A grid in finish_response draws these rows and columns with every cell filled by the library. "
    "Choose the rows to show and their order, how many open before Show all, the cells worth pointing at "
    "with a short note each, and what the visitor should know about gaps."
)


def tool_payload(data: GridData) -> dict[str, Any]:
    compact = data.to_compact()
    lengths = {"release": 0, "tape": 0, "none": 0}
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
```

- [ ] **Step 4: Implement the tool** in `build_tools`, after `get_segue_pairing`:

```python
    @tool
    def get_grid(
        row_kind: Literal["song", "show"],
        column_kind: Literal["year", "song"],
        rows: list[str] | None = None,
        columns: list[str] | None = None,
        tour: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> str:
        """Two lists of library things and the fact where each pair meets, as one table.

        Songs across years (row_kind "song", column_kind "year"): each cell is
        how many shows that year had the song, with each year's setlist
        coverage. Nights across songs (row_kind "show", column_kind "song"):
        each cell is the minutes that song ran that night, the passes it took,
        its set, what it came out of and went into, and where the length came
        from. rows and columns take IDs or titles, in the order you want them.
        For show rows, tour (a tour name) selects the nights instead of
        listing them; for year columns, year_from and year_to set the span. The result carries a grid_id for a grid in
        finish_response, the filled cells as one compact table, coverage
        facts, and for nights the songs played most on them that are not yet
        columns.
        """
        row_ids = _grid_rows(row_kind, rows or [], tour, year_from, year_to)
        if isinstance(row_ids, str):
            return row_ids
        column_ids = _grid_columns(column_kind, columns or [], year_from, year_to)
        if isinstance(column_ids, str):
            return column_ids
        spec = grids.GridSpec.from_json(
            {"row_kind": row_kind, "row_ids": row_ids, "column_kind": column_kind, "column_ids": column_ids}
        )
        if spec is None:
            return _json({"error": "Unsupported grid", "valid": [f"{r} x {c}" for r, c in grids.SUPPORTED_PAIRS]})
        return _json(grids.tool_payload(grids.build(store, spec)))
```

Add the two helpers inside `build_tools` (they close over `store`):

```python
    def _grid_rows(kind: str, rows: list[str], tour: str | None, year_from: int | None, year_to: int | None) -> list[str] | str:
        if kind == "song":
            resolved = [store.resolve_song(value) for value in rows]
            missing = [value for value, song in zip(rows, resolved) if not song]
            if missing:
                return _json({"error": "Song not found or ambiguous", "query": missing})
            return [song["song_id"] for song in resolved if song]
        if rows:
            resolved = [store.resolve_show(value) for value in rows]
            missing = [value for value, show in zip(rows, resolved) if not show]
            if missing:
                return _json({"error": "Show not found or ambiguous", "query": missing})
            return [show["show_id"] for show in resolved if show]
        if tour:
            found = sorted(
                (row for row in store.rows_in("shows", "tour_name", [tour])),
                key=lambda row: row.get("show_date", ""),
            )
            if not found:
                return _json({"error": "No shows on that tour", "query": tour})
            return [row["show_id"] for row in found]
        return _json({"error": "Name the nights as rows, or give a tour"})

    def _grid_columns(kind: str, columns: list[str], year_from: int | None, year_to: int | None) -> list[str] | str:
        if kind == "year":
            if year_from and year_to:
                return [grids.year_id(year) for year in range(year_from, year_to + 1)]
            years = [grids.parse_year(value) for value in columns]
            if not columns or None in years:
                return _json({"error": "Give year columns as year_from and year_to, or as years"})
            return [grids.year_id(year) for year in years if year]
        resolved = [store.resolve_song(value) for value in columns]
        missing = [value for value, song in zip(columns, resolved) if not song]
        if missing:
            return _json({"error": "Song not found or ambiguous", "query": missing})
        return [song["song_id"] for song in resolved if song]
```

Nights are chosen by listing them or by `tour`. If live runs in Task 8 show the model needs nights for a year span, add a store method with a parity test then. Check that `store.rows_in("shows", "tour_name", [tour])` works on all three stores (it is a plain column filter; `test_get_grid_tour_selects_show_rows` covers the CSV store; add the SQLite variant if `tests/test_research_tools.py` has a SQLite fixture).

Register the tool in the list at ~2287 next to `get_segue_pairing`. Import `grids` at the top of `tools.py`.

- [ ] **Step 5: Status line.** In `describe_tool_call`:

```python
    if name == "get_grid":
        return "Laying out the grid"
```

- [ ] **Step 6: Prompt.** Add next to the version_strip sentences in `SYSTEM_PROMPT`:

```
When the answer is how two lists meet (songs across years, nights across songs), get_grid lays them out as one table, and a grid in finish_response draws it with every cell filled by the library. Choose the rows that tell the story, open the most telling ones first, and point at the cells the visitor should hear or notice, each with a short note.
```

- [ ] **Step 7: Run tests** (`tests/test_grids.py tests/test_research_tools.py tests/test_graph.py tests/test_progress.py`), then the full suite. Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add deadbot/grids.py deadbot/tools.py deadbot/progress.py deadbot/graph.py tests/test_grids.py tests/test_research_tools.py tests/test_graph.py
git commit -m "Give the model a get_grid tool for songs across years and nights across songs"
```

---

### Task 3: `GridRef`, `GridBlock` and hydration

**Files:**
- Modify: `deadbot/experience.py` (models; `ExperienceBlock` union at ~863)
- Modify: `deadbot/finish.py` (`GridRef`, `GridHighlightRef`, `BodyItem` at ~557, branch in `_resolve_reference` at ~1294, payload finder near `_find_aggregation_payload` at ~890)
- Modify: `deadbot/grids.py` (`grid_block`)
- Regenerate: `web/openapi.json`, `web/src/generated/api.ts`
- Test: `tests/test_grids.py`, `tests/test_finish.py`, `tests/test_plan_stream.py`

**Interfaces:**
- Consumes: `grids.tool_payload` (`spec`, `grid_id`), `grids.build`
- Produces:
  - `experience.GridBlock` with `type="grid"`, `grid_id`, `title`, `note`, `coverage`, `row_kind`, `column_kind`, `measure`, `columns: list[GridColumn]`, `rows: list[GridRow]`, `open_rows: int | None`, `max_value: int`, `suggestions: list[GridSuggestion]`, `follow_ups: list[FollowUpTopic]`, `spec: GridSpecModel`
  - `GridRow(id, label, sub, total, cells: list[GridCell], setlist: list[GridSetlistEntry])`, `GridCell(state, value, passes, set_label, segue_from, segue_into, length_source, of_shows, tracks: list[PlayableTrack], highlight: bool, note)`
  - `finish.GridRef(type="grid", grid_id, row_ids: list[str] | None, open_rows: int | None, highlights: list[GridHighlightRef], title, note, coverage, follow_ups)`
  - `grids.grid_block(store, payload: dict, *, row_ids, open_rows, highlights, title, note, coverage, follow_ups) -> GridBlock | None`

- [ ] **Step 1: Failing tests**

`tests/test_grids.py`:

```python
def test_grid_block_keeps_model_choices_and_store_facts(csv_store):
    payload = grids.tool_payload(grids.build(csv_store, europe_spec()))
    block = grids.grid_block(
        csv_store,
        payload,
        row_ids=["gd-1972-05-11", "gd-1972-05-07", "gd-nope"],
        open_rows=1,
        highlights=[{"row_id": "gd-1972-05-11", "column_id": DARK_STAR, "note": "The longest of the tour."},
                    {"row_id": "gd-nope", "column_id": DARK_STAR, "note": "ignored"}],
        title="One big jam a night",
        note="They traded it.",
        coverage=None,
        follow_ups=[],
    )
    assert block.type == "grid"
    assert [row.id for row in block.rows][:2] == ["gd-1972-05-11", "gd-1972-05-07"]
    assert len(block.rows) == 22  # rows the model left out follow in payload order
    assert block.open_rows == 1
    rotterdam = block.rows[0].cells[0]
    assert rotterdam.highlight and rotterdam.note == "The longest of the tour."
    assert rotterdam.tracks and rotterdam.tracks[0].audio_url.startswith("https://archive.org/")
    assert block.max_value >= rotterdam.value


def test_grid_block_none_for_bad_spec(csv_store):
    assert grids.grid_block(csv_store, {"grid_id": "grid:x", "spec": {}}, row_ids=None, open_rows=None,
                            highlights=[], title=None, note=None, coverage=None, follow_ups=[]) is None
```

`tests/test_finish.py`, next to the data_chart tests at ~1426:

```python
def test_grid_ref_hydrates_from_this_turns_payload(csv_store):
    payload = grids.tool_payload(grids.build(csv_store, grids.GridSpec("song", ("song-dark-star",), "year", ("year:1969", "year:1970"))))
    grounded = finish.grounded_context([payload])
    ref = finish._BODY_ITEM_ADAPTER.validate_python({"type": "grid", "grid_id": payload["grid_id"], "title": "Peak"})
    block, _ = finish._resolve_reference(ref, grounded, [payload], csv_store)
    assert block.type == "grid" and block.rows[0].cells[0].value == 67


def test_grid_ref_with_unknown_grid_falls_back_to_model_text(csv_store):
    item = finish.validate_body_item({"type": "grid", "grid_id": "grid:000000000000", "title": "T", "note": "N"}, where="test")
    blocks = finish.resolve_items([item], finish.grounded_context([]), [], csv_store)[0]
    assert blocks and blocks[0].type == "editorial"
```

(Match the exact return shapes of `_resolve_reference`, `validate_body_item` and `resolve_items` to their current signatures; the version_strip tests in `tests/test_sequences.py:174-230` show both the fallback and the stream/final parity pattern. Copy that parity test for a grid.)

- [ ] **Step 2: Run, expect failures.**

- [ ] **Step 3: Models in `experience.py`** (after `VersionStripBlock`):

```python
class GridColumn(ExperienceModel):
    id: str
    label: str
    sub: str | None = None


class GridCell(ExperienceModel):
    """One meeting of a row and a column, every fact from the store."""

    state: Literal["value", "none", "no_length", "unknown"]
    value: int | None = Field(default=None, ge=0)
    passes: int = Field(default=0, ge=0)
    set_label: str | None = None
    segue_from: str | None = None
    segue_into: str | None = None
    length_source: Literal["release", "tape"] | None = None
    of_shows: int | None = Field(default=None, ge=0)
    tracks: list[PlayableTrack] = Field(default_factory=list, max_length=LIST_CEILING)
    highlight: bool = False
    note: str | None = None


class GridSetlistEntry(ExperienceModel):
    song_id: str
    title: str
    set_label: str
    segue: bool


class GridRow(ExperienceModel):
    id: str
    label: str
    sub: str | None = None
    total: int | None = None
    cells: list[GridCell] = Field(default_factory=list, max_length=LIST_CEILING)
    setlist: list[GridSetlistEntry] = Field(default_factory=list, max_length=LIST_CEILING)


class GridSuggestion(ExperienceModel):
    id: str
    label: str
    rows_with: int = Field(ge=0)


class GridSpecModel(ExperienceModel):
    row_kind: Literal["song", "show"]
    row_ids: list[str] = Field(min_length=1, max_length=LIST_CEILING)
    column_kind: Literal["year", "song"]
    column_ids: list[str] = Field(min_length=1, max_length=LIST_CEILING)


class GridBlock(ExperienceModel):
    """Two lists and where each pair meets. The model chose the lists, the
    order, what opens first, the cells to point at and the words; the server
    filled every cell, track, date and venue from the library."""

    type: Literal["grid"]
    grid_id: str
    title: str | None = None
    note: str | None = None
    coverage: str | None = None
    row_kind: Literal["song", "show"]
    column_kind: Literal["year", "song"]
    measure: Literal["shows", "minutes"]
    columns: list[GridColumn] = Field(min_length=1, max_length=LIST_CEILING)
    rows: list[GridRow] = Field(min_length=1, max_length=LIST_CEILING)
    open_rows: int | None = Field(default=None, ge=1)
    max_value: int = Field(ge=0)
    suggestions: list[GridSuggestion] = Field(default_factory=list, max_length=LIST_CEILING)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=LIST_CEILING)
    spec: GridSpecModel
```

Add `GridBlock` to the `ExperienceBlock` union at ~863.

- [ ] **Step 4: `grids.grid_block`**

```python
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
        GridBlock, GridCell, GridColumn, GridRow, GridSetlistEntry, GridSpecModel, GridSuggestion, PlayableTrack,
    )

    spec = GridSpec.from_json(payload.get("spec"))
    if spec is None or payload.get("grid_id") != grid_id(spec):
        return None
    data = build(store, spec)
    if not data.rows or not data.columns:
        return None
    by_id = {row.id: row for row in data.rows}
    chosen = [row_id for row_id in dict.fromkeys(row_ids or []) if row_id in by_id]
    ordered = [by_id[row_id] for row_id in chosen] + [row for row in data.rows if row.id not in set(chosen)]
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
        open_rows=open_rows if open_rows and open_rows < len(ordered) else None,
        max_value=data.max_value(),
        suggestions=[GridSuggestion(**s) for s in data.suggestions],
        follow_ups=list(follow_ups),
        spec=GridSpecModel(**spec.to_json()),
    )
```

Rows the model did not list stay, after its chosen rows, in the payload's order: the model's `open_rows` decides what shows before "Show all". That keeps the model's work and never silently drops library rows.

- [ ] **Step 5: `GridRef` in `finish.py`** (after `VersionStripRef`):

```python
class GridHighlightRef(_PlanModel):
    model_config = ConfigDict(extra="ignore")
    row_id: str
    column_id: str
    note: str | None = Field(default=None, description="What to hear or notice in this cell, in a sentence.")


class GridRef(_Ref):
    """A get_grid result from this turn, drawn as a table: rows down the side,
    columns across, every cell filled by the server. Hovering a cell shows its
    facts; clicking plays it or opens the night.

    The place for how two lists meet: which nights carried which songs, how a
    song's year-by-year life compares with another's.
    """

    type: Literal["grid"]
    grid_id: str = Field(description="The grid_id from a get_grid result.")
    row_ids: list[str] | None = Field(
        default=None,
        description="Rows to put first, in reading order. Rows you leave out follow in the result's order.",
    )
    open_rows: int | None = Field(default=None, description="How many rows show before Show all, when the rest can wait.")
    highlights: list[GridHighlightRef] = Field(default_factory=list, description="Cells to point at, by row and column id.")
    title: str | None = Field(default=None, description="What the visitor should see across the grid, in a few words.")
    note: str | None = None
    coverage: str | None = Field(default=None, description="What the visitor should know about gaps in these cells, when it changes how they read them.")
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, description=_FOLLOW_UPS_DESCRIPTION)
```

Add `| GridRef` to `BodyItem`. Add the payload finder and the branch:

```python
def _find_grid_payload(payloads: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    for payload in payloads:
        if payload.get("grid_id") == wanted and "spec" in payload:
            return payload
    return None
```

```python
    if kind == "grid":
        if item.grid_id not in grounded.ids:
            return None, []
        payload = _find_grid_payload(payloads, item.grid_id)
        if payload is None:
            return None, []
        block = grids.grid_block(
            store,
            payload,
            row_ids=item.row_ids,
            open_rows=item.open_rows,
            highlights=[h.model_dump() for h in item.highlights],
            title=item.title,
            note=item.note,
            coverage=item.coverage,
            follow_ups=item.follow_ups,
        )
        return (block, []) if block else (None, [])
```

If `FollowUpTopic` in `finish.py` and in `experience.py` are different classes, convert as the other units' resolvers do (search `follow_ups=` in `finish.py`).

- [ ] **Step 6: Regenerate types**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py
npm run gen:types --prefix web
```

- [ ] **Step 7: Run the targeted tests, then the full suite.** Also `tests/test_experience_contract.py` and `tests/test_plan_stream.py`.

- [ ] **Step 8: Commit**

```bash
git add deadbot/experience.py deadbot/finish.py deadbot/grids.py web/openapi.json web/src/generated/api.ts tests/test_grids.py tests/test_finish.py tests/test_plan_stream.py
git commit -m "Place a grid on the page from the model's get_grid choice, hydrated from the store"
```

---

### Task 4: The grid on the page (rendering, no interaction yet)

**Files:**
- Create: `web/src/Grid.tsx`, `web/src/Grid.css`, `web/src/Grid.test.tsx`
- Create: `web/src/fixtures/grid-europe72.json`, `web/src/fixtures/grid-song-years.json`
- Modify: `web/src/types.ts` (union), `web/src/App.tsx` (`Block` switch at ~1794), `web/src/visual-fixtures.ts` (register `grid`)
- Create: `scripts/export_grid_fixtures.py`

**Interfaces:**
- Consumes: `GridBlock` from `web/src/generated/api.ts`
- Produces: `export function Grid({ block, onFollowUp }: { block: GridBlock; onFollowUp?: (question: string, focus?: AskFocus) => void })`, `export type GridBlock` in `types.ts`, and these pure helpers in `Grid.tsx`, exported for tests: `cellFill(value: number | null, max: number): { alpha: number; light: boolean }`.

- [ ] **Step 1: Fixtures from real data.** `scripts/export_grid_fixtures.py` builds the two sketch grids with `grids.build` + `grids.tool_payload` + `grids.grid_block` against `CanonicalStore()`, with the sketch's headlines, notes and highlights as the model fields, and writes `model_dump(mode="json")` to the two fixture files. Run it with the venv Python. Keep the script: fixtures can be regenerated after data passes.

```python
"""Write the grid fixtures from the canonical data, with sketch-written model fields."""

import json
from pathlib import Path

from deadbot import grids
from deadbot.data import CanonicalStore

OUT = Path("web/src/fixtures")
EUROPE = ["gd-1972-04-07", "gd-1972-04-08", "gd-1972-04-11", "gd-1972-04-14", "gd-1972-04-16", "gd-1972-04-17",
          "gd-1972-04-21", "gd-1972-04-24", "gd-1972-04-26", "gd-1972-04-29", "gd-1972-05-03", "gd-1972-05-04",
          "gd-1972-05-07", "gd-1972-05-10", "gd-1972-05-11", "gd-1972-05-13", "gd-1972-05-16", "gd-1972-05-18",
          "gd-1972-05-23", "gd-1972-05-24", "gd-1972-05-25", "gd-1972-05-26"]


def write(name, spec, **model):
    store = CanonicalStore()
    payload = grids.tool_payload(grids.build(store, spec))
    block = grids.grid_block(store, payload, **model)
    (OUT / name).write_text(json.dumps(block.model_dump(mode="json"), indent=1) + "\n")


write(
    "grid-europe72.json",
    grids.GridSpec("show", tuple(EUROPE), "song", ("song-truckin", "song-dark-star", "song-the-other-one",
                   "song-morning-dew", "song-good-lovin", "song-playing-in-the-band", "song-china-cat-sunflower")),
    row_ids=None, open_rows=None,
    highlights=[{"row_id": "gd-1972-05-11", "column_id": "song-dark-star", "note": "The longest stretch of the tour, in two passes."},
                {"row_id": "gd-1972-05-07", "column_id": "song-dark-star", "note": "Bickershaw: the one night with both."},
                {"row_id": "gd-1972-05-07", "column_id": "song-the-other-one", "note": "Bickershaw: the one night with both."}],
    title="One big jam a night, and they traded it.",
    note="Every night of the tour had Dark Star or The Other One, and only Bickershaw on May 7 had both.",
    coverage=None, follow_ups=[],
)
write(
    "grid-song-years.json",
    grids.GridSpec("song", ("song-dark-star", "song-the-other-one", "song-playing-in-the-band"), "year",
                   tuple(grids.year_id(y) for y in range(1967, 1996))),
    row_ids=None, open_rows=None,
    highlights=[{"row_id": "song-dark-star", "column_id": "year:1969", "note": "Its height, on surviving setlists."}],
    title="Dark Star burned out early. Playing never left.",
    note="Dark Star was at its height in 1969 and was gone after 1974 apart from a handful of nights.",
    coverage="Before 1971 the library has setlists for only some shows, so early counts run low.",
    follow_ups=[],
)
```

- [ ] **Step 2: Failing tests** in `web/src/Grid.test.tsx` (copy the render setup from `VersionStrip.test.tsx`, including its `PlayerProvider` wrapper):

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import europe from "./fixtures/grid-europe72.json";
import years from "./fixtures/grid-song-years.json";
import { Grid, cellFill } from "./Grid";
import type { GridBlock } from "./types";

describe("Grid", () => {
  it("renders a header per column and a row per night", () => {
    render(<Grid block={europe as GridBlock} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader")).toHaveLength(8); // corner + 7 songs
    expect(within(table).getAllByRole("rowheader")).toHaveLength(22);
  });

  it("marks empty cells as not played, and highlighted cells", () => {
    render(<Grid block={europe as GridBlock} />);
    expect(screen.getAllByLabelText(/not played/).length).toBeGreaterThan(0);
    expect(document.querySelectorAll("td.is-highlight")).toHaveLength(3);
  });

  it("hides rows past open_rows until Show all", async () => {
    const block = { ...(europe as GridBlock), open_rows: 5 };
    render(<Grid block={block} />);
    expect(screen.getAllByRole("rowheader")).toHaveLength(5);
    screen.getByRole("button", { name: /show all 22/i }).click();
    expect(await screen.findAllByRole("rowheader")).toHaveLength(22);
  });

  it("scales fill to the block's max and flips text colour on strong cells", () => {
    expect(cellFill(null, 44).alpha).toBe(0);
    expect(cellFill(44, 44)).toEqual({ alpha: 0.9, light: true });
    expect(cellFill(4, 44).light).toBe(false);
  });

  it("labels year columns in short form with the full year for screen readers", () => {
    render(<Grid block={years as GridBlock} />);
    expect(screen.getByRole("columnheader", { name: "1969" })).toHaveTextContent("'69");
  });
});
```

- [ ] **Step 3: Implement `Grid.tsx`.** Structure, matching the sketch and the card anatomy (eyebrow row, headline, note, body, aside, footer):

```tsx
import { useMemo, useState } from "react";
import type { GridBlock } from "./types";
import "./Grid.css";

export function cellFill(value: number | null | undefined, max: number): { alpha: number; light: boolean } {
  if (!value || max <= 0) return { alpha: 0, light: false };
  const alpha = Math.round((0.08 + 0.82 * Math.min(1, value / max)) * 100) / 100;
  return { alpha, light: alpha > 0.55 };
}

const UNIT = { shows: "shows", minutes: "min" } as const;

export function Grid({ block }: { block: GridBlock }) {
  const [open, setOpen] = useState(false);
  const visible = useMemo(
    () => (open || !block.open_rows ? block.rows : block.rows.slice(0, block.open_rows)),
    [open, block],
  );
  const kindLabel = block.row_kind === "show" ? "nights" : "songs";
  return (
    <article className="grid-card">
      <header className="grid-head">
        <div className="eyebrow">
          <span className="label">Grid</span>
          <span className="fact">
            {block.rows.length} {kindLabel} · {block.columns.length} {block.column_kind === "year" ? "years" : "songs"} ·{" "}
            {block.measure === "minutes" ? "minutes played" : "shows per year"}
          </span>
        </div>
        {block.title && <h2 className="headline">{block.title}</h2>}
        {block.note && <p className="note">{block.note}</p>}
      </header>
      <div className="grid-frame">
        <table className={`grid-table grid-${block.column_kind}`}>
          <thead>
            <tr>
              <td />
              {block.columns.map((column) => (
                <th key={column.id} scope="col" aria-label={column.sub ?? column.label}
                    className={block.column_kind === "song" ? "is-vertical" : undefined}>
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id}>
                <th scope="row">
                  {row.label}
                  {(row.sub || row.total != null) && (
                    <span className="sub">{row.sub ?? `${row.total} ${UNIT[block.measure]}`}</span>
                  )}
                </th>
                {row.cells.map((cell, index) => {
                  const column = block.columns[index];
                  const where = `${row.label}, ${column.sub ?? column.label}`;
                  if (cell.state === "none") return <td key={column.id} className="is-none" aria-label={`${where}: not played`} />;
                  if (cell.state === "unknown") return <td key={column.id} className="is-unknown" aria-label={`${where}: not matched yet`}>?</td>;
                  if (cell.state === "no_length")
                    return <td key={column.id} className={`is-dot${cell.highlight ? " is-highlight" : ""}`} aria-label={`${where}: played, length not known`} />;
                  const fill = cellFill(cell.value, block.max_value);
                  return (
                    <td key={column.id}
                        className={`${fill.light ? "is-light" : ""}${cell.highlight ? " is-highlight" : ""}`}
                        style={{ background: `rgba(var(--grid-cell), ${fill.alpha})` }}
                        aria-label={`${where}: ${cell.value} ${UNIT[block.measure]}`}>
                      {cell.value}
                      {cell.passes > 1 && <span className="passes">{cell.passes}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.open_rows && block.open_rows < block.rows.length && (
        <button type="button" className="grid-more" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          {open ? `Show the first ${block.open_rows}` : `Show all ${block.rows.length}`}
        </button>
      )}
      <GridLegend block={block} />
      {block.coverage && (
        <aside className="aside"><span className="label">Coverage</span><p>{block.coverage}</p></aside>
      )}
    </article>
  );
}

function GridLegend({ block }: { block: GridBlock }) {
  const states = new Set(block.rows.flatMap((row) => row.cells.map((cell) => cell.state)));
  return (
    <div className="grid-legend">
      <span><i className="swatch ramp" />{block.measure === "minutes" ? "minutes" : "shows that year"}</span>
      {states.has("none") && <span><i className="swatch dash" />not played</span>}
      {states.has("no_length") && <span><i className="swatch dot" />played, length not known</span>}
      {states.has("unknown") && <span><i className="swatch q">?</i>not matched yet</span>}
      {block.rows.some((row) => row.cells.some((cell) => cell.highlight)) && <span><i className="swatch ring" />worth a listen</span>}
    </div>
  );
}
```

Follow-ups render below with the existing `TopicChips` from `App.tsx` (export it if it isn't, or render them in `App`'s `Block` case the way other units do; follow the version that `ShowUnit` uses).

- [ ] **Step 4: `Grid.css`.** Port the sketch's grid styles (artifact source in this session's scratchpad, `grid-sketch.template.html`, lines for `.grid`, `.legend`, `.sw`, `.aside`) onto the app tokens in `web/src/styles.css`: `--ground`, `--cream`, `--muted`, `--quiet`, `--hair`, `--listen`, `--r`, the small-caps `.label`. Add `--grid-cell: 243, 240, 226;` to the `:root` block in `styles.css`. Cells 40×34px for song columns, 27×34px for year columns; `.grid-frame { overflow-x: auto; }` so the page never scrolls sideways at 375px; row headers `position: sticky; left: 0; background: var(--panel-solid or ground)` so labels stay visible while the cells scroll.

- [ ] **Step 5: Wire it in.** `types.ts`: `| Require<components["schemas"]["GridBlock"], "suggestions" | "follow_ups">` and `export type GridBlock = Extract<ExperienceBlock, { type: "grid" }>`. `App.tsx` `Block` switch: `case "grid": return <Grid block={block} onFollowUp={onFollowUp} />;`. `visual-fixtures.ts`: register `grid` rendering both fixtures as a page with two groups.

- [ ] **Step 6: Run** `npm test --prefix web` and `npm run build --prefix web`. Expected: pass. Then `npm run dev --prefix web` and open `/?fixture=grid` at desktop width and at 375px; check no sideways page scroll and that labels stay sticky. (In a worktree, symlink `web/node_modules` from the main checkout if `npm ci` is slow, and remove the symlink before committing.)

- [ ] **Step 7: Commit**

```bash
git add web/src/Grid.tsx web/src/Grid.css web/src/Grid.test.tsx web/src/fixtures/grid-europe72.json web/src/fixtures/grid-song-years.json web/src/types.ts web/src/App.tsx web/src/visual-fixtures.ts web/src/styles.css scripts/export_grid_fixtures.py
git commit -m "Draw the grid block with cream-scaled cells, empty states and Show all"
```

---

### Task 5: Hover cards, selection, play, setlist drawer, sort (all client-side)

**Files:**
- Create: `web/src/GridFacts.tsx`, `web/src/grid-actions.ts`
- Modify: `web/src/Grid.tsx`, `web/src/Grid.css`, `web/src/Grid.test.tsx`

**Interfaces:**
- Consumes: `usePlayer()` and `toTrack(track, { showDate, venueName })` (`web/src/player.tsx`, `web/src/listen-control.tsx:53`); `VersionStrip.tsx:70-86` is the pattern for playing a queue and detecting "mine".
- Produces:
  - `GridFacts({ block, rowIndex, columnIndex }): JSX` (one cell's facts)
  - `grid-actions.ts`: `sortRows(rows, columnIndex, direction): GridRow[]`, `columnSummary(block, columnIndex): { played: number; longest?: { rowLabel: string; value: number }; shortest?: {...} }`, `type Selection = { row: number; column: number }[]`

- [ ] **Step 1: Failing tests** (append to `Grid.test.tsx`):

```tsx
it("shows a hover card with the cell's facts and the model's note", async () => {
  render(<Grid block={europe as GridBlock} />);
  const cell = screen.getByLabelText(/May 11.*Dark Star/i);
  fireEvent.mouseEnter(cell);
  const card = await screen.findByRole("tooltip");
  expect(card).toHaveTextContent(/Set 2/);
  expect(card).toHaveTextContent(/2 passes/);
  expect(card).toHaveTextContent(/The longest stretch of the tour/);
  expect(card).toHaveTextContent(/Europe|release/i); // where the length came from
});

it("selects on click and offers Play and Ask", () => {
  render(<Grid block={europe as GridBlock} onFollowUp={() => {}} />);
  fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
  expect(screen.getByRole("button", { name: /play/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /ask about this/i })).toBeInTheDocument();
});

it("moves between cells with arrow keys", () => {
  render(<Grid block={europe as GridBlock} />);
  const first = screen.getAllByRole("gridcell")[0];
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowRight" });
  expect(document.activeElement).toBe(screen.getAllByRole("gridcell")[1]);
});

it("sorts by a column on header click and restores on second click", () => {
  render(<Grid block={europe as GridBlock} />);
  const order = () => screen.getAllByRole("rowheader").map((h) => h.textContent);
  const before = order();
  fireEvent.click(screen.getByRole("button", { name: /sort by dark star/i }));
  expect(order()[0]).toMatch(/May 11/);
  fireEvent.click(screen.getByRole("button", { name: /sort by dark star/i }));
  expect(order()).toEqual(before);
});

it("opens a night's setlist under its row", () => {
  render(<Grid block={europe as GridBlock} />);
  fireEvent.click(screen.getByRole("button", { name: /setlist.*May 7/i }));
  expect(screen.getByRole("list", { name: /setlist/i })).toHaveTextContent(/Dark Star/);
});
```

- [ ] **Step 2: Run, expect failures.**

- [ ] **Step 3: Implement.**
  - The table takes `role="grid"`, cells `role="gridcell"` with roving `tabIndex` (one cell at 0, the rest -1). Arrow keys move; Enter or Space selects; Escape clears the selection.
  - Hover card: one absolutely positioned `div role="tooltip"` per grid, shown on `mouseenter` and on keyboard focus after 250 ms, hidden on `mouseleave`/blur. It renders `GridFacts`. Position it above the cell, flipped below near the top edge; clamp inside the frame.
  - `GridFacts` content, as plain sentences, not label rows (owner's taste): first line the song and night (`Dark Star · May 11, 1972`), second line the place (`De Doelen, Rotterdam`), third line one sentence: `Set 2, into Sugar Magnolia. 44 minutes in 2 passes, timed from the official release.` (`timed from the archive tape` for `tape`; `Length not known` for `no_length`). For song × year: `Dark Star · 1969` and `On 67 of the 124 shows with a setlist that year.` The model's note follows in the serif italic style used for pulled lines when `highlight` is true.
  - Selection: click selects one cell; Shift- or Cmd-click adds a second (max two). The selected cell gets the gold outline. The detail bar under the grid renders `GridFacts` for each selected cell, then actions: a gold `Play` (one cell) or `Play both` (two cells), which calls `player.play(queue[0], queue)` with every pass's tracks in order, converted by `toTrack`; and blue `Ask about this` / `Compare these` buttons (wired in Task 7; until then they call `onFollowUp(question)` with the question text only).
  - Row header for show rows becomes a button `aria-label="Open the setlist for May 7"`. Clicking toggles a full-width row under it with `ul aria-label="Setlist"`: titles in order, `>` after a segue, the grid's column songs in cream, the others muted, set labels as small breaks.
  - Column header becomes a button `aria-label="Sort by Dark Star"`; first click sorts by value descending (`sortRows`), second restores the model's order. Hovering the header shows `columnSummary` in the tooltip: `Played on 11 of 22 nights. Longest: May 11, 44 minutes.`
  - On touch (no hover), tapping selects and the detail bar carries the facts. Respect `prefers-reduced-motion` for any tooltip transition.

- [ ] **Step 4: Run** `npm test --prefix web` and `npm run build --prefix web`; check `/?fixture=grid` by hand at both widths, with a keyboard only, and with the player playing a two-pass Dark Star.

- [ ] **Step 5: Commit**

```bash
git add web/src/Grid.tsx web/src/Grid.css web/src/Grid.test.tsx web/src/GridFacts.tsx web/src/grid-actions.ts
git commit -m "Let visitors explore a grid: hover facts, select and play, setlists, sorting, keyboard"
```

---

### Task 6: Reshape the grid instantly (`POST /api/grid`)

**Files:**
- Modify: `deadbot/experience.py` (`GridRequest`), `deadbot/api.py` (route before the SPA catch-all at ~380), `deadbot/grids.py` (nothing new if `grid_block` is reused)
- Modify: `web/src/grid-actions.ts`, `web/src/Grid.tsx`
- Regenerate types
- Test: `tests/test_api_grid.py`, `web/src/Grid.test.tsx`

**Interfaces:**
- Produces: `POST /api/grid` taking `GridRequest { spec: GridSpecModel; title?: str; note?: str; open_rows?: int }` and returning `GridBlock` built by `grids.grid_block(store, grids.tool_payload(grids.build(store, spec)), row_ids=None, highlights=[], title=..., note=..., ...)`. Client: `reshapeGrid(block, change: { addColumn?: string; removeColumn?: string; removeRow?: string }): Promise<GridBlock>`.

- [ ] **Step 1: Failing API test** (`tests/test_api_grid.py`; copy the app/client fixture from an existing API test such as `tests/test_api*.py`):

```python
def test_grid_endpoint_adds_a_column(client):
    spec = {"row_kind": "show", "row_ids": ["gd-1972-05-11", "gd-1972-05-07"], "column_kind": "song",
            "column_ids": ["song-dark-star", "song-morning-dew"]}
    response = client.post("/api/grid", json={"spec": spec, "title": "T"})
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "grid"
    assert [c["id"] for c in body["columns"]] == ["song-dark-star", "song-morning-dew"]
    assert body["rows"][0]["cells"][1]["state"] == "value"  # Morning Dew in Rotterdam


def test_grid_endpoint_rejects_unsupported_pairs_cleanly(client):
    response = client.post("/api/grid", json={"spec": {"row_kind": "song", "row_ids": ["song-dark-star"],
                                                         "column_kind": "song", "column_ids": ["song-dark-star"]}})
    assert response.status_code == 422
```

- [ ] **Step 2: Implement.** `GridRequest(ExperienceModel)` with `spec: GridSpecModel`, `title: str | None = Field(default=None, max_length=300)`, `note: str | None = Field(default=None, max_length=2000)`, `open_rows: int | None = Field(default=None, ge=1)`. `GridSpecModel` already caps list lengths; also enforce `GRID_ROW_CEILING`/`GRID_COLUMN_CEILING` through `GridSpec.from_json` (it trims and logs). The route calls `_enforce_rate_limit(request)` like `/api/experience`, uses `app.state.store`, returns 422 when `from_json` is `None` and 404 when the built grid has no rows or columns. Keep the model's `title` and `note` the client sends back unchanged; the client marks them as written for the original grid.

- [ ] **Step 3: Client.** Column header menu (small `⋯` button beside the sort button) with `Remove`. An `Add a column` button at the end of the header row opens a short list of `block.suggestions` (`Sugar Magnolia · on 21 of 22 nights`). Picking calls `reshapeGrid` and swaps the block in local state; show a quiet `Written for the original grid` line under the note and an `Ask Deadbot about this grid` chip (Task 7). On failure keep the old grid and show `Couldn't change the grid. Try again.`

- [ ] **Step 4: Tests** for the add/remove flow with `fetch` mocked, then the full Python and web suites. Regenerate types first.

- [ ] **Step 5: Commit**

```bash
git add deadbot/experience.py deadbot/api.py web/openapi.json web/src/generated/api.ts tests/test_api_grid.py web/src/grid-actions.ts web/src/Grid.tsx web/src/Grid.test.tsx
git commit -m "Reshape a grid in the browser by adding or removing columns from the library"
```

---

### Task 7: Ask the model about what was clicked (`focus`)

**Files:**
- Modify: `deadbot/experience.py` (`AskFocus`, `ExperienceRequest.focus`), `deadbot/api.py` (`_prepare` at ~149; grounding at ~294 and in `_respond`)
- Modify: `web/src/App.tsx` (`askQuestion` at ~2142 and the request body at ~2176), `web/src/Grid.tsx`
- Regenerate types
- Test: `tests/test_api_focus.py`, `web/src/Grid.test.tsx`

**Interfaces:**
- Produces:
  - `AskFocus(ExperienceModel)`: `label: str (max 300)`, `block_type: Literal["grid"]`, `block_id: str (max 200)`, `ids: list[str] (max 40)`, `facts: list[str] (max 12 items, each max 300)`
  - `ExperienceRequest.focus: AskFocus | None = None`
  - `onFollowUp(question: string, focus?: AskFocus)`
- The research-notebook design consumes `AskFocus` unchanged.

- [ ] **Step 1: Failing tests**

```python
def test_focus_reaches_the_model_as_a_note_after_the_question(app_with_fake_agent):
    app, captured = app_with_fake_agent  # build like the existing api tests that fake the agent
    client = TestClient(app)
    client.post("/api/experience", json={
        "question": "Tell me about the Dark Star from May 11, 1972 in Rotterdam.",
        "focus": {"label": "Dark Star · May 11, 1972", "block_type": "grid", "block_id": "grid:abc",
                  "ids": ["gd-1972-05-11", "gd-1972-05-11-dark-star-2-7", "song-dark-star"],
                  "facts": ["Set 2, into Sugar Magnolia. 44 minutes in 2 passes."]},
    })
    text = captured.messages[-1].content
    assert "The visitor asked from a grid on the page" in text
    assert "gd-1972-05-11-dark-star-2-7" in text


def test_focus_ids_that_exist_are_grounded_and_others_are_dropped(store):
    grounded = api_focus_ids(store, ["gd-1972-05-11", "gd-nope"])  # helper added in api.py
    assert grounded == {"gd-1972-05-11"}
```

(Name and locate `api_focus_ids` to match `api.py`'s helper style.)

- [ ] **Step 2: Implement.**
  - `_prepare`: when `request.focus` is present, append to the final `HumanMessage` content a short block written by code, for example:

    ```
    The visitor asked from a grid on the page ("Dark Star · May 11, 1972").
    Facts already shown: Set 2, into Sugar Magnolia. 44 minutes in 2 passes.
    Library IDs: gd-1972-05-11, gd-1972-05-11-dark-star-2-7, song-dark-star
    ```

    This is transport of what was clicked. The model decides whether to research further.
  - Grounding: IDs in `focus.ids` that resolve in the store (`store.one` on `shows`, `performances`, `songs`, or a `grid:` / `year:` prefix) join this turn's grounded IDs, so the model can place a card for a clicked night without looking it up again. Hydration still reads every fact from the store.
  - Frontend: `askQuestion(prompt, focus?)` adds `focus` to the JSON body. In `Grid`, `Ask about this` sends `Tell me about the ${song} from ${date} in ${city}.` with focus built from the selected cell (ids: show_id, every performance_id, song_id; facts: the `GridFacts` sentence). `Compare these` sends `Compare the ${a} and the ${b}.` with both cells. `Ask Deadbot about this grid` (after a reshape) sends `What stands out in this grid?` with `block_id` = the grid_id, ids = row and column IDs (trimmed to 40), facts = up to 12 column summaries.
  - The question text is what the visitor sees in the chat transcript, so keep it plain.

- [ ] **Step 3: Run the suites; regenerate types first.**

- [ ] **Step 4: Commit**

```bash
git add deadbot/experience.py deadbot/api.py web/openapi.json web/src/generated/api.ts tests/test_api_focus.py web/src/App.tsx web/src/Grid.tsx web/src/Grid.test.tsx
git commit -m "Send what the visitor clicked in a grid along with their question"
```

---

### Task 8: Evals and live verification

**Files:**
- Create: `evals/grids-v1.json` (shape copied from `evals/data-charts-v1.json`)
- Modify: `tests/test_page_quality.py` or `tests/test_evaluations.py` only if the suite loader needs registering

- [ ] **Step 1: Write the suite** with these cases, each with the expected `get_grid` arguments, pinned facts measured on the day, and failure conditions in the visitor's terms:
  1. "Compare Dark Star and Playing in the Band over time." (song × year; also `data-charts-v1` overlap, either a chart or a grid is acceptable; failure: a wall of numbers in prose)
  2. "Tell me about the Europe '72 tour." (show × song via `tour`; failure: no grid and no way to hear the nights)
  3. "Which nights of Spring '77 had Scarlet > Fire, and how long?" (show × song; failure: lengths invented by the model)
  4. "How did The Other One and Dark Star trade places on Europe '72?" (show × song; failure: missing the Bickershaw exception)
  5. "Which songs did they play most in 1977, and when in the year?" (song × year is the wrong pair here; this checks the model picks a chart or ranked list instead, so the grid doesn't become a keyword route)
- [ ] **Step 2: Run live** against the worktree API (see the local-replay notes in the project memory: `deadbot serve` with the OpenAI key, reasoning effort `low`), every case, and read every page. Record per case: did the model choose a grid, were the rows and highlights well chosen, how many model calls and seconds. Use `scripts/measure_turns.py` for the timings.
- [ ] **Step 3: Fix the family, not the example.** If the model misses grids, improve the tool description, `GRID_NOTE` or the prompt sentence, and re-run all five. No keyword routes.
- [ ] **Step 4: Commit** the suite and a short results file `docs/measurements/2026-10-xx-grids.md`.

---

### Task 9 (after the data pass merges): release × song and guest × year

Blocked on the data-gap work running in parallel (Dick's Picks tracks with no song, the four missing volumes, the duplicate Hornsby person). When it merges:

- Add `("release", "song"): "minutes"` (cells from `official_release_tracks` by `release_id` and `song_id`; `unknown` state for a track with an empty `song_id` whose title contains the column song's title, so a blank stays honest) and `("guest", "year"): "shows"` (cells from `store.aggregate` with `dataset="guest_appearances"`, `guest_id`, `group_by="year"`).
- Extend `tool_payload` coverage with unmatched-track counts for releases.
- Same test pattern as Task 1 (facts measured on the day, CSV/SQLite parity), fixtures via `scripts/export_grid_fixtures.py`, and the Dick's Picks and "Who sat in with the Dead?" questions added to `evals/grids-v1.json` and run live.

---

## Self-review notes

- Spec coverage: three grids from the sketch (Tasks 1–4 cover two pairs; Dick's Picks is Task 9 by design), hover (Task 5), instant code clicks (Tasks 5–6), model-call clicks (Task 7), the model/code split (Global Constraints, Task 3's lenient hydration), mobile and keyboard (Tasks 4–5), live verification (Task 8).
- `FollowUpTopic` exists in both `finish.py` and `experience.py`; Task 3 Step 5 says how to convert.
- Year columns use string IDs (`year:1969`) because `grounded_context` only collects strings.
