from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import pytest

from deadbot.postgres_import import (
    CanonicalImportError,
    SCHEMA_VERSION,
    SchemaMigrationRequired,
    TABLE_SPECS,
    canonical_snapshot,
    import_canonical,
    read_canonical_tables,
)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = -1
        self._fetchone = None

    def execute(self, sql, params=None):
        self.connection.commands.append((sql, params))
        if sql.startswith("SELECT to_regclass"):
            if self.connection.initialized:
                metadata = "deadbot_schema_metadata" if self.connection.versioned else None
                self._fetchone = ("people", metadata)
            else:
                self._fetchone = (None, None)
        elif "SELECT schema_version FROM public.deadbot_schema_metadata" in sql:
            self._fetchone = (self.connection.schema_version,)
        elif sql.startswith("DELETE FROM "):
            table = sql.removeprefix("DELETE FROM ").removeprefix("public.")
            self.connection.keys[table] = set()
        elif "CREATE TABLE people" in sql:
            self.connection.initialized = True
        elif "UPDATE deadbot_schema_metadata SET schema_version =" in sql:
            match = re.search(r"schema_version\s*=\s*(\d+)", sql)
            assert match is not None
            self.connection.schema_version = int(match.group(1))
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise RuntimeError("database failure")

    def executemany(self, sql, rows):
        rows = list(rows)
        self.connection.commands.append((sql, rows))
        table = sql.split()[2].removeprefix("public.")
        if self.connection.fail_on == table:
            raise RuntimeError("database failure")
        keys = self.connection.keys.setdefault(table, set())
        inserted = 0
        for row in rows:
            # Test fixtures use the first column as their stable conflict key.
            if row[0] not in keys:
                keys.add(row[0])
                inserted += 1
        self.rowcount = inserted

    def fetchone(self):
        return self._fetchone

    def close(self):
        self.connection.cursor_closed = True


class FakeConnection:
    def __init__(
        self,
        *,
        initialized=False,
        versioned=True,
        schema_version=SCHEMA_VERSION,
        fail_on=None,
    ):
        self.initialized = initialized
        self.versioned = versioned
        self.schema_version = schema_version
        self.fail_on = fail_on
        self.commands = []
        self.keys = {}
        self.commits = 0
        self.rollbacks = 0
        self.cursor_closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def write_fixture(directory: Path, overrides=None):
    overrides = overrides or {}
    for spec in TABLE_SPECS:
        rows = overrides.get(spec.name, [])
        with (directory / spec.csv_name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(spec.columns)
            writer.writerows(rows)


def test_table_specs_cover_every_canonical_csv():
    canonical = Path(__file__).parents[1] / "data" / "canonical"
    assert {spec.csv_name for spec in TABLE_SPECS} == {
        path.name for path in canonical.glob("*.csv")
    }


def test_import_bootstraps_schema_in_dependency_order_and_reports_counts(tmp_path):
    write_fixture(
        tmp_path,
        {
            "people": [["person-jerry", "Jerry Garcia", "1942-08-01", "1995-08-09", ""]],
            "venues": [["venue-1", "Test Venue", "", "", "", "", "", "", "", ""]],
            "shows": [["show-1", "1972-08-27", "venue-1", "", "", "", "manual", "show-1"]],
        },
    )
    schema = tmp_path / "postgres.sql"
    schema.write_text("BEGIN;\nCREATE TABLE people (person_id TEXT);\nCOMMIT;\n", encoding="utf-8")
    connection = FakeConnection()

    report = import_canonical(connection, canonical_dir=tmp_path, schema_path=schema)

    assert report.schema_created is True
    assert report.migrations == ()
    assert report.snapshot.snapshot_id.startswith("sha256:")
    assert report.row_counts["people"] == 1
    assert report.tables["shows"].inserted_rows == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.commands[0][0] == "SET LOCAL search_path TO public"
    schema_sql = next(sql for sql, _ in connection.commands if "CREATE TABLE people" in sql)
    assert "BEGIN;" not in schema_sql
    assert "COMMIT;" not in schema_sql
    inserts = [
        sql.split()[2].removeprefix("public.")
        for sql, _ in connection.commands
        if sql.startswith("INSERT")
    ]
    assert inserts.index("venues") < inserts.index("shows")
    snapshot_command = next(
        item
        for item in connection.commands
        if item[0].startswith("INSERT INTO public.canonical_snapshots")
    )
    assert snapshot_command[1][0] == report.snapshot.snapshot_id
    assert any(
        sql.startswith("INSERT INTO public.canonical_imports")
        for sql, _ in connection.commands
    )


def test_snapshot_hashes_exact_validated_files_and_includes_row_counts(tmp_path):
    write_fixture(tmp_path, {"people": [["person-jerry", "Jerry Garcia", "", "", ""]]})

    rows = read_canonical_tables(tmp_path)
    first = canonical_snapshot(tmp_path, rows)
    second = canonical_snapshot(tmp_path, rows)

    assert first == second
    assert first.manifest["format"] == "deadbot-canonical-snapshot/v1"
    people = next(item for item in first.manifest["files"] if item["name"] == "people.csv")
    assert people["row_count"] == 1

    with (tmp_path / "people.csv").open("a", encoding="utf-8") as handle:
        handle.write("person-bob,Bob Weir,,,\n")
    changed = canonical_snapshot(tmp_path, read_canonical_tables(tmp_path))
    assert changed.snapshot_id != first.snapshot_id


def test_import_converts_types_and_defines_blank_semantics(tmp_path):
    write_fixture(
        tmp_path,
        {"people": [["person-jerry", "Jerry Garcia", "1942-08-01", "", ""]]},
    )
    connection = FakeConnection(initialized=True)

    import_canonical(connection, canonical_dir=tmp_path)

    people_command = next(
        item for item in connection.commands if item[0].startswith("INSERT INTO public.people")
    )
    row = people_command[1][0]
    assert row == ("person-jerry", "Jerry Garcia", date(1942, 8, 1), None, None)


def test_import_rejects_a_blank_required_text_value(tmp_path):
    write_fixture(tmp_path, {"people": [["person-jerry", "", "", "", ""]]})
    connection = FakeConnection(initialized=True)

    with pytest.raises(CanonicalImportError, match="required name is empty"):
        import_canonical(connection, canonical_dir=tmp_path)

    assert connection.commands == []


def test_import_rejects_header_drift_before_touching_database(tmp_path):
    write_fixture(tmp_path)
    (tmp_path / "people.csv").write_text("person_id,display_name\n", encoding="utf-8")
    connection = FakeConnection(initialized=True)

    with pytest.raises(CanonicalImportError, match="expected header"):
        import_canonical(connection, canonical_dir=tmp_path)

    assert connection.commands == []
    assert connection.rollbacks == 0


def test_default_import_is_non_destructive_and_idempotent(tmp_path):
    write_fixture(tmp_path, {"people": [["person-jerry", "Jerry Garcia", "", "", ""]]})
    connection = FakeConnection(initialized=True)

    first = import_canonical(connection, canonical_dir=tmp_path)
    second = import_canonical(connection, canonical_dir=tmp_path)

    deletes = [sql for sql, _ in connection.commands if sql.startswith("DELETE")]
    assert deletes == [
        "DELETE FROM public.selection_evidence",
        "DELETE FROM public.selection_entries",
        "DELETE FROM public.selection_lists",
        "DELETE FROM public.selection_evidence",
        "DELETE FROM public.selection_entries",
        "DELETE FROM public.selection_lists",
    ]
    assert first.tables["people"].inserted_rows == 1
    assert second.tables["people"].inserted_rows == 0
    assert "ON CONFLICT DO NOTHING" in next(
        sql for sql, _ in connection.commands if sql.startswith("INSERT INTO public.people")
    )


def test_rebuild_deletes_only_known_tables_in_reverse_dependency_order(tmp_path):
    write_fixture(tmp_path)
    connection = FakeConnection(initialized=True)

    report = import_canonical(connection, canonical_dir=tmp_path, rebuild=True)

    deletes = [
        sql.removeprefix("DELETE FROM public.")
        for sql, _ in connection.commands
        if sql.startswith("DELETE")
    ]
    assert deletes == [spec.name for spec in reversed(TABLE_SPECS)] + [
        "selection_evidence",
        "selection_entries",
        "selection_lists",
    ]
    assert "shows" in deletes
    assert report.rebuilt is True


def test_database_error_rolls_back_and_closes_cursor(tmp_path):
    write_fixture(tmp_path, {"people": [["person-jerry", "Jerry Garcia", "", "", ""]]})
    connection = FakeConnection(initialized=True, fail_on="people")

    with pytest.raises(RuntimeError, match="database failure"):
        import_canonical(connection, canonical_dir=tmp_path)

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.cursor_closed is True


def test_existing_unversioned_schema_requires_an_explicit_migration(tmp_path):
    write_fixture(tmp_path)
    connection = FakeConnection(initialized=True, versioned=False)

    with pytest.raises(SchemaMigrationRequired, match="predates schema versioning"):
        import_canonical(connection, canonical_dir=tmp_path)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_unsupported_schema_version_requires_an_explicit_migration(tmp_path):
    write_fixture(tmp_path)
    connection = FakeConnection(initialized=True, schema_version=SCHEMA_VERSION + 1)

    with pytest.raises(SchemaMigrationRequired, match="unsupported"):
        import_canonical(connection, canonical_dir=tmp_path)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_version_one_schema_is_migrated_before_snapshot_import(tmp_path):
    write_fixture(tmp_path)
    connection = FakeConnection(initialized=True, schema_version=1)

    report = import_canonical(connection, canonical_dir=tmp_path)

    assert report.migrations == tuple(range(2, SCHEMA_VERSION + 1))
    assert connection.schema_version == SCHEMA_VERSION
    assert any(
        "CREATE TABLE canonical_snapshots" in sql for sql, _ in connection.commands
    )


def test_real_canonical_headers_match_explicit_specs():
    canonical = Path(__file__).parents[1] / "data" / "canonical"
    for spec in TABLE_SPECS:
        with (canonical / spec.csv_name).open(encoding="utf-8-sig", newline="") as handle:
            assert tuple(next(csv.reader(handle))) == spec.columns


def test_release_track_spec_carries_a_nullable_song_id():
    spec = next(spec for spec in TABLE_SPECS if spec.name == "official_release_tracks")
    assert spec.columns == (
        "release_id",
        "track_number",
        "performance_id",
        "song_id",
        "track_title",
        "duration_seconds",
        "spotify_track_url",
        "notes",
    )
    assert "song_id" in spec.nullable


def test_release_personnel_spec_follows_show_performers_and_loads_after_releases():
    spec = next(spec for spec in TABLE_SPECS if spec.name == "release_personnel")
    assert spec.columns == ("release_id", "person_id", "role", "instrument", "notes")
    assert spec.nullable == frozenset({"notes"})
    names = [spec.name for spec in TABLE_SPECS]
    assert names.index("release_personnel") > names.index("official_releases")
    assert names.index("release_personnel") > names.index("people")


def test_schema_version_is_eight_and_each_version_has_exactly_one_migration():
    assert SCHEMA_VERSION == 8
    migrations_dir = Path(__file__).resolve().parents[1] / "schema" / "migrations"
    for version in range(2, SCHEMA_VERSION + 1):
        assert len(sorted(migrations_dir.glob(f"{version:03d}_*.sql"))) == 1
    release_dates = sorted(migrations_dir.glob("006_*.sql"))[0].read_text(encoding="utf-8")
    assert "ALTER TABLE official_releases" in release_dates
    assert "ALTER COLUMN release_date TYPE TEXT" in release_dates
    assert "schema_version" in release_dates
    response_cache = sorted(migrations_dir.glob("007_*.sql"))[0].read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS deadbot_response_cache" in response_cache
    assert "UPDATE deadbot_schema_metadata SET schema_version = 7" in response_cache
    venue_geography = sorted(migrations_dir.glob("008_*.sql"))[0].read_text(encoding="utf-8")
    assert "ALTER TABLE venues" in venue_geography
    assert "ADD COLUMN setting TEXT" in venue_geography
    assert "ADD COLUMN capacity INTEGER" in venue_geography
    assert "UPDATE deadbot_schema_metadata SET schema_version = 8" in venue_geography
    bootstrap = (Path(__file__).resolve().parents[1] / "schema" / "postgres.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE deadbot_response_cache" in bootstrap
    assert "VALUES (8)" in bootstrap


def test_every_spec_matches_its_canonical_csv_header():
    canonical = Path(__file__).resolve().parents[1] / "data" / "canonical"
    for spec in TABLE_SPECS:
        path = canonical / spec.csv_name
        with path.open(newline="", encoding="utf-8") as source:
            header = tuple(next(csv.reader(source)))
        assert header == spec.columns, spec.name


def test_check_import_is_read_only_and_names_tables_a_rebuild_would_shrink(tmp_path):
    from deadbot.postgres_import import check_import

    class CountingConnection(FakeConnection):
        def __init__(self):
            super().__init__(initialized=True, schema_version=SCHEMA_VERSION - 1)
            self.counts = {"shows": 5, "resources": 1}
            self.writes = []

        def cursor(self):
            connection = self

            class Cursor(FakeCursor):
                def execute(self, sql, params=None):
                    upper = sql.strip().upper()
                    if upper.startswith(("INSERT", "DELETE", "UPDATE", "CREATE", "ALTER")):
                        connection.writes.append(sql)
                    if upper.startswith("SELECT COUNT(*) FROM PUBLIC."):
                        table = sql.rsplit(".", 1)[1]
                        self._fetchone = (connection.counts.get(table, 0),)
                        return
                    if "FROM public.canonical_imports" in sql:
                        self._rows = [("rebuild", "2026-09-08 02:35:50", "sha256:abc")]
                        return
                    return super().execute(sql, params)

                def fetchall(self):
                    rows = getattr(self, "_rows", None)
                    self._rows = None
                    return rows or []

            return Cursor(connection)

    connection = CountingConnection()
    # The database holds one resource and the files hold one: nothing to lose
    # there. It holds five shows and the files hold none: a rebuild would
    # delete those five.
    write_fixture(tmp_path, {"resources": [["r1", "article", "T", "", "S", "https://example.org/t", "", ""]]})
    report = check_import(connection, canonical_dir=tmp_path)
    assert connection.writes == []
    assert report["installed_schema_version"] == SCHEMA_VERSION - 1
    assert report["pending_migrations"] == [f"{SCHEMA_VERSION:03d}_venue_geography.sql"]
    assert report["recent_imports"][0]["mode"] == "rebuild"
    assert report["tables"]["shows"]["database_rows"] == 5
    assert "shows" in report["rebuild_would_delete_rows_in"]
    assert "resources" not in report["rebuild_would_delete_rows_in"]
    assert report["merge_deletes_nothing"] is True
