"""Grids: two lists of library things and the fact where each pair meets."""

import dataclasses
import logging

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


def test_from_json_trims_to_the_ceilings_and_logs(caplog):
    payload = {
        "row_kind": "show",
        "row_ids": [f"gd-1970-01-{n:03d}" for n in range(grids.GRID_ROW_CEILING + 5)],
        "column_kind": "song",
        "column_ids": [f"song-{n}" for n in range(grids.GRID_COLUMN_CEILING + 3)],
    }
    with caplog.at_level(logging.WARNING, logger="deadbot.grids"):
        spec = grids.GridSpec.from_json(payload)
    assert spec is not None
    assert len(spec.row_ids) == grids.GRID_ROW_CEILING
    assert len(spec.column_ids) == grids.GRID_COLUMN_CEILING
    assert len([record for record in caplog.records if record.name == "deadbot.grids"]) == 2


def test_show_by_song_cells(csv_store):
    data = grids.build(csv_store, europe_spec())
    assert data.measure == "minutes"
    assert [row.id for row in data.rows] == EUROPE_72
    assert data.row("gd-1972-05-11").label.startswith("May 11, 1972 · Rotterdam")
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
    dry = data.cell("gd-1972-05-23", DARK_STAR)  # two passes, no release track and no timed tape track
    assert (dry.state, dry.passes, dry.value, dry.length_source) == ("no_length", 2, None, None)


def test_a_cell_with_only_a_tape_length_says_tape(csv_store):
    spec = grids.GridSpec("show", ("gd-1968-01-17",), "song", (DARK_STAR,))
    cell = grids.build(csv_store, spec).cell("gd-1968-01-17", DARK_STAR)
    assert cell.state == "value"
    assert cell.length_source == "tape"
    assert cell.tracks


class TableStore:
    """The three reads grids use, over plain dict tables."""

    def __init__(self, **tables):
        self.tables = tables

    def rows_in(self, table, column, values):
        wanted = set(values)
        return [row for row in self.tables.get(table, []) if row.get(column, "") in wanted]


def _perf(performance_id, song_id="s1", set_number="1", position="1", **extra):
    return {"performance_id": performance_id, "show_id": "gd-1", "song_id": song_id, "set_number": set_number,
            "position_in_set": position, "set_label": "Set 1", "segue_into_next": "false", **extra}


def _tape(performance_id, seconds):
    return {"performance_id": performance_id, "platform": "archive", "link_type": "recording-track",
            "url": "https://archive.org/x", "performance_link_id": performance_id, "duration_seconds": str(seconds)}


def _store(performances, links=(), releases=()):
    return TableStore(
        shows=[{"show_id": "gd-1", "show_date": "1970-01-01", "venue_id": "v1"}],
        venues=[{"venue_id": "v1", "name": "Hall", "city": "Town"}],
        songs=[{"song_id": "s1", "title": "One"}, {"song_id": "s2", "title": "Two"}],
        performances=performances,
        performance_links=list(links),
        official_release_tracks=list(releases),
    )


def _one_cell(store):
    return grids.build(store, grids.GridSpec("show", ("gd-1",), "song", ("s1",))).cell("gd-1", "s1")


def test_length_source_is_mixed_when_passes_come_from_release_and_tape():
    store = _store(
        [_perf("p1", position="1"), _perf("p2", position="2")],
        links=[_tape("p2", 600)],
        releases=[{"performance_id": "p1", "duration_seconds": "300"}],
    )
    cell = _one_cell(store)
    assert (cell.state, cell.value, cell.length_source) == ("value", 15, "mixed")


def test_length_source_is_release_or_tape_when_every_timed_pass_agrees():
    release_only = _store([_perf("p1")], links=[_tape("p1", 999)], releases=[{"performance_id": "p1", "duration_seconds": "300"}])
    assert _one_cell(release_only).length_source == "release"
    tape_only = _store([_perf("p1"), _perf("p2", position="2")], links=[_tape("p1", 300), _tape("p2", 300)])
    assert _one_cell(tape_only).length_source == "tape"


def test_untimed_pass_does_not_make_a_cell_mixed():
    store = _store([_perf("p1"), _perf("p2", position="2")], releases=[{"performance_id": "p1", "duration_seconds": "300"}])
    cell = _one_cell(store)
    assert (cell.passes, cell.length_source) == (2, "release")


def test_night_order_puts_blank_set_and_position_last_with_performance_id_as_tiebreaker():
    store = _store([
        _perf("p-blank", song_id="s2", set_number="", position=""),
        _perf("p-b", song_id="s2", position="1"),
        _perf("p-a", song_id="s1", position="1"),
        _perf("p-2", song_id="s1", position="2"),
    ])
    data = grids.build(store, grids.GridSpec("show", ("gd-1",), "song", ("s1", "s2")))
    assert [entry["song_id"] for entry in data.row("gd-1").setlist] == ["s1", "s2", "s1", "s2"]
    assert data.cell("gd-1", "s1").performance_ids == ("p-a", "p-2")


def test_parse_year_accepts_ascii_digits_only():
    assert grids.parse_year("year:1969") == 1969
    assert grids.parse_year("\uff11\uff19\uff16\uff19") is None
    assert grids.parse_year("19x9") is None


def test_from_json_normalises_year_columns_and_dedupes():
    spec = grids.GridSpec.from_json(
        {"row_kind": "song", "row_ids": [DARK_STAR], "column_kind": "year", "column_ids": ["1969", "year:1969", "1970"]}
    )
    assert spec.column_ids == ("year:1969", "year:1970")


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
    assert dataclasses.asdict(left) == dataclasses.asdict(right)  # segues, lengths, tracks, setlists, suggestions, coverage


def test_tool_payload_order_and_spec(csv_store):
    data = grids.build(csv_store, europe_spec())
    payload = grids.tool_payload(data)
    assert list(payload)[:5] == ["grid_id", "rows_are", "columns_are", "measure", "on_the_page"]
    assert payload["grid_id"] == grids.grid_id(europe_spec())
    assert grids.GridSpec.from_json(payload["spec"]) == europe_spec()
    assert "archive.org" not in str(payload)  # tape URLs stay out of the model's view
    assert payload["coverage"]["lengths"]["release"] > 0
    assert list(payload) == [
        "grid_id", "rows_are", "columns_are", "measure", "on_the_page", "rows", "columns", "cells",
        "coverage", "column_suggestions", "spec",
    ]


def test_tool_payload_counts_every_length_source():
    store = _store(
        [_perf("p1"), _perf("p2", position="2"), _perf("p3", song_id="s2", position="3")],
        links=[_tape("p2", 600)],
        releases=[{"performance_id": "p1", "duration_seconds": "300"}],
    )
    spec = grids.GridSpec("show", ("gd-1",), "song", ("s1", "s2"))
    lengths = grids.tool_payload(grids.build(store, spec))["coverage"]["lengths"]
    assert lengths == {"release": 0, "tape": 0, "mixed": 1, "none": 1}


def test_tool_payload_lists_years_whose_setlists_are_incomplete(csv_store):
    payload = grids.tool_payload(grids.build(csv_store, songs_by_year_spec()))
    assert "lengths" not in payload["coverage"]
    by_year = {entry["year"]: entry for entry in payload["coverage"]["setlists_by_year"]}
    assert by_year[1969] == {"year": 1969, "shows_on_record": 149, "shows_with_setlist": 124}


def test_grid_block_keeps_model_choices_and_store_facts(csv_store):
    payload = grids.tool_payload(grids.build(csv_store, europe_spec()))
    block = grids.grid_block(
        csv_store,
        payload,
        row_ids=["gd-1972-05-11", "gd-1972-05-07", "gd-nope"],
        open_rows=1,
        highlights=[
            {"row_id": "gd-1972-05-11", "column_id": DARK_STAR, "note": "The longest of the tour."},
            {"row_id": "gd-nope", "column_id": DARK_STAR, "note": "ignored"},
        ],
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
    assert (
        grids.grid_block(
            csv_store, {"grid_id": "grid:x", "spec": {}}, row_ids=None, open_rows=None,
            highlights=[], title=None, note=None, coverage=None, follow_ups=[],
        )
        is None
    )
