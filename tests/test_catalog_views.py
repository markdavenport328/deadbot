import csv
import sqlite3
from collections import Counter

from deadbot.canonical_import import DEFAULT_CANONICAL_DIR


def _db(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _csv(name):
    with (DEFAULT_CANONICAL_DIR / f"{name}.csv").open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_views_exist_with_their_columns(built_sqlite):
    db = _db(built_sqlite)
    expected = {
        "show_facts": ["show_id", "show_date", "year", "venue_id", "venue_name", "city", "state_region", "country", "tour_name", "event_name", "performance_count"],
        "performance_facts": ["performance_id", "song_id", "song_title", "show_id", "show_date", "year", "venue_id", "venue_name", "city", "tour_name", "set_number", "set_label", "position_in_set", "encore", "segue_into_next"],
        "release_track_facts": ["release_id", "release_title", "release_type", "release_date", "track_number", "track_title", "song_id", "song_title", "performance_id", "show_id", "show_date", "year", "venue_id", "venue_name", "city"],
        "guest_appearances": ["show_id", "show_date", "year", "person_id", "person_name", "instrument", "venue_name", "city"],
    }
    for view, columns in expected.items():
        assert [row[1] for row in db.execute(f'PRAGMA table_info("{view}")')] == columns, view


def test_most_played_1977_matches_an_independent_count(built_sqlite):
    shows = {row["show_id"]: row["show_date"] for row in _csv("shows")}
    counts = Counter(p["song_id"] for p in _csv("performances") if shows.get(p["show_id"], "").startswith("1977"))
    top_song, top_count = counts.most_common(1)[0]
    row = _db(built_sqlite).execute(
        "SELECT song_id, COUNT(*) AS n FROM performance_facts WHERE year = 1977 GROUP BY song_id ORDER BY n DESC, song_id LIMIT 1"
    ).fetchone()
    assert row == (top_song, top_count)


def test_releases_covering_1972_include_europe_72(built_sqlite):
    rows = _db(built_sqlite).execute("SELECT DISTINCT release_id FROM release_track_facts WHERE year = 1972").fetchall()
    assert ("release-europe-72-the-complete-recordings-2011",) in rows


def test_every_guest_row_is_counted(built_sqlite):
    guests = sum(1 for row in _csv("show_performers") if row["role"] == "guest")
    assert _db(built_sqlite).execute("SELECT COUNT(*) FROM guest_appearances").fetchone()[0] == guests
