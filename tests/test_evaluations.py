import json
import sys

from deadbot.evaluations import DEFAULT_SUITE_PATH, evaluate_suite, load_suite, model_evaluate_suite


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


def test_required_source_urls_counted_when_cited_in_the_body_not_the_chat_answer():
    """A required URL delivered through a resolved block still counts as cited.

    Under the single agent loop the chat answer is deliberately short; the
    sources a case requires usually reach the visitor through the main body
    (here a ``resource_list``) and ``response.sources``.
    """

    import json as _json

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from deadbot.data import CanonicalStore
    from deadbot.finish import FINISH_TOOL_NAME

    store = CanonicalStore()
    case_id = "show-oral-history-source"
    resource_id = "resource-deadcast-veneta-part-1"
    resource = store.one("resources", resource_id)
    assert resource, f"expected {resource_id} in the canonical resources table"

    plan = {
        "chat_answer": "Yes — the Deadcast covered the Creamery benefit.",
        "title": "Oral history of Veneta",
        "lead": None,
        "mode": "research",
        "body": [{"type": "resource_list", "resource_ids": [resource_id], "title": "Listen and read"}],
    }

    class FakeAgent:
        def invoke(self, _state, config=None):
            return {
                "messages": [
                    HumanMessage(content="Find an oral history of the Creamery benefit."),
                    AIMessage(content="", tool_calls=[{"name": "search_resources", "args": {}, "id": "call-1", "type": "tool_call"}]),
                    ToolMessage(content=_json.dumps({"resources": [resource]}), tool_call_id="call-1", name="search_resources"),
                    AIMessage(content="", tool_calls=[{"name": FINISH_TOOL_NAME, "args": plan, "id": "finish-1", "type": "tool_call"}]),
                    ToolMessage(content="Response delivered to the visitor.", tool_call_id="finish-1", name=FINISH_TOOL_NAME),
                ]
            }

    report = model_evaluate_suite(
        case_ids={case_id},
        agent=FakeAgent(),
        config_factory=lambda thread_id: {"configurable": {"thread_id": thread_id}},
        store=store,
    )
    (result,) = report["results"]
    assert result["required_source_urls"] == [resource["source_url"]]
    assert result["body_block_types"] == ["resource_list"]
    # The URL is nowhere in the chat answer; the old answer-only check failed here.
    assert resource["source_url"] not in result["answer"]
    assert result["required_source_urls_cited"] is True


def test_evaluate_cli_exits_non_zero_when_a_case_fails(tmp_path, monkeypatch):
    failing_suite = {
        "suite_id": "synthetic-failing-suite",
        "version": "v1",
        "cases": [
            {
                "id": "always-fails",
                "question": "n/a",
                "tool": "not-a-real-tool",
                "arguments": {},
                "expected": {},
                "failure_conditions": ["n/a"],
            }
        ],
    }
    suite_path = tmp_path / "failing-suite.json"
    suite_path.write_text(json.dumps(failing_suite), encoding="utf-8")

    from deadbot.cli import main

    monkeypatch.setattr(sys, "argv", ["deadbot", "evaluate", "--suite", str(suite_path)])
    try:
        main()
    except SystemExit as exit_info:
        assert exit_info.code == 1
    else:
        raise AssertionError("evaluate should exit non-zero when a case fails")
