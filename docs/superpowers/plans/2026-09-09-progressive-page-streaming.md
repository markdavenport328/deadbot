# Progressive Page Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the main body progressively while the model is still writing its `finish_response` plan, so the first block appears within seconds of the chat answer instead of after the whole plan.

**Architecture:** A `PlanStreamer` scanner in `deadbot/plan_stream.py` watches the streamed `finish_response` argument text beside the existing `AnswerAccumulator`, detects when the title, each group, and each item close, hydrates each item immediately through `finish.resolve_items`, and yields page events. `_stream_events` in `deadbot/api.py` forwards them as NDJSON. The browser builds a draft page from the events with the same components the final page uses, then swaps in the final `response`. A development-only replay fixture exercises the whole path without a model.

**Tech Stack:** Python 3.11, Pydantic v2 (`TypeAdapter`), FastAPI streaming, LangGraph `messages` stream mode; React 18 + TypeScript + Vite; pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-progressive-page-streaming-design.md`

## Global Constraints

- Deterministic code is transport, structure and form; it never chooses content or adds editorial copy (`AGENTS.md`). The only new visitor-facing string is "Composing the page…" at the bottom of a draft page, already used as a status.
- The plan schema does not change. No new fields on `FinishPlan`, `GroupPlan`, or unit refs.
- New NDJSON events and exact payloads: `page_head` `{title, lead}`; `group_open` and `group_close` `{index, title, lead, presentation, criteria}`; `block` `{group_index, block}`; `page_reset` `{}`. Existing `status`, `answer`, `response`, `error` are unchanged. Cached answers and the plain `/api/experience` endpoint emit no progressive events.
- Progressive scanning must never break the stream: any scanner exception disables progressive events for the rest of the turn and is logged; the final `response` path is untouched.
- Blocks streamed for a group must equal, by type and order, the blocks the final response places in that group (the final response stays authoritative and is what the cache stores).
- Python: `PY=/Users/markdavenport/Development/DeadBot/.venv/bin/python` from the worktree root; tests `$PY -m pytest <files> -q`. Web: `npm run build --prefix web` must pass at the end of every frontend task. No schema change, so no OpenAPI or type regeneration is needed; if `deadbot/experience.py` is touched by mistake, regenerate and commit.
- Dark palette and spacing tokens in `web/src/styles.css`; no new colors; no em-dashes in copy.
- Do not push. Commit locally; every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 1: PlanStreamer scanner

**Files:**
- Create: `deadbot/plan_stream.py`
- Test: `tests/test_plan_stream.py`

**Interfaces:**
- Produces: `PlanEvent(type: str, payload: dict)`, and `PlanStreamer(resolve: Callable[[list[Any]], list[Any]])` with `feed(message_chunk) -> list[PlanEvent]` and a read-only `disabled: bool`. `resolve` receives a list with one validated `BodyItem` and returns resolved blocks; each block is emitted with `model_dump(mode="json")` when it has that method, else as is.
- Consumes: `deadbot.finish.FINISH_TOOL_NAME`, `deadbot.finish.BodyItem`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_stream.py
import json

from langchain_core.messages import AIMessageChunk

from deadbot.plan_stream import PlanEvent, PlanStreamer


def chunk(args: str, *, name: str | None = None, call_id: str = "f1", index: int = 0) -> AIMessageChunk:
    return AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": name, "args": args, "id": call_id, "index": index, "type": "tool_call_chunk"}],
    )


PLAN = {
    "chat_answer": "Sugaree opened the \"second\" set, with a } brace and a \\ backslash.",
    "title": "Sugaree at Veneta",
    "lead": "A relaxed early version.",
    "groups": [
        {
            "title": "The night",
            "lead": None,
            "presentation": "comparison",
            "criteria": ["Pace", "Jam"],
            "items": [
                {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "judgments": ["Relaxed", "Long", "Extra"],
                 "supporting_sources": [{"url": "https://archive.org/details/x", "note": "A note with {braces} and [brackets]."}]},
                {"type": "editorial", "presentation": "narrative", "paragraphs": ["Text, with commas: and colons."], "items": []},
            ],
        },
        {"presentation": "collection", "items": [{"type": "song_overview", "song_id": "song-sugaree"}]},
    ],
}
PLAN_TEXT = json.dumps(PLAN)


def fake_resolve(items):
    item = items[0]
    return [{"type": item.type, "id": getattr(item, "show_id", None) or getattr(item, "song_id", None) or "editorial", "judgments": list(getattr(item, "judgments", []))}]


def drive(text: str, pieces: int) -> list[PlanEvent]:
    streamer = PlanStreamer(fake_resolve)
    events: list[PlanEvent] = []
    size = max(1, len(text) // pieces)
    for offset in range(0, len(text), size):
        fragment = text[offset : offset + size]
        events.extend(streamer.feed(chunk(fragment, name="finish_response" if offset == 0 else None)))
    return events


def test_events_arrive_in_reading_order_with_group_metadata():
    events = drive(PLAN_TEXT, 1)
    types = [event.type for event in events]
    assert types == ["page_head", "group_open", "block", "block", "group_close", "group_open", "block", "group_close"]
    assert events[0].payload == {"title": "Sugaree at Veneta", "lead": "A relaxed early version."}
    assert events[1].payload == {"index": 0, "title": "The night", "lead": None, "presentation": "comparison", "criteria": ["Pace", "Jam"]}
    assert events[2].payload["group_index"] == 0 and events[2].payload["block"]["id"] == "gd-1972-08-27"
    assert events[3].payload["block"]["type"] == "editorial"
    assert events[5].payload["presentation"] == "collection" and events[5].payload["criteria"] == []


def test_one_character_at_a_time_gives_identical_events():
    whole = drive(PLAN_TEXT, 1)
    by_char = drive(PLAN_TEXT, len(PLAN_TEXT))
    assert [(event.type, event.payload) for event in by_char] == [(event.type, event.payload) for event in whole]


def test_a_plan_with_no_groups_emits_the_head_when_the_call_completes():
    events = drive(json.dumps({"chat_answer": "Hi", "title": "Deadbot", "lead": None, "groups": []}), 3)
    assert [event.type for event in events] == ["page_head"]
    assert events[0].payload == {"title": "Deadbot", "lead": None}


def test_a_retried_call_resets_the_draft():
    streamer = PlanStreamer(fake_resolve)
    first = streamer.feed(chunk('{"chat_answer": "x", "title": "First", "groups": [{"presentation": "collection", "items": [', name="finish_response"))
    assert [event.type for event in first] == ["page_head", "group_open"]
    second = streamer.feed(chunk('{"chat_answer": "y", "title": "Second", "groups": []}', name="finish_response", call_id="f2", index=1))
    assert [event.type for event in second] == ["page_reset", "page_head"]
    assert second[1].payload["title"] == "Second"


def test_malformed_json_disables_events_without_raising():
    streamer = PlanStreamer(fake_resolve)
    events = streamer.feed(chunk('{"chat_answer": "x", "groups": ]]]', name="finish_response"))
    assert events == []
    assert streamer.disabled is True
    assert streamer.feed(chunk('{"title": "later"}')) == []


def test_chunks_from_other_tool_calls_are_ignored():
    streamer = PlanStreamer(fake_resolve)
    streamer.feed(chunk('{"query": "x"}', name="search_entities", call_id="s1", index=0))
    events = streamer.feed(chunk('{"chat_answer": "x", "title": "T", "groups": []}', name="finish_response", call_id="f1", index=1))
    assert [event.type for event in events] == ["page_head"]


def test_invalid_items_are_skipped_and_judgments_are_truncated_to_criteria():
    plan = {"chat_answer": "x", "title": "T", "groups": [{"presentation": "comparison", "criteria": ["A"], "items": [
        {"type": "not_a_block"},
        {"type": "show_unit", "show_id": "gd-1972-08-27", "judgments": ["one", "two"]},
    ]}]}

    class Block:
        def __init__(self, judgments):
            self.judgments = judgments
        def model_copy(self, update):
            return Block(update["judgments"])
        def model_dump(self, mode):
            return {"judgments": self.judgments}

    streamer = PlanStreamer(lambda items: [Block(list(items[0].judgments))])
    events = streamer.feed(chunk(json.dumps(plan), name="finish_response"))
    blocks = [event for event in events if event.type == "block"]
    assert len(blocks) == 1
    assert blocks[0].payload["block"] == {"judgments": ["one"]}
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/test_plan_stream.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.plan_stream'`.

- [ ] **Step 3: Write the scanner**

```python
# deadbot/plan_stream.py
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
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import TypeAdapter, ValidationError

from deadbot.finish import FINISH_TOOL_NAME, BodyItem

logger = logging.getLogger(__name__)

_ITEM_ADAPTER = TypeAdapter(BodyItem)


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

    def __init__(self, resolve: Callable[[list[Any]], list[Any]]) -> None:
        self._resolve = resolve
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

    def _group_payload(self, index: int) -> dict[str, Any]:
        group = self._group(index)
        return {
            "index": index,
            "title": group.get("title"),
            "lead": group.get("lead"),
            "presentation": group.get("presentation") or "collection",
            "criteria": list(group.get("criteria") or []),
        }

    def _emit_head(self) -> list[PlanEvent]:
        if self._head_sent:
            return []
        self._head_sent = True
        return [PlanEvent("page_head", {"title": self._title or "", "lead": self._lead})]

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
            events.extend(self._item_closed(path[1], raw))
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

    def _item_closed(self, group_index: int, raw: str) -> list[PlanEvent]:
        try:
            item = _ITEM_ADAPTER.validate_python(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as error:
            logger.info("Skipped a streamed item that did not validate: %s", error)
            return []
        criteria = self._group(group_index).get("criteria")
        events: list[PlanEvent] = []
        for block in self._resolve([item]):
            if criteria is not None and hasattr(block, "judgments") and hasattr(block, "model_copy"):
                block = block.model_copy(update={"judgments": list(block.judgments)[: len(criteria)]})
            payload = block.model_dump(mode="json") if hasattr(block, "model_dump") else block
            events.append(PlanEvent("block", {"group_index": group_index, "block": payload}))
        return events
```

Note on the retry test: after `page_reset`, the new call's text starts fresh, and `_scan` runs on it in the same `feed`, so `page_head` for the second call follows `page_reset` in one batch.

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/test_plan_stream.py -q`
Expected: 7 passed. If `test_one_character_at_a_time_gives_identical_events` fails, the bug is in value-start or index tracking; compare event payloads to find the first divergence.

- [ ] **Step 5: Commit**

```bash
git add deadbot/plan_stream.py tests/test_plan_stream.py
git commit -m "Scan the streamed plan into page events"
```

---

### Task 2: Stream page events from the API

**Files:**
- Modify: `deadbot/api.py` (`_stream_events`)
- Test: `tests/test_experience.py`

**Interfaces:**
- Consumes: `PlanStreamer`, `PlanEvent` from Task 1; `finish.resolve_items`, `finish.grounded_context`, `composition._tool_payloads`, `composition._latest_turn`.
- Produces: NDJSON lines `{"type": "page_head", "title", "lead"}`, `{"type": "group_open", ...}`, `{"type": "block", "group_index", "block"}`, `{"type": "group_close", ...}`, `{"type": "page_reset"}` between `answer` events and `response`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experience.py`, next to the existing streaming tests. It reuses `AnswerStreamingFakeAgent`'s shape but with a plan that has a group; look at that class and write a sibling:

```python
class PlanStreamingFakeAgent(FakeAgent):
    """Streams a complete finish_response plan with one group in fragments, after a tool step."""

    def __init__(self, messages, plan):
        super().__init__(messages)
        self.plan_text = json.dumps(plan)

    def stream(self, payload, config, stream_mode="values"):
        self.calls.append((payload, config))
        yield ("values", {"messages": self.messages[:3]})  # human, tool-calling ai, tool result
        size = 7
        for offset in range(0, len(self.plan_text), size):
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "finish_response" if offset == 0 else None, "args": self.plan_text[offset : offset + size], "id": "f1", "index": 0, "type": "tool_call_chunk"}],
            )
            yield ("messages", (chunk, {}))
        yield ("values", {"messages": self.messages})


def test_streaming_endpoint_builds_the_page_progressively_then_delivers_the_response():
    store = CanonicalStore()
    show_payload = store.show_context(store.resolve_show("1972-08-27"))
    plan = {
        "chat_answer": "Veneta opened with Promised Land.",
        "title": "Veneta, 1972",
        "lead": None,
        "groups": [{"title": "The show", "presentation": "collection", "items": [
            {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "visible_facets": ["setlist"]},
            {"type": "editorial", "presentation": "narrative", "paragraphs": ["A benefit in the heat."], "items": []},
        ]}],
    }
    messages = [
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps(show_payload), tool_call_id="t1", name="get_show"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ]
    client = TestClient(create_app(settings=Settings(), store=store, agent=PlanStreamingFakeAgent(messages, plan)))
    events = _ndjson(client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "b1"}).text)
    types = [event["type"] for event in events]
    last_answer = max(index for index, event in enumerate(events) if event["type"] == "answer")
    assert types.index("page_head") > last_answer
    assert types[types.index("page_head") :] == ["page_head", "group_open", "block", "block", "group_close", "response"]
    head = events[types.index("page_head")]
    assert head["title"] == "Veneta, 1972" and head["lead"] is None
    streamed_blocks = [event["block"] for event in events if event["type"] == "block"]
    final = events[-1]["response"]
    assert [block["type"] for block in streamed_blocks] == [block["type"] for block in final["blocks"]] == ["show_unit", "editorial"]
    assert streamed_blocks[0]["show_id"] == final["blocks"][0]["show_id"] == "gd-1972-08-27"
    assert all(event["group_index"] == 0 for event in events if event["type"] == "block")


def test_streaming_endpoint_sends_no_page_events_for_a_cached_answer():
    # Reuse the existing cached-answer arrangement in this file if one exists; otherwise ask twice with a fresh
    # thread and assert the second stream's event types are exactly ["status", "response"].
    ...
```

Replace the `...` in the second test with a concrete arrangement based on how `_cached`/`_remember` are exercised elsewhere in this test file (search for "Found a recent answer"); if no such test exists, drive two identical fresh questions through `PlanStreamingFakeAgent` and assert the second stream's types are `["status", "response"]`.

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/test_experience.py -q -k "progressively or cached_answer"`
Expected: FAIL (no `page_head` in the stream).

- [ ] **Step 3: Wire `_stream_events`**

In `deadbot/api.py` import `from deadbot import composition, finish` (if not already) and `from deadbot.plan_stream import PlanStreamer`. Inside the `if callable(stream):` branch, next to `answer_accumulator = AnswerAccumulator()`, add `plan_streamer: PlanStreamer | None = None`. Replace the `if mode == "messages":` body with:

```python
                    if mode == "messages":
                        message_chunk = chunk_payload[0] if isinstance(chunk_payload, tuple) else chunk_payload
                        answer_text = answer_accumulator.feed(message_chunk)
                        if answer_text:
                            yield line({"type": "answer", "text": answer_text})
                        if answer_accumulator.complete and not composing_page_announced:
                            composing_page_announced = True
                            yield line({"type": "status", "text": "Composing the page"})
                        if plan_streamer is None and _names_finish_call(message_chunk):
                            # Research is done by the time the plan starts; ground once.
                            payloads = composition._tool_payloads(composition._latest_turn(messages))
                            grounded = finish.grounded_context(payloads)
                            plan_streamer = PlanStreamer(
                                lambda items, _g=grounded, _p=payloads: finish.resolve_items(items, _g, _p, store)[0]
                            )
                        if plan_streamer is not None:
                            with query_cache_scope(cache):
                                page_events = plan_streamer.feed(message_chunk)
                            for event in page_events:
                                if event.type == "page_reset":
                                    answer_accumulator = AnswerAccumulator()
                                    composing_page_announced = False
                                yield line({"type": event.type, **event.payload})
                        continue
```

where `store` is the same store `_respond` resolves against (find how `_respond`/`build_experience_response` receives it in this file and use that name), and add a module-level helper:

```python
def _names_finish_call(message_chunk: Any) -> bool:
    return any(chunk.get("name") == FINISH_TOOL_NAME for chunk in getattr(message_chunk, "tool_call_chunks", None) or [])
```

importing `FINISH_TOOL_NAME` from `deadbot.finish`. Note: on `page_reset` the fresh `AnswerAccumulator` must still receive the current chunk's answer text; feed it the same `message_chunk` immediately after creating it and yield any returned answer text.

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/test_experience.py tests/test_plan_stream.py tests/test_answer_stream.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deadbot/api.py tests/test_experience.py
git commit -m "Stream page head, groups and hydrated blocks while the plan is written"
```

---

### Task 3: Draft page in the browser

**Files:**
- Modify: `web/src/App.tsx`, `web/src/styles.css`
- Test: `npm run build --prefix web`; manual review via Task 4's replay fixture

**Interfaces:**
- Produces in `App.tsx`:
  - `type PageEvent = { type: "page_head"; title: string; lead: string | null } | { type: "group_open" | "group_close"; index: number; title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[] } | { type: "block"; group_index: number; block: ExperienceBlock } | { type: "page_reset" }`
  - `type StreamEvent = { type: "status"; text: string } | { type: "answer"; text: string } | { type: "response"; response: ExperienceResponse } | { type: "error"; detail?: string } | PageEvent`
  - `type RenderGroup = { title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[]; blocks: ExperienceBlock[] }`
  - `type Draft = { title: string; lead: string | null; groups: RenderGroup[] }`
  - `function applyPageEvent(draft: Draft | null, event: PageEvent): Draft | null` (pure)
  - `function ComposedPage({ title, lead, groups, sources, composing, onFollowUp })` renders what the response branch renders today, for either a response or a draft
  - `askStreaming(body, handlers: { onStatus; onAnswer; onPage })`

- [ ] **Step 1: Pure draft reducer**

Add near the other helpers:

```tsx
type RenderGroup = { title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[]; blocks: ExperienceBlock[] };
type Draft = { title: string; lead: string | null; groups: RenderGroup[] };

type PageEvent =
  | { type: "page_head"; title: string; lead: string | null }
  | { type: "group_open" | "group_close"; index: number; title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[] }
  | { type: "block"; group_index: number; block: ExperienceBlock }
  | { type: "page_reset" };

function emptyGroup(): RenderGroup {
  return { title: null, lead: null, presentation: "collection", criteria: [], blocks: [] };
}

// The draft page grows in reading order. A block for a group we have not
// heard of yet gets a provisional group; group_close fills the heading in.
function applyPageEvent(draft: Draft | null, event: PageEvent): Draft | null {
  if (event.type === "page_reset") return null;
  if (event.type === "page_head") return { title: event.title, lead: event.lead, groups: draft?.groups ?? [] };
  const current: Draft = draft ?? { title: "", lead: null, groups: [] };
  const groups = current.groups.slice();
  const index = event.type === "block" ? event.group_index : event.index;
  while (groups.length <= index) groups.push(emptyGroup());
  if (event.type === "block") {
    groups[index] = { ...groups[index], blocks: [...groups[index].blocks, event.block] };
  } else {
    groups[index] = { ...groups[index], title: event.title, lead: event.lead, presentation: event.presentation, criteria: event.criteria };
  }
  return { ...current, groups };
}

function groupsOfResponse(response: ExperienceResponse): RenderGroup[] {
  return response.groups.map((group) => ({
    title: group.title ?? null,
    lead: group.lead ?? null,
    presentation: group.presentation,
    criteria: group.criteria ?? [],
    blocks: group.block_indexes.map((index) => response.blocks[index]).filter((block): block is ExperienceBlock => Boolean(block)),
  }));
}
```

- [ ] **Step 2: Extract `ComposedPage`**

Move the JSX currently inside the `response ? (<> ... </>)` branch of the content pane into:

```tsx
function ComposedPage({ title, lead, groups, sources, composing, onFollowUp }: {
  title: string;
  lead: string | null;
  groups: RenderGroup[];
  sources: SourceReference[];
  composing: boolean;
  onFollowUp: (prompt: string) => void;
}) {
  const unitCount = groups.reduce((count, group) => count + group.blocks.filter(isUnit).length, 0);
  return (
    <>
      <div className="content-heading">
        <h1 id="answer-title" tabIndex={-1}>{title}</h1>
      </div>
      {lead && <p className="answer-lead">{renderInline(lead)}</p>}
      {groups.map((group, groupIndex) => (
        <section className={`experience-group group-${group.presentation}`} key={`${group.presentation}-${groupIndex}-${group.title ?? ""}`}>
          {/* existing header JSX, using group.title / group.lead / group.presentation */}
          <div className="block-grid group-blocks">
            {chunkMentions(group.blocks).map((entry, position) => /* existing mention/Block JSX, with criteria={group.presentation === "comparison" ? group.criteria : []} and soleUnit={unitCount === 1} */)}
          </div>
        </section>
      ))}
      {composing && <p className="composing-note" aria-live="polite">Composing the page…</p>}
      {!composing && sources.length > 0 && (/* existing sources footer */)}
    </>
  );
}
```

Copy the existing header and block JSX verbatim into the placeholders; the only changes are that blocks come from `group.blocks` and `unitCount` is computed here.

- [ ] **Step 3: Draft state and stream handling**

In `App`: add `const [draft, setDraft] = useState<Draft | null>(null);`. In `askQuestion` reset `setDraft(null)` alongside the other resets at the start and in `finally`. Change `askStreaming` to take `handlers: { onStatus: (text: string) => void; onAnswer: (text: string) => void; onPage: (event: PageEvent) => void }` and route `page_head`, `group_open`, `group_close`, `block`, `page_reset` events to `onPage`. In `askQuestion` pass `onPage: (event) => setDraft((current) => applyPageEvent(current, event))`.

Type the parsed line as `StreamEvent` (union above) instead of the current ad hoc shape.

- [ ] **Step 4: Content pane**

Replace the pane's ternary with:

```tsx
{loading && draft ? (
  <ComposedPage title={draft.title || pendingQuestion || ""} lead={draft.lead} groups={draft.groups} sources={[]} composing onFollowUp={chooseFollowUp} />
) : loading ? (
  /* existing working panel */
) : response ? (
  <ComposedPage title={response.title} lead={response.body_lead ?? null} groups={groupsOfResponse(response)} sources={response.sources} composing={false} onFollowUp={chooseFollowUp} />
) : (
  /* existing empty state */
)}
```

Ask chips inside a draft call `chooseFollowUp`, which is already guarded by `if (!trimmed || loading) return;`, so a click during composition is ignored.

- [ ] **Step 5: CSS**

Append: `.composing-note { margin: var(--space-unit) 0 0; color: #7f9582; font-size: 0.86rem; } .composing-note::before { content: "▸ "; color: #e7b94e; }`

- [ ] **Step 6: Build and commit**

Run: `npm run build --prefix web`
Expected: PASS.

```bash
git add web/src/App.tsx web/src/styles.css
git commit -m "Build the page from streamed events before the final response arrives"
```

---

### Task 4: Replay fixture for progressive rendering

**Files:**
- Modify: `web/src/visual-fixture-loader.ts`, `web/src/visual-fixtures.ts`, `web/src/App.tsx`
- Test: `npm run build --prefix web`; browser review at 1440px and 375px of `?stream=legacy` and `?stream=views`

**Interfaces:**
- Produces: `requestedStreamFixture: string | null` and `loadRequestedStreamEvents(): Promise<StreamEvent[] | null>` in the loader; `streamEventsFor(name): StreamEvent[]` in `visual-fixtures.ts`; `App` replays them with delays through the same handlers `askStreaming` uses.

- [ ] **Step 1: Derive events from a fixture**

In `web/src/visual-fixtures.ts` add (export the `StreamEvent`/`PageEvent` types from `App.tsx` to a small `web/src/stream-events.ts` module first, and import them in both files, so the fixture file does not import the App):

```ts
export function streamEventsFor(name: VisualFixtureName): StreamEvent[] {
  const response = fixtures[name];
  const events: StreamEvent[] = [{ type: "status", text: "Looking through the library" }, { type: "status", text: "Reading the show" }];
  const words = response.answer.split(" ");
  words.forEach((_, index) => events.push({ type: "answer", text: words.slice(0, index + 1).join(" ") }));
  events.push({ type: "status", text: "Composing the page" });
  events.push({ type: "page_head", title: response.title, lead: response.body_lead ?? null });
  response.groups.forEach((group, index) => {
    const meta = { index, title: group.title ?? null, lead: group.lead ?? null, presentation: group.presentation, criteria: group.criteria ?? [] };
    events.push({ type: "group_open", ...meta });
    group.block_indexes.forEach((blockIndex) => {
      const block = response.blocks[blockIndex];
      if (block) events.push({ type: "block", group_index: index, block });
    });
    events.push({ type: "group_close", ...meta });
  });
  events.push({ type: "response", response });
  return events;
}
```

- [ ] **Step 2: Loader**

In `web/src/visual-fixture-loader.ts` add `requestedStreamFixture` reading `?stream=` in DEV, and `loadRequestedStreamEvents()` that dynamically imports `streamEventsFor` and returns the events, mirroring the existing functions.

- [ ] **Step 3: Replay in App**

Refactor the body of `askStreaming` so line handling goes through a `dispatchStreamEvent(event: StreamEvent, handlers)` function used by both the network reader and the replay. Add an effect: when `requestedStreamFixture` is set, mark `loading` true, set `pendingQuestion` to the fixture's first user turn, and replay events sequentially with `await delay(ms)` between them: 40ms per `answer`, 600ms before each `block`, 300ms otherwise; on `response` set the response and clear the pending state exactly as `askQuestion`'s `finally` does. Guard everything with `import.meta.env.DEV`.

- [ ] **Step 4: Build and review**

Run: `npm run build --prefix web`; then in Vite dev open `?stream=legacy` and `?stream=views` at 1440px and 375px. Expected: chat answer streams, working panel shows the two statuses, title appears, groups and blocks appear one by one with the "Composing the page…" line, then the final page replaces the draft with no visible jump and the sources footer appears.

- [ ] **Step 5: Commit**

```bash
git add web/src/stream-events.ts web/src/visual-fixture-loader.ts web/src/visual-fixtures.ts web/src/App.tsx
git commit -m "Replay a fixture as a progressive stream for review"
```

---

### Task 5: Measure and document

**Files:**
- Create: `scripts/trace_stream.py`
- Modify: `docs/UX-NEXT-STEPS.md`, `docs/experience-architecture.md` (streaming paragraph under "API and session boundaries")
- Test: `$PY -m pytest tests/test_plan_stream.py tests/test_experience.py tests/test_answer_stream.py -q`; `npm run build --prefix web`

- [ ] **Step 1: Trace script**

```python
# scripts/trace_stream.py
"""Time the progressive stream for one question against a running API.

Usage: PY scripts/trace_stream.py "What shows did Branford play on?" [base_url]
Prints seconds from request start to: first answer text, answer complete
("Composing the page" status), first block, last block, response.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request


def trace(question: str, base_url: str = "http://127.0.0.1:8000") -> dict[str, float | None]:
    body = json.dumps({"question": question, "thread_id": f"trace-{int(time.time())}"}).encode()
    request = urllib.request.Request(f"{base_url}/api/experience/stream", data=body, headers={"Content-Type": "application/json"})
    start = time.monotonic()
    marks: dict[str, float | None] = {"first_answer": None, "answer_complete": None, "first_block": None, "last_block": None, "response": None}
    with urllib.request.urlopen(request) as stream:
        for raw in stream:
            event = json.loads(raw)
            now = time.monotonic() - start
            kind = event.get("type")
            if kind == "answer" and marks["first_answer"] is None:
                marks["first_answer"] = now
            elif kind == "status" and event.get("text") == "Composing the page":
                marks["answer_complete"] = now
            elif kind == "block":
                marks["first_block"] = marks["first_block"] if marks["first_block"] is not None else now
                marks["last_block"] = now
            elif kind == "response":
                marks["response"] = now
    return marks


if __name__ == "__main__":
    question = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    for name, seconds in trace(question, base).items():
        print(f"{name}: {'n/a' if seconds is None else f'{seconds:.1f}s'}")
```

- [ ] **Step 2: Run the measurement if the environment allows**

If `/Users/markdavenport/Development/DeadBot/.env` provides `OPENAI_API_KEY` and `DEADBOT_DATABASE_URL`, start the API from the worktree in a subshell that sources that file (`set -a; source ...; set +a; $PY -m uvicorn deadbot.api:app --port 8000`), run the script for the three questions (Branford; Franklin's Tower best versions; American Beauty live legacy), stop the server, and record the five marks per question in a new table under "## Measurements" in `docs/UX-NEXT-STEPS.md`. Never print or store secrets. If the environment lacks either variable or a run fails, write "not run" with the reason. Do not invent numbers.

- [ ] **Step 3: Docs**

In `docs/experience-architecture.md`, replace the sentence beginning "Streaming is a follow-on capability" with a short paragraph describing the actual events: statuses per tool call, the chat answer streamed from the plan, then page head, groups and hydrated blocks as the plan is written, then the final response. In `docs/UX-NEXT-STEPS.md`, add a "## Batch: progressive page streaming" section (under 20 lines) and remove progressive streaming from the remaining-work list.

- [ ] **Step 4: Validate and commit**

Run the test and build commands above. Expected: pass.

```bash
git add scripts/trace_stream.py docs/UX-NEXT-STEPS.md docs/experience-architecture.md
git commit -m "Trace the progressive stream and record the results"
```
