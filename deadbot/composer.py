"""Model-first composition of grounded, server-validated experience blocks."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from deadbot.config import Settings
from deadbot.experience import ExperienceBlock, ExperienceResponse, LayoutSection
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
            "provenance": "canonical",
        }
    if block.type == "recording_list":
        return {
            "index": index,
            "type": block.type,
            "scope": "approved recordings for one show",
            "title": block.title,
            "recording_count": len(block.items),
            "helps_with": "listening to recordings of the show",
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
            "helps_with": "learning or playing this song; it is not a universal chart",
            "provenance": "contextual resource",
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


def _composer_brief(question: str, response: ExperienceResponse) -> str:
    """Build the structured reasoning context for the model-first composer."""

    brief = {
        "latest_question": question,
        "grounded_agent_answer": response.answer,
        "recent_conversation": [turn.model_dump() for turn in response.conversation[-8:]],
        "candidate_blocks": [_block_brief(index, block) for index, block in enumerate(response.blocks)],
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
    for section in plan.sections:
        section_indexes = []
        for index in section.candidate_indexes:
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
    return response.model_copy(update={"blocks": selected_blocks, "layout": layout})


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
            "Choose the most coherent main-column layout for the latest question using the grounded brief below. "
            "Reason from the question, answer, coverage, candidate scope, and provenance. "
            "Select the smallest useful set of candidates and arrange them in primary, supporting, context, or media regions. "
            "Omission is the default: including an irrelevant candidate is worse than omitting optional material. Most questions need one to three candidates. Use omitted_candidate_indexes to explicitly exclude candidates that do not answer the latest question. "
            "The page title already identifies the main song, show, or performance. Omit an entity card when it only repeats that title and has no additional details. "
            "For a song question, prefer the song_overview block as the standard facts panel. For a first/last performance question, prefer the performance_extremes block, which already combines both endpoints; omit the generic performance_list unless the user asks for the full known list. "
            "For a show question, prefer the show_setlist block in the main panel; do not select only the show card when an ordered setlist is available. "
            "When approved recordings are available for a show, include the recording_list for show overview or listening questions so the main panel exposes the recording links. "
            "When source-reviewed performers are available for a show, include the performer_list for lineup, guest, musician, or instrument questions; it groups each person with their recorded instruments. "
            "When named guitar claims are available for a show, include the equipment_list for Jerry Garcia guitar or equipment questions; distinguish date-range evidence from specific-show evidence and do not treat a date-range claim as a complete equipment log. "
            "Do not select a provenance note merely because a resource is present; provenance is retained in the response metadata and should not become a visible page section unless the user explicitly asks about sources or attribution. "
            "Do not select library coverage for ordinary song, show, performance, date, setlist, credit, media, or listening questions. Select coverage only when the user directly asks about library scope, completeness, coverage, or a limitation that the answer must explain. "
            "Do not choose learning, media, or reading material unless it genuinely helps the question. "
            "For a direct factual, count, date, setlist, or coverage question, select only the factual entity/performance/coverage evidence needed to answer it; omit chord arrangements, contextual resource lists, and media unless the user explicitly asks for them. "
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
