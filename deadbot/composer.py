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
    """The model's layout decision; it cannot create or mutate content blocks."""

    model_config = ConfigDict(extra="forbid")
    mode: ExperienceMode = "quick_fact"
    sections: list[CompositionSection] = Field(min_length=1, max_length=4)
    omitted_candidate_indexes: list[int] = Field(default_factory=list, max_length=16)


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
            "decision_tradeoff": "the strongest orientation for questions about sequence, sets, or what was played; it can be supporting context when the visitor's next move is listening or investigating a specific performance",
            "provenance": "canonical",
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
            "decision_tradeoff": "an immediate listening path for a visitor asking about how a guitar or performance sounds; it can be supporting context when the visitor asked about set order or song sequence",
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
            "provenance": "source-reviewed canonical assignment",
        }
    if block.type == "equipment_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "source-dated guitar claims for one show",
            "title": block.title,
            "equipment_names": [item.name for item in block.items],
            "helps_with": "named Jerry Garcia guitar and equipment questions",
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
            "helps_with": "reading, learning, or source research; not canonical proof",
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
            "provenance": "source-specific arrangements",
        }
    if block.type == "provenance_note":
        return {
            "index": index,
            "type": block.type,
            "scope": "provenance explanation",
            "helps_with": "distinguishing contextual material from canonical facts",
            "provenance": "system safeguard",
        }
    return {
        "index": index,
        "type": block.type,
        "scope": "coverage gap",
        "helps_with": "honest limitation when no grounded result is available",
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

    brief = {
        "latest_question": question,
        "grounded_agent_answer": response.answer,
        "recent_conversation": [turn.model_dump() for turn in response.conversation[-8:]],
        "candidate_blocks": [_block_brief(index, block) for index, block in enumerate(response.blocks)],
        "related_show_paths": _show_relationships(response),
    }
    return json.dumps(brief, ensure_ascii=False, separators=(",", ":"))


def apply_composition_plan(response: ExperienceResponse, plan: CompositionPlan) -> ExperienceResponse:
    """Resolve model choices to server-owned blocks and a browser-safe layout.

    The deterministic work here is intentionally narrow: discard invalid
    references and prevent duplicated blocks. The model decides relevance,
    omission, and the arrangement of valid blocks; source metadata remains in
    the response contract without forcing a visible explanation onto the page.
    """

    selected_indexes: list[int] = []
    resolved_sections: list[tuple[str, list[int]]] = []
    has_grounded_content = any(block.type not in {"coverage", "gap_state"} for block in response.blocks)
    for section in plan.sections:
        section_indexes = []
        for index in section.candidate_indexes:
            # Coverage is an explanation of a limit, never a substitute for
            # the show, performance, or gap the visitor actually asked about.
            # A composer may surface it only in the dedicated gap mode.
            if (
                0 <= index < len(response.blocks)
                and response.blocks[index].type == "coverage"
                and (plan.mode != "gap" or has_grounded_content)
            ):
                continue
            if 0 <= index < len(response.blocks) and index not in selected_indexes:
                selected_indexes.append(index)
                section_indexes.append(index)
        if section_indexes:
            resolved_sections.append((section.region, section_indexes))
    if not selected_indexes:
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

    def __init__(self, provider: ModelProvider | None = None, max_blocks: int = 8, selector: Any | None = None):
        if selector is None:
            if provider is None:
                raise ValueError("A model provider or structured selector is required.")
            model = provider.create_chat_model()
            selector = model.with_structured_output(CompositionPlan, method="json_schema").bind(stream=False)
        self.selector = selector
        self.max_blocks = max_blocks

    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        if len(response.blocks) <= 1:
            return response
        prompt = (
            "Choose the most coherent main-column guide for the latest question using the grounded brief below. "
            "Reason from the question, answer, coverage, candidate scope, and provenance. "
            "The chat column already gives the direct answer. The main column must not repeat it; use it to provide the next useful grounded action, evidence, or connection. "
            "Serve the right thing at the right depth, like a trusted, well-prepared fan. Do not perform expertise or invent critical color. "
            "First choose one experience mode: quick_fact, performance, show, listening, comparison, research, musician, or gap. "
            "Choose it from the visitor's request and the grounded material, not from a generic keyword rule. "
            "Select the smallest useful set of candidates and arrange them in primary, supporting, context, or media regions. "
            "Omission is the default: including an irrelevant candidate is worse than omitting optional material. Most questions need one to three candidates. Use omitted_candidate_indexes to explicitly exclude candidates that do not answer the latest question. "
            "The page title already identifies the main song, show, or performance. Omit an entity card when it only repeats that title and has no additional details. "
            "For a song question, prefer the song_overview block as the standard facts panel. For a first/last performance question, prefer the performance_extremes block, which already combines both endpoints; omit the generic performance_list unless the user asks for the full known list. "
            "For a specific performance question, choose performance mode and use the performance_spine when it is available; it provides only canonical set adjacency, so do not imply musical analysis that was not retrieved. "
            "For a show question, use the related_show_paths and candidate decision_tradeoff fields to decide whether the setlist, recordings, performers, or equipment offers the most useful next step. Do not select only the show card when a richer grounded show path is available. "
            "When a show has both recordings and a full setlist, decide their ordering from the visitor's intent. For a first-use or named-equipment question, the grounded equipment claim plus a recording from that show usually makes the more satisfying path: the visitor can hear the instrument in its documented setting. A full setlist is secondary unless the visitor asks about sequence or what was played. For a set-order question, the setlist may lead. Do not apply a universal ordering rule. "
            "When source-reviewed performers are available for a show, include the performer_list for lineup, guest, musician, or instrument questions; it groups each person with their recorded instruments. "
            "When named guitar claims are available for a show, include the equipment_list for Jerry Garcia guitar or equipment questions; distinguish date-range evidence from specific-show evidence and do not treat a date-range claim as a complete equipment log. "
            "Do not select a provenance note merely because a resource is present; provenance is retained in the response metadata and should not become a visible page section unless the user explicitly asks about sources or attribution. "
            "Do not select library coverage for ordinary song, show, performance, date, setlist, credit, media, or listening questions. Select coverage only in gap mode when the user directly asks about library scope, completeness, coverage, or a limitation that the answer must explain. "
            "Do not choose learning, media, or reading material unless it genuinely helps the question. "
            "For a direct factual, count, date, setlist, or coverage question, select only the factual entity/performance/coverage evidence needed to answer it; omit chord arrangements, contextual resource lists, and media unless the user explicitly asks for them. "
            "For a musician, arrangement, key, chord, tab, or lyric-source request, choose musician mode. Include source-specific arrangement material when available, retain its scope, and do not treat the documented key as universal for the song. Full tabs and lyrics remain external-source links. "
            "For a count or scope-wide question, do not present partial library evidence as a historical total; use the coverage candidate when it explains that limit. "
            "For example, a question asking for a yearly count with incomplete coverage should normally have a primary coverage block and a supporting known-performance block, with no context or media section. "
            "Return only candidate indexes received in the brief. Do not create facts, sources, URLs, blocks, or headings.\n\n"
            f"Grounded composition brief: {_composer_brief(question, response)}"
        )
        try:
            result = self.selector.invoke(
                [
                    SystemMessage(content="You are Deadbot's model-first, provenance-aware interface composer. Return only the requested structured layout plan."),
                    HumanMessage(content=prompt),
                ]
            )
            plan = result if isinstance(result, CompositionPlan) else CompositionPlan.model_validate(result)
            selected_count = sum(len(section.candidate_indexes) for section in plan.sections)
            if selected_count > self.max_blocks:
                return response
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
    return ModelGuidedComposer(provider or create_model_provider(settings), max_blocks=settings.composer_max_blocks)
