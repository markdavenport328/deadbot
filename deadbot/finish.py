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
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deadbot import composition
from deadbot.data import CanonicalStore
from deadbot.experience import (
    ConversationTurn,
    EditorialBlock,
    EditorialBlock as _EditorialBlock,
    ExperienceBlock,
    ExperienceMode,
    ExperienceResponse,
    GapStateBlock,
    LayoutSection,
    ResourceListBlock,
    SourceReference,
)


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


def _find_research_resource(payloads: list[dict[str, Any]], resource_id: str) -> dict[str, Any] | None:
    """Locate a research-sourced resource by its projected id.

    ``composition._research_resource`` synthesizes ``research:<source>:<identifier>``
    from a raw research record, so that id never appears verbatim in tool output for
    ``grounded.ids`` to have captured. It is grounded by construction instead: this
    scans the turn's research payloads and re-projects each record to find the match.
    """

    for payload in payloads:
        for key in ("research", "research_result", "research_results"):
            value = payload.get(key)
            if isinstance(value, dict):
                records = value.get("records")
            elif isinstance(value, list):
                records = value
            else:
                records = None
            for candidate in records or []:
                if not isinstance(candidate, dict):
                    continue
                projected = composition._research_resource(candidate)
                if projected and projected["resource_id"] == resource_id:
                    return projected
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
            resource: dict[str, Any] | None
            if resource_id.startswith("research:"):
                # A research resource's id is synthesized by the projection, not
                # copied from tool output, so it cannot appear in grounded.ids.
                # It is grounded by construction: only ids re-derivable from this
                # turn's own research payloads can match.
                resource = _find_research_resource(payloads, resource_id)
            else:
                if resource_id not in grounded.ids:
                    continue
                resource = store.one("resources", resource_id)
                if not resource:
                    resource = _find_in_payloads(payloads, "resources", "resource_id", resource_id)
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
    final = ConversationTurn(role="assistant", text=chat_answer[:8_000])
    if turns and turns[-1].role == "assistant":
        turns[-1] = final
    else:
        turns.append(final)
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
    if not chat_answer.strip():
        logger.warning("finish_response delivered a blank chat_answer (question=%r); substituting the lead or a placeholder", question)
        chat_answer = lead if lead else "Deadbot could not write a chat answer for this response."
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
