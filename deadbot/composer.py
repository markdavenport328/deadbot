"""Model-first composition of grounded, server-validated experience blocks."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from deadbot.config import Settings
from deadbot.experience import (
    ConversationTurn,
    EditorialBlock,
    ExperienceBlock,
    ExperienceMode,
    ExperienceResponse,
    LayoutSection,
)
from deadbot.models import ModelProvider, create_model_provider


logger = logging.getLogger(__name__)


class CompositionError(RuntimeError):
    """The final editor did not produce a usable response."""


class CompositionPlan(BaseModel):
    """The model's final editorial decision over grounded material."""

    model_config = ConfigDict(extra="forbid")
    chat_answer: str = Field(min_length=1)
    body_title: str = Field(min_length=1)
    body_lead: str = Field(min_length=1)
    mode: ExperienceMode
    body_blocks: list[EditorialBlock] = Field(max_length=8)
    body_candidate_indexes: list[int] = Field(max_length=24)


class ExperienceComposer(Protocol):
    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        """Return a response with an approved model-selected layout."""


def _block_brief(index: int, block: ExperienceBlock) -> dict[str, Any]:
    """Give the editor the grounded candidate itself, without editorial hints."""

    return {"index": index, "block": block.model_dump(mode="json")}


def _composer_brief(question: str, response: ExperienceResponse) -> str:
    """Build the grounded context for the final editor."""

    brief = {
        "latest_question": question,
        "grounded_agent_answer": response.answer,
        "recent_conversation": [turn.model_dump() for turn in response.conversation[-8:]],
        "allowed_candidate_indexes": list(range(len(response.blocks))),
        "candidate_blocks": [_block_brief(index, block) for index, block in enumerate(response.blocks)],
    }
    return json.dumps(brief, ensure_ascii=False, separators=(",", ":"))


def apply_composition_plan(response: ExperienceResponse, plan: CompositionPlan) -> ExperienceResponse:
    """Resolve referenced candidates and combine them with model-shaped blocks."""

    expected_indexes = set(range(len(response.blocks)))
    selected_indexes = plan.body_candidate_indexes
    if (
        len(selected_indexes) != len(set(selected_indexes))
        or any(index not in expected_indexes for index in selected_indexes)
        or (not selected_indexes and not plan.body_blocks)
    ):
        return response

    selected_blocks: list[ExperienceBlock] = [*plan.body_blocks, *(response.blocks[index] for index in selected_indexes)]
    layout = [
        LayoutSection(
            region="primary" if start == 0 else "supporting",
            block_indexes=list(range(start, min(start + 8, len(selected_blocks)))),
        )
        for start in range(0, len(selected_blocks), 8)
    ]
    chat_answer = plan.chat_answer.strip()
    conversation = list(response.conversation)
    for index in range(len(conversation) - 1, -1, -1):
        if conversation[index].role == "assistant":
            conversation[index] = ConversationTurn(role="assistant", text=chat_answer)
            break
    return response.model_copy(
        update={
            "answer": chat_answer,
            "title": plan.body_title.strip(),
            "body_lead": plan.body_lead.strip(),
            "conversation": conversation,
            "blocks": selected_blocks,
            "layout": layout,
            "mode": plan.mode,
        }
    )


class DeterministicComposer:
    """Compatibility path for tests and offline tooling without a model."""

    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        return response


class ModelGuidedComposer:
    """Let the model turn grounded research into the complete response."""

    def __init__(self, provider: ModelProvider | None = None, selector: Any | None = None):
        if selector is None:
            if provider is None:
                raise ValueError("A model provider or structured selector is required.")
            model = provider.create_chat_model()
            selector = model.with_structured_output(CompositionPlan, method="json_schema").bind(stream=False)
        self.selector = selector

    def compose(self, question: str, response: ExperienceResponse) -> ExperienceResponse:
        prompt = (
            "You are Deadbot's editor and musical director: a perceptive, companionable Grateful Dead guide and DJ with access to exhaustive knowledge of the facts and lore of the Grateful Dead's musical and performing history."
            "Give the visitor a crisp answer in chat, then make the main body the rewarding part: a clear title, a short synthesis that notices what matters, and useful supporting material in a natural reading order. "
            "Chat and body work together instead of repeating each other. Be selective, specific, and inviting. Make the response interesting through concrete facts and connections in the brief. Favor pathways to listening, weaving links to recordings for full shows or songs into your answers."
            "You may shape grounded facts into editorial body blocks using narrative, fact_grid, or timeline presentation, and may also reuse any supplied candidate blocks by index. Avoid inventing commentary that is not grounded in the brief.\n\n"
            f"Grounded composition brief: {_composer_brief(question, response)}\n\n"
            "Edit this into one coherent response that prioritizes the most relevant information and avoids repitition. Answer the user's question directly and also seek to anticipate what a curious dead fan might want to know or do next, such as listening to a song, exploring a show, or learning about a band member.\n"
        )
        try:
            result = self.selector.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are Deadbot's final editor. Turn grounded research into a concise chat answer and a genuinely useful main body."
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            plan = result if isinstance(result, CompositionPlan) else CompositionPlan.model_validate(result)
            composed = apply_composition_plan(response, plan)
            if composed is response:
                raise CompositionError("The final editor referenced unavailable material.")
            logger.info("Applied model composition plan: candidates=%s selected=%s", len(response.blocks), len(plan.body_candidate_indexes))
            return composed
        except CompositionError:
            raise
        except Exception as error:
            logger.exception("Model editor failed")
            raise CompositionError("The final editor did not produce a usable response.") from error


def create_experience_composer(settings: Settings, provider: ModelProvider | None = None) -> ExperienceComposer:
    """Return the final response editor without changing the agent's tool contract."""

    return ModelGuidedComposer(provider or create_model_provider(settings))
