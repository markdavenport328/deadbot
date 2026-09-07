"""Visitor-facing progress while the agent researches a question.

Each tool call the model makes becomes one short status line ("Reading the
show on 1990-03-29", "Searching Dead Essays for Branford"), streamed to the
browser as it happens. Nothing here exposes tool payloads, prompts or model
reasoning: a status names the kind of work and the subject the visitor asked
about, and that is all.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any
from urllib.parse import urlparse

from deadbot.finish import FINISH_TOOL_NAME

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _quote(value: Any, limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return f"“{text}”" if text else ""


def _host(url: Any) -> str:
    host = urlparse(str(url or "")).netloc.removeprefix("www.")
    return host or "a page"


def describe_tool_call(name: str, args: dict[str, Any] | None) -> str:
    """One line, in the visitor's terms, for what a tool call is doing."""

    args = args or {}
    if name == FINISH_TOOL_NAME:
        return "Composing the answer"
    if name == "search_entities":
        return f"Searching the library for {_quote(args.get('query'))}".rstrip()
    if name == "search_guest_musicians":
        return f"Looking up guest musicians: {_quote(args.get('query'))}".rstrip(": ")
    if name == "get_show":
        subject = str(args.get("show_id_or_date") or "").strip()
        return f"Reading the show on {subject}" if _DATE.match(subject) else f"Reading a show ({subject})" if subject else "Reading a show"
    if name == "get_song":
        return f"Reading up on {_quote(args.get('song_id_or_title'))}".rstrip()
    if name == "get_song_performance_profile":
        return f"Charting performances of {_quote(args.get('song_id_or_title'))}".rstrip()
    if name == "get_performance":
        return "Reading a performance and its set"
    if name in {"get_show_selections", "get_selection_signals"}:
        return "Consulting critics' and fans' picks"
    if name == "search_site":
        site = str(args.get("site") or "a research site").strip()
        return f"Searching {site} for {_quote(args.get('query'))}".rstrip()
    if name == "read_page":
        return f"Reading {_host(args.get('url'))}"
    if name == "get_recording_reviews":
        return "Checking listener reviews of the recordings"
    if name == "get_media_links":
        return "Finding recordings and listening links"
    if name in {"search_stored_resources", "get_lore_source_trails", "get_deadnet_song_context", "get_deadcast_metadata", "get_research_source_directory"}:
        return "Looking for lore and sources"
    if name == "find_arrangements":
        key = str(args.get("key_signature") or "").strip()
        return f"Finding arrangements in {key}" if key else "Finding arrangements"
    if name == "get_equipment_history":
        return "Checking Jerry's gear"
    if name in {"get_historical_weather", "get_astronomy", "get_astrology"}:
        return "Adding context for the night"
    return name.replace("_", " ").capitalize()


def status_lines(messages: Iterable[Any], already_seen: int) -> Iterator[str]:
    """Statuses for tool calls in messages beyond the first ``already_seen``."""

    for message in list(messages)[already_seen:]:
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            yield describe_tool_call(str(call.get("name") or ""), call.get("args"))
