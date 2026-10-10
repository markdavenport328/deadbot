"""Measure what each question costs: rounds, tokens, tool result sizes, timing.

Runs questions in-process against the configured model with the response
cache off, and prints one row per question. Compare a run before and after a
change to tools or prompt:

    PYTHONPATH=. .venv/bin/python scripts/measure_turns.py --output docs/measurements/2026-09-23-baseline.md
    PYTHONPATH=. .venv/bin/python scripts/measure_turns.py --sequence europe72 --sequence 1979 --compare --output docs/measurements/<date>-notebook-after.md

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
import uuid
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

# Follow-up paths the research notebook is meant to speed up. Each runs as one
# conversation, the way the browser asks it.
SEQUENCES = {
    "europe72": [
        "What's on Europe '72: The Complete Recordings?",
        "Tell me about the last Lyceum night, May 26, 1972.",
        "How does that night's Morning Dew compare with other Morning Dews?",
    ],
    "1979": [
        "Best shows of 1979",
        "Compare the first two shows you picked.",
        "Which songs from those nights would you play someone new to 1979?",
    ],
}


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


def measure_sequence(
    questions: list[str], *, app: Any, use_notebook: bool = True, pause_seconds: float = 0.0
) -> list[dict[str, Any]]:
    """Ask questions in order as one conversation, sending back what each answer returned."""

    collector = _Collector()
    metrics_logger = logging.getLogger("deadbot.turn_metrics")
    metrics_logger.addHandler(collector)
    client = TestClient(app)
    thread_id = f"measure-{uuid.uuid4()}"
    conversation: list[dict[str, Any]] = []
    token: str | None = None
    rows = []
    try:
        for index, question in enumerate(questions):
            if index and pause_seconds:
                time.sleep(pause_seconds)
            sent = token if use_notebook and token else None
            body: dict[str, Any] = {"question": question, "thread_id": thread_id, "conversation": conversation}
            if sent:
                body["notebook"] = sent
            before = len(collector.lines)
            delivered = None
            with client.stream("POST", "/api/experience/stream", json=body) as response:
                for line in response.iter_lines():
                    if line.strip():
                        event = json.loads(line)
                        if event.get("type") == "response":
                            delivered = event["response"]
            logged = collector.lines[before:]
            row = dict(logged[-1]) if logged else {"question": question, "error": "no metrics logged"}
            row.update(turn=index + 1, notebook_bytes=len(sent or ""))
            rows.append(row)
            if delivered is None:
                break
            conversation = delivered.get("conversation") or []
            token = delivered.get("notebook")
    finally:
        metrics_logger.removeHandler(collector)
    return rows


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def table(rows: list[dict[str, Any]]) -> str:
    header = (
        "| Question | Calls | Research rounds | Peak input | Total input | Cached input | Cached share | Total output | Reasoning | "
        "Notebook reads | Notebook index (chars) | Notebook sent (bytes) | Largest tool result | First answer (s) | Total (s) | Truncated | Error |"
    )
    lines = [header, "|" + "---|" * 17]
    for row in rows:
        truncated = sum(1 for tool in row.get("tools", []) if tool.get("truncated"))
        lines.append(
            f"| {row.get('question', '')} | {row.get('model_calls', '')} | {_cell(row.get('research_rounds'))} | "
            f"{row.get('peak_input_tokens', '')} | {row.get('total_input_tokens', '')} | {_cell(row.get('total_cached_input_tokens'))} | "
            f"{_cell(row.get('cached_input_share'))} | {_cell(row.get('total_output_tokens'))} | {_cell(row.get('total_reasoning_tokens'))} | "
            f"{_cell(row.get('notebook_reads'))} | {_cell(row.get('notebook_index_chars'))} | {_cell(row.get('notebook_bytes'))} | "
            f"{row.get('largest_tool_result_chars', '')} | {row.get('seconds_to_first_answer', '')} | {row.get('seconds_total', '')} | "
            f"{truncated} | {row.get('error') or ''} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pause", type=float, default=20.0)
    parser.add_argument("--sequence", action="append", choices=sorted(SEQUENCES), help="ask a follow-up path as one conversation")
    parser.add_argument("--compare", action="store_true", help="run each sequence without, then with, the research notebook")
    parser.add_argument("--without-notebook", action="store_true", help="send no notebook back with follow-ups")
    args = parser.parse_args(argv)

    from deadbot.api import create_app
    from deadbot.config import Settings

    settings = dataclasses.replace(Settings.from_env(), response_cache=False, rate_limit_per_minute=0)
    app = create_app(settings=settings)
    if args.sequence:
        sections = []
        rows = []
        for name in args.sequence:
            for use_notebook in ([False, True] if args.compare else [not args.without_notebook]):
                label = f"{name}, {'with' if use_notebook else 'without'} the notebook"
                found = measure_sequence(SEQUENCES[name], app=app, use_notebook=use_notebook, pause_seconds=args.pause)
                sections.append(f"## {label}\n\n{table(found)}")
                rows.extend({**row, "sequence": label} for row in found)
        rendered = "\n\n".join(sections)
    else:
        rows = measure(args.questions or DEFAULT_QUESTIONS, app=app, pause_seconds=args.pause)
        rendered = table(rows)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"# Turn measurements\n\nModel: {settings.openai_model if settings.model_provider == 'openai' else settings.ollama_model}"
            f" (reasoning effort: {settings.openai_reasoning_effort or 'default'})\n\n{rendered}\n\n"
            "Raw metrics, one JSON object per question:\n\n```json\n" + "\n".join(json.dumps(row) for row in rows) + "\n```\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    sys.exit(main())
