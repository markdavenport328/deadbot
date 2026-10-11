from pathlib import Path

from deadbot.evaluations import evaluate_suite, load_suite
from deadbot.sqlite_store import SqliteCanonicalStore

SUITE = Path(__file__).parents[1] / "evals" / "grids-v1.json"


def test_grids_suite_passes(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    try:
        result = evaluate_suite(SUITE, store=store)
    finally:
        store.close()
    assert result["total"] == 7
    assert result["failed"] == 0, result


def test_grids_suite_states_failures_for_live_review():
    for case in load_suite(SUITE)["cases"]:
        assert case["question"] and case["failure_conditions"]
