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


# The silence allowed when a call is not streamed, or when no timeout is set.
UNSTREAMED_TIMEOUT_SECONDS = 90


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
    reasoning_effort: str | None = None
    # Seconds a call may go without sending anything, and how many times a
    # failed call is tried again. The hosting function is stopped at 60
    # seconds, so (retries + 1) x timeout has to fit inside that: two silent
    # waits of 25 seconds do, where the earlier 90 seconds with two retries
    # could wait four and a half minutes for a function that was long gone.
    timeout: float = 25
    max_retries: int = 1

    def create_chat_model(self) -> BaseChatModel:
        # Keep the hosted-provider dependency out of the local Ollama import
        # path. Local development can therefore continue without it installed.
        from langchain_openai import ChatOpenAI

        options = {
            "model": self.model,
            # GPT-5.6 reasoning models require the Responses API when they
            # make function calls. It is also the API OpenAI recommends for
            # reasoning and multi-turn workflows.
            "use_responses_api": True,
            # A stalled request otherwise waits the client's default ten
            # minutes. A streamed call that has sent nothing for this long is
            # treated as stalled; it is cut off and retried.
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
        # A reasoning model sets its own sampling, and GPT-6 models refuse a
        # temperature outright; a model without reasoning keeps temperature 0.
        if self.reasoning_effort:
            options["reasoning"] = {"effort": self.reasoning_effort}
        else:
            options["temperature"] = 0
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
        timeout = settings.model_timeout_seconds if settings.model_timeout_seconds > 0 else UNSTREAMED_TIMEOUT_SECONDS
        if not settings.model_streaming:
            # Unstreamed, nothing arrives until the whole answer is written, so
            # the silence allowed has to cover a whole call.
            timeout = max(timeout, UNSTREAMED_TIMEOUT_SECONDS)
        return OpenAIProvider(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            reasoning_effort=settings.openai_reasoning_effort,
            timeout=timeout,
            max_retries=max(settings.model_max_retries, 0),
        )
    raise ValueError(
        f"Unsupported DEADBOT_MODEL_PROVIDER={settings.model_provider!r}. "
        "Registered providers: ollama, openai."
    )
