"""Deterministic import of the reviewed canonical CSVs into PostgreSQL.

The importer deliberately accepts an existing DB-API connection.  This keeps
the canonical import independent of a particular PostgreSQL driver and makes
it possible to test transaction and SQL behaviour without a running server.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_DIR = ROOT / "data" / "canonical"
DEFAULT_SELECTION_EVIDENCE_PATH = ROOT / "data" / "editorial" / "selection-evidence-review.json"
DEFAULT_SCHEMA_PATH = ROOT / "schema" / "postgres.sql"
DEFAULT_MIGRATIONS_DIR = ROOT / "schema" / "migrations"
SCHEMA_VERSION = 4


Converter = Callable[[str], Any]


def _as_date(value: str) -> date:
    return date.fromisoformat(value)


def _as_int(value: str) -> int:
    return int(value)


def _as_float(value: str) -> float:
    return float(value)


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "t", "1", "yes"}:
        return True
    if normalized in {"false", "f", "0", "no"}:
        return False
    raise ValueError(f"expected a boolean, got {value!r}")


@dataclass(frozen=True)
class TableSpec:
    """The exact CSV/database contract for one canonical table."""

    name: str
    columns: tuple[str, ...]
    nullable: frozenset[str] = frozenset()
    converters: Mapping[str, Converter] = field(default_factory=dict)

    @property
    def csv_name(self) -> str:
        return f"{self.name}.csv"


def _spec(
    name: str,
    columns: str,
    *,
    nullable: Iterable[str] = (),
    dates: Iterable[str] = (),
    integers: Iterable[str] = (),
    floats: Iterable[str] = (),
    booleans: Iterable[str] = (),
) -> TableSpec:
    converters: dict[str, Converter] = {}
    converters.update((column, _as_date) for column in dates)
    converters.update((column, _as_int) for column in integers)
    converters.update((column, _as_float) for column in floats)
    converters.update((column, _as_bool) for column in booleans)
    return TableSpec(
        name=name,
        columns=tuple(columns.split()),
        nullable=frozenset(nullable),
        converters=converters,
    )


# This order is part of the import contract: every referenced parent precedes
# its children.  It also gives rebuild mode a safe deletion order when reversed.
TABLE_SPECS: tuple[TableSpec, ...] = (
    _spec("people", "person_id name birth_date death_date notes", nullable=("birth_date", "death_date", "notes"), dates=("birth_date", "death_date")),
    _spec("songs", "song_id title slug original_artist first_known_dead_performance last_known_dead_performance notes", nullable=("original_artist", "first_known_dead_performance", "last_known_dead_performance", "notes"), dates=("first_known_dead_performance", "last_known_dead_performance")),
    _spec("venues", "venue_id name city state_region country latitude longitude notes", nullable=("city", "state_region", "country", "latitude", "longitude", "notes"), floats=("latitude", "longitude")),
    _spec("equipment", "equipment_id name category manufacturer model notes", nullable=("manufacturer", "model", "notes")),
    _spec("shows", "show_id show_date venue_id tour_name event_name notes source_key source_record_id", nullable=("tour_name", "event_name", "notes", "source_key", "source_record_id"), dates=("show_date",)),
    _spec("song_writers", "song_id person_id writer_role notes", nullable=("notes",)),
    _spec("resources", "resource_id resource_type title creator source_name source_url published_date notes", nullable=("creator", "published_date", "notes"), dates=("published_date",)),
    _spec("resource_songs", "resource_id song_id relationship_type notes", nullable=("notes",)),
    _spec("resource_shows", "resource_id show_id relationship_type notes", nullable=("notes",)),
    _spec("show_performers", "show_id person_id role instrument notes source_key source_record_id", nullable=("notes", "source_key", "source_record_id")),
    _spec("performances", "performance_id show_id song_id set_number set_label position_in_set encore segue_into_next performance_notes source_key source_record_id", nullable=("set_number", "set_label", "performance_notes", "source_key", "source_record_id"), integers=("set_number", "position_in_set"), booleans=("encore", "segue_into_next")),
    _spec("resource_performances", "resource_id performance_id relationship_type notes", nullable=("notes",)),
    _spec("show_links", "show_link_id show_id platform link_type url title is_official notes", nullable=("title", "notes"), booleans=("is_official",)),
    _spec("performance_links", "performance_link_id performance_id platform link_type url title start_seconds duration_seconds is_official notes", nullable=("title", "start_seconds", "duration_seconds", "notes"), integers=("start_seconds", "duration_seconds"), booleans=("is_official",)),
    _spec("official_releases", "release_id title artist_name release_date release_type spotify_album_url source_url notes", nullable=("artist_name", "release_date", "release_type", "spotify_album_url", "notes"), dates=("release_date",)),
    _spec("official_release_tracks", "release_id track_number performance_id track_title duration_seconds spotify_track_url notes", nullable=("performance_id", "duration_seconds", "spotify_track_url", "notes"), integers=("track_number", "duration_seconds")),
    _spec("song_arrangements", "arrangement_id song_id performance_id resource_id arrangement_scope key_signature capo tuning notes", nullable=("performance_id", "key_signature", "capo", "tuning", "notes")),
    _spec("arrangement_chord_sections", "arrangement_id section_position section_label progression notes", nullable=("notes",), integers=("section_position",)),
    _spec("recordings", "recording_id show_id source_type taper transferer shnid archive_identifier source_description lineage source_url notes", nullable=("source_type", "taper", "transferer", "shnid", "archive_identifier", "source_description", "lineage", "source_url", "notes")),
    _spec("performance_recordings", "performance_id recording_id track_number start_seconds duration_seconds track_title notes", nullable=("start_seconds", "duration_seconds", "track_title", "notes"), integers=("track_number", "start_seconds", "duration_seconds")),
    _spec("show_equipment", "show_id equipment_id usage_context claim_type claim_id source_id source_url source_note", nullable=("source_note",)),
)


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
class CanonicalSnapshot:
    """An immutable content manifest for one reviewed canonical input set."""

    snapshot_id: str
    manifest: Mapping[str, Any]


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


class CanonicalImportError(ValueError):
    """Raised when canonical input violates its explicit import contract."""


def read_selection_evidence(path: Path | str = DEFAULT_SELECTION_EVIDENCE_PATH) -> dict[str, Any]:
    """Read the reviewed selection packet that must accompany every database import."""

    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalImportError(f"selection evidence is unavailable or invalid: {source}") from exc
    entries = document.get("entries") if isinstance(document, dict) else None
    if document.get("kind") != "selection_evidence_review" or not isinstance(entries, list):
        raise CanonicalImportError("selection evidence must be a selection_evidence_review with entries")
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise CanonicalImportError(f"selection evidence entry {position} must be an object")
        if not isinstance(entry.get("source"), str) or not entry["source"]:
            raise CanonicalImportError(f"selection evidence entry {position} is missing source")
        if not isinstance(entry.get("signal_type"), str) or not entry["signal_type"]:
            raise CanonicalImportError(f"selection evidence entry {position} is missing signal_type")
        if not isinstance(entry.get("resolution_state"), str) or not entry["resolution_state"]:
            raise CanonicalImportError(f"selection evidence entry {position} is missing resolution_state")
    return document


def _stable_selection_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _selection_source_url(entry: Mapping[str, Any]) -> str:
    value = entry.get("source_url")
    if isinstance(value, str) and value.startswith("https://"):
        return value
    if entry.get("source") == "charlie-miller-user-provided-threads":
        return "https://www.threads.com/@charliedmiller87"
    raise CanonicalImportError(
        f"selection source {entry.get('source')!r} has no usable source URL"
    )


def _selector_name(entry: Mapping[str, Any]) -> str | None:
    source = entry.get("source")
    if source in {"charlie-miller-user-provided-threads", "charlie-miller-reddit"}:
        return "Charlie Miller"
    if source == "rolling-stone-australia":
        return "David Fricke / Rolling Stone"
    return None


def _replace_selection_evidence(cursor: Any, document: Mapping[str, Any]) -> None:
    """Atomically replace the generated selection projection with the reviewed packet."""

    entries = document["entries"]
    # These rows are generated solely from the reviewed packet, so replacement
    # makes the operational database exactly match the reviewed input.
    cursor.execute("DELETE FROM public.selection_evidence")
    cursor.execute("DELETE FROM public.selection_entries")
    cursor.execute("DELETE FROM public.selection_lists")

    resources: dict[str, tuple[Any, ...]] = {}
    lists: dict[str, tuple[Any, ...]] = {}
    evidence_rows: list[tuple[Any, ...]] = []
    entry_rows: list[tuple[Any, ...]] = []
    review_packet = {
        "purpose": document.get("purpose"),
        "source_constraints": document.get("source_constraints", {}),
        "summary": document.get("summary", {}),
    }
    for position, raw_entry in enumerate(entries, start=1):
        entry = dict(raw_entry)
        source = entry["source"]
        source_url = _selection_source_url(entry)
        resource_id = _stable_selection_id("resource-selection", source, source_url)
        title = entry.get("selection_label") or f"{source} selection evidence"
        resources[resource_id] = (
            resource_id,
            "selection-evidence",
            title,
            _selector_name(entry),
            source,
            source_url,
            None,
            "Reviewed source-attributed selection evidence.",
        )
        list_key = str(entry.get("selection_label") or entry["signal_type"])
        list_id = _stable_selection_id("selection-list", source, list_key, source_url)
        lists[list_id] = (
            list_id,
            list_key,
            entry["signal_type"],
            _selector_name(entry),
            resource_id,
            None,
            None,
            "Generated from the reviewed selection-evidence packet.",
        )
        evidence_id = _stable_selection_id(
            "selection-evidence", source, str(entry.get("source_record_id") or ""), str(position)
        )
        entry["review_packet"] = review_packet
        evidence_rows.append(
            (
                evidence_id,
                resource_id,
                list_id,
                entry["signal_type"],
                entry["resolution_state"],
                json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        )
        show_ids = entry.get("candidate_show_ids")
        performance_ids = entry.get("candidate_performance_ids")
        target_column = target_id = None
        if entry["resolution_state"] in {"resolved_unique_show", "resolved_show_pending_release_review"} and isinstance(show_ids, list) and len(show_ids) == 1:
            target_column, target_id = "show_id", show_ids[0]
        elif entry["resolution_state"] == "resolved_unique_performance" and isinstance(performance_ids, list) and len(performance_ids) == 1:
            target_column, target_id = "performance_id", performance_ids[0]
        if target_column and isinstance(target_id, str):
            targets = {"show_id": None, "performance_id": None, "song_id": None, "release_id": None, "recording_id": None}
            targets[target_column] = target_id
            entry_rows.append(
                (
                    _stable_selection_id("selection-entry", evidence_id),
                    list_id,
                    position,
                    entry.get("recommendation_rank") if isinstance(entry.get("recommendation_rank"), int) else None,
                    entry.get("fan_vote_count") if isinstance(entry.get("fan_vote_count"), int) else None,
                    None,
                    targets["show_id"],
                    targets["performance_id"],
                    targets["song_id"],
                    targets["release_id"],
                    targets["recording_id"],
                    entry.get("source_label") if isinstance(entry.get("source_label"), str) else None,
                    f"resolution_state={entry['resolution_state']}",
                )
            )

    cursor.executemany(
        "INSERT INTO public.resources (resource_id, resource_type, title, creator, source_name, source_url, published_date, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (resource_id) DO UPDATE SET resource_type = EXCLUDED.resource_type, title = EXCLUDED.title, "
        "creator = EXCLUDED.creator, source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url, notes = EXCLUDED.notes",
        list(resources.values()),
    )
    cursor.executemany(
        "INSERT INTO public.selection_lists (selection_list_id, title, selection_type, selector_name, source_resource_id, published_date, retrieved_at, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        list(lists.values()),
    )
    if entry_rows:
        cursor.executemany(
            "INSERT INTO public.selection_entries (selection_entry_id, selection_list_id, entry_position, rank, vote_count, score, show_id, performance_id, song_id, release_id, recording_id, source_label, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            entry_rows,
        )
    cursor.executemany(
        "INSERT INTO public.selection_evidence (selection_evidence_id, source_resource_id, selection_list_id, signal_type, resolution_state, payload) "
        "VALUES (%s, %s, %s, %s, %s, %s::jsonb)",
        evidence_rows,
    )


class SchemaMigrationRequired(RuntimeError):
    """Raised when an existing database is not at the supported schema version."""


def _convert_row(spec: TableSpec, row: Mapping[str, str], line_number: int) -> tuple[Any, ...]:
    converted: list[Any] = []
    for column in spec.columns:
        value = row[column]
        if value == "" and column in spec.nullable:
            converted.append(None)
            continue
        if value == "":
            raise CanonicalImportError(
                f"{spec.csv_name}:{line_number}: required {column} is empty"
            )
        converter = spec.converters.get(column)
        if converter is None:
            converted.append(value)
            continue
        try:
            converted.append(converter(value))
        except (TypeError, ValueError) as exc:
            raise CanonicalImportError(
                f"{spec.csv_name}:{line_number}: invalid {column}: {exc}"
            ) from exc
    return tuple(converted)


def read_canonical_table(canonical_dir: Path | str, spec: TableSpec) -> list[tuple[Any, ...]]:
    """Read and strictly validate one canonical CSV."""

    path = Path(canonical_dir) / spec.csv_name
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise CanonicalImportError(f"missing canonical file: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        if actual != spec.columns:
            raise CanonicalImportError(
                f"{spec.csv_name}: expected header {spec.columns!r}, got {actual!r}"
            )
        rows: list[tuple[Any, ...]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise CanonicalImportError(
                    f"{spec.csv_name}:{line_number}: row has more fields than its header"
                )
            rows.append(_convert_row(spec, row, line_number))
        return rows


def read_canonical_tables(
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    specs: Sequence[TableSpec] = TABLE_SPECS,
) -> dict[str, list[tuple[Any, ...]]]:
    """Validate all input before opening a database transaction."""

    return {spec.name: read_canonical_table(canonical_dir, spec) for spec in specs}


def canonical_snapshot(
    canonical_dir: Path | str,
    rows_by_table: Mapping[str, Sequence[tuple[Any, ...]]],
    specs: Sequence[TableSpec] = TABLE_SPECS,
) -> CanonicalSnapshot:
    """Create a content-addressed manifest for already validated CSV input.

    Per-file digests preserve the exact reviewed files used by an import. The
    combined digest is deliberately independent of filesystem paths and gives
    observations a stable, portable input revision identifier.
    """

    root = Path(canonical_dir)
    combined = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for spec in specs:
        payload = (root / spec.csv_name).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        combined.update(spec.csv_name.encode("utf-8"))
        combined.update(b"\0")
        combined.update(bytes.fromhex(digest))
        combined.update(b"\0")
        files.append(
            {
                "name": spec.csv_name,
                "sha256": digest,
                "row_count": len(rows_by_table[spec.name]),
            }
        )
    return CanonicalSnapshot(
        snapshot_id=f"sha256:{combined.hexdigest()}",
        manifest={"format": "deadbot-canonical-snapshot/v1", "files": files},
    )


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
