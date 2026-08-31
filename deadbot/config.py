"""Runtime settings loaded from environment variables.

The model provider is selected here rather than from application code so that
changing a model does not change the agent graph or its tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = ROOT / ".env"


def _read_env_file(path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Read the project's deliberately simple local .env format.

    Process environment values remain authoritative. This is intentionally
    small rather than a general shell parser: the checked-in template only
    needs comments, blank lines, and KEY=value entries.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


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

    data_store: str = "postgres"
    database_url: str | None = None
    model_provider: str = "ollama"
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_thinking: bool = False
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    max_tool_rounds: int = 8
    composer_enabled: bool = True
    rate_limit_per_minute: int = 10
    conversation_window: int = 12

    @classmethod
    def from_env(cls, env_path: Path = DEFAULT_ENV_PATH) -> "Settings":
        file_values = _read_env_file(env_path)

        def value(key: str, default: str | None = None) -> str | None:
            return environ[key] if key in environ else file_values.get(key, default)

        database_url = (
            environ.get("DEADBOT_DATABASE_URL")
            or environ.get("DATABASE_URL")
            or file_values.get("DEADBOT_DATABASE_URL")
            or file_values.get("DATABASE_URL")
            or None
        )

        return cls(
            data_store=(value("DEADBOT_DATA_STORE", "postgres") or "postgres").strip().lower(),
            database_url=database_url,
            model_provider=value("DEADBOT_MODEL_PROVIDER", "ollama") or "ollama",
            ollama_model=value("DEADBOT_OLLAMA_MODEL", "qwen3:8b") or "qwen3:8b",
            ollama_base_url=value("DEADBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434",
            ollama_thinking=_as_bool(value("DEADBOT_OLLAMA_THINKING"), False),
            openai_model=value("DEADBOT_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            openai_base_url=value("DEADBOT_OPENAI_BASE_URL") or None,
            openai_api_key=value("OPENAI_API_KEY"),
            max_tool_rounds=_as_int(value("DEADBOT_MAX_TOOL_ROUNDS"), 8),
            composer_enabled=_as_bool(value("DEADBOT_COMPOSER_ENABLED"), True),
            rate_limit_per_minute=_as_int(value("DEADBOT_RATE_LIMIT_PER_MINUTE"), 10),
            conversation_window=_as_int(value("DEADBOT_CONVERSATION_WINDOW"), 12),
        )
