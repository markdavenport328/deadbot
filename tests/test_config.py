from deadbot.config import Settings
from deadbot.models import OllamaProvider, OpenAIProvider, create_model_provider


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
