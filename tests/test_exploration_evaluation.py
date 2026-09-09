import json
from pathlib import Path


SUITE_PATH = Path(__file__).parents[1] / "evals" / "exploration-v1.json"
EDITORIAL_SCOPE_PATH = Path(__file__).parents[1] / "evals" / "editorial-scope-v1.json"


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
        "sugaree-album-attribution-quick-fact",
        "american-beauty-album-unit-tracklist",
        "truckin-release-vs-first-performance",
    }
    for case in suite["cases"]:
        assert case["question"]
        assert case["grounding"]["coverage"]
        assert "mode" not in case["expected"] or case["expected"]["mode"] == "gap"
        assert case["failure_conditions"]


def test_editorial_scope_suite_covers_different_earned_depths():
    suite = json.loads(EDITORIAL_SCOPE_PATH.read_text(encoding="utf-8"))

    assert suite["suite_id"] == "editorial-scope-and-priority"
    assert suite["version"] == "v1"
    cases = {case["id"]: case for case in suite["cases"]}
    assert set(cases) == {
        "compact-album-fact",
        "american-beauty-live-legacy",
        "eyes-development-earned-depth",
        "best-shows-differentiated",
    }
    assert "complete album tracklist or personnel" in " ".join(cases["american-beauty-live-legacy"]["failure_conditions"])
    for case in cases.values():
        assert case["question"]
        assert case["expected"]["scope"]
        assert case["expected"]["priority"]
        assert case["failure_conditions"]
