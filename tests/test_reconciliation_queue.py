import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_reconciliation_queue import document


def test_reconciliation_queue_matches_current_coverage_gaps():
    path = Path(__file__).parents[1] / "data" / "coverage" / "reconciliation-queue.json"
    materialized = json.loads(path.read_text(encoding="utf-8"))
    assert materialized == document()
    assert materialized["queue_counts"] == {
        "setlist_reconciliation": 282,
        "show_performer_reconciliation": 90,
        "total": 372,
    }
    assert all(row["status"] == "source_empty" for row in materialized["setlist_reconciliation"])
    assert all(row["held_reason"] for row in materialized["show_performer_reconciliation"])
    assert all(row["next_action"] for row in materialized["setlist_reconciliation"])
    assert all(row["next_action"] for row in materialized["show_performer_reconciliation"])
