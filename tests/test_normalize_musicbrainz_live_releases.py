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


# --- segment titles: jams, suites, medleys -------------------------------------

def test_a_song_named_jam_takes_the_performance_the_setlist_counts_between_its_neighbours():
    rows, songs = _setlist("s", "Truckin'", "The Other One", "Spanish Jam", "Wharf Rat")
    titles = ["Truckin’ >", "Other One Jam >", "Spanish Jam >", "Wharf Rat"]

    results = mb.match_release_tracks(titles, [{"s"}] * 4, {"s": rows}, songs)

    assert _mapped(results)[1] == "s-song-the-other-one-2"
    assert results[1]["how"] == "segment"


def test_a_song_then_jam_title_is_the_songs_performance_when_the_setlist_has_no_jam():
    rows, songs = _setlist("s", "Dark Star", "Sugar Magnolia")

    results = mb.match_release_tracks(["Dark Star > Jam >", "Sugar Magnolia"], [{"s"}] * 2, {"s": rows}, songs)

    assert _mapped(results) == ["s-song-dark-star-1", "s-song-sugar-magnolia-2"]


def test_a_named_jam_takes_only_the_setlists_own_jam():
    rows, songs = _setlist("s", "He's Gone", "Jam", "Drums")
    titles = ["He’s Gone >", "No MSG Jam >", "Drums"]

    results = mb.match_release_tracks(titles, [{"s"}] * 3, {"s": rows}, songs)

    assert _mapped(results)[1] == "s-song-jam-2"


def test_a_named_jam_with_nothing_between_its_neighbours_stays_unmapped():
    rows, songs = _setlist("s", "China Cat Sunflower", "I Know You Rider", "Jam")
    titles = ["China Cat Sunflower >", "Mud Love Buddy Jam >", "I Know You Rider"]

    results = mb.match_release_tracks(titles, [{"s"}] * 3, {"s": rows}, songs)

    assert _mapped(results)[1] is None


def test_a_suite_track_spans_its_parts_and_is_held():
    rows, songs = _setlist("s", "Row Jimmy", "Weather Report Suite Prelude", "Weather Report Suite Part 1", "Let It Grow", "Dark Star")
    titles = ["Row Jimmy", "Weather Report Suite >", "Dark Star"]

    results = mb.match_release_tracks(titles, [{"s"}] * 3, {"s": rows}, songs)

    assert _mapped(results) == ["s-song-row-jimmy-1", None, "s-song-dark-star-5"]
    assert results[1]["held"].startswith("track spans 3 canonical performances")


def test_a_jam_title_alone_never_resolves_a_song_but_spelling_variants_do():
    import normalize_release_track_songs as backfill

    folded = backfill._STUDIO.load_songs()
    assert backfill.resolve_song_id("Dark Star Jam >", folded) is None
    assert backfill.resolve_song_id("Other One Jam", folded) is None
    assert backfill.resolve_song_id("Other One >", folded) == "song-the-other-one"
    assert backfill.resolve_song_id("We Bid You Goodnight", folded) == "song-and-we-bid-you-good-night"


def test_a_two_date_release_with_no_track_dates_is_promoted_by_song_and_order():
    first, songs = _setlist("gd-1976-09-25", "Bertha", "Sugaree")
    second, more = _setlist("gd-1976-09-28", "Cold Rain and Snow", "Sugaree")
    songs.update(more)
    group = {"id": "rg-20", "title": "Dick’s Picks, Volume 20: Landover 9/25/76, Syracuse 9/28/76", "first_release_date": "2001-02-01"}
    tracks = [{"position": n, "number": str(n), "title": title, "recording": {"id": f"rec-{n}"}} for n, title in enumerate(["Bertha", "Sugaree", "Cold Rain and Snow", "Sugaree"], 1)]
    release = {"id": "r-20", "title": group["title"], "status": "official", "date": "2001-02-01", "media": [{"position": 1, "format": "CD", "tracks": tracks}], "url_relations": []}
    shows_by_date = {"1976-09-25": ["gd-1976-09-25"], "1976-09-28": ["gd-1976-09-28"]}

    decision = mb.process_group(group, [release], shows_by_date, {"gd-1976-09-25": first, "gd-1976-09-28": second}, songs)

    assert decision["status"] == "promoted"
    assert [row["performance_id"] for row in decision["track_rows"]] == [
        "gd-1976-09-25-song-bertha-1",
        "gd-1976-09-25-song-sugaree-2",
        "gd-1976-09-28-song-cold-rain-and-snow-1",
        "gd-1976-09-28-song-sugaree-2",
    ]


def test_a_reviewed_wrong_recording_date_is_ignored():
    entry = {
        "medium": {"title": ""},
        "track": {"title": "Drums >", "recording": {"id": "62a3a9f4-c71f-4704-8322-7c34b38b56a2", "disambiguation": "live, 1977-05-21: Lakeland"}},
    }
    assert mb.track_dates(entry) == (set(), "")
    entry["track"]["recording"]["id"] = "some-other-recording"
    assert mb.track_dates(entry) == ({"1977-05-21"}, "recording disambiguation")
