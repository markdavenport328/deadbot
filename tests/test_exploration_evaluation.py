import json
from pathlib import Path


SUITE_PATH = Path(__file__).parents[1] / "evals" / "exploration-v1.json"


def test_exploration_evaluation_fixture_has_versioned_two_column_shape():
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))

    assert suite["suite_id"] == "fact-first-flexible-exploration"
    assert suite["version"] == "v1"
    contract = suite["response_contract"]
    assert contract["conversation_column"]
    assert contract["main_column"]
    assert contract["exploration_column"]
    assert contract["allowed_regions"] == ["main", "exploration"]

    case_ids = {case["id"] for case in suite["cases"]}
    assert case_ids == {
        "cornell-direct-fact-optional-exploration",
        "veneta-source-context-route",
        "sugar-magnolia-recordings-main",
        "song-evolution-cross-era-candidates",
        "source-failure-partial-coverage",
    }
    for case in suite["cases"]:
        assert case["question"]
        assert case["grounding"]["coverage"]
        assert case["expected"]["mode"]
        assert case["failure_conditions"]
