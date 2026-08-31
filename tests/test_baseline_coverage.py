import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_baseline_coverage import document


def test_baseline_coverage_is_materialized_and_preserves_gaps():
    path = Path(__file__).parents[1] / "data" / "coverage" / "canonical-spine-baseline.json"
    materialized = json.loads(path.read_text(encoding="utf-8"))
    assert materialized == document()
    assert materialized["status"] == "partial_relationship_coverage"
    assert materialized["relationship_integrity"] == {
        "performances_with_missing_show": 0,
        "performances_with_missing_song": 0,
        "show_performer_assignments_with_missing_show": 0,
        "show_performer_assignments_with_missing_person": 0,
    }
    assert materialized["coverage"]["shows_without_performances"] > 0
    assert materialized["coverage"]["shows_without_performer_assignments"] > 0
    assert materialized["coverage"]["songs_without_performances"] == 0
