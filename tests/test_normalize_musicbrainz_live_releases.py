"""Tests for the zero-track release guard in process_group (Minor 2).

Small in-memory fixtures only: no network, no reading the full canonical
CSVs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import normalize_musicbrainz_live_releases as mb  # noqa: E402


def test_process_group_holds_zero_track_release_without_crashing():
    # A chosen release with zero tracks used to make `grouped` empty, so
    # `min()` raised ValueError (and `shows_covered[0]` would IndexError).
    group = {
        "id": "rg-1",
        "title": "Test Release 1977-05-08",
        "disambiguation": "",
        "first_release_date": "1977-05-08",
        "secondary_types": ["Live"],
    }
    release = {
        "id": "r-1",
        "title": "Test Release 1977-05-08",
        "disambiguation": "",
        "status": "official",
        "date": "1977-05-08",
        "media": [],
        "url_relations": [],
    }
    shows_by_date = {"1977-05-08": ["show-1"]}

    decision = mb.process_group(group, [release], shows_by_date, {}, {})

    assert decision["status"] == "held"
    assert decision["reason"] == "release_has_no_tracks"
    assert decision["track_count"] == 0


def test_a_hand_verified_spotify_album_url_survives_a_rerun():
    existing = [
        {"release_id": "release-a", "spotify_album_url": "https://open.spotify.com/album/hand", "notes": "MusicBrainz release x."},
        {"release_id": "release-b", "spotify_album_url": "https://open.spotify.com/album/old", "notes": "MusicBrainz release y."},
    ]
    new = [
        {"release_id": "release-a", "spotify_album_url": ""},
        {"release_id": "release-b", "spotify_album_url": "https://open.spotify.com/album/musicbrainz"},
        {"release_id": "release-c", "spotify_album_url": ""},
    ]

    mb.carry_forward_spotify_album_urls(new, existing)

    assert [row["spotify_album_url"] for row in new] == [
        "https://open.spotify.com/album/hand",
        "https://open.spotify.com/album/musicbrainz",
        "",
    ]


def test_validate_accepts_partial_release_dates_and_rejects_malformed_ones():
    rows = [{"release_id": "r", "title": "T", "source_url": "u", "release_date": "1972-11"}]
    mb.validate(rows, [], {}, {})
    rows[0]["release_date"] = "Nov 1972"
    with pytest.raises(SystemExit):
        mb.validate(rows, [], {}, {})


# --- release-track matcher ------------------------------------------------------

def _setlist(show_id, *titles):
    """Performances in setlist order plus the songs table they need."""

    rows, songs = [], {}
    for position, title in enumerate(titles, start=1):
        song_id = "song-" + mb.slugify(title)
        songs[song_id] = title
        rows.append({"performance_id": f"{show_id}-{song_id}-{position}", "song_id": song_id, "set_number": "1", "position_in_set": str(position)})
    return rows, songs


def _mapped(results):
    return [result["performance"]["performance_id"] if "performance" in result else None for result in results]


def test_chain_agreement_keeps_only_pairs_on_every_longest_chain():
    on_every, on_some = mb.chain_agreement([(0, 0), (1, 1), (2, 1), (3, 2)])
    assert on_every == {(0, 0), (3, 2)}
    assert on_some == {(0, 0), (1, 1), (2, 1), (3, 2)}


def test_a_re_sequenced_track_is_held_without_holding_the_rest_of_the_show():
    rows, songs = _setlist("s", "Bertha", "Deal", "Loser", "Sugaree")
    titles = ["Bertha", "Sugaree", "Deal", "Loser"]

    results = mb.match_release_tracks(titles, [{"s"}] * 4, {"s": rows}, songs)

    assert _mapped(results) == ["s-song-bertha-1", None, "s-song-deal-2", "s-song-loser-3"]
    assert results[1]["held"] == mb.ORDER_CONFLICT


def test_an_undated_bonus_track_after_the_encore_is_not_absorbed():
    rows, songs = _setlist("s", "Bertha", "Deal", "Loser", "Casey Jones")
    # The release left out the show's Deal and appended another night's Deal.
    titles = ["Bertha", "Loser", "Casey Jones", "Deal"]

    results = mb.match_release_tracks(titles, [{"s"}] * 4, {"s": rows}, songs)

    assert _mapped(results) == ["s-song-bertha-1", "s-song-loser-3", "s-song-casey-jones-4", None]


def test_a_song_played_twice_maps_in_release_order():
    rows, songs = _setlist("s", "Playing in the Band", "Drums", "Playing in the Band")
    titles = ["Playing in the Band >", "Drums >", "Playing in the Band"]

    results = mb.match_release_tracks(titles, [{"s"}] * 3, {"s": rows}, songs)

    assert _mapped(results) == ["s-song-playing-in-the-band-1", "s-song-drums-2", "s-song-playing-in-the-band-3"]


def test_one_track_for_a_song_played_twice_is_held_and_its_span_noted():
    rows, songs = _setlist("s", "Ramble On Rose", "Dark Star", "Drums", "Dark Star", "Morning Dew")
    titles = ["Ramble On Rose", "Dark Star", "Morning Dew"]

    results = mb.match_release_tracks(titles, [{"s"}] * 3, {"s": rows}, songs)

    assert _mapped(results) == ["s-song-ramble-on-rose-1", None, "s-song-morning-dew-5"]
    assert results[1]["held"] == mb.AMBIGUOUS
    assert "s-song-drums-3 (Drums)" in results[1]["span"]


def test_undated_tracks_on_a_two_show_release_follow_song_and_order():
    first, first_songs = _setlist("a", "Morning Dew", "Mexicali Blues", "Big River")
    second, second_songs = _setlist("b", "Cold Rain and Snow", "Big River", "Morning Dew")
    songs = {**first_songs, **second_songs}
    titles = ["Morning Dew", "Mexicali Blues", "Big River", "Cold Rain and Snow", "Big River", "Morning Dew"]

    results = mb.match_release_tracks(titles, [{"a", "b"}] * 6, {"a": first, "b": second}, songs)

    assert _mapped(results) == [
        "a-song-morning-dew-1",
        "a-song-mexicali-blues-2",
        "a-song-big-river-3",
        "b-song-cold-rain-and-snow-1",
        "b-song-big-river-2",
        "b-song-morning-dew-3",
    ]


def test_an_undated_track_that_fits_two_shows_in_order_is_held():
    first, songs = _setlist("a", "Bertha", "Deal")
    second, more = _setlist("b", "Deal", "Loser")
    songs.update(more)

    results = mb.match_release_tracks(["Deal"], [{"a", "b"}], {"a": first, "b": second}, songs)

    assert _mapped(results) == [None]
    assert "more than one candidate show" in results[0]["held"]
