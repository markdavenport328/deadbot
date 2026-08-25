"""Bounded model-guided selection of already validated experience blocks."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from deadbot.config import Settings
from deadbot.experience import ExperienceBlock, ExperienceResponse
from deadbot.models import ModelProvider, create_model_provider


logger = logging.getLogger(__name__)


class CompositionPlan(BaseModel):
    """The model may only select indices from the supplied candidate list."""

    model_config = ConfigDict(extra="forbid")
    selected_block_indexes: list[int] = Field(default_factory=list, max_length=8)


class ExperienceComposer(Protocol):
    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        """Return a response containing only an approved ordering of its blocks."""


def _block_label(block: ExperienceBlock) -> str:
    """Return compact, non-URL metadata for a model's selection prompt."""

    if block.type == "entity_card":
        return f"{block.entity_type}: {block.title}"
    if block.type == "resource_list":
        return f"resource list: {block.title}"
    if block.type == "media_link":
        return f"{block.provider} media: {block.title}"
    if block.type == "arrangement":
        return block.title
    if block.type == "provenance_note":
        return "provenance note"
    return "coverage gap"


def _candidate_packet(blocks: list[ExperienceBlock]) -> str:
    """Serialize only the selection metadata a composer needs."""

    return json.dumps(
        [{"index": index, "type": block.type, "label": _block_label(block)} for index, block in enumerate(blocks)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def apply_composition_plan(response: ExperienceResponse, plan: CompositionPlan) -> ExperienceResponse:
    """Validate a plan by resolving it against server-owned candidate blocks.

    Provenance and coverage-gap blocks are mandatory once present. A malformed,
    empty, or model-invented plan falls back to the deterministic candidate
    sequence rather than changing user-visible content.
    """

    valid_indexes: list[int] = []
    for index in plan.selected_block_indexes:
        if 0 <= index < len(response.blocks) and index not in valid_indexes:
            valid_indexes.append(index)
    if not valid_indexes:
        return response

    required_indexes = [
        index
        for index, block in enumerate(response.blocks)
        if block.type in {"provenance_note", "gap_state"}
    ]
    for index in required_indexes:
        if index not in valid_indexes:
            valid_indexes.append(index)

    selected_blocks = [response.blocks[index] for index in valid_indexes]
    return response.model_copy(update={"blocks": selected_blocks})


class DeterministicComposer:
    """Keep the adapter's candidate ordering unchanged."""

    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        return response


class ModelGuidedComposer:
    """Use a structured model response to choose existing content blocks only."""

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
        candidate_packet = _candidate_packet(response.blocks)
        prompt = (
            "Select the smallest useful sequence of candidate UI blocks for the user's latest question. "
            "You may only return candidate indexes. Do not create content, facts, sources, URLs, or block types. "
            "Prefer directly relevant entity, media, and source blocks; preserve context only when useful. "
            "The server will retain any required provenance or coverage-gap block.\n\n"
            f"Question: {question}\n"
            f"Candidates: {candidate_packet}"
        )
        try:
            result = self.selector.invoke(
                [
                    SystemMessage(content="You are Deadbot's bounded interface composer. Return only the requested structured selection."),
                    HumanMessage(content=prompt),
                ]
            )
            plan = result if isinstance(result, CompositionPlan) else CompositionPlan.model_validate(result)
            if len(plan.selected_block_indexes) > self.max_blocks:
                plan = plan.model_copy(update={"selected_block_indexes": plan.selected_block_indexes[:self.max_blocks]})
            composed = apply_composition_plan(response, plan)
            logger.info(
                "Applied model composition plan: candidates=%s selected=%s",
                len(response.blocks),
                plan.selected_block_indexes,
            )
            return composed
        except Exception as error:
            logger.warning(
                "Model composer failed (%s); using deterministic candidate order.",
                type(error).__name__,
            )
            return response


def create_experience_composer(settings: Settings, provider: ModelProvider | None = None) -> ExperienceComposer:
    """Return the configured composer without changing the agent's tool contract."""

    if not settings.composer_enabled:
        return DeterministicComposer()
    return ModelGuidedComposer(provider or create_model_provider(settings), max_blocks=settings.composer_max_blocks)
