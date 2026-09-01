"""Model-first composition of grounded, server-validated experience blocks."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from deadbot.config import Settings
from deadbot.experience import ExperienceBlock, ExperienceMode, ExperienceResponse, LayoutSection
from deadbot.models import ModelProvider, create_model_provider


logger = logging.getLogger(__name__)


class CompositionSection(BaseModel):
    """A model-selected region containing only candidate indexes it received."""

    model_config = ConfigDict(extra="forbid")
    region: Literal["primary", "supporting", "context", "media"]
    candidate_indexes: list[int] = Field(min_length=1, max_length=8)


class CompositionPlan(BaseModel):
    """The model's editorial and layout decision over grounded candidates."""

    model_config = ConfigDict(extra="forbid")
    mode: ExperienceMode = "quick_fact"
    sections: list[CompositionSection] = Field(min_length=1, max_length=4)
    omitted_candidate_indexes: list[int] = Field(default_factory=list, max_length=32)


class ExperienceComposer(Protocol):
    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        """Return a response with an approved model-selected layout."""


def _block_brief(index: int, block: ExperienceBlock) -> dict[str, Any]:
    """Give the model useful decision context without sending raw links or code."""

    if block.type == "entity_card":
        return {
            "index": index,
            "type": block.type,
            "scope": block.entity_type,
            "title": block.title,
            "details": block.details,
            "redundant_when_title_only": not block.subtitle and not block.details,
            "helps_with": "identity and canonical facts about this entity",
            "layout_guidance": "identity anchor; keep it low-prominence when it only repeats the page title, and move it toward primary when its details orient the rest of the page",
            "provenance": "canonical",
        }
    if block.type == "performance_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "known performances in the current library",
            "title": block.title,
            "performance_count": block.known_count,
            "dates": [item.show_date for item in block.items if item.show_date],
            "helps_with": "known performance count and performance evidence",
            "layout_guidance": "detailed evidence block; place after a compact endpoint or overview block when both are present",
            "provenance": "canonical",
        }
    if block.type == "performance_spine":
        return {
            "index": index,
            "type": block.type,
            "scope": "the directly adjacent songs in this performance's documented set",
            "title": block.title,
            "show": block.show_label,
            "set_label": block.set_label,
            "position_in_set": block.position_in_set,
            "previous_song": block.previous.title if block.previous else None,
            "next_song": block.next.title if block.next else None,
            "helps_with": "placing one rendition in its immediate set context without claiming an interpretation of the music",
            "layout_guidance": "strong primary anchor for a specific performance; keep adjacent show and listening context nearby",
            "provenance": "canonical",
        }
    if block.type == "comparison_strip":
        years = [item.year for item in block.items]
        return {
            "index": index,
            "type": block.type,
            "scope": "one representative performance per known year of one song",
            "title": block.title,
            "year_range": f"{min(years)}–{max(years)}",
            "years_represented": years,
            "item_count": len(block.items),
            "known_count": block.known_count,
            "helps_with": "seeing where a song's grounded performances sit over time, with explicit library-coverage limits",
            "layout_guidance": "strong primary comparison anchor; if a full performance list is also present, position that detailed evidence as supporting material",
            "provenance": "canonical",
        }
    if block.type == "performance_extremes":
        return {
            "index": index,
            "type": block.type,
            "scope": "first and last known performances of a song",
            "title": block.title,
            "first_show": block.first.show_label,
            "last_show": block.last.show_label,
            "helps_with": "answering first/last performance questions in one compact component",
            "layout_guidance": "compact primary endpoint block; place any full performance list after it as supporting detail",
            "provenance": "canonical",
        }
    if block.type == "song_overview":
        return {
            "index": index,
            "type": block.type,
            "scope": "standard song facts",
            "title": block.title,
            "original_artist": block.original_artist,
            "known_performance_count": block.known_performance_count,
            "credits": [{"name": credit.name, "role": credit.role} for credit in block.credits],
            "helps_with": "a compact overview of the song's identity, credits, and known performance count",
            "layout_guidance": "standard primary facts panel for song questions",
            "provenance": "canonical",
        }
    if block.type == "show_setlist":
        return {
            "index": index,
            "type": block.type,
            "scope": "ordered songs played at one show",
            "title": block.title,
            "set_labels": [section.label for section in block.sets],
            "song_count": sum(len(section.songs) for section in block.sets),
            "helps_with": "show setlist questions; each song is a grounded follow-up target",
            "layout_guidance": "primary orientation for a broad show guide or sequence question; keep recordings close, and use supporting placement when a specific performance is the stronger anchor",
            "provenance": "canonical",
        }
    if block.type == "show_selection":
        return {
            "index": index,
            "type": block.type,
            "scope": "one reviewed, source-attributed editorial selection of shows",
            "title": block.title,
            "selection_type": block.selection_type,
            "selector_name": block.selector_name,
            "show_count": len(block.items),
            "coverage_note": block.coverage_note,
            "helps_with": "broad questions about notable, essential, recommended, or worth-exploring shows",
            "layout_guidance": "source-attributed discovery anchor; position its attribution and coverage limits with the selection",
            "provenance": "reviewed source-attributed selection",
        }
    if block.type == "recording_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "approved recordings for one show",
            "title": block.title,
            "recording_count": len(block.items),
            "source_types": sorted({item.source_type for item in block.items}),
            "archive_identifiers": [item.archive_identifier for item in block.items if item.archive_identifier],
            "helps_with": "listening to recordings of the show",
            "layout_guidance": "media-region companion to its show, setlist, performance, or equipment claim; keep the audible evidence close to the relationship it supports",
            "provenance": "stored recording metadata",
        }
    if block.type == "performer_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "source-reviewed musicians and guests at one show",
            "title": block.title,
            "performer_count": len(block.items),
            "guest_names": [item.name for item in block.items if item.role == "guest"],
            "helps_with": "show lineup, guest, role, and instrument questions",
            "layout_guidance": "primary for lineup or musician questions and supporting for a broad show guide; do not place an ordinary full lineup ahead of the show's setlist or recordings",
            "provenance": "source-reviewed canonical assignment",
        }
    if block.type == "equipment_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "source-dated guitar claims for one show",
            "title": block.title,
            "equipment_names": [item.name for item in block.items],
            "claim_types": sorted({item.claim_type for item in block.items}),
            "helps_with": "named Jerry Garcia guitar and equipment questions",
            "layout_guidance": "primary for named-equipment questions; keep it beside the dated show and audible evidence that establish its context",
            "provenance": "dated photographic/video-evidence guide",
        }
    if block.type == "coverage":
        return {
            "index": index,
            "type": block.type,
            "scope": "library coverage, not a historical total",
            "title": block.title,
            "message": block.message,
            "helps_with": "whether the current library can answer a scope-wide question completely",
            "layout_guidance": "lead in a gap experience so the library limit is clear before any next-step material",
            "provenance": "canonical coverage metadata",
        }
    if block.type == "resource_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "external contextual resources",
            "title": block.title,
            "resource_types": [item.resource_type for item in block.items],
            "item_titles": [item.title for item in block.items],
            "context_notes": [item.context_note for item in block.items if item.context_note],
            "helps_with": "source-attributed interpretation, community perspective, reading, or further research; not canonical proof",
            "layout_guidance": "place in the region where its contextual and subjective provenance is clearest",
            "provenance": "contextual resources",
        }
    if block.type == "media_link":
        return {
            "index": index,
            "type": block.type,
            "scope": "external media",
            "title": block.title,
            "provider": block.provider,
            "official": block.is_official,
            "helps_with": "listening or watching",
            "layout_guidance": "place in the media region or beside the grounded performance it supports",
            "provenance": "external media link",
        }
    if block.type == "arrangement":
        return {
            "index": index,
            "type": block.type,
            "scope": "source-specific chord arrangement",
            "title": block.title,
            "key": block.key_signature,
            "arrangement_scope": block.arrangement_scope,
            "capo": block.capo,
            "tuning": block.tuning,
            "helps_with": "learning or playing this song; it is not a universal chart",
            "layout_guidance": "musician material; keep the source-specific key and external resource visually connected",
            "provenance": "contextual resource",
        }
    if block.type == "arrangement_search":
        return {
            "index": index,
            "type": block.type,
            "scope": "only source-documented arrangements in one requested key",
            "title": block.title,
            "key": block.key_signature,
            "match_count": len(block.items),
            "song_titles": [item.title for item in block.items],
            "helps_with": "rehearsal and cover planning without treating a documented arrangement as a universal song key",
            "layout_guidance": "musician material; lead with the matching arrangements and keep their coverage limit nearby",
            "provenance": "source-specific arrangements",
        }
    if block.type == "provenance_note":
        return {
            "index": index,
            "type": block.type,
            "scope": "provenance explanation",
            "helps_with": "distinguishing contextual material from canonical facts",
            "layout_guidance": "provenance metadata is retained outside the ordinary visible layout",
            "provenance": "system safeguard",
        }
    if block.type == "credit_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "song credits",
            "title": block.title,
            "credits": [{"name": item.name, "role": item.role} for item in block.items],
            "helps_with": "who wrote, composed, or is credited on the song",
            "layout_guidance": "place near the song overview or other songwriting context",
            "provenance": "canonical",
        }
    if block.type == "guest_appearance_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "all documented guest-show relationships for one resolved person in the current canonical directory",
            "title": block.person_name,
            "known_show_count": block.known_show_count,
            "dates": [item.show_date for item in block.items],
            "coverage_note": block.coverage_note,
            "helps_with": "guest appearance counts, dates, instruments, and show follow-up paths",
            "layout_guidance": "primary guest anchor; keep selected show, listening, and commentary paths after or beside it",
            "provenance": "canonical guest-credit relationships",
        }
    return {
        "index": index,
        "type": block.type,
        "scope": "coverage gap",
        "helps_with": "honest limitation when no grounded result is available",
        "layout_guidance": "primary orientation when no grounded result exists",
        "provenance": "system safeguard",
    }


def _show_relationships(response: ExperienceResponse) -> list[dict[str, Any]]:
    """Describe related candidates so the model can compare useful paths."""

    grouped: dict[str, list[tuple[int, str]]] = {}
    for index, block in enumerate(response.blocks):
        show_id = getattr(block, "show_id", None)
        if isinstance(show_id, str) and show_id:
            grouped.setdefault(show_id, []).append((index, block.type))
    return [
        {
            "show_id": show_id,
            "candidate_indexes": [index for index, _ in candidates],
            "available_paths": [block_type for _, block_type in candidates],
            "reasoning_note": "Compare these related show paths against the visitor's intent. Their order and layout are a decision for this question, not a default sequence.",
        }
        for show_id, candidates in grouped.items()
    ]


def _composer_brief(question: str, response: ExperienceResponse) -> str:
    """Build the structured reasoning context for the model-first composer."""

    research_candidates = []
    for index, block in enumerate(response.blocks):
        if block.type != "resource_list":
            continue
        for item in block.items:
            research_candidates.append(
                {
                    "candidate_index": index,
                    "resource_id": item.resource_id,
                    "title": item.title,
                    "scope": item.resource_type,
                    "purpose": "open a grounded contextual source for reading, listening, or research",
                    "relationship": "attached resource candidate",
                    "provenance": "contextual resource metadata",
                    "source_id": item.source_id,
                    "context_note": item.context_note,
                }
            )

    brief = {
        "latest_question": question,
        "grounded_agent_answer": response.answer,
        "recent_conversation": [turn.model_dump() for turn in response.conversation[-8:]],
        "candidate_blocks": [_block_brief(index, block) for index, block in enumerate(response.blocks)],
        "research_candidates": research_candidates,
        "related_show_paths": _show_relationships(response),
    }
    return json.dumps(brief, ensure_ascii=False, separators=(",", ":"))


def apply_composition_plan(response: ExperienceResponse, plan: CompositionPlan) -> ExperienceResponse:
    """Resolve model editorial choices to server-owned blocks and a safe layout.

    The composer may select, omit, order, and place candidates, but it cannot
    create or mutate them. Every supplied candidate must be explicitly selected
    or omitted; invalid, duplicate, or unaccounted references preserve the
    deterministic fallback.
    """

    expected_indexes = set(range(len(response.blocks)))
    selected_indexes: list[int] = []
    resolved_sections: list[tuple[str, list[int]]] = []
    has_grounded_content = any(
        candidate.type not in {"coverage", "gap_state", "provenance_note"}
        for candidate in response.blocks
    )
    for section in plan.sections:
        section_indexes = []
        for index in section.candidate_indexes:
            if index not in expected_indexes or index in selected_indexes:
                return response
            block = response.blocks[index]
            if block.type == "coverage" and (plan.mode != "gap" or has_grounded_content):
                return response
            selected_indexes.append(index)
            section_indexes.append(index)
        if section_indexes:
            resolved_sections.append((section.region, section_indexes))
    omitted_indexes = plan.omitted_candidate_indexes
    if (
        len(omitted_indexes) != len(set(omitted_indexes))
        or any(index not in expected_indexes for index in omitted_indexes)
        or set(omitted_indexes) & set(selected_indexes)
        or set(selected_indexes) | set(omitted_indexes) != expected_indexes
        or not selected_indexes
    ):
        return response

    selected_blocks = [response.blocks[index] for index in selected_indexes]
    original_to_selected = {original: selected for selected, original in enumerate(selected_indexes)}
    layout = [
        LayoutSection(
            region=region,
            block_indexes=[original_to_selected[index] for index in indexes],
        )
        for region, indexes in resolved_sections
    ]
    return response.model_copy(update={"blocks": selected_blocks, "layout": layout, "mode": plan.mode})


class DeterministicComposer:
    """Keep the adapter's complete candidate layout when a model is disabled."""

    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        return response


class ModelGuidedComposer:
    """Let the model reason over an enriched brief and select a safe layout."""

    def __init__(self, provider: ModelProvider | None = None, selector: Any | None = None):
        if selector is None:
            if provider is None:
                raise ValueError("A model provider or structured selector is required.")
            model = provider.create_chat_model()
            selector = model.with_structured_output(CompositionPlan, method="json_schema").bind(stream=False)
        self.selector = selector

    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        if len(response.blocks) <= 1:
            return response
        prompt = (
            "You are a knowledgeable, curious, and helpful Grateful Dead authority editing a rich exploratory experience for the visitor's latest question. "
            "The upstream model has assembled a grounded candidate packet. Exercise editorial judgment over that packet: decide what best answers the visitor, what creates a worthwhile next step, what adds illuminating listening or contextual material, what would merely clutter the page, and what should lead. "
            "Choose one experience mode (quick_fact, performance, show, listening, comparison, research, musician, or gap), then select, omit, order, prioritize, and arrange candidates into primary, supporting, context, or media regions. There is no universal template. "
            "Treat the short chat answer and main panel as one response. The panel should make the answer more useful and engaging, not simply repeat it or display every available database field. Its primary region must carry the most substantive answer and its best grounded exploration paths; do not leave those paths to a generic chat invitation. A bare directory of dates, repeated instruments, or coverage metadata is evidence, not a satisfying primary experience when the packet includes show, musical, listening, or source context. "
            "Account for every candidate index by placing it exactly once or listing it in omitted_candidate_indexes. "
            "For a show guide, place setlist and recordings ahead of ordinary lineup detail, and keep blocks about the same guest, equipment claim, or performance together. For a guest-appearance question with related show candidates, use the guest list as the count and timeline, then foreground the show context that tells the visitor where the appearances happened and what they can explore. "
            "Use each candidate's purpose, relationship, and exploration value to make these judgments, and use related_show_paths to keep blocks about the same show coherent. Source and coverage details are supporting context, not a reason to make a block prominent unless they change what the visitor should understand. "
            "Your factual universe is closed: return only candidate indexes from the brief. Do not research, create, rewrite, or embellish facts, sources, URLs, blocks, or headings.\n\n"
            f"Grounded composition brief: {_composer_brief(question, response)}"
        )
        try:
            result = self.selector.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are Deadbot's knowledgeable, curious, and music-first Grateful Dead experience editor. "
                            "Use editorial judgment to create a rich, helpful experience from grounded candidates, and return only the requested structured composition plan."
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            plan = result if isinstance(result, CompositionPlan) else CompositionPlan.model_validate(result)
            composed = apply_composition_plan(response, plan)
            logger.info("Applied model composition plan: candidates=%s sections=%s", len(response.blocks), len(plan.sections))
            return composed
        except Exception as error:
            logger.warning("Model composer failed (%s); using deterministic candidate order.", type(error).__name__)
            return response


def create_experience_composer(settings: Settings, provider: ModelProvider | None = None) -> ExperienceComposer:
    """Return the configured composer without changing the agent's tool contract."""

    if not settings.composer_enabled:
        return DeterministicComposer()
    return ModelGuidedComposer(provider or create_model_provider(settings))
