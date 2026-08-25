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


def test_blank_numeric_environment_values_use_defaults(monkeypatch):
    monkeypatch.setenv("DEADBOT_MAX_TOOL_ROUNDS", "")
    monkeypatch.setenv("DEADBOT_COMPOSER_MAX_BLOCKS", "")
    settings = Settings.from_env()
    assert settings.max_tool_rounds == 8
    assert settings.composer_max_blocks == 8


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
