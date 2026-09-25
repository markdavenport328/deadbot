import json
import time

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


@pytest.mark.parametrize("sql", [
    "SELECT length(randomblob(1000000000))",
    "SELECT replace(hex(zeroblob(100000000)),'0','00')",
])
def test_a_single_oversized_function_call_is_capped(store, sql):
    start = time.monotonic()
    result = store.run_catalog_query(sql)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0
    assert "error" in result and "too large" in result["hint"].lower()


def test_a_printf_blowup_is_capped(store):
    # SQLite's own length limit makes printf('%.*c', ...) return NULL rather
    # than raise once the requested width would exceed the limit set in
    # run_catalog_query, instead of allocating the full string. Either
    # outcome is safe; what matters is that it returns fast and small.
    start = time.monotonic()
    result = store.run_catalog_query("SELECT printf('%.*c', 1000000000, 'x')")
    elapsed = time.monotonic() - start
    assert elapsed < 1.0
    if "error" in result:
        assert "too large" in result["hint"].lower()
    else:
        assert result["rows"] == [[None]]


def test_an_oversized_cell_stays_under_the_result_ceiling(store):
    result = store.run_catalog_query("SELECT group_concat(performance_id) FROM performances")
    text = json.dumps(result)
    assert "error" in result or len(text) < 80_000


def test_blob_results_become_hex(store):
    result = store.run_catalog_query("SELECT x'00'")
    assert result["rows"] == [["00"]]


def test_menu_query_truncation_note_suggests_narrowing_filters(store):
    result = store.run_catalog_query(
        "SELECT show_id, show_date, venue_name, city, tour_name, performance_count FROM show_facts "
        "WHERE (:venue = '' OR venue_name LIKE '%' || :venue || '%') AND (:tour = '' OR tour_name LIKE '%' || :tour || '%') "
        "AND year BETWEEN :year_from AND :year_to ORDER BY show_date",
        {"venue": "", "tour": "", "year_from": 1965, "year_to": 1995},
        menu=True,
    )
    assert result["truncated"] is True
    assert "narrow" in result["note"].lower()
    assert "LIMIT" not in result["note"]


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


def test_tool_reports_a_parameter_the_named_query_ignores(store):
    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    run = lambda **args: json.loads(tool.invoke(args))
    result = run(name="most_played_songs", year_from=1977, venue="Winterland")
    assert result["ignored"] == ["venue"]


def test_tool_rejects_a_year_range_running_backwards(store):
    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    run = lambda **args: json.loads(tool.invoke(args))
    result = run(name="most_played_songs", year_from=1980, year_to=1970)
    assert "error" in result


def test_tool_reports_parameters_it_did_not_use(store):
    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    run = lambda **args: json.loads(tool.invoke(args))
    assert run(sql="SELECT 1 AS n", song="Dark Star")["ignored"] == ["song"]
    assert "sql" in run(name="most_played_songs", year_from=1977, sql="SELECT 1")["ignored"]
