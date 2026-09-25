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
