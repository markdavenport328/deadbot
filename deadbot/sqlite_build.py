"""Build the canonical SQLite read store from the reviewed CSVs.

The database is a build artifact, never committed: Vercel builds it in the
deploy's build step and bundles it with the function, and a local run builds
it on first use and whenever the checked-out inputs change. Standard library
only, so the build step can run it with a bare ``python3``:

    python3 -m deadbot.sqlite_build --output build/deadbot.sqlite
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from deadbot.canonical_import import (
    DEFAULT_CANONICAL_DIR,
    DEFAULT_SELECTION_EVIDENCE_PATH,
    ROOT,
    TABLE_SPECS,
    CanonicalImportError,
    TableSpec,
    read_canonical_tables,
    read_selection_evidence,
    selection_evidence_rows,
)

DEFAULT_SQLITE_PATH = ROOT / "build" / "deadbot.sqlite"
SQLITE_SCHEMA_PATH = ROOT / "schema" / "sqlite.sql"
SQLITE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BuildReport:
    path: Path
    fingerprint: str
    row_counts: dict[str, int]


def input_fingerprint(
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    selection_evidence_path: Path | str = DEFAULT_SELECTION_EVIDENCE_PATH,
    schema_path: Path | str = SQLITE_SCHEMA_PATH,
) -> str:
    """A digest of every input byte, cheap enough to check on each local start."""

    digest = hashlib.sha256()
    paths = [Path(canonical_dir) / spec.csv_name for spec in TABLE_SPECS]
    paths += [Path(selection_evidence_path), Path(schema_path)]
    for path in paths:
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"sha256:{digest.hexdigest()}"


def _sqlite_value(value: Any) -> Any:
    # bool before date: both would otherwise pass through as Python objects.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return value


def _insert_sql(table: str, columns: Sequence[str]) -> str:
    names = ", ".join(f'"{column}"' for column in columns)
    return f'INSERT INTO "{table}" ({names}) VALUES ({", ".join("?" for _ in columns)})'


def _insert_table(db: sqlite3.Connection, spec: TableSpec, rows: list[tuple[Any, ...]]) -> None:
    sql = _insert_sql(spec.name, spec.columns)
    values = [tuple(_sqlite_value(value) for value in row) for row in rows]
    try:
        db.executemany(sql, values)
    except sqlite3.IntegrityError:
        # Name the offending CSV line: clear the partial load, then replay
        # row by row to find it.
        db.execute(f'DELETE FROM "{spec.name}"')
        for line_number, row in enumerate(values, start=2):
            try:
                db.execute(sql, row)
            except sqlite3.IntegrityError as exc:
                raise CanonicalImportError(f"{spec.csv_name}:{line_number}: {exc}") from exc
        raise


def _insert_selection_rows(db: sqlite3.Connection, document: dict[str, Any]) -> None:
    rows = selection_evidence_rows(document)
    db.executemany(
        'INSERT INTO resources (resource_id, resource_type, title, creator, source_name, source_url, published_date, notes) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (resource_id) DO UPDATE SET resource_type = excluded.resource_type, title = excluded.title, "
        "creator = excluded.creator, source_name = excluded.source_name, source_url = excluded.source_url, notes = excluded.notes",
        rows.resources,
    )
    db.executemany(
        _insert_sql("selection_lists", ("selection_list_id", "title", "selection_type", "selector_name", "source_resource_id", "published_date", "retrieved_at", "notes")),
        rows.lists,
    )
    db.executemany(
        _insert_sql("selection_entries", ("selection_entry_id", "selection_list_id", "entry_position", "rank", "vote_count", "score", "show_id", "performance_id", "song_id", "release_id", "recording_id", "source_label", "notes")),
        rows.entries,
    )
    db.executemany(
        _insert_sql("selection_evidence", ("selection_evidence_id", "source_resource_id", "selection_list_id", "signal_type", "resolution_state", "payload")),
        rows.evidence,
    )


def build_database(
    output: Path | str = DEFAULT_SQLITE_PATH,
    *,
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    selection_evidence_path: Path | str = DEFAULT_SELECTION_EVIDENCE_PATH,
    schema_path: Path | str = SQLITE_SCHEMA_PATH,
) -> BuildReport:
    """Validate every input, build beside ``output``, then swap it into place."""

    tables = read_canonical_tables(canonical_dir)
    document = read_selection_evidence(selection_evidence_path)
    fingerprint = input_fingerprint(canonical_dir, selection_evidence_path, schema_path)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name + ".building")
    staging.unlink(missing_ok=True)
    db = sqlite3.connect(staging)
    try:
        # Foreign keys are checked once after loading, with a full report,
        # rather than failing a commit with no detail. Triggers and CHECK
        # constraints still guard every insert.
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("PRAGMA journal_mode = OFF")
        db.execute("PRAGMA synchronous = OFF")
        db.executescript(Path(schema_path).read_text(encoding="utf-8"))
        with db:
            for spec in TABLE_SPECS:
                _insert_table(db, spec, tables[spec.name])
            _insert_selection_rows(db, document)
            db.execute(
                "INSERT INTO deadbot_schema_metadata (schema_version, input_fingerprint, built_at) VALUES (?, ?, ?)",
                (SQLITE_SCHEMA_VERSION, fingerprint, datetime.now(timezone.utc).isoformat()),
            )
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            sample = "; ".join(f"{table} row {rowid} -> {parent}" for table, rowid, parent, _ in violations[:10])
            raise CanonicalImportError(f"{len(violations)} broken references: {sample}")
        db.execute("ANALYZE")
        db.commit()
        db.execute("VACUUM")
    except BaseException:
        db.close()
        staging.unlink(missing_ok=True)
        raise
    db.close()
    os.replace(staging, output)
    return BuildReport(
        path=output,
        fingerprint=fingerprint,
        row_counts={name: len(rows) for name, rows in tables.items()},
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the canonical SQLite read store.")
    parser.add_argument("--output", type=Path, default=DEFAULT_SQLITE_PATH)
    args = parser.parse_args(argv)
    report = build_database(args.output)
    print(json.dumps({
        "path": str(report.path),
        "bytes": report.path.stat().st_size,
        "fingerprint": report.fingerprint,
        "rows": sum(report.row_counts.values()),
    }, indent=2))


if __name__ == "__main__":
    main()
