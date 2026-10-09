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
