from deadbot.config import Settings
from deadbot.models import OllamaProvider, OpenAIProvider, create_model_provider
from deadbot.storage import create_canonical_store


def test_postgres_is_the_only_runtime_store():
    settings = Settings()
    assert settings.data_store == "postgres"
    assert settings.database_url is None
    try:
        create_canonical_store(settings)
    except ValueError as error:
        assert "requires DEADBOT_DATABASE_URL" in str(error)
    else:
        raise AssertionError("PostgreSQL runtime must require a database URL")


def test_postgres_store_requires_a_database_url():
    try:
        create_canonical_store(Settings(data_store="postgres"))
    except ValueError as error:
        assert "requires DEADBOT_DATABASE_URL" in str(error)
    else:
        raise AssertionError("PostgreSQL selection without a database URL should fail")


def test_unknown_canonical_store_fails_clearly():
    try:
        create_canonical_store(Settings(data_store="unknown"))
    except ValueError as error:
        assert "serves only PostgreSQL" in str(error)
    else:
        raise AssertionError("Unknown canonical store should fail")


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


def test_model_guided_composition_is_enabled_by_default():
    settings = Settings()
    assert settings.composer_enabled is True
    assert settings.composer_max_blocks == 8


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
    monkeypatch.setenv("DEADBOT_COMPOSER_MAX_BLOCKS", "")
    monkeypatch.setenv("DEADBOT_RATE_LIMIT_PER_MINUTE", "")
    monkeypatch.setenv("DEADBOT_CONVERSATION_WINDOW", "")
    settings = Settings.from_env()
    assert settings.max_tool_rounds == 8
    assert settings.composer_max_blocks == 8
    assert settings.rate_limit_per_minute == 10
    assert settings.conversation_window == 12


def test_openai_is_a_registered_alternative_provider():
    provider = create_model_provider(
        Settings(model_provider="openai", openai_model="gpt-test", openai_api_key="test-key")
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-test"


def test_unknown_provider_fails_clearly():
    settings = Settings(model_provider="unknown")
    try:
        create_model_provider(settings)
    except ValueError as error:
        assert "Registered providers: ollama, openai" in str(error)
    else:
        raise AssertionError("Unknown provider should fail")
