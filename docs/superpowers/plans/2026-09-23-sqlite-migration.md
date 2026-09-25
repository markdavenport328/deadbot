# SQLite Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Deadbot's canonical catalog from a SQLite file built from the reviewed CSVs on every deploy and every local run, replacing Neon Postgres.

**Architecture:** A stdlib-only builder (`deadbot/sqlite_build.py`) turns `data/canonical/*.csv` plus the selection-evidence packet into `build/deadbot.sqlite` using a SQLite port of the serving part of `schema/postgres.sql`. Vercel runs the builder in its build command and bundles the file with the function. `SqliteCanonicalStore` subclasses the existing `PostgresCanonicalStore`: the shared query layer already runs unchanged on SQLite once `%s` becomes `?` (the test suite has always done this). Stored answers move to a separate writable SQLite file in the temp directory.

**Tech Stack:** Python 3.11+ stdlib `sqlite3` (SQLite 3.30+ for `NULLS LAST`; local is 3.51), FastAPI, pytest, Vercel Python runtime.

**Spec:** No separate spec. The design came out of the owner conversation on 2026-09-23 and is summarized under "Why" below.

## Why

- Neon's free tier stopped the project with "You've used all of your monthly compute allowance." Neon bills for every hour the database is awake, and every visitor question wakes it. The site cannot answer questions until the allowance resets.
- The catalog is small and read-only at runtime: the CSVs total 46 MB, and a probe build on 2026-09-23 produced a **66 MB** SQLite file with the Postgres index set in **1.4 s**.
- The same probe ran the unmodified `PostgresCanonicalStore` against that file through a `%s`→`?` cursor wrapper: `show_context` for 1977-05-08 took 32 ms, `song_context` for Dark Star 42 ms, and `search_shows` 2 ms. Every lookup that used to be a network round trip becomes a local file read.
- CSV floats, integers and booleans round-trip exactly (checked: 0 mismatches in venues lat/long, performances set/position, release track numbers; booleans are the strings `true`/`false`).
- A side benefit: data PRs no longer need a separate `db-import` run by the owner. The deploy that ships the CSVs builds the database from them.

## Global Constraints

- The builder module and everything it imports must use **only the Python standard library**. Vercel runs it with a bare `python3` before project dependencies are installed.
- The canonical SQLite file is opened **read-only and immutable** at runtime (`?mode=ro&immutable=1`). Nothing at runtime writes to it.
- Stored answers (the response cache) live in a **separate** SQLite file, default `tempfile.gettempdir()/deadbot-response-cache.sqlite`, overridable with `DEADBOT_RESPONSE_CACHE_PATH`.
- Canonical database path: `build/deadbot.sqlite` (already gitignored via `build/`), overridable with `DEADBOT_SQLITE_PATH`. The file is **never committed**.
- Booleans are stored as the text `'true'`/`'false'`, and dates as ISO text, so store output matches the CSV store's string values exactly.
- Postgres code stays working until Task 7. Tasks 1–6 must leave `pytest` fully green.
- Run tests from the worktree with `PYTHONPATH=. .venv/bin/python -m pytest ...` (if the worktree has no `.venv`, use the main checkout's: `/Users/markdavenport/Development/DeadBot/.venv/bin/python`).
- Agents cannot push. When a branch is ready, give the owner the exact `git push` command in its own `bash` block and wait.
- Commit messages follow the repo's plain-sentence style (for example "Home starts without the rail, the rail floats in on ask") and end with the `Co-Authored-By` line from the session's attribution reminder.

## File Map

| File | Responsibility |
|---|---|
| `deadbot/canonical_import.py` (new) | Driver-neutral CSV contract: `TableSpec`, `TABLE_SPECS`, CSV readers, snapshot, selection-evidence reading **and row building** |
| `deadbot/postgres_import.py` (modify) | Postgres writer only; imports the contract from `canonical_import` and re-exports the old names |
| `schema/sqlite.sql` (new) | SQLite port of the serving tables, indexes and triggers |
| `deadbot/sqlite_build.py` (new) | Build `build/deadbot.sqlite`; `input_fingerprint`; `ensure_current`; `python3 -m deadbot.sqlite_build` |
| `deadbot/sqlite_store.py` (new) | `SqliteCanonicalStore`: thread-local read-only connections plus the temp-file response cache |
| `deadbot/postgres.py` (modify) | `CAST(... AS TEXT)` instead of `::text`; shared `_fresh_cached_payload` helper |
| `deadbot/config.py`, `deadbot/storage.py`, `deadbot/cli.py` (modify) | `sqlite` becomes the default store; `db-build` command |
| `vercel.json` (modify) | Build the database before the web build; bundle it with the function |
| `tests/conftest.py` (new) | Session-scoped `built_sqlite` fixture |
| `tests/test_canonical_import.py`, `tests/test_sqlite_build.py`, `tests/test_sqlite_store.py` (new) | Coverage for the new modules |
| `README.md`, `docs/agent-handoff.md` (modify) | Local setup and data-flow docs |

---

### Task 1: Extract the driver-neutral CSV contract

Move everything in `postgres_import.py` that knows nothing about Postgres into `canonical_import.py`, and split `_replace_selection_evidence` into a pure row builder plus the Postgres writer. There should be no behavior change: the existing `tests/test_postgres_import.py` must pass untouched.

**Files:**
- Create: `deadbot/canonical_import.py`
- Modify: `deadbot/postgres_import.py` (lines 1–420 become imports; `_replace_selection_evidence` at lines 210–321 becomes a thin writer)
- Test: `tests/test_canonical_import.py`

**Interfaces:**
- Produces (in `deadbot.canonical_import`): `ROOT`, `DEFAULT_CANONICAL_DIR`, `DEFAULT_SELECTION_EVIDENCE_PATH`, `TableSpec`, `TABLE_SPECS`, `CanonicalImportError`, `CanonicalSnapshot`, `read_canonical_table(canonical_dir, spec) -> list[tuple]`, `read_canonical_tables(canonical_dir=..., specs=...) -> dict[str, list[tuple]]`, `canonical_snapshot(canonical_dir, rows_by_table, specs=...) -> CanonicalSnapshot`, `read_selection_evidence(path=...) -> dict`, and the new `selection_evidence_rows(document) -> SelectionRows`.
- `SelectionRows` is a frozen dataclass with four `list[tuple[Any, ...]]` fields, in insert order: `resources` (8 columns: resource_id, resource_type, title, creator, source_name, source_url, published_date, notes), `lists` (8: selection_list_id, title, selection_type, selector_name, source_resource_id, published_date, retrieved_at, notes), `entries` (13: selection_entry_id, selection_list_id, entry_position, rank, vote_count, score, show_id, performance_id, song_id, release_id, recording_id, source_label, notes), `evidence` (6: selection_evidence_id, source_resource_id, selection_list_id, signal_type, resolution_state, payload_json_text).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_canonical_import.py
from deadbot.canonical_import import (
    TABLE_SPECS,
    SelectionRows,
    read_selection_evidence,
    selection_evidence_rows,
)
from deadbot import postgres_import


def test_selection_rows_are_deterministic_and_shaped_for_insert():
    document = read_selection_evidence()
    first = selection_evidence_rows(document)
    second = selection_evidence_rows(document)
    assert isinstance(first, SelectionRows)
    assert first == second
    assert len(first.evidence) == len(document["entries"])
    assert all(len(row) == 8 for row in first.resources)
    assert all(len(row) == 8 for row in first.lists)
    assert all(len(row) == 13 for row in first.entries)
    assert all(len(row) == 6 for row in first.evidence)
    resource_ids = {row[0] for row in first.resources}
    assert {row[1] for row in first.evidence} <= resource_ids


def test_postgres_importer_reexports_the_shared_contract():
    assert postgres_import.TABLE_SPECS is TABLE_SPECS
    assert postgres_import.read_selection_evidence is read_selection_evidence
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_canonical_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.canonical_import'`

- [ ] **Step 3: Create `deadbot/canonical_import.py`**

Move these definitions **verbatim** from `deadbot/postgres_import.py` into the new module, keeping their docstrings and comments: `ROOT`, `DEFAULT_CANONICAL_DIR`, `DEFAULT_SELECTION_EVIDENCE_PATH`, `Converter`, `_as_date`, `_as_int`, `_as_float`, `_as_bool`, `TableSpec`, `_spec`, `TABLE_SPECS` (with its ordering comment), `CanonicalSnapshot`, `CanonicalImportError`, `read_selection_evidence`, `_stable_selection_id`, `_selection_source_url`, `_selector_name`, `_convert_row`, `read_canonical_table`, `read_canonical_tables`, `canonical_snapshot`. Module header:

```python
"""The reviewed canonical CSVs as a database-neutral contract.

Every database writer (the SQLite builder, and the PostgreSQL importer while
it remains) reads and validates input through this module, so a CSV that one
accepts the other accepts too. Standard library only: Vercel's build step
imports this before any dependency is installed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
```

Then add the row builder. Its body is the first half of today's `_replace_selection_evidence` (lines 220–297), returning rows instead of executing SQL:

```python
@dataclass(frozen=True)
class SelectionRows:
    """Insert-ready rows generated solely from the reviewed selection packet."""

    resources: list[tuple[Any, ...]]
    lists: list[tuple[Any, ...]]
    entries: list[tuple[Any, ...]]
    evidence: list[tuple[Any, ...]]


def selection_evidence_rows(document: Mapping[str, Any]) -> SelectionRows:
    """Project the reviewed packet into resource, list, entry and evidence rows."""

    entries = document["entries"]
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
        # ... lines 230-297 of today's postgres_import.py, unchanged ...
    return SelectionRows(
        resources=list(resources.values()),
        lists=list(lists.values()),
        entries=entry_rows,
        evidence=evidence_rows,
    )
```

(The `# ...` line means "paste the existing loop body here unchanged". It is the only elided code in this plan because it is a verbatim move of lines 230–297.)

- [ ] **Step 4: Rewire `deadbot/postgres_import.py`**

Delete the moved definitions and import them instead, so every existing caller and test that uses `postgres_import.X` keeps working:

```python
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
```

Keep `DEFAULT_SCHEMA_PATH`, `DEFAULT_MIGRATIONS_DIR`, `SCHEMA_VERSION`, `TableImportResult` and `ImportReport` in `postgres_import.py`. Replace `_replace_selection_evidence` with:

```python
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
```

Remove imports that `postgres_import.py` no longer uses (`csv`, `hashlib`, `date`, and so on). Keep `json`, `re`, and `uuid` only if they are still referenced (check with `grep -n "json\.\|re\.\|uuid\." deadbot/postgres_import.py`).

- [ ] **Step 5: Run the new and existing importer tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_canonical_import.py tests/test_postgres_import.py tests/test_data.py tests/test_provenance.py -v`
Expected: all PASS

- [ ] **Step 6: Prove the contract module is stdlib-only**

Run: `python3 -I -c "import sys; sys.path.insert(0, '.'); import deadbot.canonical_import as m; print(len(m.TABLE_SPECS))"`
Expected: prints `24`. (`-I` ignores user site-packages; any third-party import would fail.)

- [ ] **Step 7: Commit**

```bash
git add deadbot/canonical_import.py deadbot/postgres_import.py tests/test_canonical_import.py
git commit -m "The canonical CSV contract and selection rows move to a database-neutral module"
```

---

### Task 2: SQLite schema and builder

**Files:**
- Create: `schema/sqlite.sql`
- Create: `deadbot/sqlite_build.py`
- Create: `tests/conftest.py`
- Test: `tests/test_sqlite_build.py`

**Interfaces:**
- Consumes: everything `deadbot.canonical_import` produces (Task 1).
- Produces (in `deadbot.sqlite_build`): `DEFAULT_SQLITE_PATH: Path` (`ROOT / "build" / "deadbot.sqlite"`), `SQLITE_SCHEMA_PATH: Path`, `SQLITE_SCHEMA_VERSION = 1`, `BuildReport` (frozen dataclass: `path: Path`, `fingerprint: str`, `row_counts: dict[str, int]`), `input_fingerprint(canonical_dir=DEFAULT_CANONICAL_DIR, selection_evidence_path=DEFAULT_SELECTION_EVIDENCE_PATH, schema_path=SQLITE_SCHEMA_PATH) -> str`, `build_database(output=DEFAULT_SQLITE_PATH, *, canonical_dir=..., selection_evidence_path=..., schema_path=...) -> BuildReport`.
- Produces (in `tests/conftest.py`): session fixture `built_sqlite -> Path`.

- [ ] **Step 1: Write the shared fixture and the failing tests**

```python
# tests/conftest.py
import pytest


@pytest.fixture(scope="session")
def built_sqlite(tmp_path_factory):
    """The real canonical CSVs built once per session into a SQLite file."""

    from deadbot.sqlite_build import build_database

    return build_database(tmp_path_factory.mktemp("sqlite") / "deadbot.sqlite").path
```

```python
# tests/test_sqlite_build.py
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_sqlite_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.sqlite_build'`

- [ ] **Step 3: Write `schema/sqlite.sql`**

This is a mechanical port of the **serving** part of `schema/postgres.sql`. Begin the file with:

```sql
-- Deadbot canonical schema for the SQLite read store.
--
-- A port of the serving tables in schema/postgres.sql. The file is rebuilt
-- from data/canonical on every deploy (deadbot/sqlite_build.py) and opened
-- read-only at runtime, so triggers only guard inserts. Audit and enrichment
-- tables that nothing reads at runtime (source registry, snapshots, import
-- ledger, claims, observations, release/show coverage) are not ported.

CREATE TABLE deadbot_schema_metadata (
    schema_version INTEGER PRIMARY KEY,
    input_fingerprint TEXT NOT NULL,
    built_at TEXT NOT NULL
);
```

**Port these tables, in this order, with their `CHECK`/`UNIQUE`/`REFERENCES` clauses, their comments, and every `CREATE [UNIQUE] INDEX` that targets them (some indexes sit next to the table, and others are near the end of `postgres.sql`, lines 720–846. Search for `ON <table>`):**
people, songs, venues, equipment, shows, show_equipment, song_writers, band_memberships, resources, resource_songs, resource_shows, show_performers, performances, performance_performers, resource_performances, show_links, performance_links, official_releases, official_release_tracks, release_personnel, song_arrangements, arrangement_chord_sections, recordings, performance_recordings, selection_lists, selection_entries, selection_evidence.

**Do not port:** source_registry, source_snapshots, canonical_snapshots, canonical_imports, release_shows, official_release_track_performances, claims, claim_entities, derived_observations, observation_entities, observation_resources, deadbot_response_cache, any `CREATE FUNCTION`, the `official_release_track_performances_covered_show` and `derived_observations_same_superseded_key` triggers, and `BEGIN;`/`COMMIT;`. No ported table references a skipped one (verified 2026-09-23).

**Translation rules (apply every one; nothing else changes):**

| Postgres | SQLite |
|---|---|
| `DATE` | `TEXT` |
| `TIMESTAMPTZ` | `TEXT` |
| `DOUBLE PRECISION`, `NUMERIC` | `REAL` |
| `BOOLEAN NOT NULL` column `x` | `TEXT NOT NULL CHECK (x IN ('true', 'false'))` (keep any `DEFAULT`, written as `DEFAULT 'false'`) |
| `JSONB` | `TEXT` |
| `CHECK (jsonb_typeof(x) = 'object')` | `CHECK (json_type(x) = 'object')` |
| `num_nonnulls(a, b, c, d, e) = 1` | `((a IS NOT NULL) + (b IS NOT NULL) + (c IS NOT NULL) + (d IS NOT NULL) + (e IS NOT NULL)) = 1` |
| `btrim(x)` | `trim(x)` |
| `DEFERRABLE INITIALLY DEFERRED`, `ON DELETE CASCADE`, partial-index `WHERE` | keep as written |

The two in-scope plpgsql triggers become native SQLite triggers. Place each one directly after its table, keeping the Postgres comment above it:

```sql
-- An arrangement must describe the same song as its source resource and,
-- when present, its performance-specific context.
CREATE TRIGGER song_arrangements_same_song
BEFORE INSERT ON song_arrangements
FOR EACH ROW
WHEN NOT EXISTS (
        SELECT 1 FROM resource_songs rs
        WHERE rs.resource_id = NEW.resource_id AND rs.song_id = NEW.song_id
    )
    OR (
        NEW.performance_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM performances p
            WHERE p.performance_id = NEW.performance_id AND p.song_id = NEW.song_id
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'arrangement has a resource or performance for a different song');
END;
```

```sql
-- A recording source belongs to one show, so its mapped performances must too.
CREATE TRIGGER performance_recordings_same_show
BEFORE INSERT ON performance_recordings
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM performances p
    JOIN recordings r ON r.recording_id = NEW.recording_id
    WHERE p.performance_id = NEW.performance_id AND p.show_id = r.show_id
)
BEGIN
    SELECT RAISE(ABORT, 'performance and recording belong to different shows');
END;
```

Check your port: `grep -nE "TIMESTAMPTZ|JSONB|jsonb_|num_nonnulls|btrim|BOOLEAN|DOUBLE|NUMERIC|::|plpgsql|\\$\\$" schema/sqlite.sql` must print nothing.

- [ ] **Step 4: Write `deadbot/sqlite_build.py`**

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_sqlite_build.py -v`
Expected: all PASS. If `test_every_postgres_index_on_a_served_table_exists` fails, the failure names the indexes you missed; port them. If the build raises `CanonicalImportError` naming broken references or a trigger, **stop and report the message to the owner**. That is real data drift that Postgres would also have rejected, so don't loosen the schema to get past it.

- [ ] **Step 6: Build with a bare interpreter, the way Vercel will**

Run: `python3 -I -m deadbot.sqlite_build --output build/deadbot.sqlite` (run from the repo root; `-I` isolates from user site-packages. If it cannot find `deadbot`, use `PYTHONPATH=. python3 -m deadbot.sqlite_build --output build/deadbot.sqlite` and confirm `python3 -c "import fastapi"` is not needed for it to succeed.)
Expected: JSON output with `bytes` around 66,000,000, finishing in under 5 seconds.

- [ ] **Step 7: Commit**

```bash
git add schema/sqlite.sql deadbot/sqlite_build.py tests/conftest.py tests/test_sqlite_build.py
git commit -m "The canonical CSVs build into a SQLite file with the served schema, indexes and triggers"
```

---

### Task 3: Rebuild locally when inputs change, and a `db-build` command

**Files:**
- Modify: `deadbot/sqlite_build.py` (add `ensure_current`)
- Modify: `deadbot/cli.py:22-25` (choices and help) and the dispatch block after line 53
- Test: `tests/test_sqlite_build.py` (append)

**Interfaces:**
- Consumes: `build_database`, `input_fingerprint`, `DEFAULT_SQLITE_PATH` (Task 2).
- Produces: `ensure_current(path=DEFAULT_SQLITE_PATH, **inputs) -> Path` where `inputs` are the same keyword arguments `build_database` takes; the CLI command `deadbot db-build [--output PATH]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sqlite_build.py`:

```python
from deadbot.sqlite_build import ensure_current


def test_ensure_current_keeps_a_matching_build(built_sqlite, tmp_path):
    copy = tmp_path / "deadbot.sqlite"
    shutil.copy(built_sqlite, copy)
    before = copy.stat().st_mtime_ns
    assert ensure_current(copy) == copy
    assert copy.stat().st_mtime_ns == before


def test_ensure_current_rebuilds_when_inputs_change(built_sqlite, tmp_path):
    canonical = tmp_path / "canonical"
    shutil.copytree(DEFAULT_CANONICAL_DIR, canonical)
    copy = tmp_path / "deadbot.sqlite"
    shutil.copy(built_sqlite, copy)
    with (canonical / "equipment.csv").open("a", encoding="utf-8") as handle:
        handle.write("\nequipment-test-rebuild,Test Rig,amplifier,,,\n")
    ensure_current(copy, canonical_dir=canonical)
    db = _connect(copy)
    assert db.execute("SELECT name FROM equipment WHERE equipment_id = 'equipment-test-rebuild'").fetchone() == ("Test Rig",)


def test_ensure_current_builds_a_missing_file(tmp_path):
    target = tmp_path / "nested" / "deadbot.sqlite"
    assert ensure_current(target).is_file()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_sqlite_build.py -k ensure_current -v`
Expected: FAIL with `ImportError: cannot import name 'ensure_current'`

- [ ] **Step 3: Implement `ensure_current`**

Add to `deadbot/sqlite_build.py` above `main`:

```python
def _stored_fingerprint(path: Path) -> str | None:
    try:
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            row = db.execute("SELECT input_fingerprint FROM deadbot_schema_metadata").fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def ensure_current(path: Path | str = DEFAULT_SQLITE_PATH, **inputs: Any) -> Path:
    """Build ``path`` unless it already reflects exactly the current inputs."""

    path = Path(path)
    fingerprint_inputs = {key: inputs[key] for key in ("canonical_dir", "selection_evidence_path", "schema_path") if key in inputs}
    if path.is_file() and _stored_fingerprint(path) == input_fingerprint(**fingerprint_inputs):
        return path
    return build_database(path, **inputs).path
```

- [ ] **Step 4: Add the CLI command**

In `deadbot/cli.py`, change the `command` argument to `choices=["chat", "evaluate", "serve", "db-build", "db-import"]` and its help to `"Run chat, an evaluation, the web experience, a SQLite build, or a PostgreSQL import."`. Change the `--output` help to `"Evaluation results JSON file, or the database path for db-build."`. Directly after `settings = Settings.from_env()`, add:

```python
    if args.command == "db-build":
        from deadbot.sqlite_build import DEFAULT_SQLITE_PATH, main as build_main

        build_main(["--output", str(args.output or DEFAULT_SQLITE_PATH)])
        return
```

(Task 5 adds `settings.sqlite_path` between the two.)

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_sqlite_build.py tests/test_cli.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add deadbot/sqlite_build.py deadbot/cli.py tests/test_sqlite_build.py
git commit -m "A local run rebuilds the SQLite file when the checked-out data changes; deadbot db-build builds it on demand"
```

---

### Task 4: `SqliteCanonicalStore` with a temp-file response cache

**Files:**
- Create: `deadbot/sqlite_store.py`
- Modify: `deadbot/postgres.py:404-419` (extract `_fresh_cached_payload`) and `deadbot/postgres.py:444` (`::text` → `CAST`)
- Test: `tests/test_sqlite_store.py`

**Interfaces:**
- Consumes: `built_sqlite` fixture (Task 2); `PostgresCanonicalStore`, `_parse_timestamp` from `deadbot.postgres`.
- Produces: `SqliteCanonicalStore(path: Path | str, *, response_cache_path: Path | str | None = None)` with the full `CanonicalStore` read API plus `data_version()`, `ensure_response_cache()`, `cached_response(question_key, data_version, max_age_seconds) -> dict | None`, `store_response(question_key, data_version, question, response) -> None`, `close()`. Module constant `DEFAULT_RESPONSE_CACHE_PATH: Path`. In `deadbot.postgres`: `_fresh_cached_payload(response_text: Any, created_at: Any, max_age_seconds: int) -> dict | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sqlite_store.py
from concurrent.futures import ThreadPoolExecutor

import pytest

from deadbot.data import CanonicalStore
from deadbot.sqlite_store import SqliteCanonicalStore


@pytest.fixture(scope="module")
def csv_store():
    return CanonicalStore()


@pytest.fixture
def store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def test_missing_file_names_the_build_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="db-build"):
        SqliteCanonicalStore(tmp_path / "absent.sqlite")


@pytest.mark.parametrize("show_query", ["1977-05-08", "1972-08-27"])
def test_show_context_matches_the_csv_store(store, csv_store, show_query):
    show = csv_store.resolve_show(show_query)
    assert store.resolve_show(show_query) == show
    assert store.show_context(show) == csv_store.show_context(show)


@pytest.mark.parametrize("title", ["Dark Star", "Truckin'", "Sugar Magnolia"])
def test_song_views_match_the_csv_store(store, csv_store, title):
    song = csv_store.resolve_song(title)
    assert store.song_context(song) == csv_store.song_context(song)
    assert store.song_performance_profile(song) == csv_store.song_performance_profile(song)


def test_album_and_performance_views_match_the_csv_store(store, csv_store):
    release = csv_store.resolve_release("American Beauty")
    assert store.album_context(release) == csv_store.album_context(release)
    performance_id = csv_store.show_context(csv_store.resolve_show("1977-05-08"))["performances"][0]["performance_id"]
    assert store.performance_context(performance_id) == csv_store.performance_context(performance_id)


def test_selection_signals_and_coverage_read(store):
    signals = store.selection_signal_rows()
    assert signals and all(isinstance(signal, dict) for signal in signals)
    assert store.coverage_summary()["dated_show_count"] > 2000


def test_parallel_threads_each_read_safely(store):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.resolve_song("Dark Star")["song_id"], range(32)))
    assert len(set(results)) == 1


def test_response_cache_round_trip_and_expiry(store):
    store.ensure_response_cache()
    version = store.data_version()
    store.store_response("what is dark star", version, "What is Dark Star?", {"mode": "answer"})
    assert store.cached_response("what is dark star", version, 60) == {"mode": "answer"}
    assert store.cached_response("what is dark star", "other-version", 60) is None
    assert store.cached_response("what is dark star", version, -1) is None


def test_store_reopens_after_close(store):
    store.close()
    assert store.resolve_song("Dark Star")
```

Adjust only the parametrized example values if one does not resolve in the CSV store (check with `CanonicalStore().resolve_show("1972-08-27")`). The point is real entities with rich context.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_sqlite_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.sqlite_store'`

- [ ] **Step 3: Make the shared query layer SQLite-clean and share the cache check**

In `deadbot/postgres.py`, `selection_signal_rows` (line 444): replace `e.\"payload\"::text AS payload` with `CAST(e.\"payload\" AS TEXT) AS payload`. This is valid in both databases.

Add this module-level function after `_parse_timestamp`:

```python
def _fresh_cached_payload(response_text: Any, created_at: Any, max_age_seconds: int) -> dict[str, Any] | None:
    """A stored answer's payload while it is younger than ``max_age_seconds``."""

    created = _parse_timestamp(created_at)
    if created is None or (datetime.now(created.tzinfo) - created).total_seconds() > max_age_seconds:
        return None
    try:
        payload = json.loads(response_text)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
```

and shorten `PostgresCanonicalStore.cached_response` to:

```python
    def cached_response(self, question_key: str, data_version: str, max_age_seconds: int) -> dict[str, Any] | None:
        rows = self._execute(
            f"SELECT response, created_at FROM {self._qualified_table('deadbot_response_cache')} "
            "WHERE question_key = %s AND data_version = %s",
            (question_key, data_version),
        )
        if not rows:
            return None
        return _fresh_cached_payload(rows[0].get("response"), rows[0].get("created_at"), max_age_seconds)
```

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_postgres_store.py tests/test_response_cache.py -v`
Expected: all PASS

- [ ] **Step 4: Write `deadbot/sqlite_store.py`**

```python
"""SQLite-backed access to the canonical graph.

The canonical database is a file built from the reviewed CSVs
(``deadbot.sqlite_build``) and opened read-only and immutable: nothing locks,
so every thread gets its own connection. The query layer is shared with the
PostgreSQL store; only the placeholder style differs.

Stored answers need a writable home, so they live in a separate SQLite file
in the temp directory. On Vercel that directory belongs to one instance and
empties on a cold start, which costs a repeated question only its shortcut.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deadbot.postgres import PostgresCanonicalStore, _fresh_cached_payload

DEFAULT_RESPONSE_CACHE_PATH = Path(
    os.getenv("DEADBOT_RESPONSE_CACHE_PATH")
    or Path(tempfile.gettempdir()) / "deadbot-response-cache.sqlite"
)


class _Cursor:
    """Accept the shared query layer's ``%s`` placeholders."""

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    @property
    def description(self) -> Any:
        return self._cursor.description

    def execute(self, operation: str, parameters: tuple[Any, ...] = ()) -> Any:
        return self._cursor.execute(operation.replace("%s", "?"), parameters)

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    def close(self) -> None:
        self._cursor.close()


class _Connection:
    def __init__(self, raw: sqlite3.Connection) -> None:
        self.raw = raw

    def cursor(self) -> _Cursor:
        return _Cursor(self.raw.cursor())

    def close(self) -> None:
        self.raw.close()


class SqliteCanonicalStore(PostgresCanonicalStore):
    """Read-only canonical store over a built SQLite file."""

    def __init__(self, path: Path | str, *, response_cache_path: Path | str | None = None) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Canonical SQLite database not found at {self.path}. Run `deadbot db-build`."
            )
        self._local = threading.local()
        self._opened: list[_Connection] = []
        self._opened_lock = threading.Lock()
        self._cache_path = Path(response_cache_path) if response_cache_path else DEFAULT_RESPONSE_CACHE_PATH
        self._cache_connection: sqlite3.Connection | None = None
        self._cache_lock = threading.Lock()
        super().__init__(connection_factory=self._open, schema="main")

    def _open(self) -> _Connection:
        raw = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        return _Connection(raw)

    def _connection(self) -> _Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._open()
            self._local.connection = connection
            with self._opened_lock:
                self._opened.append(connection)
        return connection

    def close(self) -> None:
        with self._opened_lock:
            opened, self._opened = self._opened, []
            self._local = threading.local()
        for connection in opened:
            connection.close()
        with self._cache_lock:
            if self._cache_connection is not None:
                self._cache_connection.close()
                self._cache_connection = None

    # ---- response cache -------------------------------------------------

    def _cache(self) -> sqlite3.Connection:
        if self._cache_connection is None:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_connection = sqlite3.connect(self._cache_path, check_same_thread=False, timeout=5)
        return self._cache_connection

    def ensure_response_cache(self) -> None:
        with self._cache_lock:
            db = self._cache()
            db.execute(
                "CREATE TABLE IF NOT EXISTS deadbot_response_cache ("
                "question_key TEXT PRIMARY KEY, data_version TEXT NOT NULL, question TEXT NOT NULL, "
                "response TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            db.commit()

    def cached_response(self, question_key: str, data_version: str, max_age_seconds: int) -> dict[str, Any] | None:
        with self._cache_lock:
            row = self._cache().execute(
                "SELECT response, created_at FROM deadbot_response_cache "
                "WHERE question_key = ? AND data_version = ?",
                (question_key, data_version),
            ).fetchone()
        if row is None:
            return None
        return _fresh_cached_payload(row[0], row[1], max_age_seconds)

    def store_response(self, question_key: str, data_version: str, question: str, response: dict[str, Any]) -> None:
        with self._cache_lock:
            db = self._cache()
            db.execute(
                "INSERT INTO deadbot_response_cache (question_key, data_version, question, response, created_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (question_key) DO UPDATE SET "
                "data_version = excluded.data_version, question = excluded.question, "
                "response = excluded.response, created_at = excluded.created_at",
                (
                    question_key,
                    data_version,
                    question,
                    json.dumps(response, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.commit()


__all__ = ["DEFAULT_RESPONSE_CACHE_PATH", "SqliteCanonicalStore"]
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_sqlite_store.py tests/test_postgres_store.py tests/test_response_cache.py -v`
Expected: all PASS. If a parity test fails, print both sides and diff them. A difference is a real bug in the schema port (usually a column typed `INTEGER`/`REAL` where the CSV text differs, or a boolean not stored as text). Fix the schema or `_sqlite_value`, not the test.

- [ ] **Step 6: Commit**

```bash
git add deadbot/sqlite_store.py deadbot/postgres.py tests/test_sqlite_store.py
git commit -m "A SQLite store serves the canonical graph read-only, with stored answers in a temp-file cache"
```

---

### Task 5: SQLite becomes the default store

**Files:**
- Modify: `deadbot/config.py:64` (`data_store` default), `Settings` fields, and `from_env` (around line 106)
- Modify: `deadbot/storage.py` (whole file)
- Modify: `deadbot/cli.py` (the `db-build` block from Task 3 now uses `settings.sqlite_path`)
- Test: `tests/test_config.py` (update the Postgres-default assertions)

**Interfaces:**
- Consumes: `ensure_current`, `DEFAULT_SQLITE_PATH` (Tasks 2–3); `SqliteCanonicalStore` (Task 4).
- Produces: `Settings.data_store` default `"sqlite"`; `Settings.sqlite_path: Path | None` from `DEADBOT_SQLITE_PATH`; `create_canonical_store(settings)` returning a `SqliteCanonicalStore` for `sqlite` and the existing `PostgresStore` for `postgres`.

- [ ] **Step 1: Update the tests first**

Replace `test_postgres_is_the_only_runtime_store` and adjust the others in `tests/test_config.py`:

```python
def test_sqlite_is_the_default_runtime_store(monkeypatch, tmp_path):
    monkeypatch.delenv("DEADBOT_DATA_STORE", raising=False)
    monkeypatch.delenv("DEADBOT_SQLITE_PATH", raising=False)
    settings = Settings.from_env(env_path=tmp_path / "absent.env")
    assert settings.data_store == "sqlite"
    assert settings.sqlite_path is None


def test_sqlite_path_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_SQLITE_PATH", str(tmp_path / "custom.sqlite"))
    assert Settings.from_env(env_path=tmp_path / "absent.env").sqlite_path == tmp_path / "custom.sqlite"


def test_sqlite_store_is_created_from_a_built_file(built_sqlite, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")  # trust the file as a deployment would
    store = create_canonical_store(Settings(data_store="sqlite", sqlite_path=built_sqlite))
    try:
        assert store.resolve_song("Dark Star")
    finally:
        store.close()


def test_unknown_store_is_rejected():
    with pytest.raises(ValueError, match="sqlite"):
        create_canonical_store(Settings(data_store="csv"))
```

Keep `test_postgres_store_requires_a_database_url` and the env-file tests, but where they assert the *default* is `postgres`, set `DEADBOT_DATA_STORE=postgres` explicitly in that test. Read the whole file first (`sed -n 1,80p tests/test_config.py`) and change only what the new default breaks. Add `import pytest` if it is missing.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL (`data_store == "postgres"`, `Settings` has no `sqlite_path`)

- [ ] **Step 3: Update `Settings`**

In `deadbot/config.py`: change the field to `data_store: str = "sqlite"` and add `sqlite_path: Path | None = None` directly below `database_url`. In `from_env`, change the `data_store=` line to:

```python
            data_store=(value("DEADBOT_DATA_STORE", "sqlite") or "sqlite").strip().lower(),
            sqlite_path=Path(sqlite_path) if (sqlite_path := value("DEADBOT_SQLITE_PATH")) else None,
```

(`Path` is already imported in `config.py`. Confirm with `grep -n "^from pathlib" deadbot/config.py`.)

- [ ] **Step 4: Rewrite `deadbot/storage.py`**

```python
"""Runtime selection for the canonical read store.

SQLite is the default: a file built from the checked-in CSVs. PostgreSQL
remains selectable until it is retired. The CSVs themselves are build inputs,
never a serving fallback.
"""

from __future__ import annotations

import os
from typing import Any

from deadbot.config import Settings


def create_canonical_store(settings: Settings | None = None) -> Any:
    """Create the configured runtime store."""

    settings = settings or Settings.from_env()
    if settings.data_store == "sqlite":
        from deadbot.sqlite_build import DEFAULT_SQLITE_PATH, ensure_current
        from deadbot.sqlite_store import SqliteCanonicalStore

        path = settings.sqlite_path or DEFAULT_SQLITE_PATH
        # A local run rebuilds whenever the checked-out data changed. A Vercel
        # deployment built its file from the same commit and cannot write one.
        if not os.environ.get("VERCEL"):
            ensure_current(path)
        return SqliteCanonicalStore(path)
    if settings.data_store == "postgres":
        if not settings.database_url:
            raise ValueError(
                "DEADBOT_DATA_STORE=postgres requires DEADBOT_DATABASE_URL "
                "(or DATABASE_URL)."
            )
        from deadbot.postgres import PostgresStore

        return PostgresStore.from_dsn(settings.database_url)
    raise ValueError(
        "DEADBOT_DATA_STORE must be sqlite or postgres; "
        "CSV files are build inputs, not a runtime store."
    )
```

In `deadbot/cli.py`'s `db-build` block, use `args.output or settings.sqlite_path or DEFAULT_SQLITE_PATH`.

- [ ] **Step 5: Run the full suite**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q`
Expected: all PASS. `tests/test_api_import.py` sets `DEADBOT_DATA_STORE=postgres` on purpose and needs no change.

- [ ] **Step 6: Smoke-test the real app locally**

Check `.env` for `DEADBOT_DATA_STORE` (`grep -n DEADBOT_DATA_STORE .env`). If it says `postgres`, tell the owner it now needs to be removed or set to `sqlite`, and pass `DEADBOT_DATA_STORE=sqlite` on the command line for this check rather than editing their `.env`. Then run:

```bash
DEADBOT_DATA_STORE=sqlite PYTHONPATH=. .venv/bin/python -m deadbot.cli serve --port 8011
```

Ask one opening-chip question in the browser pane at `http://127.0.0.1:8011` (needs `OPENAI_API_KEY`; if the worktree has none, see the memory note on local replay and copy `.env` from the main checkout). Expected: a full answer page. Server logs show no database errors. Stop the server.

- [ ] **Step 7: Commit**

```bash
git add deadbot/config.py deadbot/storage.py deadbot/cli.py tests/test_config.py
git commit -m "SQLite is the default store; a local run builds or refreshes it automatically"
```

---

### Task 6: Build and bundle on Vercel; update docs

**Files:**
- Modify: `vercel.json`
- Modify: `README.md` (local setup, around lines 80–100)
- Modify: `docs/agent-handoff.md` (lines 29–35, 56, 111–114)
- Modify: `docs/UX-NEXT-STEPS.md:386` (the `DEADBOT_DATABASE_URL` mention)

- [ ] **Step 1: Update `vercel.json`**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "python3 -m deadbot.sqlite_build --output build/deadbot.sqlite && npm --prefix web ci && npm --prefix web run build",
  "functions": {
    "app.py": {
      "includeFiles": "{web/dist/index.html,web/dist/assets/**,web/dist/fonts/**,build/deadbot.sqlite}",
      "maxDuration": 60
    }
  }
}
```

- [ ] **Step 2: Update the docs**

`README.md`: replace the Postgres install and `DEADBOT_DATABASE_URL` export with:

```markdown
Deadbot serves the catalog from `build/deadbot.sqlite`, a file built from
`data/canonical/*.csv`. You don't need a database server: the first
`deadbot serve`, `chat` or `evaluate` builds it (about two seconds), and any
later run rebuilds it when the checked-out CSVs change. To build it by hand:

    .venv/bin/python -m deadbot.cli db-build

Vercel builds the same file in its build step and bundles it with the function.
```

Change the install line to `.venv/bin/python -m pip install -e '.[dev]'`.

`docs/agent-handoff.md`: rewrite lines 29–35 to say the CSVs are the reviewed source of truth, `deadbot/sqlite_build.py` builds `build/deadbot.sqlite` from them on deploy and on local runs, `deadbot/sqlite_store.py` serves it, and `DEADBOT_DATA_STORE=sqlite` is the default. Replace the "One test needs a database" sentence on line 56 with "The suite builds its own SQLite file; no database server is needed." In the table (lines 111–114), point "Domain schema" at `schema/sqlite.sql` and add a row `| SQLite builder/store | deadbot/sqlite_build.py, deadbot/sqlite_store.py |`. Leave the Postgres rows in place until Task 7.

`docs/UX-NEXT-STEPS.md:386`: drop `DEADBOT_DATABASE_URL` from the list of needed env values.

- [ ] **Step 3: Run the full suite once more**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add vercel.json README.md docs/agent-handoff.md docs/UX-NEXT-STEPS.md
git commit -m "Vercel builds the SQLite catalog in its build step and bundles it with the function"
```

- [ ] **Step 5: Hand off to the owner for the preview deploy**

Agents cannot push. Tell the owner, in plain language, the three things they need to do, and give the push command on its own line:

```bash
git push -u origin claude/neon-sqlite-migration-da5cee
```

1. **Vercel environment variables (before or right after pushing).** In the Vercel project's Settings → Environment Variables, check for `DEADBOT_DATA_STORE`. If it is set to `postgres` for Preview or Production, delete it (the default is now `sqlite`). Leave `DEADBOT_DATABASE_URL` alone until Task 7.
2. **Open the preview deployment** once the build finishes, and confirm three things with the owner (read the build log through the browser pane if they share the URL):
   - The build log shows the builder's JSON (`"bytes": ~66000000`).
   - The function is not over Vercel's size limit. If the log reports an oversized function, add `"excludeFiles": "{data/raw/**,data/coverage/**,evals/**,tests/**,web/node_modules/**}"` next to `includeFiles` and have the owner push again.
   - Asking an opening-chip question returns a full answer.
   - If the log says `python3: command not found`, stop and report it. Don't improvise an alternative build route.
3. After the preview works, open the PR with `gh pr create` (title: "Serve the catalog from a SQLite file built on deploy; leave Neon"). The owner merges it.

---

### Task 7: Retire Neon (after production has served from SQLite)

Only start this task after the owner confirms production has answered questions from SQLite for a few days. It removes the Postgres path entirely.

**Files:**
- Delete: `deadbot/postgres_import.py`, `tests/test_postgres_import.py`, `schema/postgres.sql`, `schema/migrations/`
- Rename: `deadbot/postgres.py` → `deadbot/sql_store.py`; class `PostgresCanonicalStore` → `SqlCanonicalStore` (drop the `PostgresStore`/`PostgreSQLCanonicalStore` aliases and the psycopg factory, `from_dsn`, `verify_ready`, `REQUIRED_SCHEMA_VERSION`, and the Postgres response-cache methods, which `SqliteCanonicalStore` overrides anyway)
- Rename: `tests/test_postgres_store.py` → `tests/test_sql_store.py`
- Modify: `deadbot/sqlite_store.py`, `deadbot/api.py:30` (`query_cache_scope` import), `deadbot/storage.py` (drop the postgres branch), `deadbot/config.py` (drop `database_url`), `deadbot/cli.py` (drop `db-import`, `--database-url`, `--check`, `--rebuild`), `pyproject.toml` (drop `psycopg[binary]` and the empty `postgres` extra), `tests/test_config.py`, `tests/test_api_import.py`, `docs/agent-handoff.md`, `docs/agent-harness.md:75`
- Update the schema test in `tests/test_sqlite_build.py`: `test_every_postgres_index_on_a_served_table_exists` reads `schema/postgres.sql`. Before deleting that file, snapshot the expected index names into the test as a literal set (print them with the test's regex, then paste the sorted list).

- [ ] **Step 1:** Snapshot the index-name set into `tests/test_sqlite_build.py` as described above. Run the test; it must PASS.
- [ ] **Step 2:** `git mv deadbot/postgres.py deadbot/sql_store.py` and `git mv tests/test_postgres_store.py tests/test_sql_store.py`; rename the class and update every importer (`grep -rn "deadbot.postgres\b\|PostgresCanonicalStore\|PostgresStore" deadbot tests scripts`).
- [ ] **Step 3:** Delete the Postgres-only files and code listed above; `grep -rn "psycopg\|postgres\|DATABASE_URL" deadbot tests scripts pyproject.toml` must print only historical mentions in comments you then reword.
- [ ] **Step 4:** `PYTHONPATH=. .venv/bin/python -m pytest -q`. Expected: all PASS.
- [ ] **Step 5:** Commit: `git commit -am "Neon is retired: the SQL store serves only the built SQLite file"` (plus `git add` for renames).
- [ ] **Step 6:** Tell the owner they can delete `DEADBOT_DATABASE_URL` from Vercel and `.env`, and delete the Neon project. Give the push command and open the PR as in Task 6.

---

## Self-Review Notes

- **Coverage:** build (Tasks 2–3), serve (4–5), deploy (6), cache in temp folder (4), local auto-build (3, 5), docs (6), Neon removal (7). The owner's choice was "temp folder or Neon". This plan uses the temp folder because a Neon cache would wake the database on every question, which is exactly what used up the allowance.
- **Known risk: Vercel function size.** 66 MB file plus the existing bundle. Task 6 Step 5 checks it and gives the exact `excludeFiles` fallback.
- **Known risk: `python3` in Vercel's build image.** Vercel's build image ships Python for its Python runtime. Task 6 Step 5 makes a missing interpreter a stop-and-report, not an improvisation.
- **Not in scope:** the stale `REQUIRED_SCHEMA_VERSION = 4` in `postgres.py` (unused at runtime; removed with Task 7).
