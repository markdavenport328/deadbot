import importlib
import sys


def test_importing_the_api_module_does_not_build_the_app(monkeypatch):
    monkeypatch.setenv("DEADBOT_DATA_STORE", "postgres")
    monkeypatch.delenv("DEADBOT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("deadbot.api", None)

    module = importlib.import_module("deadbot.api")

    assert "app" not in vars(module)
    assert callable(module.create_app)


def test_app_attribute_is_built_lazily_and_cached(monkeypatch):
    sys.modules.pop("deadbot.api", None)
    module = importlib.import_module("deadbot.api")
    built = []

    def fake_create_app(*args, **kwargs):
        built.append(1)
        return object()

    monkeypatch.setattr(module, "create_app", fake_create_app)

    first = module.app
    second = module.app

    assert first is second
    assert built == [1]
