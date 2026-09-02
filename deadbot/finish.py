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
from typing import Annotated, Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from deadbot.composition import _latest_turn, _tool_payloads
from deadbot.experience import EditorialBlock, ExperienceMode


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
