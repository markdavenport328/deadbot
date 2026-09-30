"""One turn's cost in numbers: model calls, tokens, tool result sizes, timing.

Logged once per streamed turn so latency and context growth are measured
rather than guessed. Only the question text leaves the request.

Per model call: input and output tokens, and when the provider reports them,
the input tokens it served from its prompt cache (billed at a discount) and
the output tokens spent on hidden reasoning. Per turn: the totals, how many
calls asked for research tools (rounds), and the time to the first answer
text the visitor saw.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot.finish import FINISH_TOOL_NAME


def _this_turn(messages: list[Any]) -> list[Any]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index + 1 :]
    return list(messages)


def _detail(details: Any, suffix: str) -> int | None:
    """A token detail by name, summed across service-tier prefixes (``priority_cache_read``)."""

    if not isinstance(details, dict):
        return None
    values = [value for key, value in details.items() if key == suffix or key.endswith(f"_{suffix}")]
    numbers = [value for value in values if isinstance(value, int)]
    return sum(numbers) if numbers else None


def _call(message: AIMessage) -> dict[str, Any]:
    usage = message.usage_metadata or {}
    call: dict[str, Any] = {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}
    cached = _detail(usage.get("input_token_details"), "cache_read")
    reasoning = _detail(usage.get("output_token_details"), "reasoning")
    if cached is not None:
        call["cached_input_tokens"] = cached
    if reasoning is not None:
        call["reasoning_tokens"] = reasoning
    names = [call_.get("name") for call_ in (message.tool_calls or [])]
    if names:
        call["tool_calls"] = len(names)
        call["finish"] = FINISH_TOOL_NAME in names
    return call


def _total(calls: list[dict[str, Any]], key: str) -> int | None:
    values = [call[key] for call in calls if isinstance(call.get(key), int)]
    return sum(values) if values else None


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
            calls.append(_call(message))
        elif isinstance(message, ToolMessage):
            content = message.content if isinstance(message.content, str) else str(message.content)
            tools.append({"name": message.name or "", "chars": len(content), "truncated": '"_truncated"' in content})
    inputs = [call["input_tokens"] for call in calls if call["input_tokens"] is not None]
    total_input = sum(inputs) if inputs else None
    total_cached = _total(calls, "cached_input_tokens")
    research_rounds = sum(
        1 for call in calls if call.get("tool_calls") and (call["tool_calls"] > 1 or not call.get("finish"))
    )
    return {
        "question": question,
        "model_calls": len(calls),
        "research_rounds": research_rounds,
        "calls": calls,
        "peak_input_tokens": max(inputs) if inputs else None,
        "total_input_tokens": total_input,
        "total_cached_input_tokens": total_cached,
        "cached_input_share": round(total_cached / total_input, 3) if total_cached is not None and total_input else None,
        "total_output_tokens": _total(calls, "output_tokens"),
        "total_reasoning_tokens": _total(calls, "reasoning_tokens"),
        "tools": tools,
        "largest_tool_result_chars": max((tool["chars"] for tool in tools), default=0),
        "seconds_to_first_answer": round(first_answer_at - started, 2) if first_answer_at is not None else None,
        "seconds_total": round(finished_at - started, 2),
        "error": error,
    }
