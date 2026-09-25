import sys
from types import SimpleNamespace

import pytest

from deadbot.config import Settings
from deadbot.models import OllamaProvider, OpenAIProvider, create_model_provider
from deadbot.storage import create_canonical_store


def test_sqlite_is_the_default_runtime_store(monkeypatch, tmp_path):
    monkeypatch.delenv("DEADBOT_DATA_STORE", raising=False)
    monkeypatch.delenv("DEADBOT_SQLITE_PATH", raising=False)
    settings = Settings.from_env(env_path=tmp_path / "absent.env")
    assert settings.data_store == "sqlite"
    assert settings.sqlite_path is None


def test_sqlite_path_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_SQLITE_PATH", str(tmp_path / "custom.sqlite"))
    assert Settings.from_env(env_path=tmp_path / "absent.env").sqlite_path == tmp_path / "custom.sqlite"


def test_sqlite_store_is_created_from_a_built_file(built_sqlite, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")  # trust the file as a deployment would

    def must_not_rebuild(*_args, **_kwargs):
        raise AssertionError("ensure_current ran on Vercel")

    monkeypatch.setattr("deadbot.sqlite_build.ensure_current", must_not_rebuild)
    store = create_canonical_store(Settings(data_store="sqlite", sqlite_path=built_sqlite))
    try:
        assert store.resolve_song("Dark Star")
    finally:
        store.close()


def test_local_sqlite_store_is_refreshed_before_it_opens(built_sqlite, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    calls = []

    def record(path, *_args, **_kwargs):
        calls.append(path)
        return path

    monkeypatch.setattr("deadbot.sqlite_build.ensure_current", record)
    store = create_canonical_store(Settings(data_store="sqlite", sqlite_path=built_sqlite))
    try:
        assert calls == [built_sqlite]
    finally:
        store.close()


def test_unknown_store_is_rejected():
    with pytest.raises(ValueError, match="sqlite"):
        create_canonical_store(Settings(data_store="csv"))


def test_postgres_store_requires_a_database_url():
    try:
        create_canonical_store(Settings(data_store="postgres"))
    except ValueError as error:
        assert "requires DEADBOT_DATABASE_URL" in str(error)
    else:
        raise AssertionError("PostgreSQL selection without a database URL should fail")


def test_canonical_store_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEADBOT_DATA_STORE", "POSTGRES")
    monkeypatch.setenv("DEADBOT_DATABASE_URL", "postgresql://example/deadbot")
    settings = Settings.from_env()
    assert settings.data_store == "postgres"
    assert settings.database_url == "postgresql://example/deadbot"


def test_local_env_file_supplies_settings_when_process_environment_is_unset(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local settings\nDEADBOT_DATA_STORE=postgres\n"
        "DEADBOT_DATABASE_URL='postgresql://local/deadbot'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DEADBOT_DATA_STORE", raising=False)
    monkeypatch.delenv("DEADBOT_DATABASE_URL", raising=False)

    settings = Settings.from_env(env_file)

    assert settings.data_store == "postgres"
    assert settings.database_url == "postgresql://local/deadbot"


def test_process_environment_overrides_local_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEADBOT_DATA_STORE=postgres\n", encoding="utf-8")
    monkeypatch.setenv("DEADBOT_DATA_STORE", "csv")

    assert Settings.from_env(env_file).data_store == "csv"


def test_database_url_falls_back_to_standard_environment_name(monkeypatch):
    monkeypatch.delenv("DEADBOT_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/standard")

    settings = Settings.from_env()

    assert settings.database_url == "postgresql://example/standard"


def test_deadbot_database_url_takes_precedence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/standard")
    monkeypatch.setenv("DEADBOT_DATABASE_URL", "postgresql://example/deadbot")

    settings = Settings.from_env()

    assert settings.database_url == "postgresql://example/deadbot"


def test_postgres_store_factory_passes_dsn_without_connecting(monkeypatch):
    from deadbot.postgres import PostgresStore

    selected_store = object()
    calls = []

    def from_dsn(cls, dsn):
        calls.append(dsn)
        return selected_store

    monkeypatch.setattr(PostgresStore, "from_dsn", classmethod(from_dsn))

    result = create_canonical_store(
        Settings(data_store="postgres", database_url="postgresql://example/deadbot")
    )

    assert result is selected_store
    assert calls == ["postgresql://example/deadbot"]


def test_ollama_is_the_default_provider():
    provider = create_model_provider(Settings())
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen3:8b"


def test_hardening_settings_have_safe_defaults():
    settings = Settings()
    assert settings.rate_limit_per_minute == 10
    assert settings.conversation_window == 12


def test_hardening_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEADBOT_RATE_LIMIT_PER_MINUTE", "25")
    monkeypatch.setenv("DEADBOT_CONVERSATION_WINDOW", "6")
    settings = Settings.from_env()
    assert settings.rate_limit_per_minute == 25
    assert settings.conversation_window == 6


def test_blank_numeric_environment_values_use_defaults(monkeypatch):
    monkeypatch.setenv("DEADBOT_MAX_TOOL_ROUNDS", "")
    monkeypatch.setenv("DEADBOT_RATE_LIMIT_PER_MINUTE", "")
    monkeypatch.setenv("DEADBOT_CONVERSATION_WINDOW", "")
    settings = Settings.from_env()
    assert settings.max_tool_rounds == 8
    assert settings.rate_limit_per_minute == 10
    assert settings.conversation_window == 12


def test_openai_is_a_registered_alternative_provider():
    provider = create_model_provider(
        Settings(model_provider="openai", openai_model="gpt-test", openai_api_key="test-key")
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-test"


def test_openai_provider_uses_responses_api(monkeypatch):
    captured_options = {}

    class FakeChatOpenAI:
        def __init__(self, **options):
            captured_options.update(options)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))

    model = OpenAIProvider(model="gpt-5.6-luna", api_key="test-key").create_chat_model()

    assert isinstance(model, FakeChatOpenAI)
    assert captured_options["use_responses_api"] is True


def test_model_streaming_defaults_true_for_openai(monkeypatch):
    monkeypatch.delenv("DEADBOT_MODEL_STREAMING", raising=False)
    monkeypatch.setenv("DEADBOT_MODEL_PROVIDER", "openai")
    settings = Settings.from_env()
    assert settings.model_streaming is True


def test_model_streaming_defaults_false_for_ollama(monkeypatch):
    monkeypatch.delenv("DEADBOT_MODEL_STREAMING", raising=False)
    monkeypatch.setenv("DEADBOT_MODEL_PROVIDER", "ollama")
    settings = Settings.from_env()
    assert settings.model_streaming is False


def test_model_streaming_env_var_overrides_the_provider_default(monkeypatch):
    monkeypatch.setenv("DEADBOT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("DEADBOT_MODEL_STREAMING", "false")
    settings = Settings.from_env()
    assert settings.model_streaming is False


def test_unknown_provider_fails_clearly():
    settings = Settings(model_provider="unknown")
    try:
        create_model_provider(settings)
    except ValueError as error:
        assert "Registered providers: ollama, openai" in str(error)
    else:
        raise AssertionError("Unknown provider should fail")
