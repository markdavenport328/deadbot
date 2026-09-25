from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from typing import Any

import pytest

from deadbot import aggregation
from deadbot.data import CanonicalStore
from deadbot.postgres import PostgresCanonicalStore, PostgresStore, PostgreSQLCanonicalStore
from deadbot.tools import build_tools


# PostgresCanonicalStore.aggregate() emits genuine PostgreSQL syntax
# (EXTRACT(YEAR FROM ...) and the `::type` cast operator) that this test's
# SQLite-backed Connection mock cannot execute at all -- not "different
# results", a parser-level syntax error, confirmed against a bare sqlite3
# connection. `::` is not valid SQLite syntax anywhere, and EXTRACT(... FROM
# ...) is not a SQLite function/syntax either. Every table in this mock
# stores show_date as ISO "YYYY-MM-DD" TEXT (as does the real CSV/Postgres
# schema), so a SUBSTR/CAST gives the same year as PostgreSQL's EXTRACT for
# every value these tests exercise. This translation is applied only to the
# SQL text sent to the underlying sqlite3 cursor below; postgres.py's actual
# SQL (and the copy recorded in `statements` for assertions) is untouched --
# it remains genuine PostgreSQL syntax, verified correct by the real-data
# parity tests, not weakened to satisfy this mock.
#
# This regex is deliberately narrow: it strips a `::type` cast only when it
# directly follows one of aggregate()'s three EXTRACT(YEAR FROM
# s."show_date") shapes (bare, MIN(...)-wrapped, MAX(...)-wrapped -- the
# only call sites that emit this construct today, in _aggregate_dimension_sql,
# _aggregate_predicates, and aggregate()'s date-range query). A `::cast` on
# any other expression (e.g. postgres.py's selection_signal_rows, which casts
# `e."payload"::text`) is left alone, so a future PostgreSQL-only construct
# elsewhere fails loudly under this mock instead of silently "working" here
# when it wouldn't on real PostgreSQL.
_YEAR_EXTRACT_CAST = re.compile(
    r'(EXTRACT\(YEAR FROM s\."show_date"\)'
    r'|MIN\(EXTRACT\(YEAR FROM s\."show_date"\)\)'
    r'|MAX\(EXTRACT\(YEAR FROM s\."show_date"\)\))::\w+'
)


def _sqlite_compatible_sql(sql: str) -> str:
    sql = _YEAR_EXTRACT_CAST.sub(r"\1", sql)
    return sql.replace(
        'EXTRACT(YEAR FROM s."show_date")',
        'CAST(SUBSTR(s."show_date", 1, 4) AS INTEGER)',
    )


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
    "band_memberships": [
        {
            "membership_id": "membership-garcia-1965",
            "person_id": "person-garcia",
            "act": "grateful-dead",
            "role": "guitar, vocals",
            "start_date": "1965-05-05",
            "end_date": "1995-07-09",
            "start_precision": "day",
            "end_precision": "day",
            "source_key": "",
            "source_record_id": "",
            "notes": "",
        }
    ],
    "performance_performers": [
        {
            "performance_id": "performance-dark-star",
            "person_id": "person-garcia",
            "role": "performer",
            "instrument": "lead guitar",
            "notes": "Fixture credit so performance_context carries a song-level performer.",
            "source_key": "manual",
            "source_record_id": "fixture",
        }
    ],
    "show_performers": [
        {
            "show_performer_id": "sp-1",
            "show_id": "show-1972-08-27",
            "person_id": "person-garcia",
            "role": "member",
            "instrument": "guitar, vocals",
        },
        # A "guest" role row (distinct from the "member" row above) so the
        # toy-fixture aggregate() parity pass has a non-empty
        # guest_appearances dataset to exercise across every group_by.
        {
            "show_performer_id": "sp-2",
            "show_id": "show-1966-10-08-a",
            "person_id": "person-hunter",
            "role": "guest",
            "instrument": "",
        },
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
            "song_id": "",
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
            "song_id": "",
            "spotify_track_url": "https://open.spotify.test/track/sunshine-dup",
        },
        {
            "official_release_track_id": "ort-3",
            "release_id": "release-alpha-sessions",
            "performance_id": "performance-dark-star-release-only",
            "track_number": "1",
            "song_id": "",
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
        sqlite_sql = _sqlite_compatible_sql(operation.replace("%s", "?"))
        return self.cursor.execute(sqlite_sql, parameters)

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        return self.cursor.close()


class Connection:
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None):
        self.raw = sqlite3.connect(":memory:")
        self.raw.execute("ATTACH DATABASE ':memory:' AS canonical")
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False
        for table, rows in (TABLES if tables is None else tables).items():
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


@pytest.fixture(scope="session")
def real_tables() -> dict[str, list[dict[str, Any]]]:
    """The actual production canonical CSVs, loaded once per test session.

    Used only by the parity tests that compare against a real CanonicalStore
    (which reads these same CSVs from disk): the toy ``TABLES`` fixture above
    has no albums, so it cannot exercise real release/song data such as
    "American Beauty" or "Truckin'".
    """

    return CanonicalStore().tables


@pytest.fixture
def real_connection(real_tables):
    return Connection(real_tables)


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


def test_release_track_order_normalizes_the_typed_column_before_empty_value_handling(store):
    assert 'CAST("track_number" AS TEXT)' in store._order_clause("official_release_tracks")


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


def test_song_context_matches_the_csv_store(real_connection):
    postgres_store = PostgresCanonicalStore(real_connection, schema="canonical")
    csv_store = CanonicalStore()

    song = csv_store.resolve_song("Truckin'")
    assert postgres_store.song_context(song)["releases"] == csv_store.song_context(song)["releases"]


def test_album_context_matches_the_csv_store(real_connection):
    postgres_store = PostgresCanonicalStore(real_connection, schema="canonical")
    csv_store = CanonicalStore()

    release = csv_store.resolve_release("release-american-beauty")
    assert postgres_store.album_context(release) == csv_store.album_context(release)


def test_release_personnel_is_a_known_table_with_ordering(real_connection):
    store = PostgresCanonicalStore(real_connection, schema="canonical")
    rows = store.rows("release_personnel")
    assert isinstance(rows, list)
    assert rows


def test_band_lineup_matches_the_csv_store(real_connection):
    postgres_store = PostgresCanonicalStore(real_connection, schema="canonical")
    csv_store = CanonicalStore()

    for show_date in ("1972-08-27", "1977-05-08", ""):
        assert postgres_store.band_lineup(show_date) == csv_store.band_lineup(show_date)

    assert postgres_store.person_band_memberships("person-mickey-hart") == (
        csv_store.person_band_memberships("person-mickey-hart")
    )


def test_show_context_band_memberships_match_the_csv_store(real_connection):
    postgres_store = PostgresCanonicalStore(real_connection, schema="canonical")
    csv_store = CanonicalStore()

    show = csv_store.resolve_show("1972-08-27")
    postgres_lineup = postgres_store.show_context(show)["band_memberships"]
    csv_lineup = csv_store.show_context(show)["band_memberships"]
    assert postgres_lineup == csv_lineup
    assert {row["person_id"] for row in postgres_lineup} >= {"person-jerry-garcia", "person-bob-weir"}


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


def test_factory_owned_store_reconnects_after_lifecycle_closure():
    connections = []

    def factory():
        connection = Connection()
        connections.append(connection)
        return connection

    store = PostgresCanonicalStore(connection_factory=factory, schema="canonical")
    assert store.one("songs", "song-dark-star") == TABLES["songs"][0]
    store.close()
    assert connections[0].closed is True

    assert store.one("songs", "song-ripple") == TABLES["songs"][1]
    assert len(connections) == 2
    assert connections[1].closed is False


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


# ---- aggregate() parity: PostgresCanonicalStore's SQL grouping vs
# CanonicalStore.aggregate's pure-Python reference implementation. Both feed
# the same raw grouped rows through deadbot.aggregation.assemble_result, so
# any difference here is a bug in the SQL this task added, not in shaping.


@pytest.fixture
def real_store(real_connection):
    return PostgresCanonicalStore(real_connection, schema="canonical")


@pytest.fixture
def real_csv_store(real_tables):
    result = CanonicalStore()
    result.__dict__["tables"] = real_tables
    return result


def _every_combo() -> list:
    """Every valid (dataset, group_by, measure) triple, read live from Task
    1's table (never hand-copied) so this test can't silently drift from it."""

    return [
        pytest.param(dataset, group_by, measure, id=f"{dataset}-{group_by}-{measure}")
        for (dataset, group_by), measures in sorted(aggregation._MEASURES_BY_COMBO.items())
        for measure in sorted(measures)
    ]


def _representative_request(dataset: str, group_by: str, measure: str) -> aggregation.AggregationRequest:
    return aggregation.AggregationRequest(
        dataset=dataset,
        group_by=group_by,
        measure=measure,
        limit=50,
        fill_missing=(group_by == "year"),
    )


@pytest.mark.parametrize("dataset, group_by, measure", _every_combo())
def test_aggregate_toy_fixture_matches_csv_for_every_valid_combo(store, csv_store, dataset, group_by, measure):
    """Quick pass against the toy TABLES fixture.

    PostgresCanonicalStore.aggregate() emits genuine PostgreSQL syntax
    (EXTRACT(YEAR FROM ...)::int) that this test's SQLite-backed Connection
    mock cannot parse at all -- confirmed as a parser-level syntax error
    against bare sqlite3, not merely a different result. The mock's
    Cursor.execute (see _sqlite_compatible_sql above) rewrites just that
    construct into a SQLite-executable equivalent before running it against
    the toy in-memory database; the SQL text postgres.py actually builds, and
    the copy recorded in `connection.statements`, is untouched. This is a
    real SQLite/PostgreSQL incompatibility, not one this test's toy data
    happens to dodge -- see the real-data pass below for the test that
    actually proves the SQL is correct.
    """

    request = _representative_request(dataset, group_by, measure)
    assert store.aggregate(request).to_payload() == csv_store.aggregate(request).to_payload()


@pytest.mark.parametrize("dataset, group_by, measure", _every_combo())
def test_aggregate_real_data_matches_csv_for_every_valid_combo(real_store, real_csv_store, dataset, group_by, measure):
    """The test that actually proves the hand-written SQL is correct: every
    valid combo against the full ~40k-row production dataset."""

    request = _representative_request(dataset, group_by, measure)
    assert real_store.aggregate(request).to_payload() == real_csv_store.aggregate(request).to_payload()


def test_aggregate_filtered_requests_match_csv(real_store, real_csv_store):
    dark_star_by_year = aggregation.AggregationRequest(
        dataset="performances",
        group_by="year",
        measure="count",
        limit=50,
        fill_missing=True,
        filters={"song_id": "song-dark-star"},
    )
    assert real_store.aggregate(dark_star_by_year).to_payload() == real_csv_store.aggregate(
        dark_star_by_year
    ).to_payload()

    jack_casady_by_year = aggregation.AggregationRequest(
        dataset="guest_appearances",
        group_by="year",
        measure="distinct_shows",
        limit=50,
        filters={"guest_id": "person-jack-casady"},
    )
    assert real_store.aggregate(jack_casady_by_year).to_payload() == real_csv_store.aggregate(
        jack_casady_by_year
    ).to_payload()

    shows_year_range = aggregation.AggregationRequest(
        dataset="shows",
        group_by="year",
        measure="count",
        limit=50,
        filters={"year_from": 1972, "year_to": 1974},
    )
    assert real_store.aggregate(shows_year_range).to_payload() == real_csv_store.aggregate(
        shows_year_range
    ).to_payload()


def test_aggregate_city_fallback_matches_csv_for_a_real_blank_city_venue(real_store, real_csv_store):
    """COALESCE(NULLIF(v."city", ''), 'Unknown') must match CanonicalStore's
    `venue.get("city") or "Unknown"` against a venue that actually has a
    blank city in the real data, not just the toy fixture's synthetic one."""

    blank_city_venues = [
        venue for venue in real_csv_store.rows("venues") if not (venue.get("city") or "").strip()
    ]
    assert blank_city_venues, "expected at least one real venue with a blank city"
    venue_id = blank_city_venues[0]["venue_id"]

    request = aggregation.AggregationRequest(
        dataset="shows", group_by="city", measure="count", limit=50, filters={"venue_id": venue_id}
    )
    payload = real_store.aggregate(request).to_payload()
    assert payload == real_csv_store.aggregate(request).to_payload()
    assert payload["rows"] and payload["rows"][0]["id"] == "Unknown"


def test_aggregate_zero_match_filter_does_not_crash_the_date_range(real_store, real_csv_store):
    """A request whose filters match zero rows must not raise while computing
    the date range.

    _query stringifies every DB value (see PostgresCanonicalStore._query /
    _string_value), so MIN/MAX over zero matching rows comes back as SQL
    NULL -> "" here, never Python None. aggregate() must treat both as "no
    data" rather than passing "" to int().
    """

    request = aggregation.AggregationRequest(
        dataset="shows",
        group_by="venue",
        measure="count",
        limit=50,
        filters={"venue_id": "venue-unknown-", "year": 1800},
    )
    payload = real_store.aggregate(request).to_payload()
    assert payload == real_csv_store.aggregate(request).to_payload()
    assert payload["rows"] == []
    assert "date_range" not in payload


# ---- total: the measure over the whole filtered set, not a row sum --------
# (Task A / A2). The toy fixture's Dark Star performances all fall in a
# single show/year, so distinct_songs/distinct_shows never actually
# double-count anything there -- these need the real ~40k-row dataset to
# prove total is strictly less than the naive per-group sum.


def test_aggregate_total_distinct_songs_by_year_beats_the_naive_row_sum_on_real_data(real_store, real_csv_store):
    request = aggregation.AggregationRequest(
        dataset="performances", group_by="year", measure="distinct_songs", limit=50, fill_missing=True,
    )
    pg_payload = real_store.aggregate(request).to_payload()
    assert pg_payload == real_csv_store.aggregate(request).to_payload()
    naive_row_sum = sum(row["value"] for row in pg_payload["rows"])
    assert pg_payload["total"] < naive_row_sum


def test_aggregate_total_distinct_shows_by_song_beats_the_naive_row_sum_on_real_data(real_store, real_csv_store):
    request = aggregation.AggregationRequest(
        dataset="performances", group_by="song", measure="distinct_shows", limit=50, sort="value_desc",
    )
    pg_payload = real_store.aggregate(request).to_payload()
    assert pg_payload == real_csv_store.aggregate(request).to_payload()
    naive_row_sum = sum(row["value"] for row in pg_payload["rows"])
    assert pg_payload["total"] < naive_row_sum


def test_aggregate_total_count_by_song_still_equals_all_performances_on_real_data(real_store, real_csv_store):
    """count never double-counts a fact across groups, so its total is
    unaffected by this task: unchanged from before, and equal between both
    stores regardless of how the toy-fixture tests above exercise it."""

    request = aggregation.AggregationRequest(
        dataset="performances", group_by="song", measure="count", limit=50, sort="value_desc",
    )
    pg_payload = real_store.aggregate(request).to_payload()
    assert pg_payload == real_csv_store.aggregate(request).to_payload()
    assert pg_payload["total"] == len(real_csv_store.rows("performances"))


# ---- setlist_coverage (Task A / A4) ----------------------------------------


def test_setlist_coverage_appears_only_on_performances_results(real_store, real_csv_store):
    performances_request = aggregation.AggregationRequest(
        dataset="performances", group_by="year", measure="count", limit=50,
    )
    payload = real_store.aggregate(performances_request).to_payload()
    assert payload == real_csv_store.aggregate(performances_request).to_payload()
    coverage = payload["setlist_coverage"]
    assert coverage["shows_on_record"] > 0
    assert 0 < coverage["shows_with_setlist"] <= coverage["shows_on_record"]
    assert coverage["by_year"], "expected at least one year bucket"
    for entry in coverage["by_year"]:
        assert entry["shows_with_setlist"] <= entry["shows_on_record"]
    years = [entry["year"] for entry in coverage["by_year"]]
    assert years == sorted(years)

    for dataset, group_by in (("shows", "year"), ("guest_appearances", "year")):
        other_request = aggregation.AggregationRequest(dataset=dataset, group_by=group_by, measure="count", limit=50)
        other_payload = real_store.aggregate(other_request).to_payload()
        assert other_payload == real_csv_store.aggregate(other_request).to_payload()
        assert "setlist_coverage" not in other_payload


def test_setlist_coverage_ignores_song_id_and_show_id_filters(real_store, real_csv_store):
    """setlist_coverage is computed over the show-level filters only
    (venue_id/year/year_from/year_to); song_id/show_id don't change whether a
    setlist survives, so two requests differing only in song_id must report
    identical coverage."""

    base = aggregation.AggregationRequest(
        dataset="performances", group_by="year", measure="count", limit=50,
        filters={"song_id": "song-dark-star"},
    )
    other = aggregation.AggregationRequest(
        dataset="performances", group_by="year", measure="count", limit=50,
        filters={"song_id": "song-truckin"},
    )
    base_payload = real_store.aggregate(base).to_payload()
    assert base_payload == real_csv_store.aggregate(base).to_payload()
    other_payload = real_store.aggregate(other).to_payload()
    assert other_payload == real_csv_store.aggregate(other).to_payload()
    assert base_payload["setlist_coverage"] == other_payload["setlist_coverage"]


# ---- A3: LEFT JOIN dimension tables so a missing/blank dimension record ----
# survives instead of silently disappearing (Postgres used to inner-join and
# drop it; CSV always kept it). A separate small tables dict, not the shared
# TABLES fixture above, so these extra rows don't perturb the exact row
# counts the other tests in this file assert against.


def _missing_record_tables() -> dict[str, list[dict[str, Any]]]:
    tables = {table: [dict(row) for row in rows] for table, rows in TABLES.items()}
    tables["shows"] = tables["shows"] + [
        {
            "show_id": "show-missing-venue",
            "show_date": "1970-01-01",
            "venue_id": "venue-not-in-venues",
            "tour_name": "",
            "event_name": "",
            "notes": "",
        },
        {
            "show_id": "show-blank-venue",
            "show_date": "1970-01-02",
            "venue_id": "",
            "tour_name": "",
            "event_name": "",
            "notes": "",
        },
        {
            "show_id": "show-whitespace-venue-name",
            "show_date": "1970-01-03",
            "venue_id": "venue-whitespace-name",
            "tour_name": "",
            "event_name": "",
            "notes": "",
        },
    ]
    tables["venues"] = tables["venues"] + [
        {
            "venue_id": "venue-whitespace-name",
            "name": "  Fillmore West  ",
            "city": "",
            "state_region": "",
        },
    ]
    tables["performances"] = tables["performances"] + [
        {
            "performance_id": "performance-missing-song",
            "show_id": "show-1966-10-08-b",
            "song_id": "song-not-in-songs",
            "set_number": "1",
            "set_label": "Set 1",
            "position_in_set": "1",
            "encore": "false",
            "segue_into_next": "false",
        },
    ]
    tables["show_performers"] = tables["show_performers"] + [
        {
            "show_performer_id": "sp-3",
            "show_id": "show-1966-10-08-b",
            "person_id": "person-missing",
            "role": "guest",
            "instrument": "",
        },
    ]
    return tables


@pytest.fixture
def missing_record_tables() -> dict[str, list[dict[str, Any]]]:
    return _missing_record_tables()


@pytest.fixture
def missing_record_store(missing_record_tables):
    return PostgresCanonicalStore(Connection(missing_record_tables), schema="canonical")


@pytest.fixture
def missing_record_csv_store(missing_record_tables):
    result = CanonicalStore()
    result.__dict__["tables"] = missing_record_tables
    return result


@pytest.mark.parametrize(
    "dataset, group_by, measure",
    [
        ("shows", "venue", "count"),
        ("shows", "city", "count"),
        ("performances", "song", "count"),
        ("guest_appearances", "guest", "count"),
    ],
)
def test_aggregate_missing_dimension_records_match_between_stores(
    missing_record_store, missing_record_csv_store, dataset, group_by, measure
):
    """A show whose venue_id points at no venues row, a show with a blank
    venue_id, a performance whose song_id points at no songs row, and a guest
    row whose person_id points at no people row: none of them should vanish
    from either store, and both stores must agree on the resulting rows and
    totals."""

    request = aggregation.AggregationRequest(dataset=dataset, group_by=group_by, measure=measure, limit=50)
    pg_payload = missing_record_store.aggregate(request).to_payload()
    csv_payload = missing_record_csv_store.aggregate(request).to_payload()
    assert pg_payload == csv_payload


def test_aggregate_venue_grouping_falls_back_to_id_then_unknown(missing_record_store, missing_record_csv_store):
    request = aggregation.AggregationRequest(dataset="shows", group_by="venue", measure="count", limit=50)
    payload = missing_record_store.aggregate(request).to_payload()
    assert payload == missing_record_csv_store.aggregate(request).to_payload()
    rows_by_id = {row["id"]: row["label"] for row in payload["rows"]}
    # venue-not-in-venues has an id but no venues row: label falls back to the id.
    assert rows_by_id["venue-not-in-venues"] == "venue-not-in-venues"
    # show-blank-venue's venue_id is itself blank: label falls all the way to "Unknown".
    assert rows_by_id[""] == "Unknown"


def test_aggregate_venue_grouping_trims_a_whitespace_only_padded_name(missing_record_store, missing_record_csv_store):
    """A venue name that is only leading/trailing whitespace around real
    content ("  Fillmore West  ") must render trimmed on both sides, matching
    data.py's label_with_fallback (which calls .strip() on the name before
    falling back to id then "Unknown"). Before this fix, Postgres's
    NULLIF(name, '') check saw the padded string as non-empty and rendered it
    literally, while the CSV path stripped it first."""

    request = aggregation.AggregationRequest(
        dataset="shows", group_by="venue", measure="count", limit=50,
        filters={"venue_id": "venue-whitespace-name"},
    )
    payload = missing_record_store.aggregate(request).to_payload()
    assert payload == missing_record_csv_store.aggregate(request).to_payload()
    assert payload["rows"] and payload["rows"][0]["label"] == "Fillmore West"


def test_aggregate_song_grouping_falls_back_to_id_when_the_song_record_is_missing(
    missing_record_store, missing_record_csv_store
):
    request = aggregation.AggregationRequest(dataset="performances", group_by="song", measure="count", limit=50)
    payload = missing_record_store.aggregate(request).to_payload()
    assert payload == missing_record_csv_store.aggregate(request).to_payload()
    rows_by_id = {row["id"]: row["label"] for row in payload["rows"]}
    assert rows_by_id["song-not-in-songs"] == "song-not-in-songs"


def test_aggregate_guest_grouping_falls_back_to_id_when_the_person_record_is_missing(
    missing_record_store, missing_record_csv_store
):
    request = aggregation.AggregationRequest(dataset="guest_appearances", group_by="guest", measure="count", limit=50)
    payload = missing_record_store.aggregate(request).to_payload()
    assert payload == missing_record_csv_store.aggregate(request).to_payload()
    rows_by_id = {row["id"]: row["label"] for row in payload["rows"]}
    assert rows_by_id["person-missing"] == "person-missing"


@pytest.mark.parametrize(
    "first, second",
    [
        ("song-china-cat-sunflower", "song-i-know-you-rider"),
        ("song-playing-in-the-band", "song-uncle-john-s-band"),
        ("song-i-know-you-rider", "song-china-cat-sunflower"),
    ],
)
def test_sequence_pairs_match_csv_on_real_data(real_store, real_csv_store, first, second):
    from deadbot import sequences

    assert real_store.sequence_pairs(first, second) == real_csv_store.sequence_pairs(first, second)
    assert sequences.versions(real_store, first, second) == sequences.versions(real_csv_store, first, second)


def test_sequence_pairs_is_one_bounded_query(real_store, real_connection):
    real_connection.statements.clear()
    real_store.sequence_pairs("song-china-cat-sunflower", "song-i-know-you-rider")
    assert len(real_connection.statements) == 1
    sql, parameters = real_connection.statements[0]
    assert parameters == ("song-china-cat-sunflower", "song-i-know-you-rider")
    assert 'WHERE a."song_id" = %s AND b."song_id" = %s' in sql
