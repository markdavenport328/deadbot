# Single Agent Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the researcher-plus-editor pipeline with one agent loop in which the model researches with tools and delivers the finished experience by calling a `finish_response` tool whose arguments are the validated plan.

**Architecture:** The LangGraph loop keeps its read-only tools and gains one more, `finish_response`. Its argument schema (`FinishPlan`) lets the model write the chat answer, title, lead, and a body made of model-authored editorial blocks (now with outbound links) mixed with library components referenced by canonical ID. Server code resolves those references against the store, drops anything the model did not retrieve this turn, and renders the same validated `ExperienceResponse` the browser already understands. The second model call (`deadbot/composer.py`) and the payload-projection loop in `compose_experience_response` are removed.

**Tech Stack:** Python 3.11+, LangGraph, LangChain tools, Pydantic v2, FastAPI, React + TypeScript (Vite), pytest.

**Spec:** `docs/ux-audit-2026-09-01.md` (sections "Architecture: one loop or two" and "Recommended order of work", items 1 and 2), read with `AGENTS.md` and `docs/experience-brief.md`.

## Global Constraints

- Deterministic code is limited to transport and structural integrity: parse the plan, resolve references to retrieved records, render supported blocks. It never vetoes an editorial choice or substitutes a database dump (`AGENTS.md`).
- Prompts contain goals and guidance, not rules or checklists.
- The browser schema in `deadbot/experience.py` stays the only thing the client renders; the model never produces HTML, iframe markup, or arbitrary URLs. A link is kept only if its URL appeared in this turn's tool output.
- A malformed reference or ungrounded link is dropped, not fatal. Only a missing plan is a diagnosable failure, logged with a reason.
- After any change to `deadbot/experience.py` run `python scripts/export_openapi.py` then `npm run gen:types --prefix web`; CI fails on drift.
- Tests run with the repository venv: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest`. Importing `deadbot.api` requires `DEADBOT_DATABASE_URL`; tests that only touch the store use `CanonicalStore()` (CSV) directly.
- Do not commit on `main`. Work on the current feature branch. Commit after each task.

---

## File structure

| File | Responsibility |
| --- | --- |
| `deadbot/experience.py` (modify) | Browser schema. Gains `EditorialLink`, `EditorialItem.link`. Loses the lazy re-export block for the removed projection loop. |
| `deadbot/finish.py` (create) | Model-facing `FinishPlan` and reference models; `FINISH_TOOL_NAME`; `build_finish_tool()`; `GroundedContext` collection from tool payloads; `resolve_body()`; `build_experience_response()`; fallback when no plan was delivered. |
| `deadbot/composition.py` (modify) | Keep the per-block builders (`_show_setlist`, `_recording_list`, `_performance_spine`, …) as pure functions. Delete `compose_experience_response` and its helpers that only served it. |
| `deadbot/graph.py` (modify) | One merged persona prompt; `finish_response` bound with the other tools; routing ends the turn after the finish tool runs. |
| `deadbot/api.py` (modify) | Call `build_experience_response`; remove composer wiring. |
| `deadbot/cli.py` (modify) | `chat` prints the plan's chat answer. |
| `deadbot/evaluations.py` (modify) | `model_evaluate_suite` reports the plan's chat answer. |
| `deadbot/composer.py` (delete) | Second model call, removed. |
| `web/src/App.tsx`, `web/src/styles.css` (modify) | Inline markdown links in chat, lead, and editorial text; render `EditorialItem.link`. |
| `tests/test_finish.py` (create) | Plan extraction, grounding, resolution, fallback. |
| `tests/test_experience.py` (modify) | Remove composer tests; keep schema, embed, API tests; API tests use a finish tool call. |
| `tests/test_graph.py` (create) | Routing and tool surface of the merged loop. |
| Docs (modify) | `AGENTS.md`, `docs/experience-architecture.md`, `docs/agent-harness.md`, `docs/experience-brief.md`, `docs/development-plan.md`. |

---

### Task 1: Editorial links in the browser schema

**Files:**
- Modify: `deadbot/experience.py:344-360`
- Test: `tests/test_experience.py`

**Interfaces:**
- Produces: `EditorialLink(url: str, label: str)`; `EditorialItem.link: EditorialLink | None = None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_experience.py`:

```python
def test_editorial_items_can_carry_an_outbound_link():
    item = experience.EditorialItem(
        marker="1972-08-27",
        title="Veneta",
        value=None,
        detail="The Sunshine Daydream show.",
        follow_up=None,
        link=experience.EditorialLink(url="https://archive.org/details/gd1972-08-27.sbd.latvala-eaton-lutch-dankseed.4682.shnf", label="Listen on Archive.org"),
    )
    assert item.link.label == "Listen on Archive.org"
    legacy = experience.EditorialItem(marker=None, title="Appearances", value="5", detail=None, follow_up=None)
    assert legacy.link is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_experience.py::test_editorial_items_can_carry_an_outbound_link -v`
Expected: FAIL with `AttributeError: module 'deadbot.experience' has no attribute 'EditorialLink'`

- [ ] **Step 3: Add the models**

In `deadbot/experience.py`, replace the `EditorialItem` class with:

```python
class EditorialLink(ExperienceModel):
    """An outbound link the model attaches to something it wrote.

    The server keeps a link only when its URL appeared in material the tools
    returned during the same turn; anything else is dropped before rendering.
    """

    url: str
    label: str


class EditorialItem(ExperienceModel):
    marker: str | None
    title: str
    value: str | None
    detail: str | None
    follow_up: str | None
    link: EditorialLink | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_experience.py::test_editorial_items_can_carry_an_outbound_link -v`
Expected: PASS

- [ ] **Step 5: Regenerate the browser contract and commit**

```bash
/Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py
npm run gen:types --prefix web
git add deadbot/experience.py tests/test_experience.py web/openapi.json web/src/generated/api.ts
git commit -m "feat: let editorial items carry an outbound link"
```

---

### Task 2: Grounded context from tool payloads

**Files:**
- Create: `deadbot/finish.py`
- Test: `tests/test_finish.py`

**Interfaces:**
- Produces: `GroundedContext(ids: frozenset[str], urls: frozenset[str])`; `grounded_context(payloads: list[dict]) -> GroundedContext`; `keep_grounded_links(text: str, urls: frozenset[str]) -> str`.
- Consumes: `deadbot.composition._tool_payloads(messages)` and `_latest_turn(messages)` (both already exist).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_finish.py`:

```python
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import finish
from deadbot.data import CanonicalStore


def tool_message(payload, name="get_show"):
    return ToolMessage(content=json.dumps(payload), tool_call_id="call-1", name=name)


def test_grounded_context_collects_ids_and_urls_from_tool_payloads():
    payloads = [
        {"show": {"show_id": "gd-1972-08-27"}, "performances": [{"performance_id": "gd-1972-08-27-sugaree"}]},
        {"matches": [{"entity_type": "song", "id": "song-sugaree", "label": "Sugaree"}]},
        {"resources": [{"resource_id": "resource-1", "source_url": "https://www.dead.net/song/sugaree"}]},
        {"recordings": [{"recording_id": "recording-1", "archive_identifier": "gd1972-08-27.sbd.4682.shnf"}]},
    ]
    grounded = finish.grounded_context(payloads)
    assert {"gd-1972-08-27", "gd-1972-08-27-sugaree", "song-sugaree", "resource-1", "recording-1", "gd1972-08-27.sbd.4682.shnf"} <= grounded.ids
    assert "https://www.dead.net/song/sugaree" in grounded.urls


def test_keep_grounded_links_strips_urls_the_tools_did_not_return():
    urls = frozenset({"https://archive.org/details/gd1972-08-27"})
    text = "Hear it on [Archive.org](https://archive.org/details/gd1972-08-27) or [elsewhere](https://example.com/x)."
    assert finish.keep_grounded_links(text, urls) == "Hear it on [Archive.org](https://archive.org/details/gd1972-08-27) or elsewhere."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.finish'`

- [ ] **Step 3: Create the module with grounding helpers**

Create `deadbot/finish.py`:

```python
"""Turn the agent's final ``finish_response`` tool call into a browser response.

The model does its research with read-only tools and then delivers the
experience by calling ``finish_response`` with a :class:`FinishPlan`. This
module owns the model-facing plan schema, collects what the tools actually
returned this turn, resolves the plan's references against the store, and
produces the validated :class:`ExperienceResponse`. Deterministic code here is
transport and structural integrity only: it never chooses content and never
vetoes an editorial decision. An ungrounded reference or link is dropped; a
missing plan is a logged, diagnosable failure.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from deadbot.composition import _latest_turn, _tool_payloads


logger = logging.getLogger(__name__)

FINISH_TOOL_NAME = "finish_response"

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


@dataclass(frozen=True)
class GroundedContext:
    """Identifiers and URLs the tools returned during the current turn."""

    ids: frozenset[str]
    urls: frozenset[str]


def _walk(value: Any, ids: set[str], urls: set[str], key: str | None = None) -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            _walk(child, ids, urls, child_key)
    elif isinstance(value, list):
        for child in value:
            _walk(child, ids, urls, key)
    elif isinstance(value, str):
        if value.startswith(("http://", "https://")):
            urls.add(value)
        elif key and (key == "id" or key.endswith("_id") or key == "archive_identifier" or key == "key_signature"):
            ids.add(value)


def grounded_context(payloads: list[dict[str, Any]]) -> GroundedContext:
    """Collect every identifier and URL present in this turn's tool output."""

    ids: set[str] = set()
    urls: set[str] = set()
    for payload in payloads:
        _walk(payload, ids, urls)
    return GroundedContext(ids=frozenset(ids), urls=frozenset(urls))


def keep_grounded_links(text: str, urls: frozenset[str]) -> str:
    """Keep markdown links whose URL the tools returned; unwrap the others to plain text."""

    def replace(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        return match.group(0) if url in urls else label

    return _MARKDOWN_LINK.sub(replace, text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add deadbot/finish.py tests/test_finish.py
git commit -m "feat: collect grounded ids and urls from the turn's tool output"
```

---

### Task 3: The finish plan and its reference models

**Files:**
- Modify: `deadbot/finish.py`
- Test: `tests/test_finish.py`

**Interfaces:**
- Produces: `FinishPlan(chat_answer, title, lead, mode, body: list[BodyItem])` and the reference models `ShowSetlistRef`, `RecordingListRef`, `PerformerListRef`, `EquipmentListRef`, `PerformanceSpineRef`, `ComparisonStripRef`, `PerformanceListRef`, `PerformanceExtremesRef`, `SongOverviewRef`, `GuestAppearancesRef`, `ShowSelectionRef`, `ArrangementRef`, `ArrangementSearchRef`, `MediaLinkRef`, `ResourceListRef`; `build_finish_tool() -> BaseTool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finish.py`:

```python
def test_finish_plan_accepts_editorial_blocks_and_library_references():
    plan = finish.FinishPlan.model_validate(
        {
            "chat_answer": "Sugaree opened the second set.",
            "title": "Sugaree at Veneta",
            "lead": "A relaxed early version.",
            "mode": "performance",
            "body": [
                {
                    "type": "editorial",
                    "presentation": "narrative",
                    "eyebrow": None,
                    "title": "Why this one",
                    "paragraphs": ["Garcia stretches the solo."],
                    "items": [],
                },
                {"type": "show_setlist", "show_id": "gd-1972-08-27", "title": "The whole night"},
                {"type": "recording_list", "show_id": "gd-1972-08-27", "recording_ids": ["recording-gd-1972-08-27-sbd-4682"], "title": None},
            ],
        }
    )
    assert [item.type for item in plan.body] == ["editorial", "show_setlist", "recording_list"]
    assert plan.body[1].title == "The whole night"


def test_finish_tool_uses_the_plan_schema_and_confirms_delivery():
    tool = finish.build_finish_tool()
    assert tool.name == finish.FINISH_TOOL_NAME
    assert tool.args_schema is finish.FinishPlan
    assert "finished" in tool.description.casefold() or "deliver" in tool.description.casefold()
    result = tool.invoke(
        {"chat_answer": "Hi", "title": "Deadbot", "lead": None, "mode": "quick_fact", "body": []}
    )
    assert "delivered" in result.casefold()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: FAIL with `AttributeError: module 'deadbot.finish' has no attribute 'FinishPlan'`

- [ ] **Step 3: Add the plan schema and tool**

Add to `deadbot/finish.py` after the imports (keep the earlier code):

```python
from typing import Annotated, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from deadbot.experience import EditorialBlock, ExperienceMode


class _Ref(BaseModel):
    """A library component referenced by canonical ID, optionally retitled."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = None


class ShowSetlistRef(_Ref):
    type: Literal["show_setlist"]
    show_id: str


class RecordingListRef(_Ref):
    type: Literal["recording_list"]
    show_id: str
    recording_ids: list[str] = Field(default_factory=list, max_length=8)


class PerformerListRef(_Ref):
    type: Literal["performer_list"]
    show_id: str


class EquipmentListRef(_Ref):
    type: Literal["equipment_list"]
    show_id: str


class PerformanceSpineRef(_Ref):
    type: Literal["performance_spine"]
    performance_id: str


class ComparisonStripRef(_Ref):
    type: Literal["comparison_strip"]
    song_id: str


class PerformanceListRef(_Ref):
    type: Literal["performance_list"]
    song_id: str


class PerformanceExtremesRef(_Ref):
    type: Literal["performance_extremes"]
    song_id: str


class SongOverviewRef(_Ref):
    type: Literal["song_overview"]
    song_id: str


class GuestAppearancesRef(_Ref):
    type: Literal["guest_appearance_list"]
    person_id: str


class ShowSelectionRef(_Ref):
    type: Literal["show_selection"]
    selection_id: str


class ArrangementRef(_Ref):
    type: Literal["arrangement"]
    arrangement_id: str


class ArrangementSearchRef(_Ref):
    type: Literal["arrangement_search"]
    key_signature: str


class MediaLinkRef(_Ref):
    type: Literal["media_link"]
    url: str


class ResourceListRef(_Ref):
    type: Literal["resource_list"]
    resource_ids: list[str] = Field(min_length=1, max_length=8)


BodyItem = Annotated[
    EditorialBlock
    | ShowSetlistRef
    | RecordingListRef
    | PerformerListRef
    | EquipmentListRef
    | PerformanceSpineRef
    | ComparisonStripRef
    | PerformanceListRef
    | PerformanceExtremesRef
    | SongOverviewRef
    | GuestAppearancesRef
    | ShowSelectionRef
    | ArrangementRef
    | ArrangementSearchRef
    | MediaLinkRef
    | ResourceListRef,
    Field(discriminator="type"),
]


class FinishPlan(BaseModel):
    """The model's finished response: chat answer plus the main-body plan."""

    model_config = ConfigDict(extra="forbid")
    chat_answer: str = Field(
        description="The direct answer shown in the conversation. Short, specific, may use markdown links to URLs the tools returned."
    )
    title: str = Field(description="Main-body title.")
    lead: str | None = Field(default=None, description="One or two sentences that notice what matters. Markdown links allowed.")
    mode: ExperienceMode = Field(description="Overall shape of the response.")
    body: list[BodyItem] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "Reading order for the main body. Mix editorial blocks you write (narrative, fact_grid, timeline; items may carry a link or a follow_up question) "
            "with library components referenced by IDs you retrieved: show_setlist, recording_list, performer_list, equipment_list, performance_spine, "
            "comparison_strip, performance_list, performance_extremes, song_overview, guest_appearance_list, show_selection, arrangement, arrangement_search, "
            "media_link, resource_list. Give a component a title when the default would read like a database label."
        ),
    )


def _deliver(**_: Any) -> str:
    return "Response delivered to the visitor."


def build_finish_tool() -> BaseTool:
    """The one tool that ends a turn: its arguments are the finished response."""

    return StructuredTool.from_function(
        func=_deliver,
        name=FINISH_TOOL_NAME,
        description=(
            "Deliver the finished response to the visitor. Call this once, when your research is done. "
            "chat_answer is the crisp direct answer; the body is the rewarding part: your own narrative, fact grids or timelines "
            "mixed with library components referenced by the IDs you retrieved. Links you write are kept only if the URL came from a tool result."
        ),
        args_schema=FinishPlan,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add deadbot/finish.py tests/test_finish.py
git commit -m "feat: define the finish_response plan and tool"
```

---

### Task 4: Resolve references into validated blocks

**Files:**
- Modify: `deadbot/finish.py`
- Modify: `deadbot/composition.py` (keep builders; no behavior change in this task)
- Test: `tests/test_finish.py`

**Interfaces:**
- Consumes: `CanonicalStore.show_context(show)`, `song_context(song)`, `performance_context(performance_id)`, `resolve_show(id)`, `resolve_song(id)`, `one(table, id)`, `filtered_rows(table, **kw)`; builders in `deadbot/composition.py`: `_show_setlist(payload, store)`, `_show_performers(payload, store)`, `_show_equipment(payload)`, `_recording_list(payload, store)`, `_performance_spine(payload, store)`, `_comparison_strip(song, performances, store)`, `_performance_list(song, performances, store)`, `_performance_extremes(song, performances, store)`, `_guest_appearance_blocks(payload)`, `_show_selection_blocks(payload)`, `_arrangement_search_block(payload, store)`, `_media_block(link)`, `_resource_item(resource)`, `_resource_source(resource)`, `_research_resource(record)`.
- Produces: `resolve_body(plan: FinishPlan, grounded: GroundedContext, payloads: list[dict], store: CanonicalStore) -> tuple[list[ExperienceBlock], list[SourceReference]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finish.py`:

```python
def _veneta_payloads(store):
    show = store.resolve_show("1972-08-27")
    song = store.resolve_song("Sugaree")
    return [store.show_context(show), store.song_context(song)]


def test_resolve_body_builds_referenced_components_with_model_titles():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="Veneta",
        lead=None,
        mode="show",
        body=[
            finish.ShowSetlistRef(type="show_setlist", show_id="gd-1972-08-27", title="The whole night"),
            finish.RecordingListRef(type="recording_list", show_id="gd-1972-08-27", recording_ids=["recording-gd-1972-08-27-sbd-4682"]),
            finish.ComparisonStripRef(type="comparison_strip", song_id="song-sugaree"),
        ],
    )
    blocks, sources = finish.resolve_body(plan, grounded, payloads, store)
    assert [block.type for block in blocks] == ["show_setlist", "recording_list", "comparison_strip"]
    assert blocks[0].title == "The whole night"
    assert [item.recording_id for item in blocks[1].items] == ["recording-gd-1972-08-27-sbd-4682"]
    assert any(source.url and "archive.org" in source.url for source in sources)


def test_resolve_body_drops_references_the_tools_did_not_return():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        mode="show",
        body=[
            finish.ShowSetlistRef(type="show_setlist", show_id="gd-1977-05-08"),
            finish.MediaLinkRef(type="media_link", url="https://www.youtube.com/watch?v=notretrieved"),
            finish.ShowSetlistRef(type="show_setlist", show_id="gd-1972-08-27"),
        ],
    )
    blocks, _ = finish.resolve_body(plan, grounded, payloads, store)
    assert [block.type for block in blocks] == ["show_setlist"]
    assert blocks[0].show_id == "gd-1972-08-27"


def test_resolve_body_keeps_editorial_blocks_and_strips_ungrounded_links():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    good_url = next(url for url in grounded.urls if "archive.org" in url)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        mode="show",
        body=[
            {
                "type": "editorial",
                "presentation": "fact_grid",
                "eyebrow": None,
                "title": "Ways in",
                "paragraphs": [f"Start with the [soundboard]({good_url}) or [this](https://example.com/no)."],
                "items": [
                    {"marker": "SBD", "title": "Soundboard", "value": None, "detail": None, "follow_up": None, "link": {"url": good_url, "label": "Archive"}},
                    {"marker": "Bad", "title": "Nope", "value": None, "detail": None, "follow_up": None, "link": {"url": "https://example.com/no", "label": "x"}},
                ],
            }
        ],
    )
    blocks, _ = finish.resolve_body(plan, grounded, payloads, store)
    block = blocks[0]
    assert block.paragraphs[0] == f"Start with the [soundboard]({good_url}) or this."
    assert block.items[0].link is not None and block.items[1].link is None


def test_resolve_body_resolves_guest_appearances_from_the_turn_payload():
    store = CanonicalStore()
    from deadbot.tools import build_tools

    guest_tool = next(tool for tool in build_tools(store) if tool.name == "search_guest_musicians")
    payload = json.loads(guest_tool.invoke({"query": "Branford"}))
    person_id = payload["guests"][0]["person_id"]
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None, mode="musician",
        body=[finish.GuestAppearancesRef(type="guest_appearance_list", person_id=person_id)],
    )
    blocks, _ = finish.resolve_body(plan, grounded, [payload], store)
    assert blocks[0].type == "guest_appearance_list" and blocks[0].person_id == person_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: FAIL with `AttributeError: module 'deadbot.finish' has no attribute 'resolve_body'`

- [ ] **Step 3: Implement the resolvers**

Add to `deadbot/finish.py`:

```python
from deadbot import composition
from deadbot.data import CanonicalStore
from deadbot.experience import (
    EditorialBlock as _EditorialBlock,
    ExperienceBlock,
    RecordingListBlock,
    ResourceListBlock,
    SourceReference,
)


def _retitle(block: Any, title: str | None) -> Any:
    if title and hasattr(block, "title"):
        return block.model_copy(update={"title": title.strip()})
    return block


def _sanitize_editorial(block: _EditorialBlock, urls: frozenset[str]) -> _EditorialBlock:
    items = [
        item.model_copy(update={"link": item.link if item.link and item.link.url in urls else None})
        for item in block.items
    ]
    return block.model_copy(
        update={
            "paragraphs": [keep_grounded_links(paragraph, urls) for paragraph in block.paragraphs],
            "items": items,
        }
    )


def _find_in_payloads(payloads: list[dict[str, Any]], key: str, match_key: str, match_value: str) -> dict[str, Any] | None:
    for payload in payloads:
        for record in payload.get(key, []) if isinstance(payload.get(key), list) else []:
            if isinstance(record, dict) and record.get(match_key) == match_value:
                return record
    return None


def _resolve_reference(
    item: Any,
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> tuple[ExperienceBlock | None, list[SourceReference]]:
    sources: list[SourceReference] = []
    kind = item.type

    if kind in {"show_setlist", "recording_list", "performer_list", "equipment_list"}:
        if item.show_id not in grounded.ids:
            return None, []
        show = store.resolve_show(item.show_id)
        if not show:
            return None, []
        payload = store.show_context(show)
        if kind == "show_setlist":
            return _retitle(composition._show_setlist(payload, store), item.title), []
        if kind == "performer_list":
            return _retitle(composition._show_performers(payload, store), item.title), []
        if kind == "equipment_list":
            block = composition._show_equipment(payload)
            if block:
                sources = [
                    SourceReference(source_id=entry.source_id, kind="contextual_resource", label="Jerry Garcia Instrument History", url=entry.source_url)
                    for entry in block.items
                ]
            return _retitle(block, item.title), sources
        if item.recording_ids:
            # The model chose specific recordings (for example a source it saw
            # rated highly). Build from those rows rather than the default
            # first-eight projection, so its choice is not silently truncated.
            wanted = {recording_id for recording_id in item.recording_ids if recording_id in grounded.ids}
            rows = [row for row in store.filtered_rows("recordings", show_id=show["show_id"]) if row.get("recording_id") in wanted]
            block = composition._recording_list({"recordings": rows}, store)
            if block:
                block = block.model_copy(update={"show_id": show["show_id"]})
        else:
            block = composition._recording_list(payload, store)
        if block:
            sources = [SourceReference(source_id=entry.source_id, kind="contextual_resource", label=entry.source_type, url=entry.url) for entry in block.items]
        return _retitle(block, item.title), sources

    if kind in {"comparison_strip", "performance_list", "performance_extremes", "song_overview"}:
        if item.song_id not in grounded.ids:
            return None, []
        song = store.one("songs", item.song_id)
        if not song:
            return None, []
        context = store.song_context(song)
        performances = [row for row in context["performances"] if isinstance(row, dict)]
        if kind == "comparison_strip":
            return _retitle(composition._comparison_strip(song, performances, store), item.title), []
        if kind == "performance_list":
            return _retitle(composition._performance_list(song, performances, store), item.title), []
        if kind == "performance_extremes":
            return _retitle(composition._performance_extremes(song, performances, store), item.title), []
        return _retitle(composition._song_overview(context, store), item.title), []

    if kind == "performance_spine":
        if item.performance_id not in grounded.ids:
            return None, []
        context = store.performance_context(item.performance_id)
        return (_retitle(composition._performance_spine(context, store), item.title), []) if context else (None, [])

    if kind == "guest_appearance_list":
        guest = _find_in_payloads(payloads, "guests", "person_id", item.person_id)
        blocks = composition._guest_appearance_blocks({"guests": [guest]}) if guest else []
        return (blocks[0], []) if blocks else (None, [])

    if kind == "show_selection":
        selection = _find_in_payloads(payloads, "show_selections", "selection_id", item.selection_id)
        blocks, selection_sources = composition._show_selection_blocks({"show_selections": [selection]}) if selection else ([], [])
        return (_retitle(blocks[0], item.title), selection_sources) if blocks else (None, [])

    if kind == "arrangement_search":
        for payload in payloads:
            search = payload.get("arrangement_search")
            if isinstance(search, dict) and search.get("key_signature") == item.key_signature:
                block, search_sources = composition._arrangement_search_block(payload, store)
                return _retitle(block, item.title), search_sources
        return None, []

    if kind == "arrangement":
        if item.arrangement_id not in grounded.ids:
            return None, []
        block = composition._arrangement_block(item.arrangement_id, store)
        if block:
            resource = store.one("resources", block.resource_id) or {}
            source = composition._resource_source(resource)
            sources = [source] if source else []
        return _retitle(block, item.title), sources

    if kind == "media_link":
        if item.url not in grounded.urls:
            return None, []
        for payload in payloads:
            for key in ("links", "show_links"):
                for link in payload.get(key, []) if isinstance(payload.get(key), list) else []:
                    if isinstance(link, dict) and link.get("url") == item.url:
                        return _retitle(composition._media_block(link), item.title), []
            for release in payload.get("official_releases", []) if isinstance(payload.get("official_releases"), list) else []:
                if isinstance(release, dict) and release.get("spotify_album_url") == item.url:
                    link = {"platform": "spotify", "link_type": "official-release", "url": item.url, "title": release.get("title", "Official release"), "is_official": True}
                    return _retitle(composition._media_block(link), item.title), []
        return None, []

    if kind == "resource_list":
        rows: list[Any] = []
        for resource_id in item.resource_ids:
            if resource_id not in grounded.ids:
                continue
            resource = store.one("resources", resource_id)
            if not resource:
                record = _find_in_payloads(payloads, "resources", "resource_id", resource_id)
                if record is None:
                    for payload in payloads:
                        research = payload.get("research")
                        records = research.get("records") if isinstance(research, dict) else None
                        for candidate in records or []:
                            projected = composition._research_resource(candidate) if isinstance(candidate, dict) else None
                            if projected and projected["resource_id"] == resource_id:
                                record = projected
                resource = record
            entry = composition._resource_item(resource) if resource else None
            if entry:
                rows.append(entry)
                source = composition._resource_source(resource)
                if source:
                    sources.append(source)
        if not rows:
            return None, []
        return ResourceListBlock(type="resource_list", title=(item.title or "Reading and listening").strip(), items=rows[:8]), sources

    return None, []


def resolve_body(
    plan: FinishPlan,
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> tuple[list[ExperienceBlock], list[SourceReference]]:
    """Resolve the plan's body into validated blocks, dropping what was not retrieved."""

    blocks: list[ExperienceBlock] = []
    sources: list[SourceReference] = []
    for item in plan.body:
        if isinstance(item, _EditorialBlock):
            blocks.append(_sanitize_editorial(item, grounded.urls))
            continue
        block, block_sources = _resolve_reference(item, grounded, payloads, store)
        if block is None:
            logger.info("Dropped ungrounded or unresolvable reference: %s", item.model_dump())
            continue
        blocks.append(block)
        for source in block_sources:
            if source.source_id not in {existing.source_id for existing in sources}:
                sources.append(source)
    return blocks[:32], sources[:64]
```

Two builders referenced above do not exist yet. Add them to `deadbot/composition.py` next to the other builders:

```python
def _song_overview(context: dict[str, Any], store: CanonicalStore) -> SongOverviewBlock | None:
    song = context.get("song")
    if not isinstance(song, dict) or not song.get("song_id"):
        return None
    credits: list[CreditItem] = []
    for writer in context.get("writers", []) if isinstance(context.get("writers"), list) else []:
        person = store.one("people", writer.get("person_id", "")) if isinstance(writer, dict) else None
        role = writer.get("writer_role", "") if isinstance(writer, dict) else ""
        if person and role:
            credits.append(CreditItem(person_id=writer["person_id"], name=person.get("name") or writer["person_id"], role=role, follow_up=None))
    performances = context.get("performances") if isinstance(context.get("performances"), list) else []
    return SongOverviewBlock(
        type="song_overview",
        song_id=song["song_id"],
        title=song.get("title") or "Untitled song",
        original_artist=song.get("original_artist") or None,
        known_performance_count=len(performances),
        credits=credits[:12],
        source_ids=[f"canonical:{song['song_id']}"],
    )


def _arrangement_block(arrangement_id: str, store: CanonicalStore) -> ArrangementBlock | None:
    # ``store.one`` indexes tables by ``<singular>_id``; this table's key is
    # ``arrangement_id``, so look it up by scanning the rows.
    arrangement = next((row for row in store.rows("song_arrangements") if row.get("arrangement_id") == arrangement_id), None)
    if not arrangement:
        return None
    resource = store.one("resources", arrangement.get("resource_id", ""))
    source = _resource_source(resource) if resource else None
    if not resource or not source:
        return None
    sections = [
        section.get("progression", "")
        for section in store.filtered_rows("arrangement_chord_sections", arrangement_id=arrangement_id)
        if section.get("progression")
    ]
    return ArrangementBlock(
        type="arrangement",
        title=f"Source-specific arrangement: {resource.get('title', 'Chord resource')}",
        resource_id=resource["resource_id"],
        source_id=source.source_id,
        key_signature=arrangement.get("key_signature") or None,
        arrangement_scope=arrangement.get("arrangement_scope") or "source-specific arrangement",
        capo=arrangement.get("capo") or None,
        tuning=arrangement.get("tuning") or None,
        notes=arrangement.get("notes") or None,
        progressions=sections[:6],
    )
```

Note for the PostgreSQL store (`deadbot/postgres.py`): confirm `rows("song_arrangements")` and `filtered_rows("recordings", show_id=...)` exist on that implementation too; the tests here use the CSV `CanonicalStore`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add deadbot/finish.py deadbot/composition.py tests/test_finish.py
git commit -m "feat: resolve finish plan references into validated blocks"
```

---

### Task 5: Build the experience response from the turn

**Files:**
- Modify: `deadbot/finish.py`
- Test: `tests/test_finish.py`

**Interfaces:**
- Produces: `finish_plan_from_messages(messages) -> FinishPlan | None`; `build_experience_response(question: str, thread_id: str, messages: Iterable[Any], store: CanonicalStore) -> ExperienceResponse`.
- Consumes: `composition._latest_turn`, `composition._tool_payloads`, `composition._conversation_turns`, `composition._content_text`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finish.py`:

```python
def finish_call(plan: dict):
    return AIMessage(content="", tool_calls=[{"name": finish.FINISH_TOOL_NAME, "args": plan, "id": "finish-1", "type": "tool_call"}])


def delivered():
    return ToolMessage(content="Response delivered to the visitor.", tool_call_id="finish-1", name=finish.FINISH_TOOL_NAME)


def test_build_experience_response_uses_the_finish_plan():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    plan = {
        "chat_answer": "They opened with [Promised Land](https://archive.org/details/gd1972-08-27.sbd.latvala-eaton-lutch-dankseed.4682.shnf).",
        "title": "Veneta, 1972",
        "lead": "The Sunshine Daydream show.",
        "mode": "show",
        "body": [{"type": "show_setlist", "show_id": "gd-1972-08-27", "title": None}],
    }
    messages = [
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "call-1", "type": "tool_call"}]),
        tool_message(store.show_context(show)),
        finish_call(plan),
        delivered(),
    ]
    response = finish.build_experience_response("What opened Veneta?", "web-1", messages, store)
    assert response.title == "Veneta, 1972"
    assert response.answer.startswith("They opened with [Promised Land](https://archive.org")
    assert response.body_lead == "The Sunshine Daydream show."
    assert response.mode == "show"
    assert [block.type for block in response.blocks] == ["show_setlist"]
    assert response.layout[0].block_indexes == [0]
    assert response.conversation[-1].role == "assistant" and response.conversation[-1].text == response.answer
    assert response.conversation[0].text == "What opened Veneta?"


def test_build_experience_response_falls_back_when_no_plan_was_delivered(caplog):
    store = CanonicalStore()
    messages = [HumanMessage(content="Hi"), AIMessage(content="I could not find that show.")]
    with caplog.at_level("WARNING"):
        response = finish.build_experience_response("Hi", "web-1", messages, store)
    assert response.answer == "I could not find that show."
    assert response.mode == "gap"
    assert response.blocks[0].type == "gap_state"
    assert "finish_response" in caplog.text


def test_build_experience_response_only_uses_the_latest_turn():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    earlier_plan = {"chat_answer": "Earlier.", "title": "Earlier", "lead": None, "mode": "show", "body": [{"type": "show_setlist", "show_id": "gd-1972-08-27", "title": None}]}
    later_plan = {"chat_answer": "Later.", "title": "Later", "lead": None, "mode": "quick_fact", "body": []}
    messages = [
        HumanMessage(content="First"), tool_message(store.show_context(show)), finish_call(earlier_plan), delivered(),
        HumanMessage(content="Second"), finish_call(later_plan), delivered(),
    ]
    response = finish.build_experience_response("Second", "web-1", messages, store)
    assert response.title == "Later" and response.blocks == []
    assert [turn.text for turn in response.conversation] == ["First", "Earlier.", "Second", "Later."]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: FAIL with `AttributeError: module 'deadbot.finish' has no attribute 'build_experience_response'`

- [ ] **Step 3: Implement plan extraction and response assembly**

Add to `deadbot/finish.py`:

```python
from collections.abc import Iterable

from pydantic import ValidationError

from deadbot.experience import ConversationTurn, ExperienceResponse, GapStateBlock, LayoutSection


def finish_plan_from_messages(messages: list[Any]) -> FinishPlan | None:
    """Return the validated plan from the latest ``finish_response`` call, if any."""

    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") == FINISH_TOOL_NAME:
                try:
                    return FinishPlan.model_validate(call.get("args") or {})
                except ValidationError as error:
                    logger.warning("finish_response arguments failed validation: %s", error)
                    return None
    return None


def _conversation(all_messages: list[Any], chat_answer: str) -> list[ConversationTurn]:
    """Visible turns: user text, earlier assistant answers, and this turn's chat answer."""

    turns: list[ConversationTurn] = []
    for message in all_messages:
        message_type = getattr(message, "type", None)
        text = composition._content_text(getattr(message, "content", "")).strip()
        if message_type == "human" and text:
            turns.append(ConversationTurn(role="user", text=text[:8_000]))
        elif message_type == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                if call.get("name") == FINISH_TOOL_NAME and isinstance(call.get("args"), dict):
                    answer = str(call["args"].get("chat_answer") or "").strip()
                    if answer:
                        turns.append(ConversationTurn(role="assistant", text=answer[:8_000]))
            if text and not getattr(message, "tool_calls", None):
                turns.append(ConversationTurn(role="assistant", text=text[:8_000]))
    if not turns or turns[-1].role != "assistant" or turns[-1].text != chat_answer:
        turns.append(ConversationTurn(role="assistant", text=chat_answer[:8_000]))
    return turns[-50:]


def _layout(block_count: int) -> list[LayoutSection]:
    return [
        LayoutSection(region="primary" if start == 0 else "supporting", block_indexes=list(range(start, min(start + 8, block_count))))
        for start in range(0, block_count, 8)
    ][:4]


def build_experience_response(question: str, thread_id: str, messages: Iterable[Any], store: CanonicalStore) -> ExperienceResponse:
    """Assemble the browser response from the agent's latest turn."""

    all_messages = list(messages)
    turn = composition._latest_turn(all_messages)
    payloads = composition._tool_payloads(turn)
    plan = finish_plan_from_messages(turn)

    if plan is None:
        last_text = next(
            (composition._content_text(m.content).strip() for m in reversed(turn) if getattr(m, "type", None) == "ai" and composition._content_text(m.content).strip()),
            "",
        )
        logger.warning("The agent ended the turn without calling finish_response (question=%r, tool_payloads=%s)", question, len(payloads))
        answer = last_text or "Deadbot could not finish shaping this answer. Please try again."
        return ExperienceResponse(
            thread_id=thread_id,
            title="Deadbot",
            answer=answer,
            mode="gap",
            conversation=_conversation(all_messages, answer),
            blocks=[GapStateBlock(type="gap_state", message="The main body was not delivered for this answer.")],
            layout=_layout(1),
            sources=[],
        )

    grounded = grounded_context(payloads)
    blocks, sources = resolve_body(plan, grounded, payloads, store)
    chat_answer = keep_grounded_links(plan.chat_answer.strip(), grounded.urls)
    lead = keep_grounded_links(plan.lead.strip(), grounded.urls) if plan.lead and plan.lead.strip() else None
    return ExperienceResponse(
        thread_id=thread_id,
        title=plan.title.strip() or "Deadbot",
        answer=chat_answer,
        body_lead=lead,
        mode=plan.mode,
        conversation=_conversation(all_messages, chat_answer),
        blocks=blocks,
        layout=_layout(len(blocks)),
        sources=sources,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_finish.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add deadbot/finish.py tests/test_finish.py
git commit -m "feat: build the experience response from the finish_response call"
```

---

### Task 6: One loop, one persona

**Files:**
- Modify: `deadbot/graph.py`
- Test: `tests/test_graph.py` (create)

**Interfaces:**
- Consumes: `deadbot.finish.build_finish_tool`, `FINISH_TOOL_NAME`.
- Produces: `SYSTEM_PROMPT` (merged persona), `build_agent(...)` unchanged signature, routing that ends after the finish tool executes.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_graph.py`:

```python
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import graph
from deadbot.finish import FINISH_TOOL_NAME


def test_route_after_tools_ends_the_turn_once_the_response_is_delivered():
    calling = AIMessage(content="", tool_calls=[
        {"name": FINISH_TOOL_NAME, "args": {}, "id": "f1", "type": "tool_call"},
        {"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"},
    ])
    delivered = ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name=FINISH_TOOL_NAME)
    other = ToolMessage(content="{}", tool_call_id="t1", name="get_show")
    # The finish result may not be the last message when the model issued
    # parallel tool calls; any finish result in the latest batch ends the turn.
    assert graph.route_after_tools({"messages": [HumanMessage(content="q"), calling, delivered, other]}) == graph.END
    assert graph.route_after_tools({"messages": [HumanMessage(content="q"), calling, other]}) == "agent"


def test_route_after_model_sends_tool_calls_to_tools_and_text_to_end():
    calling = AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}])
    assert graph.route_after_model({"messages": [calling]}) == "tools"
    assert graph.route_after_model({"messages": [AIMessage(content="plain text")]}) == graph.END


def test_agent_tools_include_finish_response():
    from deadbot.data import CanonicalStore

    names = {tool.name for tool in graph.agent_tools(CanonicalStore())}
    assert FINISH_TOOL_NAME in names and "get_show" in names


def test_prompt_is_one_persona_without_a_handoff():
    prompt = graph.SYSTEM_PROMPT.casefold()
    assert "finish_response" in prompt
    assert "editor" not in prompt and "handoff" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: FAIL with `AttributeError: module 'deadbot.graph' has no attribute 'route_after_tools'`

- [ ] **Step 3: Rewrite the graph**

Replace the contents of `deadbot/graph.py` with:

```python
"""The bounded, tool-calling LangGraph agent loop.

One model researches with read-only tools and finishes the turn by calling
``finish_response``; its arguments are the visible answer and main-body plan
(see :mod:`deadbot.finish`).
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.finish import FINISH_TOOL_NAME, build_finish_tool
from deadbot.models import ModelProvider, create_model_provider
from deadbot.storage import create_canonical_store
from deadbot.tools import build_tools


SYSTEM_PROMPT = """You are Deadbot: a perceptive, companionable Grateful Dead
guide, historian, musicologist and DJ, and a trusted, well-prepared fan. You
work from a reviewed library of shows, performances, songs, people, recordings,
releases and sourced context, reached through read-only tools, and you deliver
every answer by calling finish_response.

Understand what the visitor actually wants and let that set the priority of
the answer. Ground factual claims in what the tools return, and notice the
contrast, surprise, continuity or listening path that makes those facts worth
exploring; a little extra research often reveals what makes one night or one
version distinct. The regular lineup and Jerry's gear are background unless the
question, a guest, or a documented change makes them notable.

Favor pathways into the music. Link to full-show recordings and, when the
library has them, to the specific performance, and to the interviews, essays
and community commentary you retrieved. Lore and interpretation come from
sourced material and carry their attribution lightly. Links are kept only when
their URL came from a tool result. When the library cannot answer, say so
plainly instead of filling the gap.

When you finish, chat_answer is the direct, crisp answer. The body is the
rewarding part: a title, a short lead, then your own narrative, fact grids or
timelines mixed with library components referenced by the IDs you retrieved
(setlists, recordings, performance context, arrangements, media, resources,
guest appearances, selections). Retitle a component when its default would
read like a database label. Chat and body complement each other; be selective
and put a few strong pieces in a natural reading order.
"""


def agent_tools(store: CanonicalStore) -> list[BaseTool]:
    """Read-only library tools plus the one tool that delivers the response."""

    return [*build_tools(store), build_finish_tool()]


def route_after_model(state: MessagesState) -> str:
    last_message = state["messages"][-1]
    return "tools" if getattr(last_message, "tool_calls", None) else END


def route_after_tools(state: MessagesState) -> str:
    """End the turn once the latest batch of tool results includes the delivered response."""

    for message in reversed(state["messages"]):
        if getattr(message, "type", None) == "ai":
            break
        if getattr(message, "type", None) == "tool" and getattr(message, "name", None) == FINISH_TOOL_NAME:
            return END
    return "agent"


def build_agent(
    settings: Settings | None = None,
    store: CanonicalStore | None = None,
    provider: ModelProvider | None = None,
):
    """Build a stateful LangGraph agent with a bounded read-only tool loop."""

    settings = settings or Settings.from_env()
    store = store or create_canonical_store(settings)
    provider = provider or create_model_provider(settings)
    tools = agent_tools(store)
    # Non-streaming: the graph consumes whole messages at each node.
    model = provider.create_chat_model().bind_tools(tools).bind(stream=False)

    def call_model(state: MessagesState):
        response = model.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", END: END})
    return graph.compile(checkpointer=MemorySaver())


def run_config(thread_id: str, settings: Settings) -> dict:
    """Return the stable session ID and a hard bound on agent iterations."""

    return {"configurable": {"thread_id": thread_id}, "recursion_limit": settings.max_tool_rounds * 2 + 2}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add deadbot/graph.py tests/test_graph.py
git commit -m "feat: merge research and editing into one agent loop with finish_response"
```

---

### Task 7: Wire the API, CLI, and evaluations; remove the composer

**Files:**
- Modify: `deadbot/api.py:19-22, 41-47, 110, 151-163`
- Modify: `deadbot/cli.py:130-132`
- Modify: `deadbot/evaluations.py:133-186`
- Delete: `deadbot/composer.py`
- Modify: `deadbot/composition.py` (delete `compose_experience_response` and helpers used only by it), `deadbot/experience.py:427-475` (lazy re-export block)
- Modify: `tests/test_experience.py`

**Interfaces:**
- Consumes: `deadbot.finish.build_experience_response(question, thread_id, messages, store)`.

- [ ] **Step 1: Rewrite the API tests to use a finish call**

In `tests/test_experience.py`:

1. Delete every test whose body references any of: `compose_experience_response`, `CompositionPlan`, `ModelGuidedComposer`, `apply_composition_plan`, `_composer_brief`, `_block_brief`, `DeterministicComposer`, `SelectionStub`. Delete the `SelectionStub` class and these imports: `from deadbot.composer import ...`, `compose_experience_response` from the `deadbot.experience` import line.
2. Keep `test_only_recognized_provider_urls_receive_embed_identifiers` and every test that exercises `Settings`, rate limiting, `/api/health`, static client serving, conversation trimming, or schema validation with `ValidationError`.
3. For the kept API tests that construct `FakeAgent([...])` or `ConversationFakeAgent`, make the fake return a finish call. Replace `ConversationFakeAgent.invoke` with:

```python
    def invoke(self, payload, config):
        self.calls.append((payload, config))
        question = payload["messages"][-1].content
        plan = {"chat_answer": f"Reply to: {question}", "title": "Deadbot", "lead": None, "mode": "quick_fact", "body": []}
        self.messages.extend([
            HumanMessage(content=question),
            AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
            ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
        ])
        return {"messages": self.messages}
```

and add one end-to-end API test:

```python
def test_experience_endpoint_renders_the_finish_plan():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    plan = {"chat_answer": "Veneta opened with Promised Land.", "title": "Veneta, 1972", "lead": None, "mode": "show",
            "body": [{"type": "show_setlist", "show_id": "gd-1972-08-27", "title": "The whole night"}]}
    agent = FakeAgent([
        HumanMessage(content="What opened Veneta?"),
        tool_message(store.show_context(show)),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    body = client.post("/api/experience", json={"question": "What opened Veneta?"}).json()
    assert body["title"] == "Veneta, 1972"
    assert body["blocks"][0]["type"] == "show_setlist" and body["blocks"][0]["title"] == "The whole night"
    assert body["conversation"][-1] == {"role": "assistant", "text": "Veneta opened with Promised Land."}
```

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_experience.py -v`
Expected: FAIL on the new test (the app still calls the composer) and import errors for the deleted names until Step 2 lands.

- [ ] **Step 2: Rewire `deadbot/api.py`**

Replace the imports and composer wiring:

```python
from deadbot.config import Settings
from deadbot.data import CanonicalStore, repository_root
from deadbot.experience import ExperienceRequest, ExperienceResponse
from deadbot.finish import build_experience_response
from deadbot.graph import build_agent, run_config
from deadbot.storage import create_canonical_store
```

In `create_app`, delete the `composer` parameter, `is_production_runtime`, the `composer = ...` line, and `app.state.composer`. In `health()`, drop the `"composer"` key. Replace the tail of `experience()` (from `response = compose_experience_response(` to the end of the function) with:

```python
        return build_experience_response(
            question=request.question,
            thread_id=thread_id,
            messages=result.get("messages", []),
            store=app.state.store,
        )
```

- [ ] **Step 3: Rewire `deadbot/cli.py` chat output**

Replace lines 130-132 with:

```python
        result = agent.invoke({"messages": [HumanMessage(content=question)]}, config=config)
        response = build_experience_response(question, thread_id, result["messages"], store)
        print(f"\nDeadbot: {response.answer}")
        if response.body_lead:
            print(f"\n{response.title}\n{response.body_lead}")
```

Add `from deadbot.finish import build_experience_response` to the imports and `store = create_canonical_store(settings)` before `agent = build_agent(settings, store=store)` at line 115.

- [ ] **Step 4: Rewire `deadbot/evaluations.py`**

In `model_evaluate_suite`, replace `answer = str(messages[-1].content)` with:

```python
        from deadbot.finish import build_experience_response

        response = build_experience_response(case["question"], f"model-eval-{case['id']}", messages, store or CanonicalStore())
        answer = response.answer
        body_types = [block.type for block in response.blocks]
```

and add `"body_block_types": body_types,` to the result dict.

- [ ] **Step 5: Remove the composer and the projection loop**

```bash
git rm deadbot/composer.py
```

In `deadbot/composition.py`, delete `compose_experience_response` and the helpers only it used: `_final_answer`, `_conversation_turns`, `_coverage_block`, `_entity_card_from_song`, `_entity_card_from_show`, `_entity_card_from_performance`, `_canonical_source`. Keep `_content_text`, `_tool_payloads`, `_latest_turn`, `_resource_source`, `_embed_details`, `_resource_item`, `_research_resource`, `_media_block`, `_performance_items`, `_performance_list`, `_performance_extremes`, `_comparison_strip`, `_performance_spine`, `_show_setlist`, `_show_selection_blocks`, `_show_performers`, `_show_equipment`, `_recording_list`, `_arrangement_search_block`, `_guest_appearance_blocks`, `_song_overview`, `_arrangement_block`. Update the module docstring to say the module holds block builders used by `deadbot.finish`. Remove now-unused imports (`CoverageBlock`, `EntityCardBlock`, `GapStateBlock`, `LayoutSection`, `ExperienceMode`, `ExperienceResponse`, `ConversationTurn`).

In `deadbot/experience.py`, delete everything from the comment banner `# Backward-compatible re-exports from the deterministic adapter.` to the end of the file. Update the module docstring's references to `deadbot.composer` to `deadbot.finish`.

Fix the `_embed_details` import in `tests/test_experience.py`: `from deadbot.composition import _embed_details`.

- [ ] **Step 6: Run the suites**

Run: `/Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest tests/test_experience.py tests/test_finish.py tests/test_graph.py tests/test_cli.py -v`
Expected: PASS. Then run `grep -rn "composer\|compose_experience_response" deadbot tests scripts` and expect no matches.

- [ ] **Step 7: Regenerate the contract and commit**

```bash
/Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py
npm run gen:types --prefix web
git add -A deadbot tests web/openapi.json web/src/generated/api.ts
git commit -m "refactor: deliver responses from the single loop and remove the composer"
```

---

### Task 8: Render links in chat and editorial text

**Files:**
- Modify: `web/src/App.tsx:59-65, 486-531, 638-643, 674`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: generated types `EditorialItem.link?: { url: string; label: string } | null`.
- Produces: `renderInline(text: string): ReactNode[]` used for chat text, `body_lead`, narrative paragraphs, and fact/timeline detail.

- [ ] **Step 1: Add the inline renderer**

After `ExternalLink` in `web/src/App.tsx` add:

```tsx
const inlineLink = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(inlineLink)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    nodes.push(<ExternalLink key={`${index}-${match[2]}`} href={match[2]}>{match[1]}</ExternalLink>);
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
```

- [ ] **Step 2: Use it**

- Conversation bubble: replace `<div>{turn.text}</div>` with `<div>{renderInline(turn.text)}</div>`.
- Lead: replace `{response.body_lead && <p className="answer-lead">{response.body_lead}</p>}` with `{response.body_lead && <p className="answer-lead">{renderInline(response.body_lead)}</p>}`.
- Narrative: `{block.paragraphs.map((paragraph, index) => <p key={index}>{renderInline(paragraph)}</p>)}`.
- Fact grid `dd` detail and timeline detail: wrap `item.detail` in `renderInline(item.detail)`.
- Fact grid and timeline items: after the follow-up/value rendering add `{item.link && <ExternalLink href={item.link.url}>{item.link.label}</ExternalLink>}`. In the timeline `<li>` put it as the last child; in the fact grid put it inside a `<dd className="fact-link">`.
- Follow-up buttons keep `↗`; change the `FollowUpButton` arrow to `→` so external links (`↗`) and ask-Deadbot actions (`→`) read differently.

- [ ] **Step 3: Style**

Append to `web/src/styles.css`:

```css
.message a, .answer-lead a, .narrative-block a { color: #f1c96a; }
.fact-grid-block .fact-link { margin-top: 0.35rem; font-size: 0.9rem; }
.timeline-block li > a { grid-column: 2; font-size: 0.9rem; }
```

- [ ] **Step 4: Build and check**

Run: `npm run build --prefix web`
Expected: `tsc -b && vite build` succeeds with no type errors. Open the app against a local server if a model is configured and confirm a chat answer containing a markdown link renders as an outbound link.

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx web/src/styles.css
git commit -m "feat: render grounded links in chat, lead, and editorial text"
```

---

### Task 9: Documentation

**Files:**
- Modify: `AGENTS.md:13-17`, `docs/experience-architecture.md:19-53, 114-138`, `docs/agent-harness.md:13-35`, `docs/experience-brief.md:23-32`, `docs/development-plan.md` (add a dated note)

- [ ] **Step 1: AGENTS.md**

Replace the bullet beginning "Keep model responsibilities coherent" with:

```markdown
- One model owns the whole turn. It researches with read-only tools and
  delivers the visible chat answer and main-body plan in one `finish_response`
  call. Do not reintroduce a handoff between a retrieval model and an editing
  model; improve the persona, tools, and plan palette instead.
```

Replace "Supply a structured decision brief ..." with:

```markdown
- Supply rich tool output: the facts, relationships, listening paths, and
  sourced context a knowledgeable fan would want, with IDs and URLs the model
  can reference in its plan. Include source or coverage context only where it
  changes how a visitor should understand or use the material.
```

- [ ] **Step 2: experience-architecture.md**

Replace the request-to-interface diagram and the paragraph after it with:

```text
browser question
      |
      v
FastAPI experience endpoint
      |
      v
agent loop: read-only tools ... finish_response(plan)
      |
      v
plan resolution (references → validated blocks; ungrounded links dropped)
      |
      v
validated experience response (answer + typed blocks + sources)
      |
      v
React block renderer
```

```markdown
One model owns the turn. It decides which tools to use, reads their results,
and ends by calling `finish_response`, whose arguments are the chat answer,
title, lead, mode, and a body that mixes model-written editorial blocks with
library components referenced by canonical ID. `deadbot/finish.py` resolves
those references against the store, keeps only links whose URLs the tools
returned this turn, and produces the validated response. The renderer is
deterministic application code.
```

Rewrite "Composition rules" as "Plan resolution rules": the model owns relevance, emphasis, omission, titles and reading order; application code resolves references, drops what was not retrieved, and enforces the response shape; it never vetoes content or substitutes a database packet.

- [ ] **Step 3: agent-harness.md and experience-brief.md**

Add to the tool list in `docs/agent-harness.md`: `` `finish_response` — the only way a turn ends: the model's chat answer and main-body plan, resolved by `deadbot/finish.py`. `` Replace the "How the models work together" section of `docs/experience-brief.md` with a "How the model works" section: one persona, research then finish, links only from retrieved material, lore from sourced material with attribution.

- [ ] **Step 4: development-plan.md**

Add under the current-state notes: "2026-09: merged the research and editing models into one loop with a `finish_response` tool; removed `deadbot/composer.py`; editorial items can carry grounded outbound links."

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md docs/experience-architecture.md docs/agent-harness.md docs/experience-brief.md docs/development-plan.md
git commit -m "docs: describe the single agent loop and finish_response"
```

---

## Self-review notes

- Spec coverage: audit items 1 (merge, persona, priority guidance) and 2 (links, model-authored titles, drop-not-fail) map to Tasks 3 through 8. Model-authored follow-up text is already possible through `EditorialItem.follow_up`; component follow-ups inside reused blocks stay code-authored in this plan and are listed in the audit's remaining-rules sweep.
- Known follow-ups outside this plan: `song_context` does not include per-performance listening links, so a song question cannot yet link to a specific version without a `get_performance` call; `comparison_strip` and `show_selection` keep their required coverage notes; the sources footer still shows kind chips.
- The `tool_choice` question: if in production the model sometimes ends with plain text instead of `finish_response`, bind `tool_choice="required"` in `OpenAIProvider` rather than adding a retry rule; the fallback in Task 5 logs every such case so the rate is measurable first.
