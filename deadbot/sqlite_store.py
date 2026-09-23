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
