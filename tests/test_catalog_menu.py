import csv
import json
from collections import Counter

import pytest

from deadbot.canonical_import import DEFAULT_CANONICAL_DIR
from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools


def _csv(name):
    with (DEFAULT_CANONICAL_DIR / f"{name}.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


SHOWS = {row["show_id"]: row for row in _csv("shows")}
VENUES = {row["venue_id"]: row["name"] for row in _csv("venues")}
SONGS = {row["title"]: row["song_id"] for row in _csv("songs")}
PERFORMANCES = _csv("performances")
PERF_SHOW = {row["performance_id"]: row["show_id"] for row in PERFORMANCES}
TRACKS = _csv("official_release_tracks")


def _year(show_id):
    return int(SHOWS[show_id]["show_date"][:4])


@pytest.fixture
def run(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    yield lambda **args: json.loads(tool.invoke(args))
    store.close()


def _column(result, name):
    index = result["columns"].index(name)
    return [row[index] for row in result["rows"]]


def test_releases_covering_years(run):
    expected = {t["release_id"] for t in TRACKS if t["performance_id"] in PERF_SHOW and _year(PERF_SHOW[t["performance_id"]]) == 1972}
    result = run(name="releases_covering_years", year_from=1972)
    assert set(_column(result, "release_id")) == expected
    assert "release-europe-72-the-complete-recordings-2011" in expected


def test_releases_from_venue(run):
    expected = {
        t["release_id"] for t in TRACKS
        if t["performance_id"] in PERF_SHOW and "winterland" in VENUES.get(SHOWS[PERF_SHOW[t["performance_id"]]]["venue_id"], "").lower()
    }
    assert set(_column(run(name="releases_from_venue", venue="Winterland"), "release_id")) == expected


def test_releases_with_show(run):
    expected = {t["release_id"] for t in TRACKS if PERF_SHOW.get(t["performance_id"]) == "gd-1972-08-27"}
    assert set(_column(run(name="releases_with_show", show="1972-08-27"), "release_id")) == expected


def test_most_played_songs(run):
    counts = Counter(p["song_id"] for p in PERFORMANCES if _year(p["show_id"]) == 1977)
    top_song, top_count = counts.most_common(1)[0]
    result = run(name="most_played_songs", year_from=1977, limit=5)
    assert (_column(result, "song_id")[0], _column(result, "times_played")[0]) == (top_song, top_count)
    assert _column(result, "shows_in_range")[0] == sum(1 for show_id in SHOWS if _year(show_id) == 1977)


def test_song_by_year(run):
    song_id = SONGS["Dark Star"]
    counts = Counter(_year(p["show_id"]) for p in PERFORMANCES if p["song_id"] == song_id)
    result = run(name="song_by_year", song="Dark Star")
    assert dict(zip(_column(result, "year"), _column(result, "times_played"))) == dict(counts)


def test_song_set_positions(run):
    song_id = SONGS["Scarlet Begonias"]
    expected = sum(
        1 for p in PERFORMANCES
        if p["song_id"] == song_id and 1980 <= _year(p["show_id"]) <= 1989 and p["set_number"] == "2" and p["position_in_set"] == "1"
    )
    result = run(name="song_set_positions", song="Scarlet Begonias", year_from=1980, year_to=1989)
    by_set = dict(zip(_column(result, "set_number"), _column(result, "opened")))
    assert by_set[2] == expected


def test_song_neighbors(run):
    song_id = SONGS["Scarlet Begonias"]
    position = {(p["show_id"], p["set_number"], int(p["position_in_set"])): p["song_id"] for p in PERFORMANCES if p["position_in_set"]}
    after = Counter(
        position.get((p["show_id"], p["set_number"], int(p["position_in_set"]) + 1))
        for p in PERFORMANCES if p["song_id"] == song_id and p["position_in_set"]
    )
    after.pop(None, None)
    result = run(name="song_neighbors", song="Scarlet Begonias")
    rows = [dict(zip(result["columns"], row)) for row in result["rows"]]
    top_after = next(row for row in rows if row["direction"] == "after")
    assert top_after["song_id"] == after.most_common(1)[0][0] == SONGS["Fire On The Mountain"]


def test_shows_by_venue(run):
    expected = {show_id for show_id, show in SHOWS.items() if "winterland" in VENUES.get(show["venue_id"], "").lower()}
    assert set(_column(run(name="shows", venue="Winterland"), "show_id")) == expected
