# Summaries First and Catalog Queries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop tool results from flooding the model's context. `get_album` returns a summary with detail on request, a read-only `query_catalog` tool answers set questions, every tool result has a size ceiling, and every turn is measured.

**Architecture:**
- **Measurement comes first**, so there is a baseline: a per-turn metrics log line plus an in-process measurement script.
- **Then the tool changes:**
  - `_json` gains an 80,000-character ceiling;
  - `get_album` gains `include`/`show` and a summary default;
  - `schema/sqlite.sql` gains four pre-joined views;
  - `SqliteCanonicalStore.run_catalog_query` runs guarded read-only SQL behind a new `query_catalog` tool;
  - the persona gains one general research line.
- **Then evals and the after-measurement.**

**Tech Stack:** Python 3.11+, FastAPI, LangGraph/LangChain tools, stdlib `sqlite3`, pytest.

**Spec:** [docs/superpowers/specs/2026-09-23-summaries-and-catalog-queries-design.md](../specs/2026-09-23-summaries-and-catalog-queries-design.md)

## Global Constraints

- The branch is `claude/tool-detail-levels`, stacked on `claude/neon-sqlite-migration-da5cee` (PR #58). The SQLite store and `built_sqlite` fixture from that branch are available.
- Tool result ceiling: **80,000 characters** (the architecture doc's 20,000-token hard ceiling).
- `query_catalog`:
  - read-only connection `?mode=ro&immutable=1`;
  - the authorizer allows only SELECT, READ, FUNCTION (except `load_extension`) and RECURSIVE;
  - one statement per call;
  - timeout **1.5 seconds**;
  - at most **200 rows**.
- `query_catalog` is registered only when the store has `run_catalog_query`, so the CSV store, the Postgres store and test doubles don't get it.
- The `query_catalog` tool description is **under 2,500 characters**.
- Code enforces structure only. Never choose content by question keywords (AGENTS.md "Keep the model in charge").
- Prompt text says what to do, not "do not" (the owner's prompt-style rule).
- Tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest ...`. The full suite is currently 622 passed.
- Never read or print `.env`. Never commit `build/`.
- Commits:
  - plain-sentence messages in the repo's style;
  - end each with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  - agents do not push.
- After any change to deadbot/api.py routes or experience models, regenerate `web/openapi.json` (`scripts/export_openapi.py`) and `web/src/generated/api.ts` (`npx --yes openapi-typescript@7.13.0 openapi.json -o src/generated/api.ts` in `web/`). This plan changes no routes or models, so this should not be needed. If `git diff web/openapi.json` shows a change, regenerate both.

## File Map

| File | Responsibility |
|---|---|
| `deadbot/turn_metrics.py` (new) | Build one turn's metrics dict from its messages and timings |
| `deadbot/api.py` (modify) | Time the stream; log the metrics line |
| `scripts/measure_turns.py` (new) | Run questions in-process with the real model; print a metrics table |
| `deadbot/tools.py` (modify) | `_json` ceiling; `get_album` summary/detail; `query_catalog` tool |
| `schema/sqlite.sql` (modify) | Four views |
| `deadbot/sqlite_build.py` (modify) | `SQLITE_SCHEMA_VERSION = 2` |
| `deadbot/sqlite_store.py` (modify) | `run_catalog_query` and its guardrails |
| `deadbot/graph.py` (modify) | Persona research line and well-worn routes |
| `evals/catalog-v1.json` (new) | Deterministic cases for album summary and catalog queries |
| `docs/measurements/2026-09-23-baseline.md`, `…-after.md` (new) | Measurement tables |

---

### Task 1: Per-turn metrics

**Files:**
- Create: `deadbot/turn_metrics.py`
- Modify: `deadbot/api.py`, in `_stream_events` (the function starting near line 230; the stream loop is at lines ~239–327)
- Test: `tests/test_turn_metrics.py`

**Interfaces:**
- Produces:
  - `turn_metrics(question: str, messages: list[Any], *, started: float, first_answer_at: float | None, finished_at: float, error: str | None) -> dict[str, Any]`;
  - the logger name `"deadbot.turn_metrics"`, which emits one `json.dumps(turn_metrics(...))` string per streamed turn at INFO.
- Dict keys:
  - `question`, `model_calls` (int), `calls` (list of `{"input_tokens": int|None, "output_tokens": int|None}`);
  - `peak_input_tokens` (int|None), `total_input_tokens` (int|None);
  - `tools` (list of `{"name": str, "chars": int, "truncated": bool}`), `largest_tool_result_chars` (int);
  - `seconds_to_first_answer` (float|None), `seconds_total` (float), `error` (str|None).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_turn_metrics.py
import json
import logging

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.turn_metrics import turn_metrics


def _turn():
    return [
        HumanMessage(content="an earlier question"),
        AIMessage(content="an earlier answer"),
        HumanMessage(content="Which releases cover 1972?"),
        AIMessage(content="", tool_calls=[{"name": "get_album", "args": {}, "id": "a", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 1200, "output_tokens": 40, "total_tokens": 1240}),
        ToolMessage(content='{"release":{}}', tool_call_id="a", name="get_album"),
        ToolMessage(content='{"rows":[],"_truncated":[{"path":"rows"}]}', tool_call_id="b", name="query_catalog"),
        AIMessage(content="", usage_metadata={"input_tokens": 5000, "output_tokens": 300, "total_tokens": 5300}),
    ]


def test_metrics_cover_only_this_turn():
    metrics = turn_metrics("Which releases cover 1972?", _turn(), started=10.0, first_answer_at=14.5, finished_at=20.0, error=None)
    assert metrics["model_calls"] == 2
    assert metrics["peak_input_tokens"] == 5000
    assert metrics["total_input_tokens"] == 6200
    assert [tool["name"] for tool in metrics["tools"]] == ["get_album", "query_catalog"]
    assert metrics["tools"][1]["truncated"] is True and metrics["tools"][0]["truncated"] is False
    assert metrics["largest_tool_result_chars"] == len('{"rows":[],"_truncated":[{"path":"rows"}]}')
    assert metrics["seconds_to_first_answer"] == 4.5 and metrics["seconds_total"] == 10.0
    json.dumps(metrics)  # serializable


def test_missing_usage_is_reported_as_unknown():
    messages = [HumanMessage(content="q"), AIMessage(content="done")]
    metrics = turn_metrics("q", messages, started=0.0, first_answer_at=None, finished_at=1.0, error="boom")
    assert metrics["calls"] == [{"input_tokens": None, "output_tokens": None}]
    assert metrics["peak_input_tokens"] is None and metrics["error"] == "boom"


class _StreamingAgent:
    def __init__(self, messages):
        self.messages = messages

    def stream(self, payload, config, stream_mode="values"):
        yield ("values", {"messages": self.messages})


def test_stream_endpoint_logs_one_metrics_line(caplog):
    finish = {"chat_answer": "Done.", "title": "T", "lead": None, "groups": []}
    messages = [
        HumanMessage(content="hello"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": finish, "id": "f", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 900, "output_tokens": 50, "total_tokens": 950}),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f", name="finish_response"),
    ]
    client = TestClient(create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=_StreamingAgent(messages)))
    with caplog.at_level(logging.INFO, logger="deadbot.turn_metrics"):
        client.post("/api/experience/stream", json={"question": "hello"})
    lines = [json.loads(record.getMessage()) for record in caplog.records if record.name == "deadbot.turn_metrics"]
    assert len(lines) == 1
    assert lines[0]["question"] == "hello" and lines[0]["peak_input_tokens"] == 900 and lines[0]["error"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_turn_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.turn_metrics'`

- [ ] **Step 3: Write `deadbot/turn_metrics.py`**

```python
"""One turn's cost in numbers: model calls, tokens, tool result sizes, timing.

Logged once per streamed turn so latency and context growth are measured
rather than guessed. Only the question text leaves the request.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _this_turn(messages: list[Any]) -> list[Any]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index + 1 :]
    return list(messages)


def turn_metrics(
    question: str,
    messages: list[Any],
    *,
    started: float,
    first_answer_at: float | None,
    finished_at: float,
    error: str | None,
) -> dict[str, Any]:
    turn = _this_turn(messages)
    calls = []
    tools = []
    for message in turn:
        if isinstance(message, AIMessage):
            usage = message.usage_metadata or {}
            calls.append({"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")})
        elif isinstance(message, ToolMessage):
            content = message.content if isinstance(message.content, str) else str(message.content)
            tools.append({"name": message.name or "", "chars": len(content), "truncated": '"_truncated"' in content})
    inputs = [call["input_tokens"] for call in calls if call["input_tokens"] is not None]
    return {
        "question": question,
        "model_calls": len(calls),
        "calls": calls,
        "peak_input_tokens": max(inputs) if inputs else None,
        "total_input_tokens": sum(inputs) if inputs else None,
        "tools": tools,
        "largest_tool_result_chars": max((tool["chars"] for tool in tools), default=0),
        "seconds_to_first_answer": round(first_answer_at - started, 2) if first_answer_at is not None else None,
        "seconds_total": round(finished_at - started, 2),
        "error": error,
    }
```

- [ ] **Step 4: Log it from `_stream_events`**

In `deadbot/api.py`:
- Add `import json` and `import time` if they are missing.
- Add `from deadbot.turn_metrics import turn_metrics`.
- Near the module logger, add:

```python
metrics_logger = logging.getLogger("deadbot.turn_metrics")
metrics_logger.setLevel(logging.INFO)
if not metrics_logger.handlers:
    metrics_logger.addHandler(logging.StreamHandler())
```

Then change `_stream_events`:
- At the top of the `try`, set `started = time.monotonic()`, `first_answer_at = None` and `error = None`.
- Where `answer_text` is yielded (both the normal yield and the `reset_answer` yield), set `first_answer_at = first_answer_at or time.monotonic()` before yielding.
- In the `except` block, set `error = "stream failed"` before yielding the error line.
- In `finally`, before `_release(invocation)`, add:

```python
            if not served_from_cache:
                metrics_logger.info(json.dumps(turn_metrics(
                    request.question, messages, started=started,
                    first_answer_at=first_answer_at, finished_at=time.monotonic(), error=error,
                )))
```

- Set `served_from_cache = False` at the top of the `try`, and `served_from_cache = True` just before the cached-response `return`.
- Make sure `messages` is defined before anything that can raise: it's set to `[]` early today, and must be above the first statement that can raise, or initialize it at the top of the `try`.
- Logging must never break the stream, so wrap the log call in `try/except Exception: logger.exception("Turn metrics failed")`.

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_turn_metrics.py tests/test_experience.py tests/test_answer_stream.py tests/test_plan_stream.py -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add deadbot/turn_metrics.py deadbot/api.py tests/test_turn_metrics.py
git commit -m "Each streamed turn logs its model calls, tokens, tool result sizes and timing"
```

---

### Task 2: The measurement script

**Files:**
- Create: `scripts/measure_turns.py`
- Test: `tests/test_measure_turns.py`

**Interfaces:**
- Consumes: the `"deadbot.turn_metrics"` log lines (Task 1).
- Produces:
  - `measure(questions: list[str], *, app, pause_seconds: float = 0.0) -> list[dict]` returns one metrics dict per question, with `"error": "no metrics logged"` if none arrived;
  - `table(rows: list[dict]) -> str` returns a Markdown table;
  - `DEFAULT_QUESTIONS: list[str]`;
  - a CLI: `python scripts/measure_turns.py [--output PATH] [--pause SECONDS] [question ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_measure_turns.py
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from scripts.measure_turns import DEFAULT_QUESTIONS, measure, table


class _Agent:
    def stream(self, payload, config, stream_mode="values"):
        question = payload["messages"][-1].content
        finish = {"chat_answer": f"About {question}", "title": "T", "lead": None, "groups": []}
        yield ("values", {"messages": [
            HumanMessage(content=question),
            AIMessage(content="", tool_calls=[{"name": "finish_response", "args": finish, "id": "f", "type": "tool_call"}],
                      usage_metadata={"input_tokens": 700, "output_tokens": 20, "total_tokens": 720}),
            ToolMessage(content="Response delivered to the visitor.", tool_call_id="f", name="finish_response"),
        ]})


def test_measure_returns_one_row_per_question_and_renders_a_table():
    app = create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=_Agent())
    rows = measure(["one", "two"], app=app)
    assert [row["question"] for row in rows] == ["one", "two"]
    assert rows[0]["peak_input_tokens"] == 700
    rendered = table(rows)
    assert rendered.splitlines()[0].startswith("| Question |") and "| one |" in rendered


def test_default_questions_include_the_opening_and_set_questions():
    assert "Which official releases cover 1972?" in DEFAULT_QUESTIONS
    assert "Which songs did they play most in 1977?" in DEFAULT_QUESTIONS
    assert len(DEFAULT_QUESTIONS) == 19
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_measure_turns.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.measure_turns'`

- [ ] **Step 3: Write `scripts/measure_turns.py`**

```python
"""Measure what each question costs: rounds, tokens, tool result sizes, timing.

Runs questions in-process against the configured model with the response
cache off, and prints one row per question. Compare a run before and after a
change to tools or prompt:

    PYTHONPATH=. .venv/bin/python scripts/measure_turns.py --output docs/measurements/2026-09-23-baseline.md

Uses the real model and costs real tokens. --pause spaces questions out so a
run stays under the provider's tokens-per-minute limit.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from scripts.warm_answers import OPENING_QUESTIONS

SET_QUESTIONS = [
    "Which songs did they play most in 1977?",
    "Which guest musicians sat in most often?",
    "How often did Scarlet Begonias open the second set in the 1980s?",
    "What live albums came from Winterland?",
]
DEFAULT_QUESTIONS = [*OPENING_QUESTIONS, *SET_QUESTIONS]


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(json.loads(record.getMessage()))
        except (TypeError, json.JSONDecodeError):
            pass


def measure(questions: list[str], *, app: Any, pause_seconds: float = 0.0) -> list[dict[str, Any]]:
    collector = _Collector()
    metrics_logger = logging.getLogger("deadbot.turn_metrics")
    metrics_logger.addHandler(collector)
    client = TestClient(app)
    rows = []
    try:
        for index, question in enumerate(questions):
            if index and pause_seconds:
                time.sleep(pause_seconds)
            before = len(collector.lines)
            with client.stream("POST", "/api/experience/stream", json={"question": question}) as response:
                for _ in response.iter_lines():
                    pass
            logged = collector.lines[before:]
            rows.append(logged[-1] if logged else {"question": question, "error": "no metrics logged"})
    finally:
        metrics_logger.removeHandler(collector)
    return rows


def table(rows: list[dict[str, Any]]) -> str:
    header = "| Question | Calls | Peak input | Total input | Largest tool result | First answer (s) | Total (s) | Truncated | Error |"
    lines = [header, "|" + "---|" * 9]
    for row in rows:
        truncated = sum(1 for tool in row.get("tools", []) if tool.get("truncated"))
        lines.append(
            f"| {row.get('question', '')} | {row.get('model_calls', '')} | {row.get('peak_input_tokens', '')} | "
            f"{row.get('total_input_tokens', '')} | {row.get('largest_tool_result_chars', '')} | "
            f"{row.get('seconds_to_first_answer', '')} | {row.get('seconds_total', '')} | {truncated} | {row.get('error') or ''} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pause", type=float, default=20.0)
    args = parser.parse_args(argv)

    from deadbot.api import create_app
    from deadbot.config import Settings

    settings = dataclasses.replace(Settings.from_env(), response_cache=False)
    rows = measure(args.questions or DEFAULT_QUESTIONS, app=create_app(settings=settings), pause_seconds=args.pause)
    rendered = table(rows)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"# Turn measurements\n\nModel: {settings.openai_model if settings.model_provider == 'openai' else settings.ollama_model}\n\n{rendered}\n\n"
            "Raw metrics, one JSON object per question:\n\n```json\n" + "\n".join(json.dumps(row) for row in rows) + "\n```\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    sys.exit(main())
```

Confirm `Settings` is a dataclass (`dataclasses.replace` needs that): run `grep -n "@dataclass" deadbot/config.py`. If `scripts/warm_answers.py` runs anything at import time, import only `OPENING_QUESTIONS` lazily in the same way. Check with `sed -n 1,45p scripts/warm_answers.py`.

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_measure_turns.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/measure_turns.py tests/test_measure_turns.py
git commit -m "A measurement script runs questions in-process and tabulates each turn's cost"
```

- [ ] **Step 6 (controller, not the implementer): record the baseline**

This runs with the real model and reads the worktree's `.env` through `Settings`; the controller never prints it. From the worktree root:

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/measure_turns.py --output docs/measurements/2026-09-23-baseline.md
```

Then commit: `git add docs/measurements/2026-09-23-baseline.md && git commit -m "Baseline turn measurements before the tool changes"`. Rate-limit errors in the baseline are data, not failures. Keep them in the table.

---

### Task 3: The tool result ceiling

**Files:**
- Modify: `deadbot/tools.py:235-245` (`_json`)
- Test: `tests/test_tool_ceiling.py`

**Interfaces:**
- Produces:
  - `TOOL_RESULT_CEILING_CHARS = 80_000` in `deadbot/tools.py`;
  - `_json(value)` keeps its signature, output under the ceiling is byte-identical to today, and output over it gains `"_truncated": [{"path": str, "kept": int, "total": int}]` plus `"_truncated_note"` at the top level of a dict payload.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tool_ceiling.py
import json

from deadbot.tools import TOOL_RESULT_CEILING_CHARS, _json


def test_small_payloads_are_unchanged():
    payload = {"a": 1, "items": [{"x": "y"}] * 3, "empty": None}
    assert _json(payload) == json.dumps({"a": 1, "items": [{"x": "y"}] * 3}, separators=(",", ":"))


def test_oversized_payload_trims_its_largest_list_and_says_so():
    payload = {"release": {"title": "Box"}, "tracks": [{"n": i, "title": "x" * 200} for i in range(2000)], "notes": ["short"]}
    result = json.loads(_json(payload))
    assert len(_json(payload)) <= TOOL_RESULT_CEILING_CHARS
    assert result["release"] == {"title": "Box"} and result["notes"] == ["short"]
    entry = result["_truncated"][0]
    assert entry["path"] == "tracks" and entry["total"] == 2000 and 0 < entry["kept"] < 2000
    assert len(result["tracks"]) == entry["kept"]
    assert "narrow" in result["_truncated_note"]


def test_nested_lists_are_found_by_path():
    payload = {"live_legacy": {"song-a": {"versions": ["v" * 100] * 3000}}}
    result = json.loads(_json(payload))
    assert result["_truncated"][0]["path"] == "live_legacy.song-a.versions"
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_tool_ceiling.py -v`
Expected: FAIL with `ImportError: cannot import name 'TOOL_RESULT_CEILING_CHARS'`

- [ ] **Step 3: Implement**

Replace `_json` in `deadbot/tools.py` with:

```python
# The architecture doc's hard ceiling for one tool result (about 20,000
# tokens). A result over it is transport damage, not an editorial choice:
# trim the largest list and tell the model how much it did not see.
TOOL_RESULT_CEILING_CHARS = 80_000


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _largest_list(value: Any, path: str = "") -> tuple[str, list | None, int]:
    best: tuple[str, list | None, int] = ("", None, 0)
    if isinstance(value, dict):
        children = ((f"{path}.{key}" if path else str(key), nested) for key, nested in value.items())
    elif isinstance(value, list):
        if len(value) > 1:
            best = (path, value, len(_dumps(value)))
        children = ((path, nested) for nested in value)
    else:
        return best
    for child_path, nested in children:
        candidate = _largest_list(nested, child_path)
        if candidate[2] > best[2]:
            best = candidate
    return best


def _json(value: Any) -> str:
    """Serialize a lean tool payload, bounded by the tool result ceiling."""

    def compact(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: compact(nested) for key, nested in item.items() if nested not in (None, "")}
        if isinstance(item, list):
            return [compact(nested) for nested in item]
        return item

    payload = compact(value)
    text = _dumps(payload)
    if len(text) <= TOOL_RESULT_CEILING_CHARS or not isinstance(payload, dict):
        return text
    totals: dict[str, int] = {}
    while len(text) > TOOL_RESULT_CEILING_CHARS:
        path, items, _ = _largest_list(payload)
        if items is None:
            break
        totals.setdefault(path, len(items))
        keep = max(1, int(len(items) * TOOL_RESULT_CEILING_CHARS / len(text) * 0.9))
        if keep >= len(items):
            keep = len(items) - 1
        del items[keep:]
        payload["_truncated"] = [{"path": p, "kept": len(_value_at(payload, p)), "total": t} for p, t in totals.items()]
        payload["_truncated_note"] = (
            "This result was over the size ceiling, so the lists above were shortened. "
            "To see the rest, narrow the request: a filter, a detail option, a smaller page, or a query_catalog query."
        )
        text = _dumps(payload)
    return text


def _value_at(payload: Any, path: str) -> list:
    current = payload
    for part in path.split("."):
        current = current[part]
    return current
```

Note: `_largest_list` never descends into the `_truncated` entry: it holds one small dict per path, well under any real list.

- [ ] **Step 4: Run the tests plus every tool test**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_tool_ceiling.py tests/test_research_tools.py tests/test_question_shaped_tools.py tests/test_latency_batching.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add deadbot/tools.py tests/test_tool_ceiling.py
git commit -m "Every tool result is bounded by the 20,000-token ceiling and says what it trimmed"
```

---

### Task 3b: `search_guest_musicians`: a directory summary by default, appearances on request

Added 2026-09-23 after the baseline. The guest lookup is the second-largest offender: `query=""` returns 201,164 characters because every guest carries every appearance in full (Branford alone is about 19,000). The owner's point stands: a list of 139 guests should be small. The same summary-first pattern as `get_album` applies.

**Files:**
- Modify: `deadbot/tools.py` (`search_guest_musicians`, ~lines 525–640)
- Modify: `deadbot/graph.py` (the well-worn route sentence naming `search_guest_musicians`)
- Modify: `tests/test_data.py`, `tests/test_finish.py` (callers that need appearances pass `include`); restore `test_guest_directory_reports_no_person_under_a_qualified_name` to scan the **full** directory, as it did at commit 6eaeadc (Task 3 narrowed it to about 4 guests)
- Test: `tests/test_guest_summary.py`

**Interfaces:**
- Produces: `search_guest_musicians(query: str = "", include: list[str] | None = None) -> str`.
- **Summary (default):** each guest is `{person_id, name, guest_show_count, first_show_date, last_show_date, instruments}`. `instruments` is the distinct credited instruments across their appearances. The order is unchanged: busiest first, as today.
- The payload is `{guest_count, guests, available}`. `available` is `{"appearances": {"count": <total appearances across the returned guests>, "ask": "include=[\"appearances\"]: each guest's shows (date, venue, instruments, songs they played on) and pathways"}}`.
- **With `include=["appearances"]`:** each guest also carries today's `appearances` exactly as now, and the payload carries today's `pathways`.
- An unknown include returns `{"error": "Unknown include", "valid": ["appearances"]}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_guest_summary.py`:
  - `query=""` returns all guests, and `len(result) < 20_000` characters.
  - No guest has `appearances`, and there is no `_truncated`.
  - Branford is present with `guest_show_count == 5`, a `first_show_date` of 1990-03-29 and a `last_show_date` of 1994-12-16.
  - `query="Branford", include=["appearances"]` returns his five show IDs (the existing expectations from `test_data.py`).
  - An unknown include returns the error.
  - Use `CanonicalStore()` like the existing guest tests.
- [ ] **Step 2:** Run it and see it fail.
- [ ] **Step 3: Implement.**
  - Build the appearances as today, then derive the summary fields from them.
  - Attach `appearances` and `pathways` only when requested.
  - Update the docstring:
    - the default is a directory: who, how often, when, on what;
    - `include=["appearances"]` returns the shows;
    - for a question about a specific guest, request appearances in the same call.
- [ ] **Step 4: Update the callers.**
  - Every existing test that reads `appearances` or `pathways` passes `include=["appearances"]`.
  - Restore the full-directory qualifier test to query `""` and check every guest name.
  - In `deadbot/graph.py`, change "search_guest_musicians returns their shows with IDs and pathways" to "search_guest_musicians lists guests with their show counts and years; ask for include=[\"appearances\"] to get a guest's shows with IDs and pathways".
- [ ] **Step 5:** Run the new, data, finish, graph and evaluation tests, then the full suite. Expect everything to pass.
- [ ] **Step 6: Commit:** "The guest directory lists who, how often and when; a guest's shows come on request"

---

### Task 4: `get_album` summary by default, detail on request

**Files:**
- Modify: `deadbot/tools.py:843-872` (`get_album`); `_album_live_legacy` (874–932) stays as it is
- Modify: `tests/test_research_tools.py:111-116` and `tests/test_question_shaped_tools.py:111-119`, whose expectations change
- Test: `tests/test_album_summary.py`

**Interfaces:**
- Produces: `get_album(release_id_or_title: str, include: list[str] | None = None, show: str | None = None) -> str`. The result keys are:
  - `release`, `track_count`, `total_duration_seconds` (when any track has a duration), `personnel`, `pathways`;
  - `contents`:
    - live: `{"shows": [{"show_id","show_date","venue_name","city","track_count"}], "unattributed_track_count": int}`;
    - otherwise: `{"songs": [{"song_id","title"}]}`;
  - `available`: a dict of details not included, each `{"count": int, "ask": str}`, for example `tracks` → `{"count": 578, ...}` and `live_legacy` → `{"count": <songs>, ...}`;
  - with `include=["tracks"]` or `show`: `tracks` (today's track dicts; with `show`, only that show's);
  - with `include=["live_legacy"]`: `live_legacy` (a dict keyed by `song_id`, each value exactly `_album_live_legacy`'s per-song dict) plus today's `live_legacy_note`.
- Errors:
  - unknown include → `{"error": "Unknown include", "valid": ["live_legacy", "tracks"]}`;
  - a show not on the release → `{"error": "Show not on this release", "shows": [<show_date>, ...]}`.

Ruling recorded in the plan: `show` implies `include=["tracks"]`. Naming a show only makes sense for its tracks. `live_legacy` moves from per-track to one dict keyed by song, so a song repeated across a box set's shows isn't repeated.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_album_summary.py
import json

import pytest

from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools

BOX = "release-europe-72-the-complete-recordings-2011"


@pytest.fixture
def album(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tool = next(t for t in build_tools(store) if t.name == "get_album")
    yield lambda **args: json.loads(tool.invoke(args))
    store.close()


def test_live_box_set_summary_lists_shows_not_tracks(album):
    payload = album(release_id_or_title=BOX)
    assert "tracks" not in payload and "live_legacy" not in payload
    shows = payload["contents"]["shows"]
    assert shows[0]["show_date"] == "1972-04-07" and shows[-1]["show_id"] == "gd-1972-05-26"
    assert sum(show["track_count"] for show in shows) + payload["contents"].get("unattributed_track_count", 0) == payload["track_count"]
    assert payload["available"]["tracks"]["count"] == payload["track_count"]
    assert "include" in payload["available"]["tracks"]["ask"]
    assert len(json.dumps(payload)) < 12_000


def test_studio_summary_lists_songs(album):
    payload = album(release_id_or_title="American Beauty")
    assert payload["release"]["release_type"] == "studio"
    assert any(song["song_id"] == "song-truckin" for song in payload["contents"]["songs"])
    assert "tracks" not in payload


def test_tracks_on_request_and_narrowed_to_one_show(album):
    full = album(release_id_or_title=BOX, include=["tracks"])
    one = album(release_id_or_title=BOX, show="1972-05-26")
    assert len(full["tracks"]) == full["track_count"]
    assert 0 < len(one["tracks"]) < len(full["tracks"])
    assert "tracks" not in one["available"]


def test_live_legacy_on_request_keyed_by_song(album):
    payload = album(release_id_or_title="American Beauty", include=["live_legacy"])
    truckin = payload["live_legacy"]["song-truckin"]
    assert truckin["performance_count"] > 400
    assert sum(truckin["by_era"].values()) == truckin["performance_count"]
    assert "get_song_notable_versions" in payload["live_legacy_note"]


def test_bad_requests_explain_themselves(album):
    assert album(release_id_or_title=BOX, include=["lyrics"])["valid"] == ["live_legacy", "tracks"]
    assert "shows" in album(release_id_or_title=BOX, show="1977-05-08")
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_album_summary.py -v`
Expected: FAIL (`tracks` present; `contents` missing)

- [ ] **Step 3: Implement**

Replace the `get_album` tool in `deadbot/tools.py` with:

```python
    _ALBUM_DETAILS = ("live_legacy", "tracks")

    @tool
    def get_album(release_id_or_title: str, include: list[str] | None = None, show: str | None = None) -> str:
        """Get one official release: a summary first, with detail on request.

        The summary names the release, its date and type, and what is on it:
        for a live release the shows its tracks come from (date, venue, how many
        tracks); for a studio album its songs. It carries the IDs you need to
        place the album, its shows or its songs on the page. `available` lists
        what the summary left out and how to ask for it. Ask only for what your
        answer will use:
        - include=["tracks"]: the full tracklist (each track's song or
          performance, duration and Spotify link). show="<show id or date>"
          narrows it to one show's tracks on a multi-show release.
        - include=["live_legacy"]: each song's life on stage (count, span, count
          by era, the performances most often issued on official live records).
        pathways lists the cataloged lore for the release or the research sites
        to search when nothing is cataloged.
        """
        release = store.resolve_release(release_id_or_title)
        if not release:
            return _json({"error": "Release not found or ambiguous", "query": release_id_or_title})
        wanted = set(include or [])
        if show:
            wanted.add("tracks")
        unknown = wanted - set(_ALBUM_DETAILS)
        if unknown:
            return _json({"error": "Unknown include", "valid": list(_ALBUM_DETAILS)})

        context = store.album_context(release)
        tracks = context.get("tracks", [])
        performance_ids = {track["performance_id"] for track in tracks if track.get("performance_id")}
        performances = {row["performance_id"]: row for row in store.rows_in("performances", "performance_id", performance_ids)}
        shows = {row["show_id"]: row for row in store.rows_in("shows", "show_id", {p.get("show_id", "") for p in performances.values()})}
        venues = {row["venue_id"]: row for row in store.rows_in("venues", "venue_id", {s.get("venue_id", "") for s in shows.values()})}

        def show_of(track: dict[str, Any]) -> str:
            return performances.get(track.get("performance_id") or "", {}).get("show_id", "")

        payload: dict[str, Any] = {
            "release": context["release"],
            "track_count": len(tracks),
            "personnel": context.get("personnel", []),
        }
        durations = [int(track["duration_seconds"]) for track in tracks if str(track.get("duration_seconds") or "").isdigit()]
        if durations:
            payload["total_duration_seconds"] = sum(durations)
        song_ids = list(dict.fromkeys(track["song_id"] for track in tracks if track.get("song_id")))
        if release.get("release_type") == "live":
            counts: dict[str, int] = {}
            for track in tracks:
                if show_of(track):
                    counts[show_of(track)] = counts.get(show_of(track), 0) + 1
            ordered = sorted(counts, key=lambda show_id: (shows[show_id].get("show_date", ""), show_id))
            payload["contents"] = {
                "shows": [
                    {
                        "show_id": show_id,
                        "show_date": shows[show_id].get("show_date", ""),
                        "venue_name": venues.get(shows[show_id].get("venue_id", ""), {}).get("name", ""),
                        "city": venues.get(shows[show_id].get("venue_id", ""), {}).get("city", ""),
                        "track_count": counts[show_id],
                    }
                    for show_id in ordered
                ],
                "unattributed_track_count": len(tracks) - sum(counts.values()),
            }
        else:
            titles = {track["song_id"]: track.get("song_title") or track.get("title", "") for track in tracks if track.get("song_id")}
            payload["contents"] = {"songs": [{"song_id": song_id, "title": titles[song_id]} for song_id in song_ids]}

        if "tracks" in wanted:
            if show:
                resolved = store.resolve_show(show)
                show_id = resolved["show_id"] if resolved else ""
                if show_id not in {show_of(track) for track in tracks}:
                    return _json({"error": "Show not on this release", "shows": [entry["show_date"] for entry in payload["contents"].get("shows", [])]})
                payload["tracks"] = [track for track in tracks if show_of(track) == show_id]
            else:
                payload["tracks"] = tracks
        if "live_legacy" in wanted:
            payload["live_legacy"] = _album_live_legacy(song_ids)
            payload["live_legacy_note"] = (
                "live_legacy per song: performance count, span, count by era and the "
                "performances most often issued on official live records. Call get_song_notable_versions "
                "for one song's versions with critic, curator and fan signals."
            )

        available: dict[str, Any] = {}
        if "tracks" not in wanted:
            ask = 'include=["tracks"]'
            if len(payload["contents"].get("shows", [])) > 1:
                ask += f'; narrow to one show with show="{payload["contents"]["shows"][0]["show_date"]}"'
            available["tracks"] = {"count": len(tracks), "ask": ask}
        if "live_legacy" not in wanted and song_ids:
            available["live_legacy"] = {"count": len(song_ids), "ask": 'include=["live_legacy"]: each song\'s stage history'}
        if available:
            payload["available"] = available
        payload["pathways"] = pathways_for(store, [("release", release["release_id"])]).get(release["release_id"], {})
        return _json(payload)
```

Check the track dict keys against `album_context` (they are `track_number, title, song_id, song_title, performance_id, duration_seconds, spotify_track_url`). Adjust the `song_title`/`title` fallback if needed.

- [ ] **Step 4: Update the two old tests to the new contract**

`tests/test_research_tools.py::test_get_album_returns_the_tracklist` becomes:

```python
def test_get_album_returns_the_tracklist_on_request():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "get_album").invoke({"release_id_or_title": "American Beauty", "include": ["tracks"]}))
    assert payload["release"]["release_type"] == "studio"
    assert any(track["song_id"] == "song-truckin" for track in payload["tracks"])
```

`tests/test_question_shaped_tools.py::test_album_tracks_carry_their_live_legacy` becomes:

```python
def test_album_live_legacy_on_request():
    payload = json.loads(_tools()["get_album"].invoke({"release_id_or_title": "American Beauty", "include": ["live_legacy"]}))
    legacy = payload["live_legacy"]["song-truckin"]
    assert legacy["performance_count"] > 400
    assert legacy["first_performance"] < "1971" < legacy["last_performance"]
    assert sum(legacy["by_era"].values()) == legacy["performance_count"]
    assert legacy["most_released_performances"][0]["release_titles"]
    assert "get_song_notable_versions" in payload["live_legacy_note"]
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_album_summary.py tests/test_research_tools.py tests/test_question_shaped_tools.py tests/test_latency_batching.py tests/test_evaluations.py -q`
Expected: all PASS. If an eval case or another test assumed `get_album` returns `tracks` by default (`grep -rn "get_album" evals tests`), update it to pass `include`.

- [ ] **Step 6: Commit**

```bash
git add deadbot/tools.py tests/test_album_summary.py tests/test_research_tools.py tests/test_question_shaped_tools.py
git commit -m "get_album answers with a summary and lists what more it can give; tracks and stage history come on request"
```

---

### Task 5: The catalog views

**Files:**
- Modify: `schema/sqlite.sql` (append at the end)
- Modify: `deadbot/sqlite_build.py` (`SQLITE_SCHEMA_VERSION = 2`)
- Test: `tests/test_catalog_views.py`

**Interfaces:**
- Produces four views:
  - `show_facts(show_id, show_date, year, venue_id, venue_name, city, state_region, country, tour_name, event_name, performance_count)`;
  - `performance_facts(performance_id, song_id, song_title, show_id, show_date, year, venue_id, venue_name, city, tour_name, set_number, set_label, position_in_set, encore, segue_into_next)`;
  - `release_track_facts(release_id, release_title, release_type, release_date, track_number, track_title, song_id, song_title, performance_id, show_id, show_date, year, venue_id, venue_name, city)`;
  - `guest_appearances(show_id, show_date, year, person_id, person_name, instrument, venue_name, city)`.
- Ruling: `show_facts` counts setlist entries as `performance_count`, not the spec's `song_count`. The count includes Drums and Space, so "song" would mislead the model.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_catalog_views.py
import csv
import sqlite3
from collections import Counter

from deadbot.canonical_import import DEFAULT_CANONICAL_DIR


def _db(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _csv(name):
    with (DEFAULT_CANONICAL_DIR / f"{name}.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_views_exist_with_their_columns(built_sqlite):
    db = _db(built_sqlite)
    expected = {
        "show_facts": ["show_id", "show_date", "year", "venue_id", "venue_name", "city", "state_region", "country", "tour_name", "event_name", "performance_count"],
        "performance_facts": ["performance_id", "song_id", "song_title", "show_id", "show_date", "year", "venue_id", "venue_name", "city", "tour_name", "set_number", "set_label", "position_in_set", "encore", "segue_into_next"],
        "release_track_facts": ["release_id", "release_title", "release_type", "release_date", "track_number", "track_title", "song_id", "song_title", "performance_id", "show_id", "show_date", "year", "venue_id", "venue_name", "city"],
        "guest_appearances": ["show_id", "show_date", "year", "person_id", "person_name", "instrument", "venue_name", "city"],
    }
    for view, columns in expected.items():
        assert [row[1] for row in db.execute(f'PRAGMA table_info("{view}")')] == columns, view


def test_most_played_1977_matches_an_independent_count(built_sqlite):
    shows = {row["show_id"]: row["show_date"] for row in _csv("shows")}
    counts = Counter(p["song_id"] for p in _csv("performances") if shows.get(p["show_id"], "").startswith("1977"))
    top_song, top_count = counts.most_common(1)[0]
    row = _db(built_sqlite).execute(
        "SELECT song_id, COUNT(*) AS n FROM performance_facts WHERE year = 1977 GROUP BY song_id ORDER BY n DESC, song_id LIMIT 1"
    ).fetchone()
    assert row == (top_song, top_count)


def test_releases_covering_1972_include_europe_72(built_sqlite):
    rows = _db(built_sqlite).execute("SELECT DISTINCT release_id FROM release_track_facts WHERE year = 1972").fetchall()
    assert ("release-europe-72-the-complete-recordings-2011",) in rows


def test_every_guest_row_is_counted(built_sqlite):
    guests = sum(1 for row in _csv("show_performers") if row["role"] == "guest")
    assert _db(built_sqlite).execute("SELECT COUNT(*) FROM guest_appearances").fetchone()[0] == guests
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_catalog_views.py -v`
Expected: FAIL (no such view)

- [ ] **Step 3: Append the views to `schema/sqlite.sql`**

```sql
-- Catalog views for query_catalog: each pre-joins what set questions usually
-- need, so most queries are one table with WHERE, GROUP BY and ORDER BY.
-- year is the integer year of show_date.

CREATE VIEW show_facts AS
SELECT s.show_id, s.show_date, CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       s.venue_id, v.name AS venue_name, v.city, v.state_region, v.country,
       s.tour_name, s.event_name,
       (SELECT COUNT(*) FROM performances p WHERE p.show_id = s.show_id) AS performance_count
FROM shows s
LEFT JOIN venues v ON v.venue_id = s.venue_id;

CREATE VIEW performance_facts AS
SELECT p.performance_id, p.song_id, so.title AS song_title, p.show_id, s.show_date,
       CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       s.venue_id, v.name AS venue_name, v.city, s.tour_name,
       p.set_number, p.set_label, p.position_in_set, p.encore, p.segue_into_next
FROM performances p
JOIN shows s ON s.show_id = p.show_id
LEFT JOIN songs so ON so.song_id = p.song_id
LEFT JOIN venues v ON v.venue_id = s.venue_id;

CREATE VIEW release_track_facts AS
SELECT t.release_id, r.title AS release_title, r.release_type, r.release_date,
       t.track_number, t.track_title,
       COALESCE(t.song_id, p.song_id) AS song_id, so.title AS song_title,
       t.performance_id, p.show_id, s.show_date,
       CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       s.venue_id, v.name AS venue_name, v.city
FROM official_release_tracks t
JOIN official_releases r ON r.release_id = t.release_id
LEFT JOIN performances p ON p.performance_id = t.performance_id
LEFT JOIN songs so ON so.song_id = COALESCE(t.song_id, p.song_id)
LEFT JOIN shows s ON s.show_id = p.show_id
LEFT JOIN venues v ON v.venue_id = s.venue_id;

CREATE VIEW guest_appearances AS
SELECT sp.show_id, s.show_date, CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       sp.person_id, pe.name AS person_name, sp.instrument, v.name AS venue_name, v.city
FROM show_performers sp
JOIN shows s ON s.show_id = sp.show_id
LEFT JOIN people pe ON pe.person_id = sp.person_id
LEFT JOIN venues v ON v.venue_id = s.venue_id
WHERE sp.role = 'guest';
```

Set `SQLITE_SCHEMA_VERSION = 2` in `deadbot/sqlite_build.py`. The schema file's bytes are part of `input_fingerprint`, so local stores rebuild automatically.

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_catalog_views.py tests/test_sqlite_build.py tests/test_sqlite_store.py -q`
Expected: all PASS. If a test pins `SQLITE_SCHEMA_VERSION == 1`, update it to 2.

- [ ] **Step 5: Commit**

```bash
git add schema/sqlite.sql deadbot/sqlite_build.py tests/test_catalog_views.py
git commit -m "Four catalog views pre-join shows, performances, release tracks and guest appearances for set questions"
```

---

### Task 6: `run_catalog_query` and the `query_catalog` tool

**Files:**
- Modify: `deadbot/sqlite_store.py` (add a method and module constants)
- Modify: `deadbot/tools.py` (add the tool; register it conditionally at the end of `build_tools`)
- Test: `tests/test_catalog_query.py`

**Interfaces:**
- Consumes: the views from Task 5.
- Produces:
  - `CATALOG_QUERY_MAX_ROWS = 200` and `CATALOG_QUERY_TIMEOUT_SECONDS = 1.5` in `deadbot/sqlite_store.py`;
  - `SqliteCanonicalStore.run_catalog_query(sql: str) -> dict`. On success it returns `{"columns": [...], "rows": [[...]], "row_count": int, "truncated": bool}` plus `note` when truncated. On failure it returns `{"error": str, "hint": str}`;
  - the tool `query_catalog(sql: str) -> str`, present in `build_tools(store)` only when `callable(getattr(store, "run_catalog_query", None))`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_catalog_query.py
import json

import pytest

from deadbot.data import CanonicalStore
from deadbot.sqlite_store import CATALOG_QUERY_MAX_ROWS, SqliteCanonicalStore
from deadbot.tools import build_tools


@pytest.fixture
def store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def test_select_returns_columns_and_rows(store):
    result = store.run_catalog_query("SELECT song_title, COUNT(*) AS n FROM performance_facts WHERE year = 1977 GROUP BY song_id ORDER BY n DESC LIMIT 3")
    assert result["columns"] == ["song_title", "n"] and result["row_count"] == 3 and result["truncated"] is False


def test_rows_are_capped(store):
    result = store.run_catalog_query("SELECT performance_id FROM performances")
    assert result["row_count"] == CATALOG_QUERY_MAX_ROWS and result["truncated"] is True and "LIMIT" in result["note"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM songs",
    "UPDATE songs SET title = 'x'",
    "CREATE TABLE t (x)",
    "PRAGMA table_info(songs)",
    "ATTACH DATABASE ':memory:' AS other",
])
def test_anything_but_reading_is_refused(store, sql):
    result = store.run_catalog_query(sql)
    assert "error" in result and result["hint"]


def test_two_statements_are_refused(store):
    assert "error" in store.run_catalog_query("SELECT 1; SELECT 2")


def test_runaway_query_times_out(store):
    result = store.run_catalog_query("SELECT COUNT(*) FROM performances a, performances b, performances c")
    assert "error" in result and "time" in result["hint"].lower()


def test_unknown_column_explains_itself(store):
    result = store.run_catalog_query("SELECT nope FROM show_facts")
    assert "no such column" in result["error"]


def test_tool_is_registered_only_for_stores_that_can_query(store):
    assert "query_catalog" in {t.name for t in build_tools(store)}
    assert "query_catalog" not in {t.name for t in build_tools(CanonicalStore())}


def test_tool_description_stays_small(store):
    tool = next(t for t in build_tools(store) if t.name == "query_catalog")
    assert len(tool.description) < 2500
    assert json.loads(tool.invoke({"sql": "SELECT COUNT(*) AS n FROM show_facts"}))["rows"][0][0] > 2000
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_catalog_query.py -v`
Expected: FAIL with `ImportError: cannot import name 'CATALOG_QUERY_MAX_ROWS'`

- [ ] **Step 3: Implement the store method**

In `deadbot/sqlite_store.py`, add `import time` and:

```python
CATALOG_QUERY_MAX_ROWS = 200
CATALOG_QUERY_TIMEOUT_SECONDS = 1.5

_READ_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _read_only(action: int, arg1: str | None, arg2: str | None, _db: str | None, _trigger: str | None) -> int:
    """Allow reading and ordinary functions; deny everything else."""

    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() == "load_extension":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY
```

and this method on `SqliteCanonicalStore`:

```python
    def run_catalog_query(self, sql: str) -> dict[str, Any]:
        """Run one read-only SELECT with a row cap and a time limit.

        The guardrails protect the service, not the answer: reading is the only
        permitted action, one statement runs per call, a runaway query is cut
        off, and errors come back in words the model can act on.
        """

        connection = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
        try:
            connection.set_authorizer(_read_only)
            deadline = time.monotonic() + CATALOG_QUERY_TIMEOUT_SECONDS
            connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
            cursor = connection.execute(sql)
            columns = [item[0] for item in cursor.description or ()]
            fetched = cursor.fetchmany(CATALOG_QUERY_MAX_ROWS + 1)
        except sqlite3.OperationalError as exc:
            message = str(exc)
            if "interrupted" in message:
                hint = f"The query ran past the {CATALOG_QUERY_TIMEOUT_SECONDS}s time limit. Filter earlier, join on keys, or aggregate."
            elif "not authorized" in message:
                hint = "Only a single read-only SELECT is allowed."
            else:
                hint = "Check table and column names against the views in the tool description."
            return {"error": message, "hint": hint}
        except (sqlite3.ProgrammingError, sqlite3.Warning) as exc:
            return {"error": str(exc), "hint": "Send one SELECT statement per call."}
        except sqlite3.DatabaseError as exc:
            return {"error": str(exc), "hint": "Only a single read-only SELECT is allowed."}
        finally:
            connection.close()
        truncated = len(fetched) > CATALOG_QUERY_MAX_ROWS
        result: dict[str, Any] = {
            "columns": columns,
            "rows": [list(row) for row in fetched[:CATALOG_QUERY_MAX_ROWS]],
            "row_count": min(len(fetched), CATALOG_QUERY_MAX_ROWS),
            "truncated": truncated,
        }
        if truncated:
            result["note"] = f"Only the first {CATALOG_QUERY_MAX_ROWS} rows are shown. Aggregate, filter, or add ORDER BY with a LIMIT."
        return result
```

If `test_anything_but_reading_is_refused` shows a statement slipping through (for example `ATTACH` raising a different error class), extend the exception handling. Never widen `_READ_ACTIONS`.

- [ ] **Step 4: Add the tool**

In `deadbot/tools.py`, inside `build_tools`, before the final `return`:

```python
    tools = [ ... the existing list, unchanged ... ]

    if callable(getattr(store, "run_catalog_query", None)):

        @tool
        def query_catalog(sql: str) -> str:
            """Find or count things across the catalog with one read-only SQLite SELECT.

            Use this for sets: which releases, how many times, the most, by year,
            venue or tour. Then use the lookup tools for depth on the few items
            your answer will feature. Views (prefer these):
            - show_facts: show_id, show_date, year, venue_id, venue_name, city, state_region, country, tour_name, event_name, performance_count
            - performance_facts: one row per setlist entry. performance_id, song_id, song_title, show_id, show_date, year, venue_id, venue_name, city, tour_name, set_number, set_label, position_in_set, encore, segue_into_next
            - release_track_facts: one row per official release track. release_id, release_title, release_type (live/studio), release_date, track_number, track_title, song_id, song_title, performance_id, show_id, show_date, year, venue_id, venue_name, city (show columns are NULL for studio tracks)
            - guest_appearances: show_id, show_date, year, person_id, person_name, instrument, venue_name, city
            Base tables (songs, shows, venues, people, official_releases, ...) are also readable.
            Notes: dates are ISO text, so compare as strings or use year. release_date may be partial ("1972", "1972-05").
            Booleans are the text 'true'/'false'. Count shows with COUNT(DISTINCT show_id); performance_count
            and setlist rows include Drums and Space. Results stop at 200 rows; aggregate or LIMIT.
            Examples:
            SELECT release_id, release_title, COUNT(DISTINCT show_id) AS shows FROM release_track_facts WHERE year = 1972 GROUP BY release_id ORDER BY shows DESC
            SELECT song_title, COUNT(*) AS times FROM performance_facts WHERE year = 1977 GROUP BY song_id ORDER BY times DESC LIMIT 15
            """
            return _json(store.run_catalog_query(sql))

        tools.append(query_catalog)
    return tools
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_catalog_query.py tests/test_research_tools.py tests/test_graph.py -q`
Expected: all PASS. If a graph test pins the exact tool count or list, update it: `query_catalog` exists only with the SQLite store.

- [ ] **Step 6: Commit**

```bash
git add deadbot/sqlite_store.py deadbot/tools.py tests/test_catalog_query.py
git commit -m "A read-only catalog query tool answers set questions, with a row cap, a time limit and read-only access"
```

---

### Task 7: Persona, well-worn routes, and the evaluation suite

**Files:**
- Modify: `deadbot/graph.py`, `## RESEARCH THE ACTUAL QUESTION` (lines ~33–71)
- Create: `evals/catalog-v1.json`
- Modify: `tests/test_graph.py`; add a test that runs the catalog suite
- Test: `tests/test_catalog_eval_suite.py`

**Interfaces:**
- Consumes: `query_catalog` (Task 6) and the `get_album` `include`/`show` options (Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph.py`:

```python
def test_prompt_teaches_survey_then_detail_and_querying_sets():
    assert "Work like a researcher" in SYSTEM_PROMPT
    assert "query_catalog" in SYSTEM_PROMPT
    assert 'include=["live_legacy"]' in SYSTEM_PROMPT
```

Create `tests/test_catalog_eval_suite.py`:

```python
from pathlib import Path

from deadbot.evaluations import evaluate_suite
from deadbot.sqlite_store import SqliteCanonicalStore


def test_catalog_suite_passes(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    try:
        result = evaluate_suite(Path("evals/catalog-v1.json"), store=store)
    finally:
        store.close()
    assert result["failed"] == 0, result
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_graph.py tests/test_catalog_eval_suite.py -v`
Expected: FAIL (the prompt text is missing; the suite file is missing)

- [ ] **Step 3: Edit the persona**

In `deadbot/graph.py`, append this paragraph to the end of the "Research efficiently." paragraph:

```
Work like a researcher. Lookups return a summary and list what more is
available; open a detail only when your answer will use it. To find or count
things across the catalog (which releases, how many times, the most, by year,
venue or tour), query it with query_catalog; to understand one thing deeply or
put it on the page, look it up.
```

In the "Well-worn routes." paragraph:
- replace `For a record's life on stage, get_album carries each track's live legacy.` with `For a record's life on stage, get_album with include=["live_legacy"] carries each song's stage history.`;
- add `For releases, shows or songs by year, venue or tour, query_catalog first, then get_album or get_show for the few you will feature.`

- [ ] **Step 4: Write `evals/catalog-v1.json`**

```json
{
  "suite_id": "catalog",
  "version": 1,
  "description": "Album summaries and read-only catalog queries: shape, detail on request, set answers, guardrails.",
  "cases": [
    {
      "id": "album-summary-lists-shows",
      "category": "album-summary",
      "question": "What is on Europe '72: The Complete Recordings?",
      "tool": "get_album",
      "arguments": {"release_id_or_title": "release-europe-72-the-complete-recordings-2011"},
      "expected": {"contains": {"contents.shows": {"show_id": "gd-1972-05-26"}}, "equals": {"available.tracks.count": 578}},
      "failure_conditions": ["Summary does not list the box set's shows or does not offer its tracks."]
    },
    {
      "id": "album-tracks-for-one-show",
      "category": "album-detail",
      "question": "What did they play on the last night of Europe '72?",
      "tool": "get_album",
      "arguments": {"release_id_or_title": "release-europe-72-the-complete-recordings-2011", "show": "1972-05-26"},
      "expected": {"contains": {"tracks": {"performance_id": "gd-1972-05-26-promised-land-1-1"}}},
      "failure_conditions": ["Narrowing to one show does not return that show's tracks."]
    },
    {
      "id": "releases-covering-1972",
      "category": "catalog-query",
      "question": "Which official releases cover 1972?",
      "tool": "query_catalog",
      "arguments": {"sql": "SELECT DISTINCT release_id FROM release_track_facts WHERE year = 1972 ORDER BY release_id"},
      "expected": {"contains": {"rows": ["release-europe-72-the-complete-recordings-2011"]}},
      "failure_conditions": ["The Europe '72 box is missing from 1972's releases."]
    },
    {
      "id": "most-played-1977",
      "category": "catalog-query",
      "question": "Which songs did they play most in 1977?",
      "tool": "query_catalog",
      "arguments": {"sql": "SELECT song_title, COUNT(*) AS times FROM performance_facts WHERE year = 1977 GROUP BY song_id ORDER BY times DESC LIMIT 1"},
      "expected": {"contains": {"rows": ["Estimated Prophet", 51]}},
      "failure_conditions": ["The top 1977 song or its count is wrong."]
    },
    {
      "id": "writes-refused",
      "category": "catalog-guardrail",
      "question": "(guardrail) a write attempt",
      "tool": "query_catalog",
      "arguments": {"sql": "DELETE FROM songs"},
      "expected": {"equals": {"hint": "Only a single read-only SELECT is allowed."}},
      "failure_conditions": ["A write was not refused."]
    }
  ]
}
```

The evaluation runner's `_value_at_path` follows dotted dict keys (`available.tracks.count`, `contents.shows`), which these cases use. The values (578 tracks; `gd-1972-05-26-promised-land-1-1` on the box set; Estimated Prophet played 51 times in 1977) were read from `data/canonical` on 2026-09-23. If Task 5's independent count gives a different 1977 figure after a data change, use that figure.

- [ ] **Step 5: Run the tests, then the full suite**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_graph.py tests/test_catalog_eval_suite.py -v` and then `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add deadbot/graph.py evals/catalog-v1.json tests/test_graph.py tests/test_catalog_eval_suite.py
git commit -m "The persona works like a researcher: survey, query sets, open detail only when the answer uses it"
```

---

### Task 8 (controller): after-measurement and model review

- [ ] **Step 1:** Run the measurement again. Rebuild the web app first if any web file changed; this plan changes none.

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/measure_turns.py --output docs/measurements/2026-09-23-after.md
```

- [ ] **Step 2:** Compare against the baseline for the spec's success criteria:
  - the 1972 question has no rate-limit error, peak input under 60,000, and a first answer sooner than baseline;
  - no call exceeds 100,000 input tokens;
  - truncations are recorded.
  
  Add a short "Comparison" section at the top of the after file with the numbers side by side.
- [ ] **Step 3:** Run the model evaluation on the four set questions and review the traces:

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m deadbot.cli evaluate --model --suite evals/exploration-v1.json --output build/model-eval-after.json
```

If the exploration suite lacks the set questions, review them from the measurement run instead. For each set question:
- confirm the model used `query_catalog`;
- check its numbers with a hand-written query in `build/deadbot.sqlite`;
- note any wrong query.

Record the findings in the after file.
- [ ] **Step 4:** Commit the after file, then report to the owner with the comparison and any quality concerns. Improve the guide or the views for wrong queries. Never write question-specific code.

---

## Self-Review Notes

- **Spec coverage.** Album summary and detail (Task 4); query tool, views and guardrails (Tasks 5–6); ceiling (Task 3); persona and routes (Task 7); metrics and script (Tasks 1–2); evals (Task 7); measurement and success criteria (Tasks 2 and 8).
- **Rulings recorded in the plan:**
  - `show` implies tracks;
  - `live_legacy` is keyed by song;
  - `show_facts.performance_count` replaces the spec's `song_count`.
