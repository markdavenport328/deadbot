"""Tests for the zero-track release guard in process_group (Minor 2).

Small in-memory fixtures only: no network, no reading the full canonical
CSVs.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
