"""Tests for the Deadcast episode-title mapping rules.

Fixture-only: exercises ``song_matches`` and ``show_mapping`` directly against
a small canonical song/show universe, without touching the real canonical
CSVs or making any network call.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "normalize"))
import normalize_deadcast_episodes as nde  # noqa: E402


SONGS = [
    {"song_id": "song-uncle-john-s-band", "title": "Uncle John's Band"},
    {"song_id": "song-slipknot", "title": "Slipknot!"},
    {"song_id": "song-till-the-morning-comes", "title": "Till The Morning Comes"},
    {"song_id": "song-to-lay-me-down", "title": "To Lay Me Down"},
    {"song_id": "song-weather-report-suite-part-1", "title": "Weather Report Suite Part 1"},
    {"song_id": "song-weather-report-suite-prelude", "title": "Weather Report Suite Prelude"},
    {"song_id": "song-stronger-than-dirt", "title": "Stronger Than Dirt"},
]
SHOWS_BY_DATE = {"1966-07-03": ["gd-1966-07-03"], "1970-03-21": ["gd-1970-03-21-early", "gd-1970-03-21-late"]}


def test_a_colon_segment_names_exactly_one_song():
    songs = nde.SongLookup(SONGS)
    song_ids, hold = nde.song_matches("Workingman’s Dead 50: Uncle John’s Band", songs)
    assert song_ids == ["song-uncle-john-s-band"]
    assert hold is None


def test_a_slash_segment_names_two_songs():
    songs = nde.SongLookup(SONGS)
    song_ids, hold = nde.song_matches("American Beauty 50: Till the Morning Comes / To Lay Me Down", songs)
    assert sorted(song_ids) == ["song-till-the-morning-comes", "song-to-lay-me-down"]
    assert hold is None


def test_a_segment_that_prefixes_two_songs_is_held_not_guessed():
    songs = nde.SongLookup(SONGS)
    song_ids, hold = nde.song_matches("Wake Of The Flood 50: Weather Report Suite", songs)
    assert song_ids == []
    assert sorted(hold) == ["song-weather-report-suite-part-1", "song-weather-report-suite-prelude"]


def test_a_segment_naming_no_canonical_song_is_unmapped_not_held():
    songs = nde.SongLookup(SONGS)
    song_ids, hold = nde.song_matches("Ace 50", songs)
    assert song_ids == []
    assert hold is None


def test_partial_overlap_inside_a_slash_part_is_not_forced():
    """"Stronger Than Dirt or Milkin' The Turkey" is not an exact match for the
    canonical "Stronger Than Dirt", so it stays unmapped rather than guessed."""

    songs = nde.SongLookup(SONGS)
    song_ids, hold = nde.song_matches(
        "Blues For Allah 50: King Solomon's Marbles/Stronger Than Dirt or Milkin' The Turkey", songs
    )
    assert song_ids == []
    assert hold is None


def test_a_full_date_in_the_title_maps_to_its_one_canonical_show():
    show_ids, hold = nde.show_mapping("Independence Ball, 7/3/66", SHOWS_BY_DATE)
    assert show_ids == ["gd-1966-07-03"]
    assert hold is None


def test_a_month_and_year_alone_is_not_a_date():
    show_ids, hold = nde.show_mapping("Friend Of the Devils: Florida, 4/78", SHOWS_BY_DATE)
    assert show_ids == []
    assert hold is None


def test_a_date_with_two_canonical_shows_is_held():
    show_ids, hold = nde.show_mapping("Some Title, 3/21/70", SHOWS_BY_DATE)
    assert show_ids == []
    assert hold["reason"] == "1970-03-21 matches more than one canonical show."
