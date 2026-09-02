"""Deterministic evaluation of Deadbot's read-only tool contracts.

The first suite deliberately tests tool retrieval rather than model prose. This
makes failures reproducible without Ollama and provides a stable baseline for a
separate response-quality evaluation later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deadbot.data import CanonicalStore, repository_root
from deadbot.tools import build_tools


DEFAULT_SUITE_PATH = repository_root() / "evals" / "veneta-v1.json"


@dataclass(frozen=True)
class EvaluationCaseResult:
    """One case's deterministic retrieval result."""

    case_id: str
    passed: bool
    failures: list[str]


def load_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    """Load and minimally validate a versioned JSON evaluation suite."""
    with path.open(encoding="utf-8") as source:
        suite = json.load(source)
    if not isinstance(suite, dict) or not isinstance(suite.get("cases"), list):
        raise ValueError("Evaluation suite must be a JSON object with a 'cases' list.")
    return suite


def _value_at_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def _contains(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(expected_value, actual[key])
            for key, expected_value in expected.items()
        )
    return expected == actual


def _all_resource_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        ids = {value["resource_id"]} if isinstance(value.get("resource_id"), str) else set()
        for nested in value.values():
            ids.update(_all_resource_ids(nested))
        return ids
    if isinstance(value, list):
        return set().union(*(_all_resource_ids(item) for item in value)) if value else set()
    return set()


def evaluate_case(case: dict[str, Any], tools_by_name: dict[str, Any]) -> EvaluationCaseResult:
    """Execute one case and apply its compact JSON assertions."""
    case_id = case.get("id", "<missing id>")
    failures: list[str] = []
    tool_name = case.get("tool")
    tool = tools_by_name.get(tool_name)
    if not tool:
        return EvaluationCaseResult(case_id, False, [f"Unknown tool: {tool_name!r}"])

    try:
        result = json.loads(tool.invoke(case.get("arguments", {})))
    except Exception as error:  # pragma: no cover - defensive harness reporting
        return EvaluationCaseResult(case_id, False, [f"Tool invocation failed: {error}"])

    expected = case.get("expected", {})
    for path, value in expected.get("equals", {}).items():
        try:
            actual = _value_at_path(result, path)
        except KeyError:
            failures.append(f"Missing expected path: {path}")
        else:
            if actual != value:
                failures.append(f"Expected {path} to equal {value!r}; got {actual!r}")

    for path, item in expected.get("contains", {}).items():
        try:
            values = _value_at_path(result, path)
        except KeyError:
            failures.append(f"Missing expected list: {path}")
            continue
        if not isinstance(values, list) or not any(_contains(item, value) for value in values):
            failures.append(f"Expected {path} to contain {item!r}")

    returned_source_ids = _all_resource_ids(result)
    for source_id in case.get("required_source_ids", []):
        if source_id not in returned_source_ids:
            failures.append(f"Required source was not returned: {source_id}")

    return EvaluationCaseResult(case_id, not failures, failures)


def evaluate_suite(
    suite_path: Path = DEFAULT_SUITE_PATH,
    store: CanonicalStore | None = None,
) -> dict[str, Any]:
    """Run a suite against local canonical data and return JSON-serializable results."""
    suite = load_suite(suite_path)
    tools_by_name = {tool.name: tool for tool in build_tools(store or CanonicalStore())}
    results = [evaluate_case(case, tools_by_name) for case in suite["cases"]]
    passed = sum(result.passed for result in results)
    return {
        "suite_id": suite.get("suite_id"),
        "version": suite.get("version"),
        "suite_path": str(suite_path),
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "results": [
            {"id": result.case_id, "passed": result.passed, "failures": result.failures}
            for result in results
        ],
    }


def model_evaluate_suite(
    suite_path: Path = DEFAULT_SUITE_PATH,
    case_ids: set[str] | None = None,
    *,
    agent: Any,
    config_factory: Any,
    store: CanonicalStore | None = None,
) -> dict[str, Any]:
    """Run model responses for selected cases and retain traceable review data.

    This intentionally does not assign an overall prose-quality pass/fail. The
    suite's failure conditions include attribution and scope judgements that need
    a reviewer. It does perform an objective check for required source URLs.
    """
    from langchain_core.messages import HumanMessage

    suite = load_suite(suite_path)
    selected_cases = [
        case for case in suite["cases"] if case_ids is None or case["id"] in case_ids
    ]
    unknown_ids = (case_ids or set()) - {case["id"] for case in selected_cases}
    if unknown_ids:
        raise ValueError(f"Unknown evaluation case IDs: {', '.join(sorted(unknown_ids))}")

    resource_urls = {
        row["resource_id"]: row["source_url"]
        for row in (store or CanonicalStore()).rows("resources")
    }
    results = []
    for index, case in enumerate(selected_cases):
        result = agent.invoke(
            {"messages": [HumanMessage(content=case["question"])]},
            config=config_factory(f"model-eval-{case['id']}-{index}"),
        )
        messages = result["messages"]
        from deadbot.finish import build_experience_response

        response = build_experience_response(case["question"], f"model-eval-{case['id']}", messages, store or CanonicalStore())
        answer = response.answer
        body_types = [block.type for block in response.blocks]
        tool_calls = [
            {"name": call["name"], "arguments": call["args"]}
            for message in messages
            for call in getattr(message, "tool_calls", [])
        ]
        required_urls = [resource_urls[source_id] for source_id in case.get("required_source_ids", [])]
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "answer": answer,
                "body_block_types": body_types,
                "tool_calls": tool_calls,
                "required_source_urls": required_urls,
                "required_source_urls_cited": all(url in answer for url in required_urls),
                "failure_conditions": case["failure_conditions"],
                "manual_review_required": True,
            }
        )

    return {
        "suite_id": suite.get("suite_id"),
        "version": suite.get("version"),
        "mode": "model-response-review",
        "total": len(results),
        "results": results,
    }
