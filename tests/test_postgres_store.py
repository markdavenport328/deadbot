from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Any

import pytest

from deadbot.data import CanonicalStore
from deadbot.postgres import PostgresCanonicalStore, PostgresStore, PostgreSQLCanonicalStore
from deadbot.tools import build_tools


TABLES: dict[str, list[dict[str, Any]]] = {
    "songs": [
        {"song_id": "song-dark-star", "title": "Dark Star", "slug": "dark-star"},
        {"song_id": "song-ripple", "title": "Ripple", "slug": "ripple"},
    ],
    "shows": [
        {
            "show_id": "show-1972-08-27",
            "show_date": "1972-08-27",
            "venue_id": "venue-old-renaissance",
            "tour_name": "Summer 1972",
            "event_name": "Springfield Creamery Benefit",
            "notes": "",
        },
        {
            "show_id": "show-1966-10-08-a",
            "show_date": "1966-10-08",
            "venue_id": "venue-one",
            "tour_name": "",
            "event_name": "Early show",
            "notes": "",
        },
        {
            "show_id": "show-1966-10-08-b",
            "show_date": "1966-10-08",
            "venue_id": "venue-two",
            "tour_name": "",
            "event_name": "Late show",
            "notes": "",
        },
    ],
    "venues": [
        {
            "venue_id": "venue-old-renaissance",
            "name": "Old Renaissance Faire Grounds",
            "city": "Veneta",
            "state_region": "OR",
        },
        {"venue_id": "venue-one", "name": "One", "city": "", "state_region": ""},
        {"venue_id": "venue-two", "name": "Two", "city": "", "state_region": ""},
    ],
    "performances": [
        {
            "performance_id": "performance-dark-star",
            "show_id": "show-1972-08-27",
            "song_id": "song-dark-star",
            "set_number": "3",
            "set_label": "Set 3",
            "position_in_set": "2",
            "encore": "false",
            "segue_into_next": "true",
        },
        {
            "performance_id": "performance-dark-star-no-links",
            "show_id": "show-1972-08-27",
            "song_id": "song-dark-star",
            "set_number": "3",
            "set_label": "Set 3",
            "position_in_set": "5",
            "encore": "false",
            "segue_into_next": "false",
        },
        {
            "performance_id": "performance-dark-star-release-only",
            "show_id": "show-1972-08-27",
            "song_id": "song-dark-star",
            "set_number": "3",
            "set_label": "Set 3",
            "position_in_set": "6",
            "encore": "false",
            "segue_into_next": "false",
        },
    ],
    "song_writers": [
        {
            "song_id": "song-dark-star",
            "person_id": "person-hunter",
            "writer_role": "lyrics",
        }
    ],
    "song_arrangements": [
        {
            "arrangement_id": "arrangement-1",
            "song_id": "song-dark-star",
            "key_signature": "A",
            "resource_id": "resource-song",
        }
    ],
    "resources": [
        {"resource_id": "resource-song", "title": "Song notes", "url": "https://example.test/song"},
        {"resource_id": "resource-show", "title": "Show notes", "url": "https://example.test/show"},
        {
            "resource_id": "resource-performance",
            "title": "Performance notes",
            "url": "https://example.test/performance",
        },
    ],
    "resource_songs": [
        {"resource_song_id": "rs-1", "resource_id": "resource-song", "song_id": "song-dark-star"}
    ],
    "resource_shows": [
        {
            "resource_show_id": "rshow-1",
            "resource_id": "resource-show",
            "show_id": "show-1972-08-27",
        }
    ],
    "resource_performances": [
        {
            "resource_performance_id": "rp-1",
            "resource_id": "resource-performance",
            "performance_id": "performance-dark-star",
        }
    ],
    "people": [
        {"person_id": "person-garcia", "name": "Jerry Garcia"},
        {"person_id": "person-hunter", "name": "Robert Hunter"},
    ],
    "show_performers": [
        {
            "show_performer_id": "sp-1",
            "show_id": "show-1972-08-27",
            "person_id": "person-garcia",
            "role": "member",
            "instrument": "guitar, vocals",
        }
    ],
    "equipment": [
        {
            "equipment_id": "equipment-alligator",
            "name": "Alligator",
            "manufacturer": "Fender",
            "model": "Stratocaster",
        }
    ],
    "show_equipment": [
        {
            "show_equipment_id": "se-1",
            "show_id": "show-1972-08-27",
            "equipment_id": "equipment-alligator",
            "usage_context": "played by Jerry Garcia",
            "claim_type": "photographic",
            "source_id": "source-photo",
            "source_url": "https://example.test/photo",
            "source_note": "Visible in source photograph",
        }
    ],
    "recordings": [
        {
            "recording_id": "recording-1",
            "show_id": "show-1972-08-27",
            "source_type": "soundboard",
            "archive_identifier": "gd1972-08-27.sbd",
            "notes": "",
        }
    ],
    "show_links": [
        {"show_link_id": "sl-1", "show_id": "show-1972-08-27", "url": "https://example.test/show-link"}
    ],
    "performance_links": [
        {
            "performance_link_id": "pl-1",
            "performance_id": "performance-dark-star",
            "platform": "archive",
            "link_type": "recording-track",
            "url": "https://example.test/play",
        }
    ],
    "performance_recordings": [
        {
            "performance_recording_id": "pr-1",
            "performance_id": "performance-dark-star",
            "recording_id": "recording-1",
            "track_number": "12",
        }
    ],
    "official_releases": [
        {
            "release_id": "release-sunshine-daydream",
            "title": "Sunshine Daydream",
            "spotify_album_url": "https://open.spotify.test/album/1",
        }
    ],
    "official_release_tracks": [
        {
            "official_release_track_id": "ort-1",
            "release_id": "release-sunshine-daydream",
            "performance_id": "performance-dark-star",
            "spotify_track_url": "https://open.spotify.test/track/1",
        },
        # Listed here in raw (non-alphabetical) release_id order on purpose: a
        # naive "first row encountered" selection would pick this row's URL,
        # while PostgreSQL's ORDER BY release_id would pick the other row's
        # URL first. The deterministic sort in _listen_paths must make both
        # stores agree on "release-alpha-sessions" regardless of row order.
        {
            "official_release_track_id": "ort-2",
            "release_id": "release-sunshine-daydream",
            "performance_id": "performance-dark-star-release-only",
            "track_number": "9",
            "spotify_track_url": "https://open.spotify.test/track/sunshine-dup",
        },
        {
            "official_release_track_id": "ort-3",
            "release_id": "release-alpha-sessions",
            "performance_id": "performance-dark-star-release-only",
            "track_number": "1",
            "spotify_track_url": "https://open.spotify.test/track/alpha",
        },
    ],
}


class Cursor:
    def __init__(self, cursor: sqlite3.Cursor, statements: list[tuple[str, tuple[Any, ...]]]):
        self.cursor = cursor
        self.statements = statements

    @property
    def description(self):
        return self.cursor.description

    def execute(self, operation: str, parameters: tuple[Any, ...] = ()):
        self.statements.append((operation, parameters))
        return self.cursor.execute(operation.replace("%s", "?"), parameters)

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        return self.cursor.close()


class Connection:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.execute("ATTACH DATABASE ':memory:' AS canonical")
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False
        for table, rows in TABLES.items():
            columns = list(dict.fromkeys(key for row in rows for key in row))
            definitions = ", ".join(f'"{column}" TEXT' for column in columns)
            self.raw.execute(f'CREATE TABLE canonical."{table}" ({definitions})')
            placeholders = ", ".join("?" for _ in columns)
            column_names = ", ".join(f'"{column}"' for column in columns)
            for row in rows:
                self.raw.execute(
                    f'INSERT INTO canonical."{table}" ({column_names}) VALUES ({placeholders})',
                    tuple(row.get(column) for column in columns),
                )
        self.raw.commit()

    def cursor(self):
        return Cursor(self.raw.cursor(), self.statements)

    def close(self):
        self.closed = True
        self.raw.close()


@pytest.fixture
def connection():
    return Connection()


@pytest.fixture
def store(connection):
    return PostgresCanonicalStore(connection, schema="canonical")


@pytest.fixture
def csv_store():
    result = CanonicalStore()
    result.__dict__["tables"] = TABLES
    return result


def test_rows_one_matching_and_resolution_match_csv_behavior(store, csv_store):
    assert store.rows("songs") == csv_store.rows("songs")
    assert store.one("songs", "song-dark-star") == csv_store.one("songs", "song-dark-star")
    assert store.one("songs", "missing") is None
    assert store.one("song_writers", "writer-1") is None
    assert [row["show_id"] for row in store.rows("shows")] == [
        "show-1966-10-08-a",
        "show-1966-10-08-b",
        "show-1972-08-27",
    ]
    assert store.matching_rows("songs", "DARK STAR", ("title", "slug")) == [TABLES["songs"][0]]
    assert store.matching_rows("songs", "rip", ("title", "slug")) == [TABLES["songs"][1]]
    assert store.matching_rows("songs", "%", ("title",)) == []
    assert store.resolve_song("dark-star") == TABLES["songs"][0]
    assert store.resolve_equipment("alligator") == TABLES["equipment"][0]
    assert store.resolve_show("show-1972-08-27") == TABLES["shows"][0]
    assert store.resolve_show("1966-10-08") is None
    assert store.show_candidates("1966-10-08") == TABLES["shows"][1:]


def test_context_methods_match_existing_domain_projection(store, csv_store):
    song = TABLES["songs"][0]
    show = TABLES["shows"][0]
    equipment = TABLES["equipment"][0]

    assert store.resources_for("resource_songs", "song_id", song["song_id"]) == csv_store.resources_for(
        "resource_songs", "song_id", song["song_id"]
    )
    song_context = store.song_context(song)
    csv_song_context = csv_store.song_context(song)
    assert song_context == csv_song_context
    performances_by_id = {row["performance_id"]: row for row in song_context["performances"]}
    csv_performances_by_id = {row["performance_id"]: row for row in csv_song_context["performances"]}
    assert performances_by_id["performance-dark-star"]["listen"] == {
        "archive_track_url": "https://example.test/play",
        "release_track_url": "https://open.spotify.test/track/1",
    }
    assert "listen" not in performances_by_id["performance-dark-star-no-links"]
    # "performance-dark-star-release-only" has no performance_links row (so no
    # archive_track_url) and two official_release_tracks rows with different
    # spotify_track_url values. Both stores must deterministically pick the
    # same one ("release-alpha-sessions" sorts first) regardless of the raw
    # row order each store happens to iterate.
    for by_id in (performances_by_id, csv_performances_by_id):
        assert by_id["performance-dark-star-release-only"]["listen"] == {
            "release_track_url": "https://open.spotify.test/track/alpha",
        }
    assert store.arrangement_search("a") == csv_store.arrangement_search("a")
    assert store.equipment_history(equipment) == csv_store.equipment_history(equipment)
    assert store.show_context(show) == csv_store.show_context(show)
    assert store.performance_context("performance-dark-star") == csv_store.performance_context(
        "performance-dark-star"
    )
    assert store.performance_context("missing") is None
    assert store.filtered_rows("shows", show_date="1966-10-08") == csv_store.filtered_rows(
        "shows", show_date="1966-10-08"
    )
    assert store.row_count("shows") == csv_store.row_count("shows")
    assert store.coverage_summary() == csv_store.coverage_summary()


def test_entity_search_uses_a_bounded_show_venue_query(store, connection):
    tools = {tool.name: tool for tool in build_tools(store)}
    result = json.loads(tools["search_entities"].invoke({"query": "Veneta"}))

    assert any(
        match["entity_type"] == "show" and match["id"] == "show-1972-08-27"
        for match in result["matches"]
    )
    show_searches = [
        sql
        for sql, _ in connection.statements
        if 'FROM "canonical"."shows" s' in sql
    ]
    assert show_searches
    assert "LEFT JOIN" in show_searches[-1]
    assert "LIMIT %s" in show_searches[-1]


def test_context_queries_are_scoped_to_the_requested_entity(store, connection):
    store.song_context(TABLES["songs"][0])
    store.show_context(TABLES["shows"][0])

    performance_queries = [
        sql for sql, _ in connection.statements if 'FROM "canonical"."performances"' in sql
    ]
    assert performance_queries
    assert all(" WHERE " in sql for sql in performance_queries)
    assert all(" ORDER BY " in sql for sql in performance_queries)
    assert all("NULLIF" not in sql for sql in performance_queries)


def test_factory_is_lazy_and_store_owns_its_connection():
    connection = Connection()
    calls = []

    def factory():
        calls.append(True)
        return connection

    store = PostgresCanonicalStore(connection_factory=factory, schema="canonical")
    assert calls == []
    assert store.one("songs", "song-dark-star") == TABLES["songs"][0]
    assert calls == [True]
    store.close()
    assert connection.closed is True


def test_from_dsn_is_lazy():
    store = PostgresStore.from_dsn("postgresql://unused.example/deadbot")
    assert store._connection_instance is None
    assert store.schema == "public"


def test_explicit_connection_remains_caller_owned(connection):
    with PostgreSQLCanonicalStore(connection, schema="canonical") as store:
        assert store.one("songs", "song-dark-star")
    assert connection.closed is False


def test_invalid_configuration_and_identifiers_are_rejected(connection):
    with pytest.raises(ValueError, match="exactly one"):
        PostgresCanonicalStore()
    with pytest.raises(ValueError, match="exactly one"):
        PostgresCanonicalStore(connection, connection_factory=lambda: connection)
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        PostgresCanonicalStore(connection, schema="canonical; DROP SCHEMA canonical")
    store = PostgresCanonicalStore(connection, schema="canonical")
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        store.rows("songs; DROP TABLE songs")


def test_database_scalar_types_match_csv_string_semantics():
    class TypedCursor:
        description = [
            ("nullable",),
            ("enabled",),
            ("disabled",),
            ("show_date",),
            ("captured_at",),
            ("count",),
        ]

        def execute(self, operation, parameters=()):
            return None

        def fetchall(self):
            return [
                (
                    None,
                    True,
                    False,
                    date(1972, 8, 27),
                    datetime(1972, 8, 27, 12, 30),
                    7,
                )
            ]

        def close(self):
            return None

    class TypedConnection:
        def cursor(self):
            return TypedCursor()

    store = PostgresCanonicalStore(TypedConnection())

    assert store._query("SELECT typed values") == [
        {
            "nullable": "",
            "enabled": "true",
            "disabled": "false",
            "show_date": "1972-08-27",
            "captured_at": "1972-08-27T12:30:00",
            "count": "7",
        }
    ]
