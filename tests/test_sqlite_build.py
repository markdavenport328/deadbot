import csv
import re
import shutil
import sqlite3

import pytest

from deadbot.canonical_import import DEFAULT_CANONICAL_DIR, TABLE_SPECS, CanonicalImportError
from deadbot.sqlite_build import SQLITE_SCHEMA_VERSION, build_database, input_fingerprint

SELECTION_TABLES = ("selection_lists", "selection_entries", "selection_evidence")


def _connect(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def test_every_canonical_table_has_the_csv_columns_and_rows(built_sqlite):
    db = _connect(built_sqlite)
    for spec in TABLE_SPECS:
        columns = tuple(row[1] for row in db.execute(f'PRAGMA table_info("{spec.name}")'))
        assert columns == spec.columns, spec.name
        with (DEFAULT_CANONICAL_DIR / spec.csv_name).open(encoding="utf-8-sig", newline="") as handle:
            csv_rows = sum(1 for _ in csv.DictReader(handle))
        (count,) = db.execute(f'SELECT COUNT(*) FROM "{spec.name}"').fetchone()
        # resources also receives generated selection-evidence resources.
        if spec.name == "resources":
            assert count >= csv_rows
        else:
            assert count == csv_rows, spec.name


def test_selection_evidence_is_loaded(built_sqlite):
    db = _connect(built_sqlite)
    for table in ("selection_lists", "selection_evidence"):
        assert db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] > 0
    (kind,) = db.execute("SELECT json_type(payload) FROM selection_evidence LIMIT 1").fetchone()
    assert kind == "object"


def test_foreign_keys_hold_and_metadata_is_recorded(built_sqlite):
    db = _connect(built_sqlite)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    version, fingerprint = db.execute(
        "SELECT schema_version, input_fingerprint FROM deadbot_schema_metadata"
    ).fetchone()
    assert version == SQLITE_SCHEMA_VERSION
    assert fingerprint == input_fingerprint()


def test_every_postgres_index_on_a_served_table_exists(built_sqlite):
    served = {spec.name for spec in TABLE_SPECS} | set(SELECTION_TABLES)
    postgres = open("schema/postgres.sql", encoding="utf-8").read()
    expected = {
        match.group(2)
        for match in re.finditer(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)", postgres)
        if match.group(3) in served
    }
    db = _connect(built_sqlite)
    actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert expected - actual == set()


def test_booleans_and_dates_are_stored_as_csv_text(built_sqlite):
    db = _connect(built_sqlite)
    assert {row[0] for row in db.execute("SELECT DISTINCT encore FROM performances")} == {"true", "false"}
    (show_date,) = db.execute("SELECT show_date FROM shows WHERE show_id IS NOT NULL LIMIT 1").fetchone()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", show_date)


def test_triggers_reject_cross_entity_mismatches(built_sqlite, tmp_path):
    copy = tmp_path / "writable.sqlite"
    shutil.copy(built_sqlite, copy)
    db = sqlite3.connect(copy)
    performance_id, recording_id = db.execute(
        "SELECT p.performance_id, r.recording_id FROM performances p "
        "JOIN recordings r ON r.show_id <> p.show_id LIMIT 1"
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="different shows"):
        db.execute(
            "INSERT INTO performance_recordings (performance_id, recording_id, track_number) VALUES (?, ?, 99)",
            (performance_id, recording_id),
        )


def test_invalid_input_fails_before_the_output_is_replaced(tmp_path):
    canonical = tmp_path / "canonical"
    shutil.copytree(DEFAULT_CANONICAL_DIR, canonical)
    with (canonical / "songs.csv").open("a", encoding="utf-8") as handle:
        handle.write("\nsong-broken,,broken,,,,\n")  # required title is empty
    output = tmp_path / "deadbot.sqlite"
    output.write_text("previous build")
    with pytest.raises(CanonicalImportError, match="songs.csv"):
        build_database(output, canonical_dir=canonical)
    assert output.read_text() == "previous build"
