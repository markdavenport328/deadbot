"""Grids: two lists of library things and the fact where each pair meets."""

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
