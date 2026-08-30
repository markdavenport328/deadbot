from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from deadbot.config import Settings


def test_db_import_passes_explicit_url_and_rebuild_flag(monkeypatch, capsys):
    from deadbot import cli, postgres_import

    calls = []

    def fake_import(dsn, *, rebuild=False):
        calls.append((dsn, rebuild))
        return SimpleNamespace(
            schema_created=False,
            rebuilt=rebuild,
            migrations=(2,),
            snapshot=SimpleNamespace(snapshot_id="sha256:" + "a" * 64),
            tables={
                "people": SimpleNamespace(
                    source_rows=2, inserted_rows=2, skipped_rows=0
                ),
                "shows": SimpleNamespace(
                    source_rows=3, inserted_rows=1, skipped_rows=2
                ),
            },
            row_counts={"people": 2, "shows": 3},
        )

    monkeypatch.setattr(postgres_import, "import_from_dsn", fake_import)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deadbot",
            "db-import",
            "--database-url",
            "postgresql://explicit/deadbot",
            "--rebuild",
        ],
    )

    cli.main()

    assert calls == [("postgresql://explicit/deadbot", True)]
    assert json.loads(capsys.readouterr().out) == {
        "schema_created": False,
        "rebuilt": True,
        "migrations": [2],
        "canonical_snapshot": "sha256:" + "a" * 64,
        "canonical_tables": 2,
        "source_rows": 5,
        "row_counts": {"people": 2, "shows": 3},
        "tables": {
            "people": {"source_rows": 2, "inserted_rows": 2, "skipped_rows": 0},
            "shows": {"source_rows": 3, "inserted_rows": 1, "skipped_rows": 2},
        },
        "mode_note": "Canonical tables were deleted and reloaded.",
    }


def test_db_import_uses_configured_database_url(monkeypatch, capsys):
    from deadbot import cli, postgres_import

    calls = []

    monkeypatch.setenv("DEADBOT_DATABASE_URL", "postgresql://environment/deadbot")
    monkeypatch.setattr(
        postgres_import,
        "import_from_dsn",
        lambda dsn, *, rebuild=False: (
            calls.append((dsn, rebuild))
            or SimpleNamespace(
                schema_created=True,
                rebuilt=False,
                migrations=(),
                snapshot=SimpleNamespace(snapshot_id="sha256:" + "a" * 64),
                tables={},
                row_counts={},
            )
        ),
    )
    monkeypatch.setattr(sys, "argv", ["deadbot", "db-import"])

    cli.main()

    assert calls == [("postgresql://environment/deadbot", False)]
    assert json.loads(capsys.readouterr().out)["schema_created"] is True


def test_db_import_requires_a_database_url(monkeypatch, capsys):
    from deadbot import cli
    from deadbot.cli import main

    monkeypatch.delenv("DEADBOT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(sys, "argv", ["deadbot", "db-import"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    assert "db-import requires --database-url" in capsys.readouterr().err


def test_deterministic_evaluation_uses_selected_canonical_store(monkeypatch, capsys):
    from deadbot import cli

    selected_store = object()
    calls = []
    settings = Settings(
        data_store="postgres",
        database_url="postgresql://example/deadbot",
    )

    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(
        cli,
        "create_canonical_store",
        lambda actual_settings: (
            calls.append(("store", actual_settings)) or selected_store
        ),
    )
    monkeypatch.setattr(
        cli,
        "evaluate_suite",
        lambda suite, *, store: (
            calls.append(("evaluate", suite, store))
            or {"total": 1, "passed": 1, "failed": 0}
        ),
    )
    monkeypatch.setattr(sys, "argv", ["deadbot", "evaluate"])

    cli.main()

    assert calls[0] == ("store", settings)
    assert calls[1][0] == "evaluate"
    assert calls[1][2] is selected_store
    assert json.loads(capsys.readouterr().out)["failed"] == 0
