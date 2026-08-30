"""PostgreSQL-backed access to the canonical graph.

The adapter deliberately has no import-time PostgreSQL dependency.  Callers may
inject any PEP 249 connection (handy for tests), a zero-argument connection
factory, or a DSN.  ``psycopg`` is imported only when a DSN is actually used.

Context methods fetch a bounded projection from PostgreSQL and delegate the
domain-specific response shaping to :class:`deadbot.data.CanonicalStore`.  This
keeps the CSV and PostgreSQL representations behaviorally aligned without
loading whole relationship tables for a single entity lookup.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime
import re
from typing import Any, Protocol

from deadbot.data import CanonicalStore


class DBAPICursor(Protocol):
    description: Any

    def execute(self, operation: str, parameters: tuple[Any, ...] = ()) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def close(self) -> Any: ...


class DBAPIConnection(Protocol):
    def cursor(self) -> DBAPICursor: ...
    def close(self) -> Any: ...


ConnectionFactory = Callable[[], DBAPIConnection]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# These keys reproduce the deterministic ordering of the tracked canonical
# exports. They also make entity disambiguation and setlist rendering stable
# across query plans, VACUUMs, and replicas.
_ORDER_COLUMNS: dict[str, tuple[str, ...]] = {
    "arrangement_chord_sections": ("arrangement_id", "section_position"),
    "equipment": ("equipment_id",),
    "official_release_tracks": ("release_id", "track_number", "performance_id"),
    "official_releases": ("release_id",),
    "people": ("person_id",),
    "performance_links": ("performance_link_id",),
    "performance_recordings": ("performance_id", "recording_id", "track_number"),
    "recordings": ("recording_id",),
    "resource_performances": ("resource_id", "performance_id", "relationship_type"),
    "resource_shows": ("resource_id", "show_id", "relationship_type"),
    "resource_songs": ("resource_id", "song_id", "relationship_type"),
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


def _identifier(value: str) -> str:
    """Quote a validated SQL identifier.

    Table and column names are application-owned, never user input. Validation
    remains important because DB-API placeholders cannot parameterize them.
    """

    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return f'"{value}"'


_ID_COLUMNS = {
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
    """Normalize database values to the string representation used by CSV."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


class PostgresCanonicalStore(CanonicalStore):
    """Read-only canonical store backed by a DB-API PostgreSQL connection.

    Exactly one of ``connection``, ``connection_factory``, or ``dsn`` should be
    supplied. A factory-created connection is opened lazily and owned by the
    store; an explicitly supplied connection remains owned by its caller.
    """

    def __init__(
        self,
        connection: DBAPIConnection | None = None,
        *,
        connection_factory: ConnectionFactory | None = None,
        dsn: str | None = None,
        schema: str = "public",
    ) -> None:
        choices = sum(value is not None for value in (connection, connection_factory, dsn))
        if choices != 1:
            raise ValueError("Supply exactly one of connection, connection_factory, or dsn")
        _identifier(schema)
        self.schema = schema
        self._connection_instance = connection
        self._owns_connection = connection is None
        if dsn is not None:
            self._connection_factory = self._psycopg_factory(dsn)
        else:
            self._connection_factory = connection_factory

    @classmethod
    def from_dsn(cls, dsn: str, *, schema: str = "public") -> PostgresCanonicalStore:
        """Create a lazy DSN-backed store without importing a driver yet."""

        return cls(dsn=dsn, schema=schema)

    @staticmethod
    def _psycopg_factory(dsn: str) -> ConnectionFactory:
        def connect() -> DBAPIConnection:
            try:
                import psycopg  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "A PostgreSQL driver is required for DSN connections. "
                    "Install psycopg or inject a DB-API connection factory."
                ) from exc
            return psycopg.connect(dsn, autocommit=True)

        return connect

    def _connection(self) -> DBAPIConnection:
        if self._connection_instance is None:
            if self._connection_factory is None:  # defensive; constructor prevents this
                raise RuntimeError("No PostgreSQL connection is configured")
            self._connection_instance = self._connection_factory()
        return self._connection_instance

    def close(self) -> None:
        """Close a lazily factory-created connection; leave injected ones alone."""

        if self._owns_connection and self._connection_instance is not None:
            self._connection_instance.close()
            self._connection_instance = None

    def __enter__(self) -> PostgresCanonicalStore:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _qualified_table(self, table: str) -> str:
        return f"{_identifier(self.schema)}.{_identifier(table)}"

    def _order_clause(self, table: str) -> str:
        if table == "shows":
            return ' ORDER BY "show_date" NULLS LAST, "show_id"'
        if table == "performances":
            return (
                ' ORDER BY "show_id", '
                'CAST("set_number" AS INTEGER) NULLS LAST, '
                'CAST("position_in_set" AS INTEGER) NULLS LAST, "performance_id"'
            )
        columns = _ORDER_COLUMNS.get(table)
        if columns:
            return " ORDER BY " + ", ".join(_identifier(column) for column in columns)
        # Unknown extension tables still receive a deterministic order without
        # guessing at an ID column that may not exist.
        return " ORDER BY 1"

    def _query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, str]]:
        cursor = self._connection().cursor()
        try:
            cursor.execute(sql, parameters)
            description = cursor.description or ()
            columns = [
                item.name if hasattr(item, "name") else item[0]
                for item in description
            ]
            result = []
            for raw_row in cursor.fetchall():
                if isinstance(raw_row, Mapping):
                    result.append({str(key): _string_value(value) for key, value in raw_row.items()})
                else:
                    result.append({name: _string_value(value) for name, value in zip(columns, raw_row)})
            return result
        finally:
            cursor.close()

    def filtered_rows(self, table: str, **criteria: str) -> list[dict[str, str]]:
        if not criteria:
            return self.rows(table)
        predicates = [f"{_identifier(column)} = %s" for column in criteria]
        sql = (
            f"SELECT * FROM {self._qualified_table(table)} WHERE {' AND '.join(predicates)}"
            f"{self._order_clause(table)}"
        )
        return self._query(sql, tuple(criteria.values()))

    _filtered_rows = filtered_rows

    def _rows_in(self, table: str, column: str, values: Iterable[str]) -> list[dict[str, str]]:
        unique_values = tuple(dict.fromkeys(values))
        if not unique_values:
            return []
        placeholders = ", ".join("%s" for _ in unique_values)
        sql = (
            f"SELECT * FROM {self._qualified_table(table)} "
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
            f"SELECT * FROM {self._qualified_table(table)}{self._order_clause(table)}"
        )

    def row_count(self, table: str) -> int:
        rows = self._query(
            f"SELECT COUNT(*) AS row_count FROM {self._qualified_table(table)}"
        )
        return int(rows[0]["row_count"]) if rows else 0

    def coverage_summary(self) -> dict[str, Any]:
        """Compute catalog coverage without transferring whole tables."""

        show_rows = self._query(
            f"SELECT COUNT(*) AS dated_show_count, MIN(\"show_date\") AS first_date, "
            f"MAX(\"show_date\") AS last_date FROM {self._qualified_table('shows')} "
            'WHERE "show_date" IS NOT NULL'
        )
        performance_rows = self._query(
            f"SELECT COUNT(*) AS performance_count, "
            f"COUNT(DISTINCT \"song_id\") AS performance_song_count "
            f"FROM {self._qualified_table('performances')}"
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
        predicates = [f"LOWER({searchable}) LIKE LOWER(%s) ESCAPE '\\'" for _ in normalized]
        values = [
            f"%{phrase.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')}%"
            for phrase in normalized
        ]
        sql = (
            f"SELECT s.*, v.\"name\" AS venue_name, v.\"city\" AS venue_city, "
            f"v.\"state_region\" AS venue_state_region "
            f"FROM {self._qualified_table('shows')} s "
            f"LEFT JOIN {self._qualified_table('venues')} v ON v.\"venue_id\" = s.\"venue_id\" "
            f"WHERE {' OR '.join(predicates)} "
            'ORDER BY s."show_date" NULLS LAST, s."show_id" LIMIT %s'
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
        qualified = self._qualified_table(table)
        exact_predicates = [
            f"LOWER(COALESCE(CAST({_identifier(field)} AS TEXT), '')) = LOWER(%s)"
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
            f"LOWER(COALESCE(CAST({_identifier(field)} AS TEXT), '')) LIKE LOWER(%s) ESCAPE '\\'"
            for field in fields
        ]
        return self._query(
            f"SELECT * FROM {qualified} WHERE {' OR '.join(fuzzy_predicates)}"
            f"{self._order_clause(table)}",
            tuple(f"%{escaped}%" for _ in fields),
        )

    # resolve_song, show_candidates, resolve_show, and resolve_equipment are
    # inherited: they compose the optimized ``one`` and ``matching_rows`` calls.

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

    def song_context(self, song: dict[str, str]) -> dict[str, Any]:
        song_id = song["song_id"]
        relationships = self._filtered_rows("resource_songs", song_id=song_id)
        tables = {
            "song_writers": self._filtered_rows("song_writers", song_id=song_id),
            "performances": self._filtered_rows("performances", song_id=song_id),
            "song_arrangements": self._filtered_rows("song_arrangements", song_id=song_id),
            "resource_songs": relationships,
            "resources": self._rows_in(
                "resources", "resource_id", (row["resource_id"] for row in relationships)
            ),
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
            f"SELECT * FROM {self._qualified_table('song_arrangements')} "
            "WHERE LOWER(COALESCE(CAST(\"key_signature\" AS TEXT), '')) = LOWER(%s)"
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

    def show_context(self, show: dict[str, str]) -> dict[str, Any]:
        show_id = show["show_id"]
        performances = self._filtered_rows("performances", show_id=show_id)
        performance_ids = [row["performance_id"] for row in performances]
        release_tracks = self._rows_in("official_release_tracks", "performance_id", performance_ids)
        performer_assignments = self._filtered_rows("show_performers", show_id=show_id)
        equipment_assignments = self._filtered_rows("show_equipment", show_id=show_id)
        resource_relationships = self._filtered_rows("resource_shows", show_id=show_id)
        tables = {
            "performances": performances,
            "official_release_tracks": release_tracks,
            "official_releases": self._rows_in(
                "official_releases", "release_id", (row["release_id"] for row in release_tracks)
            ),
            "venues": self._rows_in("venues", "venue_id", (show.get("venue_id", ""),)),
            "show_performers": performer_assignments,
            "people": self._rows_in(
                "people", "person_id", (row["person_id"] for row in performer_assignments)
            ),
            "show_equipment": equipment_assignments,
            "equipment": self._rows_in(
                "equipment", "equipment_id", (row["equipment_id"] for row in equipment_assignments)
            ),
            "recordings": self._filtered_rows("recordings", show_id=show_id),
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
        tables = {
            "performances": [performance],
            "songs": self._rows_in("songs", "song_id", (performance["song_id"],)),
            "shows": self._rows_in("shows", "show_id", (performance["show_id"],)),
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
            "performance_recordings": self._filtered_rows(
                "performance_recordings", performance_id=performance_id
            ),
        }
        return CanonicalStore.performance_context(self._projection(tables), performance_id)


# A spelling-friendly alias for callers that prefer the expanded initialism.
PostgresStore = PostgresCanonicalStore
PostgreSQLCanonicalStore = PostgresCanonicalStore


__all__ = ["PostgresCanonicalStore", "PostgresStore", "PostgreSQLCanonicalStore"]
