"""Tests for merge_links's replace-and-hold behaviour.

Small in-memory fixtures only: no network, no reading the full canonical
CSVs.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import normalize_internet_archive_track_links as ia_links  # noqa: E402


def counter() -> dict[str, int]:
    return defaultdict(int)


def link_row(performance_id: str, url: str, platform: str = "archive", link_type: str = "recording-track") -> dict:
    return {
        "performance_link_id": f"performance-link-{performance_id}-archive-track",
        "performance_id": performance_id,
        "platform": platform,
        "link_type": link_type,
        "url": url,
        "title": "Song",
        "start_seconds": "",
        "duration_seconds": "",
        "is_official": "false",
        "notes": "note",
    }


# ---------------------------------------------------------------------------
# Important 4 — merge_links replaces a regenerated managed row instead of
# holding the corrected candidate forever.
# ---------------------------------------------------------------------------


def test_merge_links_replaces_regenerated_managed_row_with_corrected_url():
    existing = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track12.mp3")]
    candidates = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track13.mp3")]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links(existing, candidates, review, counts)

    assert len(merged) == 1
    assert merged[0]["url"] == "https://archive.org/details/item/track13.mp3"
    assert review == []
    assert counts["written"] == 1
    assert "held:existing_link_id_with_different_url" not in counts


def test_merge_links_keeps_unmanaged_row_with_colliding_id_and_holds_candidate():
    # A row this script does not manage (different platform) happens to
    # share a performance_link_id with a candidate; it must not be dropped,
    # and the candidate is held rather than silently discarded.
    existing = [link_row("gd-1977-05-08-scarlet-begonias", "https://youtube.com/watch?v=abc", platform="youtube", link_type="video")]
    candidates = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track12.mp3")]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links(existing, candidates, review, counts)

    assert len(merged) == 1
    assert merged[0]["platform"] == "youtube"
    assert counts["held:existing_link_id_with_different_url"] == 1
    assert review[0]["reason"] == "existing_link_id_with_different_url"


def test_merge_links_counts_unchanged_row_as_existing_url_unchanged():
    existing = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track12.mp3")]
    candidates = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track12.mp3")]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links(existing, candidates, review, counts)

    assert merged == existing
    assert counts["existing_url_unchanged"] == 1
    assert "written" not in counts
    assert review == []


# ---------------------------------------------------------------------------
# Important 3 — a candidate whose URL already belongs to a different
# performance is held, not silently counted as unchanged.
# ---------------------------------------------------------------------------


def test_merge_links_holds_candidate_whose_url_belongs_to_another_performance():
    # A segued pair: two different performances resolve to the same source
    # file/url. The second must be held, not counted as unchanged.
    shared_url = "https://archive.org/details/item/track07.mp3"
    candidates = [
        link_row("gd-1977-05-08-scarlet-begonias", shared_url),
        link_row("gd-1977-05-08-fire-on-the-mountain", shared_url),
    ]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links([], candidates, review, counts)

    assert len(merged) == 1
    assert merged[0]["performance_id"] == "gd-1977-05-08-scarlet-begonias"
    assert counts["written"] == 1
    assert counts["held:url_already_used_by_another_performance"] == 1
    assert "existing_url_unchanged" not in counts
    assert len(review) == 1
    assert review[0]["reason"] == "url_already_used_by_another_performance"
    assert review[0]["performance_id"] == "gd-1977-05-08-fire-on-the-mountain"


def test_merge_links_holds_candidate_whose_url_matches_a_pre_existing_different_performance():
    existing = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track07.mp3")]
    candidates = [link_row("gd-1977-05-08-fire-on-the-mountain", "https://archive.org/details/item/track07.mp3")]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links(existing, candidates, review, counts)

    assert merged == existing
    assert counts["held:url_already_used_by_another_performance"] == 1
    assert review[0]["performance_id"] == "gd-1977-05-08-fire-on-the-mountain"
    assert review[0]["existing_performance_link_id"] == existing[0]["performance_link_id"]


def test_merge_links_restores_a_managed_row_whose_own_candidate_loses_a_url_collision():
    # Reviewer-confirmed regression: perf-X had a good previous link
    # (old.mp3). This run regenerates a candidate for perf-X pointing at
    # shared.mp3, but a different candidate (perf-Y) claims shared.mp3 first
    # in iteration order. perf-X's candidate is rightly held for the url
    # collision, but perf-X's own previous row must not vanish along with
    # it -- a fact must stay visibly missing, not be silently destroyed.
    old_url = "https://archive.org/details/item/old.mp3"
    shared_url = "https://archive.org/details/item/shared.mp3"
    existing = [link_row("gd-1977-05-08-scarlet-begonias", old_url)]  # perf-X
    candidates = [
        link_row("gd-1977-05-08-fire-on-the-mountain", shared_url),  # perf-Y, processed first
        link_row("gd-1977-05-08-scarlet-begonias", shared_url),  # perf-X's regenerated (losing) candidate
    ]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links(existing, candidates, review, counts)

    by_performance = {row["performance_id"]: row for row in merged}
    assert len(merged) == 2
    assert by_performance["gd-1977-05-08-fire-on-the-mountain"]["url"] == shared_url
    # perf-X's previous row survived instead of being silently dropped.
    assert by_performance["gd-1977-05-08-scarlet-begonias"]["url"] == old_url
    assert by_performance["gd-1977-05-08-scarlet-begonias"] == existing[0]

    held_entries = [entry for entry in review if entry["performance_id"] == "gd-1977-05-08-scarlet-begonias"]
    assert len(held_entries) == 1
    assert held_entries[0]["reason"] == "url_already_used_by_another_performance"
    assert held_entries[0]["previous_row_kept"] is True


# ---------------------------------------------------------------------------
# A managed row this run could not regenerate (held in build_links) is left
# untouched rather than dropped.
# ---------------------------------------------------------------------------


def test_merge_links_leaves_unregenerated_managed_row_untouched():
    existing = [link_row("gd-1977-05-08-scarlet-begonias", "https://archive.org/details/item/track12.mp3")]
    review: list[dict] = []
    counts = counter()

    merged = ia_links.merge_links(existing, [], review, counts)

    assert merged == existing
    assert review == []
    assert dict(counts) == {}
