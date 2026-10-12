"""Shared builders for research-notebook tests: real tool output, real turns."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.data import CanonicalStore
from deadbot.finish import build_experience_response
from deadbot.tools import build_tools

SECRET = "test-notebook-secret"
LYCEUM = [("get_show", {"show_id_or_date": "1972-05-26"})]


@lru_cache(maxsize=1)
def store() -> CanonicalStore:
    return CanonicalStore()


@lru_cache(maxsize=1)
def tools() -> dict[str, Any]:
    return {item.name: item for item in build_tools(store())}


def call_messages(calls: list[tuple[str, dict]], *, prefix: str = "c") -> list[Any]:
    messages: list[Any] = []
    for index, (name, args) in enumerate(calls):
        call_id = f"{prefix}{index}"
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}]))
        messages.append(ToolMessage(content=tools()[name].invoke(args), tool_call_id=call_id, name=name))
    return messages


def plan_for(answer: str, items: list[dict] | None = None) -> dict[str, Any]:
    groups = [{"presentation": "collection", "items": items}] if items else []
    return {"chat_answer": answer, "title": answer[:40], "lead": None, "groups": groups}


def finish_messages(answer: str, *, items: list[dict] | None = None, call_id: str = "f1") -> list[Any]:
    return [
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan_for(answer, items), "id": call_id, "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id=call_id, name="finish_response"),
    ]


def turn(question: str, answer: str, calls: list[tuple[str, dict]], *, items: list[dict] | None = None, prefix: str = "c") -> list[Any]:
    return [HumanMessage(content=question), *call_messages(calls, prefix=prefix), *finish_messages(answer, items=items, call_id=f"{prefix}f")]


def record(book, question, answer, calls, *, items=None, prefix="c"):
    messages = turn(question, answer, calls, items=items, prefix=prefix)
    response = build_experience_response(question, "t", messages, store())
    return notebook.record_turn(book, composition._latest_turn(messages), response), response
