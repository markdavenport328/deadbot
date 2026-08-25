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


@dataclass(frozen=True)
class Settings:
    """Configuration shared by the graph and model-provider layer."""

    model_provider: str = "ollama"
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_thinking: bool = False
    max_tool_rounds: int = 8
    composer_enabled: bool = True
    composer_max_blocks: int = 8

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model_provider=getenv("DEADBOT_MODEL_PROVIDER", "ollama"),
            ollama_model=getenv("DEADBOT_OLLAMA_MODEL", "qwen3:8b"),
            ollama_base_url=getenv("DEADBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_thinking=_as_bool(getenv("DEADBOT_OLLAMA_THINKING"), False),
            max_tool_rounds=int(getenv("DEADBOT_MAX_TOOL_ROUNDS", "8")),
            composer_enabled=_as_bool(getenv("DEADBOT_COMPOSER_ENABLED"), True),
            composer_max_blocks=int(getenv("DEADBOT_COMPOSER_MAX_BLOCKS", "8")),
        )
