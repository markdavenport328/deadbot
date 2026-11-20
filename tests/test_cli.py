from __future__ import annotations

import json
import sys

import pytest

from deadbot.config import Settings


def test_db_build_writes_the_sqlite_catalog_to_the_requested_path(monkeypatch, tmp_path):
    from deadbot import cli, sqlite_build

    calls = []
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(sqlite_build, "main", lambda argv: calls.append(argv))
    monkeypatch.setattr(sys, "argv", ["deadbot", "db-build", "--output", str(tmp_path / "catalog.sqlite")])

    cli.main()

    assert calls == [["--output", str(tmp_path / "catalog.sqlite")]]


def test_the_postgres_import_command_is_gone(monkeypatch, capsys):
    from deadbot import cli

    monkeypatch.setattr(sys, "argv", ["deadbot", "db-import"])

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 2
    assert "invalid choice: 'db-import'" in capsys.readouterr().err


def test_deterministic_evaluation_uses_the_canonical_store(monkeypatch, capsys, tmp_path):
    from deadbot import cli

    selected_store = object()
    calls = []
    settings = Settings(sqlite_path=tmp_path / "catalog.sqlite")

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
