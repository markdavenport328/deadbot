"""Tested catalog queries the model can pick from, and the query tool's description.

Each query is written once and checked against an independent count
(tests/test_catalog_menu.py), so the common set questions are always right.
Free SQL covers what the menu does not; queries the measurements show
recurring get promoted here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NamedQuery:
    name: str
    summary: str
    requires: tuple[str, ...]
    sql: str


_YEARS = "year BETWEEN :year_from AND :year_to"

NAMED_QUERIES: dict[str, NamedQuery] = {
    query.name: query
    for query in (
        NamedQuery(
            "releases_covering_years",
            "official releases with shows from year_from–year_to: title, type, date, shows in range, first/last show",
            ("year_from",),
            "SELECT release_id, release_title, release_type, release_date, COUNT(DISTINCT show_id) AS shows_in_range, "
            "MIN(show_date) AS first_show, MAX(show_date) AS last_show FROM release_track_facts "
            f"WHERE {_YEARS} GROUP BY release_id ORDER BY release_date, release_title",
        ),
        NamedQuery(
            "releases_from_venue",
            "official releases with shows from a venue (name match): title, type, date, shows there",
            ("venue",),
            "SELECT release_id, release_title, release_type, release_date, venue_name, COUNT(DISTINCT show_id) AS shows_there, "
            "MIN(show_date) AS first_show, MAX(show_date) AS last_show FROM release_track_facts "
            "WHERE venue_name LIKE '%' || :venue || '%' GROUP BY release_id, venue_name ORDER BY release_date, release_title",
        ),
        NamedQuery(
            "releases_with_show",
            "official releases carrying tracks from one show: title, type, date, tracks from the show",
            ("show",),
            "SELECT release_id, release_title, release_type, release_date, COUNT(*) AS tracks_from_show "
            "FROM release_track_facts WHERE show_id = :show GROUP BY release_id ORDER BY release_date, release_title",
        ),
        NamedQuery(
            "song_set_positions",
            "where a song sat in year_from–year_to: per set, times it opened, closed, and appeared",
            ("song",),
            "WITH placed AS (SELECT p.show_id, p.set_number, p.set_label, "
            "p.position_in_set = 1 AS opens, "
            "p.position_in_set = (SELECT MAX(p2.position_in_set) FROM performances p2 "
            "WHERE p2.show_id = p.show_id AND p2.set_number IS p.set_number) AS closes "
            "FROM performances p JOIN shows s ON s.show_id = p.show_id "
            "WHERE p.song_id = :song AND CAST(substr(s.show_date, 1, 4) AS INTEGER) BETWEEN :year_from AND :year_to) "
            "SELECT set_number, set_label, SUM(opens) AS opened, SUM(closes) AS closed, COUNT(*) AS times_in_set "
            "FROM placed GROUP BY set_number, set_label ORDER BY set_number",
        ),
        NamedQuery(
            "song_neighbors",
            "what a song followed and led into in year_from–year_to: direction, song, times, how often segued",
            ("song",),
            "SELECT * FROM (SELECT 'after' AS direction, nxt.song_id, so.title AS song_title, COUNT(*) AS times, "
            "SUM(cur.segue_into_next = 'true') AS segued FROM performances cur "
            "JOIN shows s ON s.show_id = cur.show_id "
            "JOIN performances nxt ON nxt.show_id = cur.show_id AND nxt.set_number IS cur.set_number "
            "AND nxt.position_in_set = cur.position_in_set + 1 "
            "LEFT JOIN songs so ON so.song_id = nxt.song_id "
            "WHERE cur.song_id = :song AND CAST(substr(s.show_date, 1, 4) AS INTEGER) BETWEEN :year_from AND :year_to "
            "GROUP BY nxt.song_id ORDER BY times DESC, song_title LIMIT :limit) "
            "UNION ALL SELECT * FROM (SELECT 'before' AS direction, prv.song_id, so.title AS song_title, COUNT(*) AS times, "
            "SUM(prv.segue_into_next = 'true') AS segued FROM performances cur "
            "JOIN shows s ON s.show_id = cur.show_id "
            "JOIN performances prv ON prv.show_id = cur.show_id AND prv.set_number IS cur.set_number "
            "AND prv.position_in_set = cur.position_in_set - 1 "
            "LEFT JOIN songs so ON so.song_id = prv.song_id "
            "WHERE cur.song_id = :song AND CAST(substr(s.show_date, 1, 4) AS INTEGER) BETWEEN :year_from AND :year_to "
            "GROUP BY prv.song_id ORDER BY times DESC, song_title LIMIT :limit)",
        ),
        NamedQuery(
            "shows",
            "shows filtered by venue, tour and/or year_from–year_to: date, venue, city, tour, setlist length",
            (),
            "SELECT show_id, show_date, venue_name, city, tour_name, performance_count FROM show_facts "
            "WHERE (:venue = '' OR venue_name LIKE '%' || :venue || '%') "
            "AND (:tour = '' OR tour_name LIKE '%' || :tour || '%') "
            f"AND {_YEARS} ORDER BY show_date",
        ),
    )
}


_GUIDE = """Views for SQL (prefer these):
- show_facts: show_id, show_date, year, venue_id, venue_name, city, state_region, country, tour_name, event_name, performance_count
- performance_facts (one row per setlist entry): performance_id, song_id, song_title, show_id, show_date, year, venue_id, venue_name, city, tour_name, set_number, set_label, position_in_set, encore, segue_into_next
- release_track_facts (one row per official release track): release_id, release_title, release_type, release_date, track_number, track_title, song_id, song_title, performance_id, show_id, show_date, year, venue_id, venue_name, city (show columns NULL for studio tracks)
- guest_appearances: show_id, show_date, year, person_id, person_name, instrument, venue_name, city
Base tables are readable too. Dates are ISO text; use year for years. release_date may be partial ("1972"). Booleans are 'true'/'false'. Count shows with COUNT(DISTINCT show_id); setlists include Drums and Space. Results stop at 200 rows; aggregate or LIMIT."""


def catalog_tool_description() -> str:
    menu = "\n".join(
        f"- {query.name}({', '.join(query.requires) or 'filters optional'}): {query.summary}"
        for query in NAMED_QUERIES.values()
    )
    return (
        "Find or list things across the catalog. For how many times, the most, or change "
        "over the years, use aggregate_data instead: its results can become a chart. "
        "Use a listed query when one fits "
        "(song and show accept a title, ID or date; one year: set year_from only). "
        "When none fits, pass sql: one read-only SQLite SELECT. Then look up the few items "
        "your answer will feature for depth. Each result carries a result_id; a unit's from_result "
        "puts every record in it on the page.\n"
        f"Queries:\n{menu}\n{_GUIDE}"
    )
