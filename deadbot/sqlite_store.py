"""SQLite-backed access to the canonical graph.

The canonical database is a file built from the reviewed CSVs
(``deadbot.sqlite_build``) and opened read-only and immutable: nothing locks,
so any thread may borrow any connection. Reads borrow from a small pool of
idle connections and hand them back, so short-lived thread pools (LangGraph
starts one per tools step) reuse connections instead of opening new ones.
The query layer is shared with the PostgreSQL store; only the placeholder
style differs.

Stored answers need a writable home, so they live in a separate SQLite file
in the temp directory. On Vercel that directory belongs to one instance and
empties on a cold start, which costs a repeated question only its shortcut.
"""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deadbot.postgres import PostgresCanonicalStore, _fresh_cached_payload
from deadbot.sqlite_build import SQLITE_SCHEMA_VERSION

DEFAULT_RESPONSE_CACHE_PATH = Path(
    os.getenv("DEADBOT_RESPONSE_CACHE_PATH")
    or Path(tempfile.gettempdir()) / "deadbot-response-cache.sqlite"
)

CATALOG_QUERY_MAX_ROWS = 200
CATALOG_QUERY_TIMEOUT_SECONDS = 1.5

_READ_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _read_only(action: int, arg1: str | None, arg2: str | None, _db: str | None, _trigger: str | None) -> int:
    """Allow reading and ordinary functions; deny everything else."""

    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() == "load_extension":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY


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

    # These tables' row order is itself curated content (which resource or
    # release a person listed first for a show or song), not derivable from
    # any column. The shared query layer sorts most tables by id for
    # cross-database determinism, but for these it would silently reshuffle
    # a curator's own sequencing. SQLite's ``rowid`` reproduces the CSV
    # build's insertion order exactly, so use it here instead of the shared
    # id-based ordering — a fix scoped to this SQLite-only class, since
    # PostgreSQL has no equivalent stable proxy for physical row order.
    _CSV_ORDERED_TABLES = frozenset(
        {"official_releases", "recordings", "resource_performances", "resource_shows", "resource_songs"}
    )

    # Idle read connections kept for reuse. LIFO hands back the most recently
    # used connection, whose page cache is warmest. Extra connections opened
    # under a burst are closed when returned to a full pool.
    MAX_IDLE_CONNECTIONS = 8

    # aggregate() (the aggregate_data tool) is inherited: its GROUP BY, joins,
    # label fallbacks and totals are plain SQL both engines run. The show year
    # is the one dialect-specific piece. show_date is NOT NULL ISO
    # "YYYY-MM-DD" TEXT here, so the leading four characters are the year,
    # the same reading the catalog views in schema/sqlite.sql use.
    _AGGREGATE_YEAR_SQL = 'CAST(substr(s."show_date", 1, 4) AS INTEGER)'

    def __init__(self, path: Path | str, *, response_cache_path: Path | str | None = None) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Canonical SQLite database not found at {self.path}. Run `deadbot db-build`."
            )
        self._pool: queue.LifoQueue[_Connection] = queue.LifoQueue(maxsize=self.MAX_IDLE_CONNECTIONS)
        self._pool_lock = threading.Lock()
        self._checked_out = 0
        self._cache_path = Path(response_cache_path) if response_cache_path else DEFAULT_RESPONSE_CACHE_PATH
        self._cache_connection: sqlite3.Connection | None = None
        self._cache_lock = threading.Lock()
        super().__init__(connection_factory=self._open, schema="main")

    def _order_clause(self, table: str) -> str:
        if table in self._CSV_ORDERED_TABLES:
            return " ORDER BY rowid"
        return super()._order_clause(table)

    def _open(self) -> _Connection:
        raw = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        return _Connection(raw)

    def _connection(self) -> _Connection:
        # Every read goes through ``_execute``'s borrow-and-return, and the
        # response cache has its own file, so nothing should ask for a
        # long-lived connection. Refuse rather than hand out one that leaks.
        raise RuntimeError("SqliteCanonicalStore reads borrow pooled connections through _execute")

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, str]]:
        with self._pool_lock:
            pool = self._pool
            try:
                connection = pool.get_nowait()
            except queue.Empty:
                connection = None
            self._checked_out += 1
        try:
            if connection is None:
                connection = self._open()
            return self._run(connection, sql, parameters)
        finally:
            self._give_back(pool, connection)

    def _give_back(self, pool: queue.LifoQueue[_Connection], connection: _Connection | None) -> None:
        with self._pool_lock:
            self._checked_out -= 1
            if connection is None:
                return
            # ``close()`` swaps in a fresh pool; a connection borrowed from the
            # old one is closed rather than returned to a pool nobody drains.
            if pool is self._pool:
                try:
                    pool.put_nowait(connection)
                    return
                except queue.Full:
                    pass
        connection.close()

    @property
    def open_connection_count(self) -> int:
        """Read connections currently open: idle in the pool plus checked out."""

        with self._pool_lock:
            return self._pool.qsize() + self._checked_out

    def close(self) -> None:
        with self._pool_lock:
            idle, self._pool = self._pool, queue.LifoQueue(maxsize=self.MAX_IDLE_CONNECTIONS)
        while True:
            try:
                idle.get_nowait().close()
            except queue.Empty:
                break
        with self._cache_lock:
            if self._cache_connection is not None:
                self._cache_connection.close()
                self._cache_connection = None

    def run_catalog_query(
        self, sql: str, params: dict[str, Any] | None = None, *, menu: bool = False
    ) -> dict[str, Any]:
        """Run one read-only SELECT with a row cap, a value-size cap, and a time limit.

        The guardrails protect the service, not the answer: reading is the only
        permitted action, one statement runs per call, a single oversized value
        or a runaway query is cut off, and errors come back in words the model
        can act on. ``menu`` picks the wording of the truncation note: a menu
        query's caller can narrow the filters it exposes, where free SQL can
        also add its own ``ORDER BY``/``LIMIT``.
        """

        connection = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
        try:
            # Bounds any single string or blob a function call can produce
            # (e.g. randomblob, printf, zeroblob). The progress handler below
            # only interrupts between VM opcodes, so it cannot stop one
            # oversized value computed within a single opcode; this can.
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 60_000)
            connection.set_authorizer(_read_only)
            deadline = time.monotonic() + CATALOG_QUERY_TIMEOUT_SECONDS
            connection.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
            cursor = connection.execute(sql, params or {})
            columns = [item[0] for item in cursor.description or ()]
            fetched = cursor.fetchmany(CATALOG_QUERY_MAX_ROWS + 1)
        except sqlite3.OperationalError as exc:
            message = str(exc)
            if "interrupted" in message:
                hint = f"The query ran past the {CATALOG_QUERY_TIMEOUT_SECONDS}s time limit. Filter earlier, join on keys, or aggregate."
            elif "not authorized" in message:
                hint = "Only a single read-only SELECT is allowed."
            else:
                hint = "Check table and column names against the views in the tool description."
            return {"error": message, "hint": hint}
        except sqlite3.DataError as exc:
            return {"error": str(exc), "hint": "A value in the result is too large. Aggregate less, or return fewer columns."}
        except (sqlite3.ProgrammingError, sqlite3.Warning) as exc:
            return {"error": str(exc), "hint": "Send one SELECT statement per call."}
        except sqlite3.DatabaseError as exc:
            return {"error": str(exc), "hint": "Only a single read-only SELECT is allowed."}
        finally:
            connection.close()
        truncated = len(fetched) > CATALOG_QUERY_MAX_ROWS
        result: dict[str, Any] = {
            "columns": columns,
            "rows": [
                [value.hex() if isinstance(value, bytes) else value for value in row]
                for row in fetched[:CATALOG_QUERY_MAX_ROWS]
            ],
            "row_count": min(len(fetched), CATALOG_QUERY_MAX_ROWS),
            "truncated": truncated,
        }
        if truncated:
            if menu:
                result["note"] = (
                    f"Only the first {CATALOG_QUERY_MAX_ROWS} rows are shown. "
                    "Narrow the filters (venue, tour, or the year range) to see fewer."
                )
            else:
                result["note"] = (
                    f"Only the first {CATALOG_QUERY_MAX_ROWS} rows are shown. "
                    "Aggregate, filter, or add ORDER BY with a LIMIT."
                )
        return result

    def verify_ready(self) -> None:
        """Fail closed unless this file was built by the current builder and holds the catalog."""

        version_rows = self._query("SELECT schema_version FROM deadbot_schema_metadata")
        version = int(version_rows[0]["schema_version"]) if version_rows else 0
        if version != SQLITE_SCHEMA_VERSION:
            raise RuntimeError(
                f"SQLite schema version {version} is not ready; expected {SQLITE_SCHEMA_VERSION}. "
                "Run `deadbot db-build`."
            )
        missing = [
            label
            for label, table in (
                ("shows", "shows"),
                ("performances", "performances"),
                ("selection evidence", "selection_evidence"),
            )
            if self.row_count(table) <= 0
        ]
        if missing:
            raise RuntimeError("SQLite is not ready to serve Deadbot; missing " + ", ".join(missing) + ".")

    def data_version(self) -> str:
        """The shared fingerprint plus the build's input fingerprint.

        Row counts miss a same-count edit to the CSVs; the input fingerprint
        changes with any edit, so stored answers built on old data go stale.
        """

        rows = self._query("SELECT input_fingerprint FROM deadbot_schema_metadata")
        fingerprint = rows[0]["input_fingerprint"] if rows else ""
        return f"{super().data_version()}|input_fingerprint={fingerprint}"

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
