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

    def in_range(show_id):
        return 1980 <= _year(show_id) <= 1989

    max_position: dict[tuple[str, str], int] = {}
    for p in PERFORMANCES:
        if not p["position_in_set"]:
            continue
        key = (p["show_id"], p["set_number"])
        pos = int(p["position_in_set"])
        if pos > max_position.get(key, -1):
            max_position[key] = pos

    opened: Counter = Counter()
    closed: Counter = Counter()
    appeared_sets: set[int] = set()
    for p in PERFORMANCES:
        if p["song_id"] != song_id or not in_range(p["show_id"]) or not p["position_in_set"]:
            continue
        set_number = int(p["set_number"])
        appeared_sets.add(set_number)
        pos = int(p["position_in_set"])
        if pos == 1:
            opened[set_number] += 1
        if pos == max_position.get((p["show_id"], p["set_number"])):
            closed[set_number] += 1

    result = run(name="song_set_positions", song="Scarlet Begonias", year_from=1980, year_to=1989)
    result_sets = _column(result, "set_number")
    assert set(result_sets) == appeared_sets
    by_opened = dict(zip(result_sets, _column(result, "opened")))
    by_closed = dict(zip(result_sets, _column(result, "closed")))
    assert by_opened == {s: opened.get(s, 0) for s in appeared_sets}
    assert by_closed == {s: closed.get(s, 0) for s in appeared_sets}


def test_song_neighbors(run):
    song_id = SONGS["Scarlet Begonias"]
    by_position = {
        (p["show_id"], p["set_number"], int(p["position_in_set"])): p
        for p in PERFORMANCES if p["position_in_set"]
    }

    after_times: Counter = Counter()
    after_segued: Counter = Counter()
    before_times: Counter = Counter()
    before_segued: Counter = Counter()
    for p in PERFORMANCES:
        if p["song_id"] != song_id or not p["position_in_set"]:
            continue
        pos = int(p["position_in_set"])
        nxt = by_position.get((p["show_id"], p["set_number"], pos + 1))
        if nxt is not None:
            after_times[nxt["song_id"]] += 1
            if p["segue_into_next"] == "true":
                after_segued[nxt["song_id"]] += 1
        prv = by_position.get((p["show_id"], p["set_number"], pos - 1))
        if prv is not None:
            before_times[prv["song_id"]] += 1
            if prv["segue_into_next"] == "true":
                before_segued[prv["song_id"]] += 1

    result = run(name="song_neighbors", song="Scarlet Begonias", limit=200)
    rows = [dict(zip(result["columns"], row)) for row in result["rows"]]
    after_rows = {row["song_id"]: row for row in rows if row["direction"] == "after"}
    before_rows = {row["song_id"]: row for row in rows if row["direction"] == "before"}

    assert set(after_rows) == set(after_times)
    assert set(before_rows) == set(before_times)
    assert {sid: row["times"] for sid, row in after_rows.items()} == dict(after_times)
    assert {sid: row["times"] for sid, row in before_rows.items()} == dict(before_times)
    assert {sid: row["segued"] for sid, row in after_rows.items()} == {
        sid: after_segued.get(sid, 0) for sid in after_times
    }
    assert {sid: row["segued"] for sid, row in before_rows.items()} == {
        sid: before_segued.get(sid, 0) for sid in before_times
    }

    top_after = after_times.most_common(1)[0][0]
    assert top_after == SONGS["Fire On The Mountain"]
    assert after_rows[top_after]["segued"] == after_segued[top_after]


def test_shows_by_venue(run):
    expected = {show_id for show_id, show in SHOWS.items() if "winterland" in VENUES.get(show["venue_id"], "").lower()}
    assert set(_column(run(name="shows", venue="Winterland"), "show_id")) == expected
