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

from deadbot.experience import PAGE_BLOCK_CEILING
from deadbot.finish import FINISH_TOOL_NAME, clean_criteria, drop_repeated_records, group_presentation, keep_grounded_links, read_joining_repeats, validate_body_item

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
        self._blocks_sent = 0
        # The records each group already shows, so a repeat is left out as the final page leaves it out.
        self._group_records: dict[int, set[tuple[str, str]]] = {}
        # The model can write "groups" more than once; later lists continue the
        # first. A later list's groups are held until each closes: one that
        # repeats an earlier group is left out, as finish.read_joining_repeats
        # leaves it out of the delivered plan; a new one is sent then.
        self._groups_lists = 0
        self._group_offset = 0
        self._seen_groups: set[str] = set()
        self._held: dict[int, list[PlanEvent]] = {}
        self._emitted_index: dict[int, int] = {}
        self._next_index = 0
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
        path = [frame.key if frame.kind == "object" else frame.index for frame in self._stack]
        if len(path) >= 2 and path[0] == "groups" and isinstance(path[1], int):
            # A second "groups" list continues the first, as the delivered plan reads it.
            path[1] += self._group_offset
        return path

    def _group(self, index: int) -> dict[str, Any]:
        return self._groups.setdefault(index, {})

    def _grounded(self, lead: str | None) -> str | None:
        if not lead:
            return lead
        return keep_grounded_links(lead, self._grounded_urls)

    def _group_payload(self, index: int) -> dict[str, Any]:
        group = self._group(index)
        return {
            "index": index,
            "title": group.get("title"),
            "lead": self._grounded(group.get("lead")),
            # The same reading finish.FinishPlan gives a group.
            "presentation": group_presentation(group.get("presentation")),
            "criteria": clean_criteria(group.get("criteria")),
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
            if self._groups_lists:
                self._group_offset = max(self._groups) + 1 if self._groups else 0
            self._groups_lists += 1
            return self._emit_head()
        if len(path) == 3 and path[0] == "groups" and path[2] == "items" and ch == "[":
            return self._in_group(path[1], [PlanEvent("group_open", self._group_payload(path[1]))])
        return []

    def _in_group(self, index: int, events: list[PlanEvent]) -> list[PlanEvent]:
        """Send a group's events now, or hold them while a later groups list is read."""

        if self._groups_lists > 1:
            self._held.setdefault(index, []).extend(events)
            return []
        return events

    def _group_closed(self, index: int, raw: str) -> list[PlanEvent]:
        parsed = read_joining_repeats(raw)
        canonical = json.dumps(parsed, sort_keys=True) if parsed is not None else raw
        opened: list[PlanEvent] = []
        if isinstance(parsed, dict) and "items" not in parsed and isinstance(parsed.get("type"), str):
            # A body item written straight into groups stands as its own
            # collection, as finish.FinishPlan reads it; its title is the item's.
            self._groups[index] = {"presentation": "collection"}
            open_event = PlanEvent("group_open", self._group_payload(index))
            item_events = self._item_closed(index, 0, raw)
            if self._groups_lists > 1:
                self._held[index] = [open_event, *self._held.get(index, [])]
            else:
                opened = [open_event, *item_events]
        close = PlanEvent("group_close", self._group_payload(index))
        if self._groups_lists <= 1:
            self._seen_groups.add(canonical)
            self._next_index = max(self._next_index, index + 1)
            return [*opened, close]
        held = [*self._held.pop(index, []), close]
        if canonical in self._seen_groups:
            self._blocks_sent -= sum(1 for event in held if event.type == "block")
            return []
        self._seen_groups.add(canonical)
        emitted = self._next_index
        self._next_index += 1
        for event in held:
            key = "group_index" if event.type == "block" else "index"
            event.payload[key] = emitted
        return held

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
            events.extend(self._group_closed(path[1], raw))
        elif not self._stack:
            self._done = True
            events.extend(self._emit_head())
        parent = self._top()
        if parent is not None:
            parent.value_start = None
        return events

    def _item_closed(self, group_index: int, position: int, raw: str) -> list[PlanEvent]:
        # The same reading the plan's validation gives each item
        # (finish.validate_body_item) and the same resolution the final page
        # uses (finish.resolve_items), so every block streamed here is in the
        # delivered page.
        # Read the way the delivered plan is read (finish.read_joining_repeats).
        parsed = read_joining_repeats(raw)
        if parsed is None:
            logger.info("Skipped a streamed item that was not JSON")
            return []
        item = validate_body_item(parsed, where="streamed")
        if item is None:
            return []
        try:
            resolved = self._resolve([item])
        except Exception:  # One bad item must not disable the whole streamer.
            logger.exception("Skipped a streamed item that failed to hydrate")
            return []
        resolved = drop_repeated_records(resolved, self._group_records.setdefault(group_index, set()))
        room = PAGE_BLOCK_CEILING - self._blocks_sent
        if len(resolved) > room:
            logger.warning("The page reached the transport ceiling of %d blocks; later blocks are left out", PAGE_BLOCK_CEILING)
            resolved = resolved[: max(room, 0)]
        self._blocks_sent += len(resolved)
        events: list[PlanEvent] = []
        for block in resolved:
            payload = block.model_dump(mode="json") if hasattr(block, "model_dump") else block
            events.append(PlanEvent("block", {"group_index": group_index, "block": payload}))
        return self._in_group(group_index, events)
