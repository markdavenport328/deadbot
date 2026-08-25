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


@dataclass(frozen=True)
class OpenAIProvider:
    """Hosted OpenAI-compatible implementation for deployed environments."""

    model: str
    api_key: str | None = None
    base_url: str | None = None

    def create_chat_model(self) -> BaseChatModel:
        # Keep the hosted-provider dependency out of the local Ollama import
        # path. Local development can therefore continue without it installed.
        from langchain_openai import ChatOpenAI

        options = {
            "model": self.model,
            "temperature": 0,
        }
        if self.api_key:
            options["api_key"] = self.api_key
        if self.base_url:
            options["base_url"] = self.base_url
        return ChatOpenAI(**options)


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
    if settings.model_provider == "openai":
        return OpenAIProvider(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    raise ValueError(
        f"Unsupported DEADBOT_MODEL_PROVIDER={settings.model_provider!r}. "
        "Registered providers: ollama, openai."
    )
