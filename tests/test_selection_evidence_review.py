import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_selection_evidence_review import document


def test_selection_evidence_review_is_materialized_and_preserves_holds():
    path = Path(__file__).parents[1] / "data" / "editorial" / "selection-evidence-review.json"
    materialized = json.loads(path.read_text(encoding="utf-8"))
    assert materialized == document()
    summary = materialized["summary"]
    assert summary["by_source"] == {
        "deadnet-official-release-pass": 5,
        "headyversion": 16,
        "rolling-stone-australia": 20,
    }
    assert summary["by_resolution_state"]["resolved_unique_show"] == 19
    assert summary["by_resolution_state"]["held_ambiguous_show_date"] > 0
    assert summary["by_resolution_state"]["held_multiple_canonical_performances"] > 0
