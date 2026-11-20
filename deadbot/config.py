"""Runtime settings loaded from environment variables.

The model provider is selected here rather than from application code so that
changing a model does not change the agent graph or its tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    # Where the built catalog lives; unset means build/deadbot.sqlite.
    sqlite_path: Path | None = None
    model_provider: str = "ollama"
    ollama_model: str = "qwen3:8b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_thinking: bool = False
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    # Reasoning effort for OpenAI reasoning models (minimal, low, medium, high).
    # Unset means the model's default. Lower effort cuts latency per model call.
    openai_reasoning_effort: str | None = None
    # Stream model output so finish_response's lead can reach the
    # visitor before the whole turn finishes. Defaults to the openai provider
    # since Ollama tool-call streaming is not relied on here.
    model_streaming: bool = False
    max_tool_rounds: int = 8
    rate_limit_per_minute: int = 10
    # Reshaping a grid is a cheap read of the library, so it has its own per-IP
    # budget and never spends the question allowance above.
    grid_rate_limit_per_minute: int = 60
    conversation_window: int = 12
    # Serve a stored answer for a repeated fresh question (the opening chips
    # above all) while the data version and deployed commit are unchanged.
    response_cache: bool = True
    response_cache_ttl_seconds: int = 7 * 24 * 60 * 60
    # Signs the research notebook the browser carries between turns. Unset
    # means turns run without a notebook. Kept out of repr so it never lands
    # in a log line.
    notebook_secret: str | None = field(default=None, repr=False)

    # --- Provider prompt cache and usage limits (documented in .env.example) ---
    # How many provider cache keys the conversations are spread over. One key
    # lets every visitor share the cached system prompt and tool schemas.
    prompt_cache_shards: int = 1
    # Mark the end of the system prompt as an explicit cache breakpoint
    # (OpenAI GPT-5.6 and later only; other models may refuse the request).
    prompt_cache_breakpoint: bool = False
    # Read the visitor's address from the platform's forwarded headers. Only
    # safe behind a proxy that overwrites them, as Vercel does.
    trust_forwarded_ip: bool = False
    # Questions that reach the model, per visitor (a signed cookie carries the
    # count between function instances). 0 turns a limit off.
    visitor_limit_per_minute: int = 6
    visitor_limit_per_day: int = 40
    # Per client address, per function instance (rate_limit_per_minute above
    # is the per-minute partner of the daily figure).
    rate_limit_per_day: int = 150
    # Requests from one address that arrive without a valid allowance cookie.
    new_visitors_per_day: int = 20
    # Everything one function instance will send to the model in a day.
    instance_limit_per_day: int = 500
    # Characters of browser-supplied conversation replayed to the model; the
    # oldest turns are dropped first.
    conversation_max_chars: int = 24_000
    # Seconds one model call may stay silent, and how often a failed call is
    # tried again. Together they fit inside the function's 60 seconds.
    model_timeout_seconds: int = 25
    model_max_retries: int = 1
    # Seconds a whole turn may take before it ends with an honest error rather
    # than being cut off by the platform. 0 means no budget.
    turn_budget_seconds: int = 0

    def without_limits(self) -> "Settings":
        """For build steps and measurement scripts that ask many questions in one process."""

        # Imported here so this block stays self-contained in a file others edit.
        from dataclasses import replace

        return replace(
            self,
            rate_limit_per_minute=0,
            rate_limit_per_day=0,
            visitor_limit_per_minute=0,
            visitor_limit_per_day=0,
            new_visitors_per_day=0,
            instance_limit_per_day=0,
            turn_budget_seconds=0,
        )

    @classmethod
    def from_env(cls, env_path: Path = DEFAULT_ENV_PATH) -> "Settings":
        file_values = _read_env_file(env_path)

        def value(key: str, default: str | None = None) -> str | None:
            return environ[key] if key in environ else file_values.get(key, default)

        model_provider = value("DEADBOT_MODEL_PROVIDER", "ollama") or "ollama"

        return cls(
            sqlite_path=Path(sqlite_path) if (sqlite_path := value("DEADBOT_SQLITE_PATH")) else None,
            model_provider=model_provider,
            ollama_model=value("DEADBOT_OLLAMA_MODEL", "qwen3:8b") or "qwen3:8b",
            ollama_base_url=value("DEADBOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434",
            ollama_thinking=_as_bool(value("DEADBOT_OLLAMA_THINKING"), False),
            model_streaming=_as_bool(value("DEADBOT_MODEL_STREAMING"), model_provider == "openai"),
            openai_model=value("DEADBOT_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            openai_base_url=value("DEADBOT_OPENAI_BASE_URL") or None,
            openai_api_key=value("OPENAI_API_KEY"),
            openai_reasoning_effort=(value("DEADBOT_OPENAI_REASONING_EFFORT") or "").strip().lower() or None,
            max_tool_rounds=_as_int(value("DEADBOT_MAX_TOOL_ROUNDS"), 8),
            rate_limit_per_minute=_as_int(value("DEADBOT_RATE_LIMIT_PER_MINUTE"), 10),
            grid_rate_limit_per_minute=_as_int(value("DEADBOT_GRID_RATE_LIMIT_PER_MINUTE"), 60),
            conversation_window=_as_int(value("DEADBOT_CONVERSATION_WINDOW"), 12),
            response_cache=_as_bool(value("DEADBOT_RESPONSE_CACHE"), True),
            response_cache_ttl_seconds=_as_int(value("DEADBOT_RESPONSE_CACHE_TTL_SECONDS"), 7 * 24 * 60 * 60),
            notebook_secret=(value("DEADBOT_NOTEBOOK_SECRET") or "").strip() or None,
            prompt_cache_shards=_as_int(value("DEADBOT_PROMPT_CACHE_SHARDS"), 1),
            prompt_cache_breakpoint=_as_bool(value("DEADBOT_PROMPT_CACHE_BREAKPOINT"), False),
            # Vercel sets VERCEL=1 and overwrites the forwarded headers itself.
            trust_forwarded_ip=_as_bool(value("DEADBOT_TRUST_FORWARDED_IP"), bool(environ.get("VERCEL"))),
            visitor_limit_per_minute=_as_int(value("DEADBOT_VISITOR_LIMIT_PER_MINUTE"), 6),
            visitor_limit_per_day=_as_int(value("DEADBOT_VISITOR_LIMIT_PER_DAY"), 40),
            rate_limit_per_day=_as_int(value("DEADBOT_RATE_LIMIT_PER_DAY"), 150),
            new_visitors_per_day=_as_int(value("DEADBOT_NEW_VISITORS_PER_DAY"), 20),
            instance_limit_per_day=_as_int(value("DEADBOT_INSTANCE_LIMIT_PER_DAY"), 500),
            conversation_max_chars=_as_int(value("DEADBOT_CONVERSATION_MAX_CHARS"), 24_000),
            model_timeout_seconds=_as_int(value("DEADBOT_MODEL_TIMEOUT_SECONDS"), 25),
            model_max_retries=_as_int(value("DEADBOT_MODEL_MAX_RETRIES"), 1),
            # A hosted model answers inside the function's 60 seconds; a local
            # model on a laptop may need longer, so it gets no budget.
            turn_budget_seconds=_as_int(value("DEADBOT_TURN_BUDGET_SECONDS"), 55 if model_provider == "openai" else 0),
        )
