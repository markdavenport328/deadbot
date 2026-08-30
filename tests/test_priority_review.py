import copy

import pytest

from deadbot.priority_review import PriorityReviewValidationError, load_priority_queue, validate_priority_queue


def test_priority_queue_is_bounded_and_preserves_candidate_facts():
    rows = load_priority_queue()
    assert 25 <= len(rows) <= 35
    assert any("lore_source_trail" in row["reasons"] for row in rows)
    assert any("long_tail" in row["reasons"] for row in rows)
    assert all(row["candidate"]["coverage_risk"] in {"low", "medium", "high"} for row in rows)


def test_priority_queue_rejects_modified_coverage_or_unknown_provenance():
    rows = [copy.deepcopy(row) for row in load_priority_queue()]
    document = {
        "schema_version": 1,
        "kind": "editorial_priority_review_queue",
        "selection_policy": {"remaining_candidates_eligible": True},
        "priorities": rows,
    }
    document["priorities"][0]["candidate"]["performance_count"] += 1
    with pytest.raises(PriorityReviewValidationError):
        validate_priority_queue(document)

    document = {
        "schema_version": 1,
        "kind": "editorial_priority_review_queue",
        "selection_policy": {"remaining_candidates_eligible": True},
        "priorities": [copy.deepcopy(row) for row in rows],
    }
    document["priorities"][0]["lead_ids"] = []
    with pytest.raises(PriorityReviewValidationError, match="needs a lead ID"):
        validate_priority_queue(document)
