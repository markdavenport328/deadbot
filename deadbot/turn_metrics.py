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
