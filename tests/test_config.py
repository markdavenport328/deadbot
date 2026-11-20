import sys
from types import SimpleNamespace

import pytest

from deadbot.config import Settings
from deadbot.models import OllamaProvider, OpenAIProvider, create_model_provider
from deadbot.storage import create_canonical_store


def test_the_sqlite_path_defaults_to_the_build_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("DEADBOT_SQLITE_PATH", raising=False)
    settings = Settings.from_env(env_path=tmp_path / "absent.env")
    assert settings.sqlite_path is None


def test_sqlite_path_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_SQLITE_PATH", str(tmp_path / "custom.sqlite"))
    assert Settings.from_env(env_path=tmp_path / "absent.env").sqlite_path == tmp_path / "custom.sqlite"


def test_sqlite_store_is_created_from_a_built_file(built_sqlite, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")  # trust the file as a deployment would

    def must_not_rebuild(*_args, **_kwargs):
        raise AssertionError("ensure_current ran on Vercel")

    monkeypatch.setattr("deadbot.sqlite_build.ensure_current", must_not_rebuild)
    store = create_canonical_store(Settings(sqlite_path=built_sqlite))
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
    store = create_canonical_store(Settings(sqlite_path=built_sqlite))
    try:
        assert calls == [built_sqlite]
    finally:
        store.close()


@pytest.mark.parametrize("stale", ["postgres", "POSTGRES", "csv", ""])
def test_a_leftover_store_variable_is_ignored(built_sqlite, monkeypatch, tmp_path, stale):
    # An older deployment chose its store with DEADBOT_DATA_STORE and a
    # database URL. SQLite is the only store now, so neither is read and a
    # value left behind in an environment cannot break a deploy.
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DEADBOT_DATA_STORE", stale)
    monkeypatch.setenv("DEADBOT_DATABASE_URL", "postgresql://example/deadbot")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/standard")
    monkeypatch.setenv("DEADBOT_SQLITE_PATH", str(built_sqlite))
    settings = Settings.from_env(env_path=tmp_path / "absent.env")
    assert not hasattr(settings, "data_store")
    assert not hasattr(settings, "database_url")
    store = create_canonical_store(settings)
    try:
        assert type(store).__name__ == "SqliteCanonicalStore"
        store.verify_ready()
    finally:
        store.close()


def test_local_env_file_supplies_settings_when_process_environment_is_unset(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local settings\nDEADBOT_OLLAMA_MODEL=local-model\n"
        "DEADBOT_SQLITE_PATH='build/local.sqlite'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DEADBOT_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("DEADBOT_SQLITE_PATH", raising=False)

    settings = Settings.from_env(env_file)

    assert settings.ollama_model == "local-model"
    assert str(settings.sqlite_path) == "build/local.sqlite"


def test_process_environment_overrides_local_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEADBOT_OLLAMA_MODEL=from-file\n", encoding="utf-8")
    monkeypatch.setenv("DEADBOT_OLLAMA_MODEL", "from-environment")

    assert Settings.from_env(env_file).ollama_model == "from-environment"


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


def test_the_notebook_secret_is_read_from_the_environment_and_kept_out_of_repr(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_NOTEBOOK_SECRET", "  s3cret-value  ")
    settings = Settings.from_env(env_path=tmp_path / "absent.env")
    assert settings.notebook_secret == "s3cret-value"
    assert "s3cret-value" not in repr(settings)


def test_a_blank_notebook_secret_means_no_notebook(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_NOTEBOOK_SECRET", " ")
    assert Settings.from_env(env_path=tmp_path / "absent.env").notebook_secret is None
    assert Settings().notebook_secret is None
