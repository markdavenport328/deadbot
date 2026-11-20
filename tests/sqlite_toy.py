"""A small hand-written catalog as a SQLite file, for tests of the store's queries.

The real catalog (the ``built_sqlite`` fixture) proves the queries against
production data. These few rows prove the edges production data may not hold
today (a missing venue record, a blank id, two release tracks for one
performance) and keep statement-count tests fast and exact. Every column is
TEXT, as in the CSVs, so the same ``TABLES`` dict seeds a ``CanonicalStore``
for parity checks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from deadbot.data import CanonicalStore
from deadbot.sqlite_store import SqliteCanonicalStore


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
        # while a query ordered by release_id would pick the other row's URL
        # first. The deterministic sort in _listen_paths must make both
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


class RecordingStore(SqliteCanonicalStore):
    """The SQLite store, keeping every statement it runs for a test to count."""

    def __init__(self, path: Path | str, **kwargs: Any) -> None:
        super().__init__(path, **kwargs)
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, str]]:
        self.statements.append((sql, tuple(parameters)))
        return super()._execute(sql, parameters)


def build_toy_sqlite(
    path: Path | str,
    tables: dict[str, list[dict[str, Any]]] | None = None,
    *,
    with_metadata: bool = False,
) -> Path:
    """Write ``tables`` (default ``TABLES``) to a new SQLite file, in row order.

    ``with_metadata`` adds the build's metadata row and an empty selection
    table, which ``data_version`` reads.
    """

    path = Path(path)
    db = sqlite3.connect(path)
    try:
        for table, rows in (TABLES if tables is None else tables).items():
            columns = list(dict.fromkeys(key for row in rows for key in row))
            definitions = ", ".join(f'"{column}" TEXT' for column in columns)
            db.execute(f'CREATE TABLE "{table}" ({definitions})')
            placeholders = ", ".join("?" for _ in columns)
            column_names = ", ".join(f'"{column}"' for column in columns)
            db.executemany(
                f'INSERT INTO "{table}" ({column_names}) VALUES ({placeholders})',
                [tuple(row.get(column) for column in columns) for row in rows],
            )
        if with_metadata:
            db.execute('CREATE TABLE "deadbot_schema_metadata" ("schema_version" TEXT, "input_fingerprint" TEXT)')
            db.execute('INSERT INTO "deadbot_schema_metadata" VALUES (7, \'sha256:toy\')')
            db.execute('CREATE TABLE "selection_evidence" ("selection_evidence_id" TEXT)')
        db.commit()
    finally:
        db.close()
    return path


def toy_store(
    directory: Path,
    tables: dict[str, list[dict[str, Any]]] | None = None,
    *,
    with_metadata: bool = False,
) -> RecordingStore:
    """A recording store over a fresh toy file in ``directory`` (a test's ``tmp_path``)."""

    directory = Path(directory)
    path = build_toy_sqlite(directory / "toy.sqlite", tables, with_metadata=with_metadata)
    return RecordingStore(path, response_cache_path=directory / "toy-cache.sqlite")


def toy_csv_store(tables: dict[str, list[dict[str, Any]]] | None = None) -> CanonicalStore:
    """The same rows behind the in-memory CSV store."""

    result = CanonicalStore()
    result.__dict__["tables"] = TABLES if tables is None else tables
    return result
