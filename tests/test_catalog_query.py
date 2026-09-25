import json

import pytest

from deadbot.data import CanonicalStore
from deadbot.sqlite_store import CATALOG_QUERY_MAX_ROWS, SqliteCanonicalStore
from deadbot.tools import build_tools


@pytest.fixture
def store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def test_select_returns_columns_and_rows(store):
    result = store.run_catalog_query("SELECT song_title, COUNT(*) AS n FROM performance_facts WHERE year = 1977 GROUP BY song_id ORDER BY n DESC LIMIT 3")
    assert result["columns"] == ["song_title", "n"] and result["row_count"] == 3 and result["truncated"] is False


def test_named_parameters_bind(store):
    result = store.run_catalog_query("SELECT COUNT(*) FROM show_facts WHERE year = :year", {"year": 1977})
    assert result["rows"][0][0] > 50


def test_rows_are_capped(store):
    result = store.run_catalog_query("SELECT performance_id FROM performances")
    assert result["row_count"] == CATALOG_QUERY_MAX_ROWS and result["truncated"] is True and "LIMIT" in result["note"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM songs",
    "UPDATE songs SET title = 'x'",
    "CREATE TABLE t (x)",
    "PRAGMA table_info(songs)",
    "ATTACH DATABASE ':memory:' AS other",
])
def test_anything_but_reading_is_refused(store, sql):
    result = store.run_catalog_query(sql)
    assert "error" in result and result["hint"]


def test_two_statements_are_refused(store):
    assert "error" in store.run_catalog_query("SELECT 1; SELECT 2")


def test_runaway_query_times_out(store):
    result = store.run_catalog_query("SELECT COUNT(*) FROM performances a, performances b, performances c")
    assert "error" in result and "time" in result["hint"].lower()


def test_unknown_column_explains_itself(store):
    assert "no such column" in store.run_catalog_query("SELECT nope FROM show_facts")["error"]


def test_tool_is_registered_only_for_stores_that_can_query(store):
    assert "query_catalog" in {t.name for t in build_tools(store)}
    assert "query_catalog" not in {t.name for t in build_tools(CanonicalStore())}


def test_tool_description_stays_small_and_lists_every_query(store):
    from deadbot.catalog_queries import NAMED_QUERIES

    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    assert len(tool.description) < 3500
    assert all(name in tool.description for name in NAMED_QUERIES)


def test_tool_runs_free_sql_and_explains_bad_calls(store):
    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    run = lambda **args: json.loads(tool.invoke(args))
    assert run(sql="SELECT COUNT(*) AS n FROM show_facts")["rows"][0][0] > 2000
    assert run()["error"].startswith("Pass name")
    assert "queries" in run(name="nope")
    assert run(name="most_played_songs")["requires"] == ["year_from"]
    assert run(name="song_by_year", song="Not A Real Song")["error"].startswith("Song not found")
