import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_featured_show_candidates import FEATURED_SHOWS, document, make_candidates


def test_featured_show_queue_is_reproducible_and_cross_era():
    first = make_candidates()
    assert first == make_candidates()
    assert len(first) == 20
    assert [row["queue_position"] for row in first] == list(range(1, 21))
    assert {row["show_id"] for row in first} == {show_id for show_id, _ in FEATURED_SHOWS}
    assert min(int(row["show_date"][:4]) for row in first) <= 1970
    assert max(int(row["show_date"][:4]) for row in first) >= 1990
    assert all(row["coverage"]["performance_count"] >= 0 for row in first)
    assert all(row["enhancement_targets"] for row in first)


def test_materialized_featured_show_queue_matches_derivation():
    path = Path(__file__).parents[1] / "data" / "editorial" / "featured-show-candidates.json"
    materialized = json.loads(path.read_text(encoding="utf-8"))
    assert materialized == document()
    assert materialized["selection_policy"]["not_a_ranking"] is True
    assert materialized["selection_policy"]["runtime_visible"] is False
