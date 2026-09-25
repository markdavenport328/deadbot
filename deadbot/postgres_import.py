"""Deterministic import of the reviewed canonical CSVs into PostgreSQL.

The importer deliberately accepts an existing DB-API connection.  This keeps
the canonical import independent of a particular PostgreSQL driver and makes
it possible to test transaction and SQL behaviour without a running server.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from deadbot.canonical_import import (  # noqa: F401 - re-exported for existing callers
    DEFAULT_CANONICAL_DIR,
    DEFAULT_SELECTION_EVIDENCE_PATH,
    ROOT,
    TABLE_SPECS,
    CanonicalImportError,
    CanonicalSnapshot,
    TableSpec,
    _as_bool,
    _as_date,
    _as_float,
    _as_int,
    _convert_row,
    _selection_source_url,
    _selector_name,
    _spec,
    _stable_selection_id,
    canonical_snapshot,
    read_canonical_table,
    read_canonical_tables,
    read_selection_evidence,
    selection_evidence_rows,
)


DEFAULT_SCHEMA_PATH = ROOT / "schema" / "postgres.sql"
DEFAULT_MIGRATIONS_DIR = ROOT / "schema" / "migrations"
SCHEMA_VERSION = 10


@dataclass(frozen=True)
class TableImportResult:
    source_rows: int
    inserted_rows: int | None

    @property
    def skipped_rows(self) -> int | None:
        if self.inserted_rows is None:
            return None
        return self.source_rows - self.inserted_rows


@dataclass(frozen=True)
class ImportReport:
    schema_created: bool
    rebuilt: bool
    migrations: tuple[int, ...]
    snapshot: CanonicalSnapshot
    tables: Mapping[str, TableImportResult]

    @property
    def row_counts(self) -> dict[str, int]:
        """Canonical source row counts, keyed by table."""

        return {name: result.source_rows for name, result in self.tables.items()}


def _replace_selection_evidence(cursor: Any, document: Mapping[str, Any]) -> None:
    """Atomically replace the generated selection projection with the reviewed packet."""

    rows = selection_evidence_rows(document)
    # These rows are generated solely from the reviewed packet, so replacement
    # makes the operational database exactly match the reviewed input.
    cursor.execute("DELETE FROM public.selection_evidence")
    cursor.execute("DELETE FROM public.selection_entries")
    cursor.execute("DELETE FROM public.selection_lists")
    cursor.executemany(
        "INSERT INTO public.resources (resource_id, resource_type, title, creator, source_name, source_url, published_date, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (resource_id) DO UPDATE SET resource_type = EXCLUDED.resource_type, title = EXCLUDED.title, "
        "creator = EXCLUDED.creator, source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url, notes = EXCLUDED.notes",
        rows.resources,
    )
    cursor.executemany(
        "INSERT INTO public.selection_lists (selection_list_id, title, selection_type, selector_name, source_resource_id, published_date, retrieved_at, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        rows.lists,
    )
    if rows.entries:
        cursor.executemany(
            "INSERT INTO public.selection_entries (selection_entry_id, selection_list_id, entry_position, rank, vote_count, score, show_id, performance_id, song_id, release_id, recording_id, source_label, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows.entries,
        )
    cursor.executemany(
        "INSERT INTO public.selection_evidence (selection_evidence_id, source_resource_id, selection_list_id, signal_type, resolution_state, payload) "
        "VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
        rows.evidence,
    )


class SchemaMigrationRequired(RuntimeError):
    """Raised when an existing database is not at the supported schema version."""


def _schema_version(cursor: Any) -> int | None:
    cursor.execute(
        "SELECT to_regclass(%s), to_regclass(%s)",
        ("public.people", "public.deadbot_schema_metadata"),
    )
    row = cursor.fetchone()
    people_exists = bool(row and row[0])
    metadata_exists = bool(row and row[1])
    if not people_exists and not metadata_exists:
        return None
    if not people_exists or not metadata_exists:
        raise SchemaMigrationRequired(
            "Existing PostgreSQL schema is incomplete or predates schema versioning; "
            "recreate it from schema/postgres.sql or apply an explicit migration."
        )
    cursor.execute("SELECT schema_version FROM public.deadbot_schema_metadata")
    version_row = cursor.fetchone()
    actual_version = version_row[0] if version_row else None
    if actual_version is None or actual_version < 1:
        raise SchemaMigrationRequired(
            f"PostgreSQL schema version {actual_version!r} is invalid; "
            "recreate it from schema/postgres.sql or apply an explicit migration."
        )
    if actual_version > SCHEMA_VERSION:
        raise SchemaMigrationRequired(
            f"PostgreSQL schema version {actual_version!r} is unsupported; "
            f"expected {SCHEMA_VERSION}. Apply an explicit migration before importing."
        )
    return actual_version


def _schema_sql(path: Path | str) -> str:
    sql = Path(path).read_text(encoding="utf-8")
    # The checked-in schema is also runnable by psql and therefore owns a
    # BEGIN/COMMIT pair.  The importer removes only those standalone controls
    # so schema bootstrap and data import share the caller's transaction.
    return re.sub(r"(?im)^\s*(?:BEGIN|COMMIT)\s*;\s*$", "", sql)


def _apply_migrations(cursor: Any, from_version: int) -> tuple[int, ...]:
    """Apply each checked-in forward migration in the caller's transaction."""

    applied: list[int] = []
    for version in range(from_version + 1, SCHEMA_VERSION + 1):
        candidates = sorted(DEFAULT_MIGRATIONS_DIR.glob(f"{version:03d}_*.sql"))
        if len(candidates) != 1:
            raise SchemaMigrationRequired(
                f"Expected exactly one migration for schema version {version}, found "
                f"{len(candidates)} in {DEFAULT_MIGRATIONS_DIR}."
            )
        cursor.execute(_schema_sql(candidates[0]))
        cursor.execute("SELECT schema_version FROM public.deadbot_schema_metadata")
        row = cursor.fetchone()
        if not row or row[0] != version:
            raise SchemaMigrationRequired(
                f"Migration {candidates[0].name} did not set schema version {version}."
            )
        applied.append(version)
    return tuple(applied)


def _insert_sql(spec: TableSpec) -> str:
    columns = ", ".join(spec.columns)
    placeholders = ", ".join("%s" for _ in spec.columns)
    return (
        f"INSERT INTO public.{spec.name} ({columns}) "
        f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    )


def _record_snapshot(cursor: Any, snapshot: CanonicalSnapshot) -> None:
    cursor.execute(
        "INSERT INTO public.canonical_snapshots (snapshot_id, manifest) "
        "VALUES (%s, %s::jsonb) ON CONFLICT (snapshot_id) DO NOTHING",
        (snapshot.snapshot_id, json.dumps(snapshot.manifest, sort_keys=True, separators=(",", ":"))),
    )


def _record_import(
    cursor: Any,
    *,
    snapshot: CanonicalSnapshot,
    mode: str,
    results: Mapping[str, TableImportResult],
) -> None:
    table_results = {
        name: {
            "source_rows": result.source_rows,
            "inserted_rows": result.inserted_rows,
            "skipped_rows": result.skipped_rows,
        }
        for name, result in results.items()
    }
    cursor.execute(
        "INSERT INTO public.canonical_imports "
        "(import_id, snapshot_id, import_mode, table_results) "
        "VALUES (%s, %s, %s, %s::jsonb)",
        (
            str(uuid.uuid4()),
            snapshot.snapshot_id,
            mode,
            json.dumps(table_results, sort_keys=True, separators=(",", ":")),
        ),
    )


def import_canonical(
    connection: Any,
    *,
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    selection_evidence_path: Path | str = DEFAULT_SELECTION_EVIDENCE_PATH,
    schema_path: Path | str = DEFAULT_SCHEMA_PATH,
    rebuild: bool = False,
    specs: Sequence[TableSpec] = TABLE_SPECS,
) -> ImportReport:
    """Import canonical CSVs using an injectable DB-API connection.

    Default mode is non-destructive: existing rows win and primary/unique-key
    conflicts are skipped.  ``rebuild=True`` deletes rows only from the known
    canonical tables, in reverse dependency order, before reloading them.  It
    does not drop a database, schema, extension, or unrelated application data.
    """

    # Fail before touching PostgreSQL if a file is missing or malformed.
    rows_by_table = read_canonical_tables(canonical_dir, specs)
    selection_document = read_selection_evidence(selection_evidence_path)
    snapshot = canonical_snapshot(canonical_dir, rows_by_table, specs)
    cursor = connection.cursor()
    schema_created = False
    migrations: tuple[int, ...] = ()
    try:
        # Pin the transaction so a DSN-level search_path cannot create or load
        # identically named tables outside the supported public schema.
        cursor.execute("SET LOCAL search_path TO public")
        installed_version = _schema_version(cursor)
        if installed_version is None:
            cursor.execute(_schema_sql(schema_path))
            schema_created = True
        elif installed_version < SCHEMA_VERSION:
            migrations = _apply_migrations(cursor, installed_version)

        _record_snapshot(cursor, snapshot)

        if rebuild and not schema_created:
            for spec in reversed(specs):
                cursor.execute(f"DELETE FROM public.{spec.name}")

        results: dict[str, TableImportResult] = {}
        for spec in specs:
            rows = rows_by_table[spec.name]
            if rows:
                cursor.executemany(_insert_sql(spec), rows)
                affected = getattr(cursor, "rowcount", -1)
                inserted = affected if isinstance(affected, int) and affected >= 0 else None
            else:
                inserted = 0
            results[spec.name] = TableImportResult(
                source_rows=len(rows),
                inserted_rows=inserted,
            )

        _replace_selection_evidence(cursor, selection_document)

        import_mode = "bootstrap" if schema_created else "rebuild" if rebuild else "merge"
        _record_import(cursor, snapshot=snapshot, mode=import_mode, results=results)

        connection.commit()
        return ImportReport(
            schema_created=schema_created,
            rebuilt=rebuild,
            migrations=migrations,
            snapshot=snapshot,
            tables=results,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def check_import(
    connection: Any,
    *,
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    specs: Sequence[TableSpec] = TABLE_SPECS,
) -> dict[str, Any]:
    """Read-only preflight: what an import from this checkout would meet.

    Validates the CSVs exactly as an import would, then reads (never writes)
    the schema version, the newest ledger rows and per-table row counts, and
    names the tables where the database holds more rows than the files: those
    are the rows a ``--rebuild`` would delete. A merge deletes nothing.
    """

    rows_by_table = read_canonical_tables(canonical_dir, specs)
    snapshot = canonical_snapshot(canonical_dir, rows_by_table, specs)
    cursor = connection.cursor()
    try:
        cursor.execute("SET LOCAL search_path TO public")
        installed = _schema_version(cursor)
        pending = [
            candidate.name
            for version in range((installed or 0) + 1, SCHEMA_VERSION + 1)
            for candidate in sorted(DEFAULT_MIGRATIONS_DIR.glob(f"{version:03d}_*.sql"))
        ] if installed is not None else []
        ledger: list[dict[str, Any]] = []
        if installed is not None:
            cursor.execute(
                "SELECT import_mode, imported_at, snapshot_id FROM public.canonical_imports "
                "ORDER BY imported_at DESC LIMIT 5"
            )
            ledger = [
                {"mode": mode, "imported_at": str(imported_at), "snapshot_id": snapshot_id}
                for mode, imported_at, snapshot_id in cursor.fetchall()
            ]
        tables: dict[str, dict[str, Any]] = {}
        rebuild_would_delete: list[str] = []
        not_yet_created: list[str] = []
        for spec in specs:
            database_rows: int | None = None
            if installed is not None:
                # A table added by a pending migration does not exist yet;
                # counting it would abort the read-only transaction.
                cursor.execute("SELECT to_regclass(%s)", (f"public.{spec.name}",))
                exists_row = cursor.fetchone()
                if exists_row and exists_row[0]:
                    cursor.execute(f"SELECT COUNT(*) FROM public.{spec.name}")
                    fetched = cursor.fetchone()
                    database_rows = int(fetched[0]) if fetched else 0
                else:
                    not_yet_created.append(spec.name)
            csv_rows = len(rows_by_table[spec.name])
            tables[spec.name] = {"database_rows": database_rows, "csv_rows": csv_rows}
            if database_rows is not None and database_rows > csv_rows:
                rebuild_would_delete.append(spec.name)
    finally:
        cursor.close()
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
    return {
        "checkout_snapshot": snapshot.snapshot_id,
        "installed_schema_version": installed,
        "importer_schema_version": SCHEMA_VERSION,
        "pending_migrations": pending,
        "recent_imports": ledger,
        "tables": tables,
        "rebuild_would_delete_rows_in": rebuild_would_delete,
        "tables_created_by_pending_migrations": not_yet_created,
        "merge_deletes_nothing": True,
    }


def check_from_dsn(dsn: str, *, canonical_dir: Path | str = DEFAULT_CANONICAL_DIR, **connect_kwargs: Any) -> dict[str, Any]:
    connection = connect_postgres(dsn, **connect_kwargs)
    try:
        return check_import(connection, canonical_dir=canonical_dir)
    finally:
        connection.close()


def connect_postgres(dsn: str, **kwargs: Any) -> Any:
    """Create a connection while keeping PostgreSQL drivers optional.

    Psycopg 3 is preferred.  Psycopg 2 remains a compatible fallback for local
    environments that already provide it.
    """

    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        try:
            import psycopg2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL import requires the optional 'psycopg' or 'psycopg2' driver"
            ) from exc
        return psycopg2.connect(dsn, **kwargs)
    return psycopg.connect(dsn, **kwargs)


def import_from_dsn(
    dsn: str,
    *,
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    selection_evidence_path: Path | str = DEFAULT_SELECTION_EVIDENCE_PATH,
    schema_path: Path | str = DEFAULT_SCHEMA_PATH,
    rebuild: bool = False,
    **connect_kwargs: Any,
) -> ImportReport:
    """Convenience wrapper for callers that have a DSN rather than a connection."""

    connection = connect_postgres(dsn, **connect_kwargs)
    try:
        return import_canonical(
            connection,
            canonical_dir=canonical_dir,
            selection_evidence_path=selection_evidence_path,
            schema_path=schema_path,
            rebuild=rebuild,
        )
    finally:
        connection.close()
