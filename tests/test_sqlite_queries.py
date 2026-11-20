"""The SQLite store's queries against small hand-written tables and the real catalog.

Each test compares the store's SQL with ``CanonicalStore``, the in-memory
reading of the same CSV rows, so a difference is a bug in the SQL.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from deadbot import aggregation
from deadbot.data import CanonicalStore
from deadbot.tools import build_tools
from sqlite_toy import TABLES, RecordingStore, toy_csv_store, toy_store


@pytest.fixture
def store(tmp_path):
    result = toy_store(tmp_path)
    yield result
    result.close()


@pytest.fixture
def csv_store():
    return toy_csv_store()


@pytest.fixture(scope="module")
def real_csv_store():
    """The reviewed canonical CSVs, read in memory once for this module."""

    return CanonicalStore()


@pytest.fixture
def real_store(built_sqlite, tmp_path):
    result = RecordingStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


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



def test_song_context_matches_the_csv_store(real_store, real_csv_store):
    song = real_csv_store.resolve_song("Truckin'")
    assert real_store.song_context(song)["releases"] == real_csv_store.song_context(song)["releases"]


def test_release_personnel_is_a_known_table_with_ordering(real_store):
    rows = real_store.rows("release_personnel")
    assert isinstance(rows, list)
    assert rows


def test_band_lineup_matches_the_csv_store(real_store, real_csv_store):
    for show_date in ("1972-08-27", "1977-05-08", ""):
        assert real_store.band_lineup(show_date) == real_csv_store.band_lineup(show_date)

    assert real_store.person_band_memberships("person-mickey-hart") == (
        real_csv_store.person_band_memberships("person-mickey-hart")
    )


def test_show_context_band_memberships_match_the_csv_store(real_store, real_csv_store):
    show = real_csv_store.resolve_show("1972-08-27")
    sqlite_lineup = real_store.show_context(show)["band_memberships"]
    csv_lineup = real_csv_store.show_context(show)["band_memberships"]
    assert sqlite_lineup == csv_lineup
    assert {row["person_id"] for row in sqlite_lineup} >= {"person-jerry-garcia", "person-bob-weir"}


def test_entity_search_uses_a_bounded_show_venue_query(store):
    tools = {tool.name: tool for tool in build_tools(store)}
    result = json.loads(tools["search_entities"].invoke({"query": "Veneta"}))

    assert any(
        match["entity_type"] == "show" and match["id"] == "show-1972-08-27"
        for match in result["matches"]
    )
    show_searches = [sql for sql, _ in store.statements if 'FROM "shows" s' in sql]
    assert show_searches
    assert "LEFT JOIN" in show_searches[-1]
    assert "LIMIT ?" in show_searches[-1]


def test_context_queries_are_scoped_to_the_requested_entity(store):
    store.song_context(TABLES["songs"][0])
    store.show_context(TABLES["shows"][0])

    performance_queries = [sql for sql, _ in store.statements if 'FROM "performances"' in sql]
    assert performance_queries
    assert all(" WHERE " in sql for sql in performance_queries)
    assert all(" ORDER BY " in sql for sql in performance_queries)
    assert all("NULLIF" not in sql for sql in performance_queries)


def test_the_store_closes_its_connections_when_used_as_a_context_manager(tmp_path):
    with toy_store(tmp_path) as opened:
        assert opened.one("songs", "song-dark-star") == TABLES["songs"][0]
        assert opened.open_connection_count == 1
    assert opened.open_connection_count == 0


def test_invalid_identifiers_are_rejected(store):
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        store.rows("songs; DROP TABLE songs")
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        store.filtered_rows("songs", **{"title = '' OR 1=1 --": "x"})


def test_stored_values_read_as_csv_strings(tmp_path):
    typed = {"typed": [{"nullable": None, "count": 7, "ratio": 1.5, "flag": "true", "show_date": "1972-08-27"}]}
    with toy_store(tmp_path, typed) as opened:
        assert opened._query('SELECT "nullable", CAST("count" AS INTEGER) AS count, CAST("ratio" AS REAL) AS ratio, "flag", "show_date" FROM "typed"') == [
            {"nullable": "", "count": "7", "ratio": "1.5", "flag": "true", "show_date": "1972-08-27"}
        ]


# ---- aggregate() parity: the store's SQL grouping vs
# CanonicalStore.aggregate's pure-Python reference implementation. Both feed
# the same raw grouped rows through deadbot.aggregation.assemble_result, so
# any difference here is a bug in the SQL, not in shaping.


def _every_combo() -> list:
    """Every valid (dataset, group_by, measure) triple, read live from the
    aggregation module's table (never hand-copied) so this test can't drift."""

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
    """Every combo over the toy tables; tests/test_sqlite_store.py runs the
    same combos over the real catalog."""

    request = _representative_request(dataset, group_by, measure)
    assert store.aggregate(request).to_payload() == csv_store.aggregate(request).to_payload()



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

    _query stringifies every DB value (see SqliteCanonicalStore._query /
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
# The toy fixture's Dark Star performances all fall in a
# single show/year, so distinct_songs/distinct_shows never actually
# double-count anything there -- these need the real ~40k-row dataset to
# prove total is strictly less than the naive per-group sum.


def test_aggregate_total_distinct_songs_by_year_beats_the_naive_row_sum_on_real_data(real_store, real_csv_store):
    request = aggregation.AggregationRequest(
        dataset="performances", group_by="year", measure="distinct_songs", limit=50, fill_missing=True,
    )
    sqlite_payload = real_store.aggregate(request).to_payload()
    assert sqlite_payload == real_csv_store.aggregate(request).to_payload()
    naive_row_sum = sum(row["value"] for row in sqlite_payload["rows"])
    assert sqlite_payload["total"] < naive_row_sum


def test_aggregate_total_distinct_shows_by_song_beats_the_naive_row_sum_on_real_data(real_store, real_csv_store):
    request = aggregation.AggregationRequest(
        dataset="performances", group_by="song", measure="distinct_shows", limit=50, sort="value_desc",
    )
    sqlite_payload = real_store.aggregate(request).to_payload()
    assert sqlite_payload == real_csv_store.aggregate(request).to_payload()
    naive_row_sum = sum(row["value"] for row in sqlite_payload["rows"])
    assert sqlite_payload["total"] < naive_row_sum


def test_aggregate_total_count_by_song_still_equals_all_performances_on_real_data(real_store, real_csv_store):
    """count never double-counts a fact across groups, so its total is the
    plain number of performances, and equal between both stores."""

    request = aggregation.AggregationRequest(
        dataset="performances", group_by="song", measure="count", limit=50, sort="value_desc",
    )
    sqlite_payload = real_store.aggregate(request).to_payload()
    assert sqlite_payload == real_csv_store.aggregate(request).to_payload()
    assert sqlite_payload["total"] == len(real_csv_store.rows("performances"))


# ---- setlist_counts ---------------------------------------------------------


def test_setlist_counts_appears_only_on_performances_results(real_store, real_csv_store):
    performances_request = aggregation.AggregationRequest(
        dataset="performances", group_by="year", measure="count", limit=50,
    )
    payload = real_store.aggregate(performances_request).to_payload()
    assert payload == real_csv_store.aggregate(performances_request).to_payload()
    coverage = payload["setlist_counts"]
    assert coverage["shows_played"] > 0
    assert 0 < coverage["shows_with_setlist"] <= coverage["shows_played"]
    assert coverage["by_year"], "expected at least one year bucket"
    for entry in coverage["by_year"]:
        assert entry["shows_with_setlist"] <= entry["shows_played"]
    years = [entry["year"] for entry in coverage["by_year"]]
    assert years == sorted(years)

    for dataset, group_by in (("shows", "year"), ("guest_appearances", "year")):
        other_request = aggregation.AggregationRequest(dataset=dataset, group_by=group_by, measure="count", limit=50)
        other_payload = real_store.aggregate(other_request).to_payload()
        assert other_payload == real_csv_store.aggregate(other_request).to_payload()
        assert "setlist_counts" not in other_payload


def test_setlist_counts_ignores_song_id_and_show_id_filters(real_store, real_csv_store):
    """setlist_counts is computed over the show-level filters only
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
    assert base_payload["setlist_counts"] == other_payload["setlist_counts"]


# ---- LEFT JOIN dimension tables so a missing/blank dimension record --------
# survives instead of silently disappearing (an inner join would drop it; the
# CSV store always keeps it). A separate small tables dict, not the shared
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
def missing_record_store(missing_record_tables, tmp_path):
    result = toy_store(tmp_path, missing_record_tables)
    yield result
    result.close()


@pytest.fixture
def missing_record_csv_store(missing_record_tables):
    return toy_csv_store(missing_record_tables)


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
    sqlite_payload = missing_record_store.aggregate(request).to_payload()
    csv_payload = missing_record_csv_store.aggregate(request).to_payload()
    assert sqlite_payload == csv_payload


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
    falling back to id then "Unknown"). A bare NULLIF(name, '') check would
    see the padded string as non-empty and render it literally, while the CSV
    path strips it first."""

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


def test_sequence_pairs_is_one_bounded_query(real_store):
    real_store.statements.clear()
    real_store.sequence_pairs("song-china-cat-sunflower", "song-i-know-you-rider")
    assert len(real_store.statements) == 1
    sql, parameters = real_store.statements[0]
    assert parameters == ("song-china-cat-sunflower", "song-i-know-you-rider")
    assert 'WHERE a."song_id" = ? AND b."song_id" = ?' in sql
