import json

from deadbot.evaluations import DEFAULT_SUITE_PATH, evaluate_suite, load_suite


def test_veneta_tool_retrieval_suite_passes_against_canonical_data():
    result = evaluate_suite()
    assert result["total"] == 30
    assert result["failed"] == 0
    assert result["passed"] == result["total"]


def test_evaluation_suite_contains_human_review_metadata():
    suite = load_suite()
    assert suite["version"] == "v1"
    for case in suite["cases"]:
        assert case["question"]
        assert case["failure_conditions"]


def test_evaluation_result_is_json_serializable():
    result = evaluate_suite(DEFAULT_SUITE_PATH)
    assert json.loads(json.dumps(result))["suite_id"] == "veneta-tool-retrieval"


def test_model_evaluation_rejects_unknown_case_ids_without_calling_a_model():
    try:
        from deadbot.evaluations import model_evaluate_suite

        model_evaluate_suite(
            case_ids={"not-a-case"},
            agent=None,
            config_factory=None,
        )
    except ValueError as error:
        assert "Unknown evaluation case IDs: not-a-case" in str(error)
    else:
        raise AssertionError("Unknown case IDs should fail clearly")
