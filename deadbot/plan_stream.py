"""Turn the streamed ``finish_response`` arguments into page events.

The model writes its plan as JSON text, in schema order: ``chat_answer``,
``title``, ``lead``, then ``groups`` whose scalar fields precede ``items``.
:class:`PlanStreamer` scans that text once, character by character, tracking
strings, the container stack and the key path, and emits an event when the
title closes, a group's items begin, an item closes (after resolving it to
hydrated blocks), and a group closes. Everything here is transport: it
never chooses content, and any failure disables progressive events for the
turn while the final response is built exactly as before.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from deadbot.finish import FINISH_TOOL_NAME, GROUP_ITEM_LIMIT, PRESENTATIONS, keep_grounded_links, validate_body_item

logger = logging.getLogger(__name__)


@dataclass
class PlanEvent:
    type: str
    payload: dict[str, Any]


@dataclass
class _Frame:
    kind: str  # "object" or "array"
    start: int  # offset of the opening bracket in the argument text
    key: str | None = None  # object: the key whose value is being read
    index: int = -1  # array: index of the element being read
    expecting_key: bool = True  # object: the next string is a key
    value_start: int | None = None  # where the current value began


class PlanStreamer:
    """Feed every ``AIMessageChunk`` from a ``messages`` stream; collect the events."""

    def __init__(
        self,
        resolve: Callable[[list[Any]], list[Any]],
        grounded_urls: frozenset[str] = frozenset(),
    ) -> None:
        self._resolve = resolve
        self._grounded_urls = grounded_urls
        self._call_id: str | None = None
        self._call_index: int | None = None
        self._reset_state()

    @property
    def disabled(self) -> bool:
        return self._disabled

    def _reset_state(self) -> None:
        self._text = ""
        self._pos = 0
        self._stack: list[_Frame] = []
        self._in_string = False
        self._escape = False
        self._string_start = 0
        self._title: str | None = None
        self._lead: str | None = None
        self._groups: dict[int, dict[str, Any]] = {}
        self._head_sent = False
        self._disabled = False
        self._done = False

    # --- chunk routing -------------------------------------------------------

    def feed(self, message_chunk: Any) -> list[PlanEvent]:
        events: list[PlanEvent] = []
        for chunk in getattr(message_chunk, "tool_call_chunks", None) or []:
            if not self._belongs(chunk, events):
                continue
            self._text += chunk.get("args") or ""
        if self._disabled or self._done:
            return events
        try:
            events.extend(self._scan())
        except Exception:  # A scanner fault must never break the stream.
            logger.exception("Progressive plan scanning disabled for this turn")
            self._disabled = True
        return events

    def _belongs(self, chunk: dict[str, Any], events: list[PlanEvent]) -> bool:
        name, call_id, call_index = chunk.get("name"), chunk.get("id"), chunk.get("index")
        if name == FINISH_TOOL_NAME:
            if self._call_id is None and self._call_index is None:
                self._call_id, self._call_index = call_id, call_index
                return True
            same = (call_id is not None and call_id == self._call_id) or (call_id is None and call_index == self._call_index)
            if not same:
                # The model is retrying finish_response; the draft is void.
                self._reset_state()
                self._call_id, self._call_index = call_id, call_index
                events.append(PlanEvent("page_reset", {}))
            return True
        if name:
            return False
        if call_id is not None and call_id == self._call_id:
            return True
        return call_index is not None and call_index == self._call_index

    # --- scanning ------------------------------------------------------------

    def _top(self) -> _Frame | None:
        return self._stack[-1] if self._stack else None

    def _path(self) -> list[Any]:
        return [frame.key if frame.kind == "object" else frame.index for frame in self._stack]

    def _group(self, index: int) -> dict[str, Any]:
        return self._groups.setdefault(index, {})

    def _grounded(self, lead: str | None) -> str | None:
        if not lead:
            return lead
        return keep_grounded_links(lead, self._grounded_urls)

    def _group_payload(self, index: int) -> dict[str, Any]:
        group = self._group(index)
        criteria = [c.strip() for c in (group.get("criteria") or []) if isinstance(c, str) and c.strip()][:5]
        presentation = group.get("presentation")
        return {
            "index": index,
            "title": group.get("title"),
            "lead": self._grounded(group.get("lead")),
            # The same reading finish.FinishPlan gives an unknown presentation.
            "presentation": presentation if presentation in PRESENTATIONS else "collection",
            "criteria": criteria,
        }

    def _emit_head(self) -> list[PlanEvent]:
        if self._head_sent:
            return []
        self._head_sent = True
        return [PlanEvent("page_head", {"title": self._title or "", "lead": self._grounded(self._lead)})]

    def _begin_value(self) -> None:
        top = self._top()
        if top is None:
            return
        if top.kind == "object":
            if top.expecting_key:
                return
            if top.value_start is None:
                top.value_start = self._pos
        elif top.value_start is None:
            top.index += 1
            top.value_start = self._pos

    def _end_value(self) -> None:
        top = self._top()
        if top is None:
            return
        top.value_start = None
        if top.kind == "object":
            top.expecting_key = True
            top.key = None

    def _scan(self) -> list[PlanEvent]:
        events: list[PlanEvent] = []
        text = self._text
        while self._pos < len(text) and not self._done:
            ch = text[self._pos]
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                    events.extend(self._string_closed(self._string_start, self._pos + 1))
            elif ch == '"':
                self._begin_value()
                self._in_string = True
                self._string_start = self._pos
            elif ch in "{[":
                self._begin_value()
                events.extend(self._container_opened(ch))
            elif ch in "}]":
                events.extend(self._container_closed(self._pos, ch))
            elif ch == ":":
                top = self._top()
                if top is not None and top.kind == "object":
                    top.expecting_key = False
            elif ch == ",":
                self._end_value()
            elif not ch.isspace():
                self._begin_value()
            self._pos += 1
        return events

    def _string_closed(self, start: int, end: int) -> list[PlanEvent]:
        top = self._top()
        if top is None:
            return []
        value = json.loads(self._text[start:end])
        if top.kind == "object" and top.expecting_key:
            top.key = value
            return []
        path = self._path()
        if path == ["title"]:
            self._title = value
        elif path == ["lead"]:
            self._lead = value
        elif len(path) == 3 and path[0] == "groups" and path[2] in ("title", "lead", "presentation"):
            self._group(path[1])[path[2]] = value
        return []

    def _container_opened(self, ch: str) -> list[PlanEvent]:
        path = self._path()
        self._stack.append(_Frame(kind="object" if ch == "{" else "array", start=self._pos))
        if path == ["groups"] and ch == "[":
            return self._emit_head()
        if len(path) == 3 and path[0] == "groups" and path[2] == "items" and ch == "[":
            return [PlanEvent("group_open", self._group_payload(path[1]))]
        return []

    def _container_closed(self, pos: int, ch: str) -> list[PlanEvent]:
        if not self._stack:
            raise ValueError("unbalanced closing bracket in finish_response arguments")
        frame = self._stack.pop()
        if frame.kind != ("object" if ch == "}" else "array"):
            raise ValueError("mismatched closing bracket in finish_response arguments")
        path = self._path()
        raw = self._text[frame.start : pos + 1]
        events: list[PlanEvent] = []
        if len(path) == 4 and path[0] == "groups" and path[2] == "items" and frame.kind == "object":
            items_frame = self._top()
            events.extend(self._item_closed(path[1], items_frame.index if items_frame else 0, raw))
        elif len(path) == 3 and path[0] == "groups" and path[2] == "criteria" and frame.kind == "array":
            self._group(path[1])["criteria"] = [entry for entry in json.loads(raw) if isinstance(entry, str)]
        elif len(path) == 2 and path[0] == "groups" and frame.kind == "object":
            events.append(PlanEvent("group_close", self._group_payload(path[1])))
        elif not self._stack:
            self._done = True
            events.extend(self._emit_head())
        parent = self._top()
        if parent is not None:
            parent.value_start = None
        return events

    def _item_closed(self, group_index: int, position: int, raw: str) -> list[PlanEvent]:
        # The same two rules the plan's validation applies (finish.FinishPlan):
        # a group keeps its first GROUP_ITEM_LIMIT items, and an item that does
        # not fit its schema is dropped.
        if position >= GROUP_ITEM_LIMIT:
            logger.warning("Skipped streamed item %d of group %d: past the group limit of %d", position + 1, group_index, GROUP_ITEM_LIMIT)
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            logger.info("Skipped a streamed item that was not JSON: %s", error)
            return []
        item = validate_body_item(parsed, where="streamed")
        if item is None:
            return []
        criteria = self._group(group_index).get("criteria")
        events: list[PlanEvent] = []
        try:
            resolved = self._resolve([item])
        except Exception:  # One bad item must not disable the whole streamer.
            logger.exception("Skipped a streamed item that failed to hydrate")
            return []
        for block in resolved:
            if criteria is not None and hasattr(block, "judgments") and hasattr(block, "model_copy"):
                block = block.model_copy(update={"judgments": list(block.judgments)[: len(criteria)]})
            payload = block.model_dump(mode="json") if hasattr(block, "model_dump") else block
            events.append(PlanEvent("block", {"group_index": group_index, "block": payload}))
        return events
