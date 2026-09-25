from pathlib import Path

from deadbot.evaluations import evaluate_suite
from deadbot.sqlite_store import SqliteCanonicalStore


def test_catalog_suite_passes(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    try:
        result = evaluate_suite(Path("evals/catalog-v1.json"), store=store)
    finally:
        store.close()
    assert result["failed"] == 0, result
