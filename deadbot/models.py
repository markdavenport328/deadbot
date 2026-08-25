"""Provider-neutral chat-model construction.

The LangGraph agent depends only on a LangChain chat model with tool binding.
Adding another provider means implementing ModelProvider and registering it
below; the graph and domain tools remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama

from deadbot.config import Settings


class ModelProvider(Protocol):
    """The stable provider contract used by the Deadbot agent graph."""

    def create_chat_model(self) -> BaseChatModel:
        """Return a tool-capable chat model."""


@dataclass(frozen=True)
class OllamaProvider:
    """Local Ollama implementation of the provider contract."""

    model: str
    base_url: str
    thinking: bool

    def create_chat_model(self) -> BaseChatModel:
        return ChatOllama(
            model=self.model,
            base_url=self.base_url,
            reasoning=self.thinking,
            temperature=0,
        )


def create_model_provider(settings: Settings) -> ModelProvider:
    """Select a registered provider from configuration.

    Keep this registry intentionally small. A future provider adds an adapter
    here without altering agent behavior or data retrieval contracts.
    """

    if settings.model_provider == "ollama":
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            thinking=settings.ollama_thinking,
        )
    raise ValueError(
        f"Unsupported DEADBOT_MODEL_PROVIDER={settings.model_provider!r}. "
        "Registered providers: ollama."
    )
