import json
import os
import shutil
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from deadbot import aggregation
from deadbot.data import CanonicalStore
from deadbot.sqlite_build import SQLITE_SCHEMA_VERSION
from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools


@pytest.fixture(scope="module")
def csv_store():
    return CanonicalStore()


@pytest.fixture
def store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def test_missing_file_names_the_build_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="db-build"):
        SqliteCanonicalStore(tmp_path / "absent.sqlite")


@pytest.mark.parametrize("show_query", ["1977-05-08", "1972-08-27"])
def test_show_context_matches_the_csv_store(store, csv_store, show_query):
    show = csv_store.resolve_show(show_query)
    assert store.resolve_show(show_query) == show
    assert store.show_context(show) == csv_store.show_context(show)


@pytest.mark.parametrize("title", ["Dark Star", "Truckin'", "Sugar Magnolia"])
def test_song_views_match_the_csv_store(store, csv_store, title):
    song = csv_store.resolve_song(title)
    assert store.song_context(song) == csv_store.song_context(song)
    assert store.song_performance_profile(song) == csv_store.song_performance_profile(song)


def test_album_and_performance_views_match_the_csv_store(store, csv_store):
    release = csv_store.resolve_release("American Beauty")
    assert store.album_context(release) == csv_store.album_context(release)
    performance_id = csv_store.show_context(csv_store.resolve_show("1977-05-08"))["performances"][0]["performance_id"]
    assert store.performance_context(performance_id) == csv_store.performance_context(performance_id)


def test_selection_signals_and_coverage_read(store):
    signals = store.selection_signal_rows()
    assert signals and all(isinstance(signal, dict) for signal in signals)
    assert store.coverage_summary()["dated_show_count"] > 2000


def test_parallel_threads_each_read_safely(store):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.resolve_song("Dark Star")["song_id"], range(32)))
    assert len(set(results)) == 1


def test_response_cache_round_trip_and_expiry(store):
    store.ensure_response_cache()
    version = store.data_version()
    store.store_response("what is dark star", version, "What is Dark Star?", {"mode": "answer"})
    assert store.cached_response("what is dark star", version, 60) == {"mode": "answer"}
    assert store.cached_response("what is dark star", "other-version", 60) is None
    assert store.cached_response("what is dark star", version, -1) is None


def test_store_reopens_after_close(store):
    store.close()
    assert store.resolve_song("Dark Star")


def test_short_lived_thread_pools_do_not_leak_connections(store):
    # LangGraph starts a fresh thread pool for every tools step; each round
    # here stands in for one question's worth of parallel tool calls.
    for _ in range(50):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda query: (store.resolve_song("Dark Star"), store.search_shows(query)), ["1977", "Cornell", "1972", "Veneta"]))
    assert store.open_connection_count <= SqliteCanonicalStore.MAX_IDLE_CONNECTIONS == 8


def test_a_connection_returned_after_close_is_closed_not_pooled(store):
    store.resolve_song("Dark Star")
    assert store.open_connection_count >= 1
    old_pool = store._pool
    borrowed = old_pool.get_nowait()
    store._checked_out += 1
    store.close()
    store._give_back(old_pool, borrowed)
    assert store.open_connection_count == 0
    assert old_pool.qsize() == 0
    with pytest.raises(Exception):
        borrowed.raw.execute("SELECT 1")
    assert store.resolve_song("Dark Star")


def test_close_drains_idle_connections(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: store.resolve_song("Dark Star"), range(16)))
    assert store.open_connection_count >= 1
    store.close()
    assert store.open_connection_count == 0


def test_verify_ready_passes_on_a_built_file(store):
    store.verify_ready()


def test_verify_ready_names_sqlite_on_a_version_mismatch(store, monkeypatch):
    monkeypatch.setattr("deadbot.sqlite_store.SQLITE_SCHEMA_VERSION", SQLITE_SCHEMA_VERSION + 1)
    with pytest.raises(RuntimeError, match="SQLite schema version"):
        store.verify_ready()


def test_data_version_carries_the_build_input_fingerprint(store):
    fingerprint = store._query("SELECT input_fingerprint FROM deadbot_schema_metadata")[0]["input_fingerprint"]
    assert fingerprint
    assert store.data_version().endswith(f"|input_fingerprint={fingerprint}")
    assert "shows=" in store.data_version()


def test_opens_from_a_read_only_directory(built_sqlite, tmp_path):
    folder = tmp_path / "readonly"
    folder.mkdir()
    database = folder / "deadbot.sqlite"
    shutil.copy(built_sqlite, database)
    os.chmod(database, 0o444)
    os.chmod(folder, 0o555)
    try:
        store = SqliteCanonicalStore(database, response_cache_path=tmp_path / "cache.sqlite")
        try:
            assert store.resolve_song("Dark Star")
        finally:
            store.close()
        leftovers = [path.name for path in folder.iterdir() if path.name != "deadbot.sqlite"]
        assert not any(name.endswith(("-journal", "-wal", "-shm")) for name in leftovers), leftovers
    finally:
        os.chmod(folder, stat.S_IRWXU)
        os.chmod(database, stat.S_IRUSR | stat.S_IWUSR)


# ---- aggregate() parity: the SQLite store's SQL GROUP BY vs
# CanonicalStore.aggregate's pure-Python reference implementation, over the
# real catalog. Both feed raw grouped rows through
# deadbot.aggregation.assemble_result, so any difference is a bug in the SQL.


def _every_aggregate_combo() -> list:
    return [
        pytest.param(dataset, group_by, measure, id=f"{dataset}-{group_by}-{measure}")
        for (dataset, group_by), measures in sorted(aggregation._MEASURES_BY_COMBO.items())
        for measure in sorted(measures)
    ]


@pytest.mark.parametrize("dataset, group_by, measure", _every_aggregate_combo())
def test_aggregate_matches_the_csv_store_for_every_valid_combo(store, csv_store, dataset, group_by, measure):
    request = aggregation.AggregationRequest(
        dataset=dataset, group_by=group_by, measure=measure, limit=50, fill_missing=(group_by == "year"),
    )
    assert store.aggregate(request).to_payload() == csv_store.aggregate(request).to_payload()


@pytest.mark.parametrize(
    "payload",
    [
        {"dataset": "performances", "group_by": "year", "measure": "count", "fill_missing": True,
         "filters": {"song_id": "song-dark-star"}},
        {"dataset": "guest_appearances", "group_by": "year", "measure": "distinct_shows",
         "filters": {"guest_id": "person-jack-casady"}},
        {"dataset": "shows", "group_by": "year", "measure": "count", "fill_missing": True,
         "filters": {"year_from": 1972, "year_to": 1974}},
        {"dataset": "performances", "group_by": "song", "measure": "count", "filters": {"year": 1977}},
        {"dataset": "shows", "group_by": "venue", "measure": "count",
         "filters": {"venue_id": "venue-unknown-", "year": 1800}},
    ],
    ids=["dark-star-by-year", "guest-by-year", "shows-year-range", "songs-in-1977", "zero-match"],
)
def test_filtered_aggregates_match_the_csv_store(store, csv_store, payload):
    request = aggregation.parse_request({"limit": 50, **payload})
    assert store.aggregate(request).to_payload() == csv_store.aggregate(request).to_payload()


def test_aggregate_data_tool_ranks_most_played_songs_from_sqlite(store, csv_store):
    tool = next(item for item in build_tools(store) if item.name == "aggregate_data")
    result = json.loads(
        tool.invoke({"dataset": "performances", "group_by": "song", "measure": "count", "limit": 10})
    )
    assert "error" not in result
    assert len(result["rows"]) == 10
    values = [row["value"] for row in result["rows"]]
    assert values == sorted(values, reverse=True) and values[0] > 0
    assert result["total"] == len(csv_store.rows("performances"))
    assert result["setlist_coverage"]["shows_with_setlist"] > 0
