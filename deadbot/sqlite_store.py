"""SQLite-backed access to the canonical graph: Deadbot's one read store.

The canonical database is a file built from the reviewed CSVs
(``deadbot.sqlite_build``) and opened read-only and immutable: nothing locks,
so any thread may borrow any connection. Reads borrow from a small pool of
idle connections and hand them back, so short-lived thread pools (LangGraph
starts one per tools step) reuse connections instead of opening new ones.

Context methods fetch a bounded projection in SQL and hand the
domain-specific response shaping to :class:`deadbot.data.CanonicalStore`, so
a single entity lookup never loads a whole relationship table.

Stored answers need a writable home, so they live in a separate SQLite file
in the temp directory. On Vercel that directory belongs to one instance and
empties on a cold start, which costs a repeated question only its shortcut.
"""

from __future__ import annotations

import json
import os
import queue
import re
import sqlite3
import tempfile
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deadbot import aggregation
from deadbot.data import CanonicalStore
from deadbot.sqlite_build import SQLITE_SCHEMA_VERSION

# A per-request read-through cache of query results, keyed by SQL and
# parameters. The canonical data is read only, so within one request the same
# query always returns the same rows; without this, plan resolution re-fetched
# every show and song the research phase had already read. The cache lives in
# a context variable so parallel tool threads, which copy the context, share
# the same dict, and requests never see each other's entries.
_QUERY_CACHE: ContextVar[dict[tuple[str, tuple[Any, ...]], list[dict[str, str]]] | None] = ContextVar(
    "deadbot_query_cache", default=None
)


@contextmanager
def query_cache_scope(cache: dict | None = None) -> Iterator[dict]:
    """Serve repeated canonical queries from memory while the block runs.

    Pass the same ``cache`` dict to successive scopes to carry one request's
    cache across the steps of a streamed agent run, each of which may resume
    in a fresh copy of the context.
    """

    cache = {} if cache is None else cache
    token = _QUERY_CACHE.set(cache)
    try:
        yield cache
    finally:
        _QUERY_CACHE.reset(token)


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


# Titles keep their typography ("Dick’s Picks", "Help on the Way–Slipknot!"),
# while visitors and the model type straight quotes and hyphens. LIKE folds
# both sides so a search finds the record however its name is typed.
_TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_LIKE_PATTERNS: dict[tuple[str, str | None], re.Pattern[str]] = {}


def _fold(text: str) -> str:
    return text.translate(_TYPOGRAPHY).casefold()


def _like_pattern(pattern: str, escape: str | None) -> re.Pattern[str]:
    key = (pattern, escape)
    compiled = _LIKE_PATTERNS.get(key)
    if compiled is None:
        parts: list[str] = []
        chars = iter(_fold(pattern))
        for char in chars:
            if escape is not None and char == escape:
                parts.append(re.escape(next(chars, "")))
            elif char == "%":
                parts.append(".*")
            elif char == "_":
                parts.append(".")
            else:
                parts.append(re.escape(char))
        compiled = re.compile("".join(parts), re.DOTALL)
        if len(_LIKE_PATTERNS) < 4096:
            _LIKE_PATTERNS[key] = compiled
    return compiled


def _like(pattern: Any, value: Any, escape: Any = None) -> int | None:
    """SQLite's LIKE, folding case, curly quotes and dashes on both sides."""

    if pattern is None or value is None:
        return None
    return 1 if _like_pattern(str(pattern), escape).fullmatch(_fold(str(value))) else 0


def _with_folding_like(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.create_function("like", 2, _like, deterministic=True)
    connection.create_function("like", 3, _like, deterministic=True)
    return connection


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# aggregate()'s internal, literal (never request-derived) spec tables. Table
# and column names reaching SQL come only from these dicts (passed through
# _identifier/_table) or from _aggregate_dimension_sql's own
# literal branches below -- never directly from request.dataset/group_by/
# filters. Every value from request.filters becomes a bound ? parameter.

# filter name -> (table alias in the aggregate query, column name)
_AGGREGATE_FILTER_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "shows": {"venue_id": ("s", "venue_id")},
    "performances": {
        "song_id": ("p", "song_id"),
        "show_id": ("p", "show_id"),
        "venue_id": ("s", "venue_id"),
    },
    "guest_appearances": {
        "guest_id": ("g", "person_id"),
        "show_id": ("g", "show_id"),
        "venue_id": ("s", "venue_id"),
    },
}

# measure -> SQL aggregate expression (table aliases match the FROM clauses below)
_AGGREGATE_MEASURE_SQL: dict[str, str] = {
    "count": "COUNT(*)",
    "distinct_shows": 'COUNT(DISTINCT s."show_id")',
    "distinct_songs": 'COUNT(DISTINCT p."song_id")',
}

# These keys reproduce the deterministic ordering of the tracked canonical
# exports. They also make entity disambiguation and setlist rendering stable
# across query plans.
_ORDER_COLUMNS: dict[str, tuple[str, ...]] = {
    "arrangement_chord_sections": ("arrangement_id", "section_position"),
    "band_memberships": ("person_id", "start_date"),
    "equipment": ("equipment_id",),
    "people": ("person_id",),
    "performance_links": ("performance_link_id",),
    "performance_performers": ("performance_id", "person_id", "role", "instrument"),
    "performance_recordings": ("performance_id", "recording_id", "track_number"),
    "release_personnel": ("release_id", "person_id", "role", "instrument"),
    "resources": ("resource_id",),
    "show_equipment": (
        "show_id",
        "equipment_id",
        "usage_context",
        "claim_id",
        "source_id",
    ),
    "show_links": ("show_link_id",),
    "show_performers": ("show_id", "person_id", "role", "instrument"),
    "song_arrangements": ("arrangement_id",),
    "song_writers": ("song_id", "person_id", "writer_role"),
    "songs": ("song_id",),
    "venues": ("venue_id",),
}

# These tables' row order is itself curated content (which resource or release
# a person listed first for a show or song), not derivable from any column.
# ``rowid`` reproduces the CSV build's insertion order exactly, so reads of
# these tables keep the curator's own sequencing.
_CSV_ORDERED_TABLES = frozenset(
    {"official_releases", "recordings", "resource_performances", "resource_shows", "resource_songs"}
)


def _parse_timestamp(value: Any) -> datetime | None:
    """A stored answer's ISO timestamp; naive text is read as UTC."""

    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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


def _identifier(value: str) -> str:
    """Quote a validated SQL identifier.

    Table and column names are application-owned, never user input. Validation
    remains important because DB-API placeholders cannot parameterize them.
    """

    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return f'"{value}"'


_ID_COLUMNS = {
    "band_memberships": "membership_id",
    "equipment": "equipment_id",
    "official_releases": "release_id",
    "people": "person_id",
    "performance_links": "performance_link_id",
    "performances": "performance_id",
    "recordings": "recording_id",
    "resources": "resource_id",
    "show_links": "show_link_id",
    "shows": "show_id",
    "songs": "song_id",
    "venues": "venue_id",
}


def _string_value(value: Any) -> str:
    """A stored value as the string the CSVs hold; NULL reads as empty.

    The build writes booleans as ``"true"``/``"false"`` and dates as ISO text
    (``deadbot.sqlite_build._sqlite_value``), so those arrive as strings.
    """

    return "" if value is None else str(value)


class SqliteCanonicalStore(CanonicalStore):
    """Read-only canonical store over a built SQLite file."""

    # Idle read connections kept for reuse. LIFO hands back the most recently
    # used connection, whose page cache is warmest. Extra connections opened
    # under a burst are closed when returned to a full pool.
    MAX_IDLE_CONNECTIONS = 8

    def __init__(self, path: Path | str, *, response_cache_path: Path | str | None = None) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Canonical SQLite database not found at {self.path}. Run `deadbot db-build`."
            )
        self._pool: queue.LifoQueue[sqlite3.Connection] = queue.LifoQueue(maxsize=self.MAX_IDLE_CONNECTIONS)
        self._pool_lock = threading.Lock()
        self._checked_out = 0
        self._cache_path = Path(response_cache_path) if response_cache_path else DEFAULT_RESPONSE_CACHE_PATH
        self._cache_connection: sqlite3.Connection | None = None
        self._cache_lock = threading.Lock()

    def __enter__(self) -> SqliteCanonicalStore:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ---- connections ------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        raw = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        return _with_folding_like(raw)

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

    def _give_back(self, pool: queue.LifoQueue[sqlite3.Connection], connection: sqlite3.Connection | None) -> None:
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

    @staticmethod
    def _run(connection: sqlite3.Connection, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, str]]:
        """Run one read on ``connection`` and return its rows as string dicts."""

        cursor = connection.cursor()
        try:
            cursor.execute(sql, parameters)
            columns = [item[0] for item in cursor.description or ()]
            return [
                {name: _string_value(value) for name, value in zip(columns, row)}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()

    def _query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, str]]:
        cache = _QUERY_CACHE.get()
        key = (sql, tuple(parameters))
        if cache is not None and key in cache:
            return [dict(row) for row in cache[key]]
        rows = self._execute(sql, parameters)
        if cache is not None:
            cache[key] = [dict(row) for row in rows]
        return rows

    # ---- tables -----------------------------------------------------------

    def _table(self, table: str) -> str:
        return _identifier(table)

    def _order_clause(self, table: str) -> str:
        if table in _CSV_ORDERED_TABLES:
            return " ORDER BY rowid"
        if table == "shows":
            return ' ORDER BY "show_date" NULLS LAST, "show_id"'
        if table == "performances":
            return (
                ' ORDER BY "show_id", '
                'CAST("set_number" AS INTEGER) NULLS LAST, '
                'CAST("position_in_set" AS INTEGER) NULLS LAST, "performance_id"'
            )
        if table == "official_release_tracks":
            # The built file stores track_number as INTEGER; small test files
            # may hold it as TEXT, where a blank must sort as missing.
            return (
                ' ORDER BY "release_id", '
                'CAST(NULLIF(CAST("track_number" AS TEXT), \'\') AS INTEGER) NULLS FIRST, "performance_id"'
            )
        columns = _ORDER_COLUMNS.get(table)
        if columns:
            return " ORDER BY " + ", ".join(_identifier(column) for column in columns)
        # Unknown extension tables still receive a deterministic order without
        # guessing at an ID column that may not exist.
        return " ORDER BY 1"

    def filtered_rows(self, table: str, **criteria: str) -> list[dict[str, str]]:
        if not criteria:
            return self.rows(table)
        predicates = [f"{_identifier(column)} = ?" for column in criteria]
        sql = (
            f"SELECT * FROM {self._table(table)} WHERE {' AND '.join(predicates)}"
            f"{self._order_clause(table)}"
        )
        return self._query(sql, tuple(criteria.values()))

    _filtered_rows = filtered_rows

    def rows_in(self, table: str, column: str, values: Iterable[str]) -> list[dict[str, str]]:
        """Rows whose ``column`` is one of ``values``, in one query."""

        return self._rows_in(table, column, values)

    def _rows_in(self, table: str, column: str, values: Iterable[str]) -> list[dict[str, str]]:
        unique_values = tuple(dict.fromkeys(values))
        if not unique_values:
            return []
        placeholders = ", ".join("?" for _ in unique_values)
        sql = (
            f"SELECT * FROM {self._table(table)} "
            f"WHERE {_identifier(column)} IN ({placeholders}){self._order_clause(table)}"
        )
        return self._query(sql, unique_values)

    @staticmethod
    def _projection(tables: dict[str, list[dict[str, str]]]) -> CanonicalStore:
        projection = CanonicalStore()
        # ``tables`` is a cached_property on CanonicalStore, so seeding the
        # instance dictionary creates an in-memory, query-scoped graph.
        projection.__dict__["tables"] = tables
        return projection

    def rows(self, table: str) -> list[dict[str, str]]:
        return self._query(
            f"SELECT * FROM {self._table(table)}{self._order_clause(table)}"
        )

    def row_count(self, table: str) -> int:
        rows = self._query(
            f"SELECT COUNT(*) AS row_count FROM {self._table(table)}"
        )
        return int(rows[0]["row_count"]) if rows else 0

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
        """A fingerprint that changes whenever a build changes what answers rest on.

        Row counts miss a same-count edit to the CSVs; the input fingerprint
        changes with any edit, so stored answers built on old data go stale.
        """

        rows = self._query("SELECT input_fingerprint FROM deadbot_schema_metadata")
        fingerprint = rows[0]["input_fingerprint"] if rows else ""
        counts = self._query(
            "SELECT "
            f"(SELECT MAX(schema_version) FROM {self._table('deadbot_schema_metadata')}) AS schema_version, "
            f"(SELECT COUNT(*) FROM {self._table('shows')}) AS shows, "
            f"(SELECT COUNT(*) FROM {self._table('performances')}) AS performances, "
            f"(SELECT COUNT(*) FROM {self._table('official_release_tracks')}) AS release_tracks, "
            f"(SELECT COUNT(*) FROM {self._table('resources')}) AS resources, "
            f"(SELECT COUNT(*) FROM {self._table('selection_evidence')}) AS selection_evidence"
        )
        row = counts[0] if counts else {}
        version = "|".join(f"{key}={row.get(key, '')}" for key in sorted(row))
        return f"{version}|input_fingerprint={fingerprint}"

    def selection_signal_rows(self) -> list[dict[str, Any]]:
        """Read the complete reviewed source-attributed evidence packet."""

        rows = self._query(
            f"SELECT e.\"selection_evidence_id\", CAST(e.\"payload\" AS TEXT) AS payload, "
            f"r.\"source_url\" AS resource_url, l.\"title\" AS selection_list_title "
            f"FROM {self._table('selection_evidence')} e "
            f"JOIN {self._table('resources')} r ON r.\"resource_id\" = e.\"source_resource_id\" "
            f"LEFT JOIN {self._table('selection_lists')} l ON l.\"selection_list_id\" = e.\"selection_list_id\" "
            'ORDER BY e."selection_evidence_id"'
        )
        evidence = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Stored selection evidence payload is invalid.") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("Stored selection evidence payload is invalid.")
            payload.setdefault("source_url", row.get("resource_url"))
            evidence.append(payload)
        return evidence

    def coverage_summary(self) -> dict[str, Any]:
        """Compute catalog coverage without transferring whole tables."""

        show_rows = self._query(
            f"SELECT COUNT(*) AS dated_show_count, MIN(\"show_date\") AS first_date, "
            f"MAX(\"show_date\") AS last_date FROM {self._table('shows')} "
            'WHERE "show_date" IS NOT NULL'
        )
        performance_rows = self._query(
            f"SELECT COUNT(*) AS performance_count, "
            f"COUNT(DISTINCT \"song_id\") AS performance_song_count "
            f"FROM {self._table('performances')}"
        )
        shows = show_rows[0] if show_rows else {}
        performances = performance_rows[0] if performance_rows else {}
        first_date = shows.get("first_date", "")
        last_date = shows.get("last_date", "")
        return {
            "dated_show_count": int(shows.get("dated_show_count") or 0),
            "performance_count": int(performances.get("performance_count") or 0),
            "performance_song_count": int(performances.get("performance_song_count") or 0),
            "first_year": first_date[:4] if first_date else "",
            "last_year": last_date[:4] if last_date else "",
        }

    def search_shows(self, phrases: list[str], limit: int = 20) -> list[dict[str, str]]:
        """Search show and venue fields in one bounded indexed query surface."""

        normalized = [phrase.casefold().strip() for phrase in phrases if phrase.strip()]
        if not normalized or limit <= 0:
            return []
        searchable = " || ' ' || ".join(
            [
                f"COALESCE(CAST(s.{_identifier(column)} AS TEXT), '')"
                for column in ("show_id", "show_date", "event_name", "tour_name")
            ]
            + [
                f"COALESCE(CAST(v.{_identifier(column)} AS TEXT), '')"
                for column in ("name", "city", "state_region")
            ]
        )
        predicates = [f"LOWER({searchable}) LIKE LOWER(?) ESCAPE '\\'" for _ in normalized]
        values = [
            f"%{phrase.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
            for phrase in normalized
        ]
        sql = (
            f"SELECT s.*, v.\"name\" AS venue_name, v.\"city\" AS venue_city, "
            f"v.\"state_region\" AS venue_state_region "
            f"FROM {self._table('shows')} s "
            f"LEFT JOIN {self._table('venues')} v ON v.\"venue_id\" = s.\"venue_id\" "
            f"WHERE {' OR '.join(predicates)} "
            'ORDER BY s."show_date" NULLS LAST, s."show_id" LIMIT ?'
        )
        return self._query(sql, tuple([*values, limit]))

    def one(self, table: str, entity_id: str) -> dict[str, str] | None:
        id_column = _ID_COLUMNS.get(table)
        # CanonicalStore indexes only tables with their conventional entity ID
        # column; relationship and composite-key tables intentionally return
        # no result from ``one``.
        if id_column is None:
            return None
        rows = self._filtered_rows(table, **{id_column: entity_id})
        return rows[0] if rows else None

    def matching_rows(self, table: str, query: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
        needle = query.casefold().strip()
        if not needle or not fields:
            return []
        qualified = self._table(table)
        exact_predicates = [
            f"LOWER(COALESCE(CAST({_identifier(field)} AS TEXT), '')) = LOWER(?)"
            for field in fields
        ]
        exact = self._query(
            f"SELECT * FROM {qualified} WHERE {' OR '.join(exact_predicates)}"
            f"{self._order_clause(table)}",
            tuple(needle for _ in fields),
        )
        if exact:
            return exact
        # Escape LIKE metacharacters so substring matching has the same literal
        # semantics as CanonicalStore's Python implementation.
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        fuzzy_predicates = [
            f"LOWER(COALESCE(CAST({_identifier(field)} AS TEXT), '')) LIKE LOWER(?) ESCAPE '\\'"
            for field in fields
        ]
        return self._query(
            f"SELECT * FROM {qualified} WHERE {' OR '.join(fuzzy_predicates)}"
            f"{self._order_clause(table)}",
            tuple(f"%{escaped}%" for _ in fields),
        )

    def matching_rows_any(
        self, table: str, phrases: list[str], fields: tuple[str, ...], limit: int = 12
    ) -> list[dict[str, str]]:
        """One query for every phrase: exact matches rank ahead of substring matches."""

        needles = [phrase.casefold().strip() for phrase in phrases]
        needles = [needle for needle in dict.fromkeys(needles) if needle]
        if not needles or not fields or limit <= 0:
            return []
        qualified = self._table(table)
        exact = " OR ".join(
            f"LOWER(COALESCE(CAST({_identifier(field)} AS TEXT), '')) = LOWER(?)"
            for field in fields
            for _ in needles
        )
        fuzzy = " OR ".join(
            f"LOWER(COALESCE(CAST({_identifier(field)} AS TEXT), '')) LIKE LOWER(?) ESCAPE '\\'"
            for field in fields
            for _ in needles
        )
        exact_values = [needle for _ in fields for needle in needles]
        fuzzy_values = [
            "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            for _ in fields
            for needle in needles
        ]
        order = self._order_clause(table).replace(" ORDER BY ", ", ", 1)
        sql = (
            f"SELECT *, CASE WHEN {exact} THEN 0 ELSE 1 END AS _match_rank FROM {qualified} "
            f"WHERE {exact} OR {fuzzy} ORDER BY _match_rank{order} LIMIT ?"
        )
        rows = self._query(sql, tuple([*exact_values, *exact_values, *fuzzy_values, limit]))
        for row in rows:
            row.pop("_match_rank", None)
        return rows

    # resolve_song, show_candidates, resolve_show, resolve_person and
    # resolve_equipment are inherited: they compose the optimized ``one`` and
    # ``matching_rows`` calls.

    def resources_for(self, relation_table: str, target_key: str, target_id: str) -> list[dict[str, str]]:
        relationships = self._filtered_rows(relation_table, **{target_key: target_id})
        resources = self._rows_in(
            "resources", "resource_id", (row["resource_id"] for row in relationships)
        )
        projection = self._projection({relation_table: relationships, "resources": resources})
        return projection.resources_for(relation_table, target_key, target_id)

    def official_release_summaries(self, release_ids: set[str]) -> list[dict[str, str]]:
        releases = self._rows_in("official_releases", "release_id", release_ids)
        return CanonicalStore.official_release_summaries(
            self._projection({"official_releases": releases}), release_ids
        )

    def resolve_release(self, identifier: str) -> dict[str, str] | None:
        direct = self.one("official_releases", identifier)
        if direct:
            return direct
        matches = self.matching_rows("official_releases", identifier, ("title",))
        return matches[0] if len(matches) == 1 else None

    def album_context(self, release: dict[str, str]) -> dict[str, Any]:
        release_id = release["release_id"]
        tracks = self.filtered_rows("official_release_tracks", release_id=release_id)
        personnel = self.filtered_rows("release_personnel", release_id=release_id)
        song_ids = {row["song_id"] for row in tracks if row.get("song_id", "").strip()}
        person_ids = {row["person_id"] for row in personnel}
        return CanonicalStore.album_context(
            self._projection(
                {
                    "official_release_tracks": tracks,
                    "release_personnel": personnel,
                    "songs": self._rows_in("songs", "song_id", song_ids),
                    "people": self._rows_in("people", "person_id", person_ids),
                }
            ),
            release,
        )

    def _release_tracks_for_song(
        self, song_id: str, performance_ids: list[str]
    ) -> list[dict[str, str]]:
        """official_release_tracks rows naming this song or one of its performances.

        A studio release names the song directly on the track row; a live
        release names one of its performances instead. ``song_releases`` needs
        both, so this narrows to their union in one query rather than pulling
        the whole table.
        """

        table = "official_release_tracks"
        predicates = [f"{_identifier('song_id')} = ?"]
        values: list[Any] = [song_id]
        if performance_ids:
            placeholders = ", ".join("?" for _ in performance_ids)
            predicates.append(f"{_identifier('performance_id')} IN ({placeholders})")
            values.extend(performance_ids)
        sql = (
            f"SELECT * FROM {self._table(table)} "
            f"WHERE {' OR '.join(predicates)}{self._order_clause(table)}"
        )
        return self._query(sql, tuple(values))

    def song_context(self, song: dict[str, str]) -> dict[str, Any]:
        song_id = song["song_id"]
        relationships = self._filtered_rows("resource_songs", song_id=song_id)
        performances = self._filtered_rows("performances", song_id=song_id)
        performance_ids = [row["performance_id"] for row in performances]
        release_tracks = self._release_tracks_for_song(song_id, performance_ids)
        release_ids = {row["release_id"] for row in release_tracks}
        tables = {
            "song_writers": self._filtered_rows("song_writers", song_id=song_id),
            "performances": performances,
            "song_arrangements": self._filtered_rows("song_arrangements", song_id=song_id),
            "resource_songs": relationships,
            "resources": self._rows_in(
                "resources", "resource_id", (row["resource_id"] for row in relationships)
            ),
            "performance_links": self._rows_in(
                "performance_links", "performance_id", performance_ids
            ),
            "official_release_tracks": release_tracks,
            "official_releases": self._rows_in("official_releases", "release_id", release_ids),
        }
        return CanonicalStore.song_context(self._projection(tables), song)

    def song_performance_profile(self, song: dict[str, str]) -> dict[str, Any]:
        """Compute the same derived profile as CSV from a bounded projection."""
        song_id = song["song_id"]
        target = self._filtered_rows("performances", song_id=song_id)
        show_ids = tuple(row.get("show_id", "") for row in target)
        all_performances = self._rows_in("performances", "show_id", show_ids)
        shows = self._rows_in("shows", "show_id", show_ids)
        neighbor_ids = {row.get("song_id", "") for row in all_performances}
        songs = self._rows_in("songs", "song_id", neighbor_ids | {song_id})
        projection = self._projection({"performances": all_performances, "shows": shows, "songs": songs})
        return CanonicalStore.song_performance_profile(projection, song)

    def arrangement_search(self, key_signature: str) -> dict[str, Any]:
        normalized_key = key_signature.strip()
        sql = (
            f"SELECT * FROM {self._table('song_arrangements')} "
            "WHERE LOWER(COALESCE(CAST(\"key_signature\" AS TEXT), '')) = LOWER(?)"
            f"{self._order_clause('song_arrangements')}"
        )
        arrangements = self._query(sql, (normalized_key,))
        return CanonicalStore.arrangement_search(
            self._projection({"song_arrangements": arrangements}), normalized_key
        )

    def equipment_history(self, equipment: dict[str, str]) -> dict[str, Any]:
        equipment_id = equipment["equipment_id"]
        assignments = self._filtered_rows("show_equipment", equipment_id=equipment_id)
        shows = self._rows_in("shows", "show_id", (row.get("show_id", "") for row in assignments))
        venues = self._rows_in("venues", "venue_id", (row.get("venue_id", "") for row in shows))
        return CanonicalStore.equipment_history(
            self._projection({"show_equipment": assignments, "shows": shows, "venues": venues}),
            equipment,
        )

    def band_lineup(self, show_date: str, act: str = "grateful-dead") -> list[dict[str, str]]:
        memberships = self._filtered_rows("band_memberships", act=act) if show_date else []
        people = self._rows_in(
            "people", "person_id", (row["person_id"] for row in memberships)
        )
        return CanonicalStore.band_lineup(
            self._projection({"band_memberships": memberships, "people": people}), show_date, act
        )

    def show_context(self, show: dict[str, str]) -> dict[str, Any]:
        show_id = show["show_id"]
        performances = self._filtered_rows("performances", show_id=show_id)
        performance_ids = [row["performance_id"] for row in performances]
        release_tracks = self._rows_in("official_release_tracks", "performance_id", performance_ids)
        performer_assignments = self._filtered_rows("show_performers", show_id=show_id)
        equipment_assignments = self._filtered_rows("show_equipment", show_id=show_id)
        resource_relationships = self._filtered_rows("resource_shows", show_id=show_id)
        # band_memberships is small enough (a few dozen rows at most) to fetch
        # whole; CanonicalStore.band_lineup derives the date-range match
        # rather than issuing a per-show query.
        band_memberships = self.rows("band_memberships")
        person_ids = {row["person_id"] for row in performer_assignments} | {
            row["person_id"] for row in band_memberships
        }
        tables = {
            "performances": performances,
            "official_release_tracks": release_tracks,
            "official_releases": self._rows_in(
                "official_releases", "release_id", (row["release_id"] for row in release_tracks)
            ),
            "venues": self._rows_in("venues", "venue_id", (show.get("venue_id", ""),)),
            "show_performers": performer_assignments,
            "people": self._rows_in("people", "person_id", person_ids),
            "show_equipment": equipment_assignments,
            "equipment": self._rows_in(
                "equipment", "equipment_id", (row["equipment_id"] for row in equipment_assignments)
            ),
            "recordings": self._filtered_rows("recordings", show_id=show_id),
            # Per-performance listening paths (CanonicalStore._listen_paths)
            # read performance_links and official_release_tracks.
            "performance_links": self._rows_in("performance_links", "performance_id", performance_ids),
            "band_memberships": band_memberships,
            "resource_shows": resource_relationships,
            "resources": self._rows_in(
                "resources", "resource_id", (row["resource_id"] for row in resource_relationships)
            ),
            "show_links": self._filtered_rows("show_links", show_id=show_id),
        }
        return CanonicalStore.show_context(self._projection(tables), show)

    def performance_context(self, performance_id: str) -> dict[str, Any] | None:
        performance = self.one("performances", performance_id)
        if not performance:
            return None
        release_tracks = self._filtered_rows("official_release_tracks", performance_id=performance_id)
        resource_relationships = self._filtered_rows(
            "resource_performances", performance_id=performance_id
        )
        performer_credits = self._filtered_rows("performance_performers", performance_id=performance_id)
        tables = {
            "performances": [performance],
            "songs": self._rows_in("songs", "song_id", (performance["song_id"],)),
            "shows": self._rows_in("shows", "show_id", (performance["show_id"],)),
            "performance_performers": performer_credits,
            "people": self._rows_in("people", "person_id", (row["person_id"] for row in performer_credits)),
            "official_release_tracks": release_tracks,
            "official_releases": self._rows_in(
                "official_releases", "release_id", (row["release_id"] for row in release_tracks)
            ),
            "resource_performances": resource_relationships,
            "resources": self._rows_in(
                "resources", "resource_id", (row["resource_id"] for row in resource_relationships)
            ),
            "performance_links": self._filtered_rows(
                "performance_links", performance_id=performance_id
            ),
            "show_links": self._filtered_rows("show_links", show_id=performance["show_id"]),
            "performance_recordings": self._filtered_rows(
                "performance_recordings", performance_id=performance_id
            ),
        }
        return CanonicalStore.performance_context(self._projection(tables), performance_id)

    # ---- song pairings ---------------------------------------------------
    # One self-join finds song A at position p and song B at p + 1 in the same
    # set. Positions compare as integers through CAST (a no-op on the typed
    # columns, and what makes text-typed test tables agree), and
    # segue_into_next is stored as "true"/"false". deadbot.sequences shapes
    # the rows the same way as for the in-memory CSV store.

    def sequence_pairs(self, first_song_id: str, second_song_id: str) -> list[dict[str, str]]:
        from deadbot import sequences

        performances = self._table("performances")
        shows = self._table("shows")
        venues = self._table("venues")
        sql = (
            'SELECT a."performance_id" AS first_performance_id, b."performance_id" AS second_performance_id, '
            's."show_id" AS show_id, s."show_date" AS show_date, a."set_number" AS set_number, '
            'a."set_label" AS set_label, a."position_in_set" AS position_in_set, a."segue_into_next" AS segue, '
            'v."name" AS venue_name, v."city" AS city, v."state_region" AS state_region '
            f"FROM {performances} a "
            f'JOIN {performances} b ON b."show_id" = a."show_id" '
            'AND CAST(b."set_number" AS INTEGER) = CAST(a."set_number" AS INTEGER) '
            'AND CAST(b."position_in_set" AS INTEGER) = CAST(a."position_in_set" AS INTEGER) + 1 '
            f'JOIN {shows} s ON s."show_id" = a."show_id" '
            f'LEFT JOIN {venues} v ON v."venue_id" = s."venue_id" '
            'WHERE a."song_id" = ? AND b."song_id" = ?'
        )
        return sequences.sort_pair_rows(self._query(sql, (first_song_id, second_song_id)))

    # ---- model-selected aggregation --------------------------------------
    # Grouping/counting happens in SQL; deadbot.aggregation shapes the raw
    # grouped rows (zero-fill, sort, limit, totals) identically for both this
    # store and CanonicalStore.aggregate's Python reference implementation.

    # The show year as an integer SQL expression over the aggregate query's
    # ``s`` alias. show_date is NOT NULL ISO "YYYY-MM-DD" TEXT, so the leading
    # four characters are the year, the same reading the catalog views in
    # schema/sqlite.sql use.
    _AGGREGATE_YEAR_SQL = 'CAST(substr(s."show_date", 1, 4) AS INTEGER)'

    def _aggregate_from_clause(self, dataset: str) -> tuple[str, list[Any]]:
        shows = self._table("shows")
        if dataset == "shows":
            return f"{shows} s", []
        if dataset == "performances":
            performances = self._table("performances")
            return f'{performances} p JOIN {shows} s ON s."show_id" = p."show_id"', []
        show_performers = self._table("show_performers")
        return (
            f'(SELECT DISTINCT "show_id", "person_id" FROM {show_performers} WHERE "role" = ?) g '
            f'JOIN {shows} s ON s."show_id" = g."show_id"',
            ["guest"],
        )

    def _aggregate_dimension_sql(self, group_by: str) -> tuple[str, str, str, str]:
        if group_by == "year":
            expr = self._AGGREGATE_YEAR_SQL
            return expr, expr, expr, ""
        if group_by == "venue":
            venues = self._table("venues")
            # Label fallback: the venue's name -> its id -> "Unknown" when the
            # id itself is blank. LEFT JOIN (not JOIN) so a show whose
            # venue_id has no matching venues row survives instead of
            # disappearing -- data.py's dimension() falls back identically.
            # TRIM the name before the blank check so a whitespace-only or
            # whitespace-padded name is treated the same as data.py's
            # label_with_fallback, which calls .strip() on the name before
            # falling back -- otherwise a padded name would pass this
            # NULLIF(..., '') check (non-empty) and render un-trimmed here
            # while the CSV path strips it down to empty and falls through.
            label_expr = "COALESCE(NULLIF(TRIM(v.\"name\"), ''), NULLIF(s.\"venue_id\", ''), 'Unknown')"
            return (
                's."venue_id"', label_expr, 's."venue_id", v."name"',
                f'LEFT JOIN {venues} v ON v."venue_id" = s."venue_id"',
            )
        if group_by == "city":
            venues = self._table("venues")
            # venues.city is nullable; COALESCE to match CanonicalStore.aggregate's
            # `venue.get("city") or "Unknown"` in data.py exactly, or the
            # CSV/SQLite parity test fails on any blank city. LEFT JOIN so a
            # show whose venue record is entirely missing still counts (as
            # "Unknown") instead of disappearing.
            city_expr = "COALESCE(NULLIF(v.\"city\", ''), 'Unknown')"
            return city_expr, city_expr, city_expr, f'LEFT JOIN {venues} v ON v."venue_id" = s."venue_id"'
        if group_by == "song":
            songs = self._table("songs")
            # TRIM before the blank check, matching data.py's label_with_fallback
            # (.strip() on the name before falling back to id then "Unknown") --
            # see the venue case above for why.
            label_expr = "COALESCE(NULLIF(TRIM(so.\"title\"), ''), NULLIF(p.\"song_id\", ''), 'Unknown')"
            return (
                'p."song_id"', label_expr, 'p."song_id", so."title"',
                f'LEFT JOIN {songs} so ON so."song_id" = p."song_id"',
            )
        people = self._table("people")
        # TRIM before the blank check, matching data.py's label_with_fallback --
        # see the venue case above for why.
        label_expr = "COALESCE(NULLIF(TRIM(pe.\"name\"), ''), NULLIF(g.\"person_id\", ''), 'Unknown')"
        return (
            'g."person_id"', label_expr, 'g."person_id", pe."name"',
            f'LEFT JOIN {people} pe ON pe."person_id" = g."person_id"',
        )

    def _aggregate_predicates(self, dataset: str, filters: aggregation.AggregationFilters) -> tuple[list[str], list[Any]]:
        predicates: list[str] = []
        params: list[Any] = []
        filter_columns = _AGGREGATE_FILTER_COLUMNS[dataset]
        for name in ("song_id", "venue_id", "guest_id", "show_id"):
            value = getattr(filters, name)
            if value is None or name not in filter_columns:
                continue
            alias, column = filter_columns[name]
            predicates.append(f"{alias}.{_identifier(column)} = ?")
            params.append(value)
        excluded = [song_id for song_id in (filters.exclude_song_ids or []) if song_id]
        if excluded and dataset == "performances":
            predicates.append(f'p."song_id" NOT IN ({", ".join("?" for _ in excluded)})')
            params.extend(excluded)
        if filters.year is not None:
            predicates.append(f"{self._AGGREGATE_YEAR_SQL} = ?")
            params.append(filters.year)
        if filters.year_from is not None:
            predicates.append(f"{self._AGGREGATE_YEAR_SQL} >= ?")
            params.append(filters.year_from)
        if filters.year_to is not None:
            predicates.append(f"{self._AGGREGATE_YEAR_SQL} <= ?")
            params.append(filters.year_to)
        return predicates, params

    def aggregate(self, request: aggregation.AggregationRequest) -> aggregation.AggregationResult:
        dataset, group_by = request.dataset, request.group_by
        from_sql, base_params = self._aggregate_from_clause(dataset)
        dim_id_sql, dim_label_sql, dim_group_sql, join_sql = self._aggregate_dimension_sql(group_by)
        measure_sql = _AGGREGATE_MEASURE_SQL[request.measure]
        predicates, filter_params = self._aggregate_predicates(dataset, request.filters)

        grouped_predicates = list(predicates)
        if group_by == "year":
            grouped_predicates.append('s."show_date" IS NOT NULL')
        where_sql = f"WHERE {' AND '.join(grouped_predicates)}" if grouped_predicates else ""
        sql = (
            f"SELECT {dim_id_sql} AS dim_id, {dim_label_sql} AS dim_label, {measure_sql} AS value "
            f"FROM {from_sql} {join_sql} {where_sql} GROUP BY {dim_group_sql}"
        )
        grouped = self._query(sql, tuple(base_params + filter_params))

        range_predicates = list(predicates) + ['s."show_date" IS NOT NULL']
        range_where_sql = f"WHERE {' AND '.join(range_predicates)}"
        range_sql = (
            f"SELECT MIN({self._AGGREGATE_YEAR_SQL}) AS min_year, "
            f"MAX({self._AGGREGATE_YEAR_SQL}) AS max_year "
            f"FROM {from_sql} {range_where_sql}"
        )
        range_rows = self._query(range_sql, tuple(base_params + filter_params))
        min_year = range_rows[0].get("min_year") if range_rows else None
        max_year = range_rows[0].get("max_year") if range_rows else None
        # _query stringifies every value (see _string_value), so a SQL NULL
        # from MIN/MAX over zero matching rows comes back as "" here, never
        # Python None -- guard against both or int("") raises ValueError.
        date_range = (
            {"from": int(min_year), "to": int(max_year)}
            if min_year not in (None, "") and max_year not in (None, "")
            else None
        )

        raw_rows = []
        for row in grouped:
            value = int(row["value"] or 0)
            if group_by == "year":
                raw_rows.append(aggregation.AggregationRow(year=int(row["dim_id"]), value=value))
            else:
                raw_rows.append(aggregation.AggregationRow(id=row["dim_id"], label=row["dim_label"] or row["dim_id"], value=value))

        # total is the measure over the whole filtered set, computed with the
        # same where_sql/params as the grouped query above (so it sees the
        # same rows) rather than summed from `grouped` -- summing per-group
        # distinct_shows/distinct_songs would double-count a fact that
        # appears in more than one group. join_sql is unused by measure_sql
        # itself (it only ever references the base from_sql aliases s/p/g)
        # but is included for a query shaped like the grouped one above.
        total_sql = f"SELECT {measure_sql} AS total FROM {from_sql} {join_sql} {where_sql}"
        total_rows = self._query(total_sql, tuple(base_params + filter_params))
        total = int(total_rows[0]["total"] or 0) if total_rows else 0

        setlist_counts = None
        if dataset == "performances":
            setlist_counts = self._setlist_counts(request.filters)

        return aggregation.assemble_result(request, raw_rows, date_range, total, setlist_counts)

    def _setlist_counts(self, filters: aggregation.AggregationFilters) -> dict[str, Any]:
        """Coverage over the show-level filters only (venue_id/year/year_from/
        year_to) -- reusing `_aggregate_predicates("shows", filters)` gives
        exactly that subset, since song_id/show_id aren't in
        _AGGREGATE_FILTER_COLUMNS["shows"] and so are silently dropped
        whether or not the caller's (performances) filters carry them.
        """

        shows = self._table("shows")
        performances = self._table("performances")
        predicates, params = self._aggregate_predicates("shows", filters)
        setlist_join = (
            f'LEFT JOIN (SELECT DISTINCT "show_id" FROM {performances}) sl ON sl."show_id" = s."show_id"'
        )

        where_sql = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        totals_sql = (
            'SELECT COUNT(*) AS shows_played, COUNT(sl."show_id") AS shows_with_setlist '
            f'FROM {shows} s {setlist_join} {where_sql}'
        )
        totals_rows = self._query(totals_sql, tuple(params))
        shows_played = int(totals_rows[0]["shows_played"] or 0) if totals_rows else 0
        shows_with_setlist = int(totals_rows[0]["shows_with_setlist"] or 0) if totals_rows else 0

        by_year_predicates = predicates + ['s."show_date" IS NOT NULL']
        by_year_where_sql = f"WHERE {' AND '.join(by_year_predicates)}"
        by_year_sql = (
            f"SELECT {self._AGGREGATE_YEAR_SQL} AS year, COUNT(*) AS shows_played, "
            'COUNT(sl."show_id") AS shows_with_setlist '
            f'FROM {shows} s {setlist_join} {by_year_where_sql} '
            f"GROUP BY {self._AGGREGATE_YEAR_SQL}"
        )
        by_year_rows = self._query(by_year_sql, tuple(params))
        by_year = [
            (int(row["year"]), int(row["shows_played"] or 0), int(row["shows_with_setlist"] or 0))
            for row in by_year_rows
        ]

        return aggregation.build_setlist_counts(shows_played, shows_with_setlist, by_year)

    # ---- free catalog queries ---------------------------------------------

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

        connection = _with_folding_like(sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro&immutable=1", uri=True))
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


__all__ = ["DEFAULT_RESPONSE_CACHE_PATH", "SqliteCanonicalStore", "query_cache_scope"]
