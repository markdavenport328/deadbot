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
