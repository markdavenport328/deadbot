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


def test_openapi_publishes_the_album_unit_block():
    # Build via create_app with an injected store/agent rather than the
    # module-level ``deadbot.api.app`` singleton: that lazy attribute builds
    # the production app through ``create_canonical_store``, which requires
    # DEADBOT_DATABASE_URL. This test only needs the schema, so it follows
    # scripts/export_openapi.py's pattern (a CSV-backed store, a plain
    # sentinel agent) to read the OpenAPI schema without a database.
    from deadbot.api import create_app
    from deadbot.config import Settings
    from deadbot.data import CanonicalStore

    app = create_app(settings=Settings(), store=CanonicalStore(), agent=object())
    schemas = app.openapi()["components"]["schemas"]
    assert "AlbumUnitBlock" in schemas
    assert "AlbumTrackItem" in schemas
    assert "albums" in schemas["SongOverviewBlock"]["properties"]
