"""Focused tests for conservative Internet Archive track alignment."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import normalize_internet_archive_tracks as ia_tracks  # noqa: E402


def test_repeated_song_is_disambiguated_by_the_following_track():
    songs = {
        "eyes": "Eyes Of The World",
        "dark-star": "Dark Star",
        "drums": "Drums",
    }
    performances = [
        {"song_id": "eyes"},
        {"song_id": "dark-star"},
        {"song_id": "drums"},
        {"song_id": "dark-star"},
    ]
    source_tracks = [
        (1, {"title": "Eyes Of The World"}),
        (2, {"title": "Dark Star >"}),
        (3, {"title": "Drums >"}),
        (4, {"title": "Dark Star >"}),
    ]

    status, matches, reason = ia_tracks.align_tracks(source_tracks, performances, songs)

    assert status == "accepted_full"
    assert [canonical_index for _, canonical_index, _ in matches] == [0, 1, 2, 3]
    assert reason == ""


def test_common_minglewood_source_title_matches_the_canonical_title():
    assert ia_tracks.normalized_title("New Minglewood Blues") == ia_tracks.normalized_title("Minglewood Blues")


def test_source_track_number_prefix_does_not_hide_the_song_title():
    assert ia_tracks.normalized_title("14 Franklin's Tower") == ia_tracks.normalized_title("Franklin's Tower")


def test_franklins_tower_without_an_apostrophe_matches_the_canonical_title():
    assert ia_tracks.normalized_title("Franklins Tower") == ia_tracks.normalized_title("Franklin's Tower")


# ---------------------------------------------------------------------------
# Tolerant fallback alignment
# ---------------------------------------------------------------------------


def _performances(*song_ids: str) -> list[dict]:
    return [{"song_id": song_id, "performance_id": f"p{index}"} for index, song_id in enumerate(song_ids)]


def _tracks(*titles: str) -> list[tuple[int, dict]]:
    return [(number, {"title": title}) for number, title in enumerate(titles, start=1)]


def test_file_name_prefix_and_spelling_variant_match_the_canonical_title():
    assert ia_tracks.title_keys("gd66-07-03 t01 Dancin' In The Street") & ia_tracks.title_keys("Dancin' In The Streets")
    assert ia_tracks.title_keys("d2t04 Sittin' On Top Of The World") & ia_tracks.title_keys("Sitting On Top Of The World")
    assert ia_tracks.title_keys("St. Stephen >") & ia_tracks.title_keys("Saint Stephen")
    assert ia_tracks.title_keys("Death Don't Have No Mercy (cut)") & ia_tracks.title_keys("Death Don't Have No Mercy")
    assert not ia_tracks.title_keys("Uncle John's Band Reprise") & ia_tracks.title_keys("Uncle John's Band")


def test_zero_length_is_an_unknown_duration():
    assert ia_tracks.parse_duration("0") == ""
    assert ia_tracks.parse_duration("0.00") == ""
    assert ia_tracks.parse_duration("") == ""
    assert ia_tracks.parse_duration("04:05") == "245"


def test_tolerant_alignment_skips_an_untitled_track_instead_of_holding_the_item():
    songs = {"a": "Promised Land", "b": "Samson And Delilah", "c": "Brown Eyed Women"}
    status, matches, reason, skipped = ia_tracks.align_tracks_tolerant(
        _tracks("Promised Land", "-", "Brown Eyed Women"), _performances("a", "b", "c"), songs
    )

    assert status == "accepted_partial"
    assert [(track, index) for track, index, _ in matches] == [(1, 0), (3, 2)]
    assert skipped == [{"track_number": 2, "title": "-", "reason": "untitled_track"}]


def test_tolerant_alignment_leaves_a_repeated_song_unlinked_when_its_position_is_unsettled():
    # Alligator > Drums > Alligator on the setlist, one "Alligator" file: the
    # file could be either Alligator, so neither is linked.
    songs = {"al": "Alligator", "dr": "Drums", "ca": "Caution"}
    status, matches, _, skipped = ia_tracks.align_tracks_tolerant(
        _tracks("Alligator >", "Caution (Do Not Stop On Tracks) >"),
        _performances("al", "dr", "al", "ca"),
        songs,
    )

    assert status == "accepted_partial"
    assert [(track, index) for track, index, _ in matches] == [(2, 3)]
    assert skipped[0]["reason"] == "repeated_song_position_ambiguous"


def test_tolerant_alignment_skips_an_out_of_order_track():
    songs = {"a": "Bertha", "b": "Loser", "c": "Deal", "d": "Jack Straw"}
    status, matches, _, skipped = ia_tracks.align_tracks_tolerant(
        _tracks("Bertha", "Loser", "Jack Straw", "Deal"), _performances("a", "b", "c", "d"), songs
    )

    # Either Deal or Jack Straw is out of order; neither can be settled.
    assert [(track, index) for track, index, _ in matches] == [(1, 0), (2, 1)]
    assert {row["title"] for row in skipped} == {"Jack Straw", "Deal"}
    assert status == "accepted_partial"


def test_tolerant_alignment_never_splits_a_combined_track():
    songs = {"ds": "Dark Star", "ss": "Saint Stephen", "el": "The Eleven"}
    status, matches, _, skipped = ia_tracks.align_tracks_tolerant(
        _tracks("Dark Star > St. Stephen", "The Eleven"), _performances("ds", "ss", "el"), songs
    )

    assert [(track, index) for track, index, _ in matches] == [(2, 2)]
    assert skipped[0]["reason"] == "combined_track_spans_several_songs"


def test_tolerant_alignment_holds_an_item_whose_songs_mostly_are_not_this_show():
    songs = {"a": "Bertha", "b": "Loser", "x1": "Sugaree", "x2": "Deal", "x3": "Jack Straw"}
    status, matches, reason, _ = ia_tracks.align_tracks_tolerant(
        _tracks("Sugaree", "Deal", "Jack Straw", "Bertha"),
        _performances("a", "b"),
        songs,
        catalog_keys=set().union(*(ia_tracks.title_keys(title) for title in songs.values())),
    )

    assert status == "held"
    assert matches == []
    assert reason.startswith("item_does_not_evidently_match_show_1_of_4")


def test_fallback_prefers_an_alternate_item_that_aligns_every_performance(tmp_path, monkeypatch):
    import json

    def item(identifier: str, titles: list[str]) -> dict:
        return {
            "source_record_id": identifier,
            "raw_payload": {
                "files": [
                    {"name": f"t{n}.flac", "source": "original", "format": "Flac", "track": str(n), "title": title, "length": "60"}
                    for n, title in enumerate(titles, start=1)
                ]
            },
        }

    (tmp_path / "internet-archive-1970-representatives.jsonl").write_text(
        json.dumps(item("gd1970-01-01.sbd.a", ["Casey Jones", "Tuning", "-"])) + "\n", encoding="utf-8"
    )
    alternates = tmp_path / "internet-archive-alternate-items.jsonl"
    alternates.write_text(json.dumps(item("gd1970-01-01.aud.b", ["Casey Jones", "Dire Wolf"])) + "\n", encoding="utf-8")
    monkeypatch.setattr(ia_tracks, "RAW_DIR", tmp_path)
    monkeypatch.setattr(ia_tracks, "ALTERNATES_PATH", alternates)

    songs = {"cj": "Casey Jones", "dw": "Dire Wolf"}
    performances = {
        "gd-1970-01-01": [
            {"performance_id": "gd-1970-01-01-casey-jones", "song_id": "cj"},
            {"performance_id": "gd-1970-01-01-dire-wolf", "song_id": "dw"},
        ]
    }
    recordings = {
        "gd1970-01-01.sbd.a": {"recording_id": "rec-a", "show_id": "gd-1970-01-01"},
        "gd1970-01-01.aud.b": {"recording_id": "rec-b", "show_id": "gd-1970-01-01"},
    }

    additions, review, counts, managed = ia_tracks.fallback_pass(songs, recordings, performances, [], set())

    assert {row["recording_id"] for row in additions} == {"rec-b"}
    assert [row["track_number"] for row in additions] == [1, 2]
    assert [row["chosen_for_show"] for row in review] == [False, True]
    assert managed == {"rec-a", "rec-b"}
    assert counts["accepted_full"] == 1
