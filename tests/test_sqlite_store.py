from concurrent.futures import ThreadPoolExecutor

import pytest

from deadbot.data import CanonicalStore
from deadbot.sqlite_store import SqliteCanonicalStore


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
