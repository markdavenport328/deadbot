"""Runtime settings loaded from environment variables.

The model provider is selected here rather than from application code so that
changing a model does not change the agent graph or its tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    """Parse an integer environment value, treating blank values as unset."""

    if value is None or not value.strip():
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    """Configuration shared by the graph and model-provider layer."""

    model_provider: str = "ollama"
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_thinking: bool = False
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    max_tool_rounds: int = 8
    composer_enabled: bool = True
    composer_max_blocks: int = 8
    rate_limit_per_minute: int = 10
    conversation_window: int = 12

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model_provider=getenv("DEADBOT_MODEL_PROVIDER", "ollama"),
            ollama_model=getenv("DEADBOT_OLLAMA_MODEL", "qwen3:8b"),
            ollama_base_url=getenv("DEADBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_thinking=_as_bool(getenv("DEADBOT_OLLAMA_THINKING"), False),
            openai_model=getenv("DEADBOT_OPENAI_MODEL", "gpt-4o-mini"),
            openai_base_url=getenv("DEADBOT_OPENAI_BASE_URL") or None,
            openai_api_key=getenv("OPENAI_API_KEY"),
            max_tool_rounds=_as_int(getenv("DEADBOT_MAX_TOOL_ROUNDS"), 8),
            composer_enabled=_as_bool(getenv("DEADBOT_COMPOSER_ENABLED"), True),
            composer_max_blocks=_as_int(getenv("DEADBOT_COMPOSER_MAX_BLOCKS"), 8),
            rate_limit_per_minute=_as_int(getenv("DEADBOT_RATE_LIMIT_PER_MINUTE"), 10),
            conversation_window=_as_int(getenv("DEADBOT_CONVERSATION_WINDOW"), 12),
        )
