from deadbot.config import Settings
from deadbot.models import OllamaProvider, create_model_provider


def test_ollama_is_the_default_provider():
    provider = create_model_provider(Settings())
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen3:8b"


def test_model_guided_composition_is_enabled_by_default():
    settings = Settings()
    assert settings.composer_enabled is True
    assert settings.composer_max_blocks == 8


def test_unknown_provider_fails_clearly():
    settings = Settings(model_provider="unknown")
    try:
        create_model_provider(settings)
    except ValueError as error:
        assert "Registered providers: ollama" in str(error)
    else:
        raise AssertionError("Unknown provider should fail")
