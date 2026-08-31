#!/usr/bin/env python3
"""Build the first reviewable featured-show enhancement queue.

The queue is an editorial work plan, not a claim that a show is objectively
"best" or that its current evidence is complete. Every factual coverage field
is recalculated from the canonical CSV snapshot so review priorities cannot
silently drift from the underlying graph.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
OUTPUT = ROOT / "data" / "editorial" / "featured-show-candidates.json"


# These anchors span the usable setlist timeline and deliberately include
# early, thinly documented years. Their notes describe review utility, not a
# historical judgment about artistic quality or notoriety.
FEATURED_SHOWS = [
    ("gd-1969-02-27", "early-era comparison and source-reconciliation anchor"),
    ("gd-1970-05-08", "early-era performer and setlist-coverage anchor"),
    ("gd-1972-04-08", "1972 international-tour comparison anchor"),
    ("gd-1972-05-26", "1972 international-tour comparison anchor"),
    ("gd-1972-08-27", "existing deep-slice reference for validating enrichment"),
    ("gd-1972-09-21", "1972 autumn comparison anchor"),
    ("gd-1973-02-09", "1973 repertoire and recording-path comparison anchor"),
    ("gd-1973-11-11", "1973 late-year comparison anchor"),
    ("gd-1974-02-24", "1974 winter comparison anchor"),
    ("gd-1974-06-18", "1974 summer comparison anchor"),
    ("gd-1977-05-08", "1977 show-context and source-trail test anchor"),
    ("gd-1977-05-22", "1977 listening-path comparison anchor"),
    ("gd-1978-04-12", "late-1970s transition comparison anchor"),
    ("gd-1980-11-30", "acoustic/electric-era retrieval comparison anchor"),
    ("gd-1981-03-09", "early-1980s recording-path comparison anchor"),
    ("gd-1982-07-27", "early-1980s outdoor-show context anchor"),
    ("gd-1987-09-18", "late-1980s full-band comparison anchor"),
    ("gd-1989-07-17", "late-1980s listening-path comparison anchor"),
    ("gd-1990-03-29", "1990 personnel-era comparison anchor"),
    ("gd-1991-09-10", "1990s repertoire and personnel comparison anchor"),
]


def rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def enhancement_targets(
    *, performance_count: int, performer_assignment_count: int,
    mapped_performance_count: int, direct_context_count: int,
    official_release_count: int,
) -> list[str]:
    """Name missing relationship types, never a conclusion about the show."""

    targets = []
    if performance_count == 0:
        targets.append("setlist_reconciliation")
    if performer_assignment_count == 0:
        targets.append("performer_reconciliation")
    if mapped_performance_count < performance_count:
        targets.append("recording_to_performance_track_mappings")
    if official_release_count == 0:
        targets.append("official_release_track_review")
    if direct_context_count == 0:
        targets.append("direct_show_or_performance_context")
    # The existing Veneta deep slice is intentionally retained as a control:
    # it lets later enrichment prove that a rich response survives the same
    # import, retrieval, and composition paths used for thinner candidates.
    return targets or ["deep_slice_regression_control"]


def make_candidates() -> list[dict[str, object]]:
    shows_by_id = {row["show_id"]: row for row in rows("shows.csv")}
    venue_by_id = {row["venue_id"]: row for row in rows("venues.csv")}
    performances_by_show: dict[str, list[dict[str, str]]] = defaultdict(list)
    for performance in rows("performances.csv"):
        performances_by_show[performance["show_id"]].append(performance)

    assignments_by_show: dict[str, list[dict[str, str]]] = defaultdict(list)
    for assignment in rows("show_performers.csv"):
        assignments_by_show[assignment["show_id"]].append(assignment)

    recordings_by_show: dict[str, set[str]] = defaultdict(set)
    for recording in rows("recordings.csv"):
        recordings_by_show[recording["show_id"]].add(recording["recording_id"])

    mapped_performance_ids = {row["performance_id"] for row in rows("performance_recordings.csv")}
    show_resource_ids: dict[str, set[str]] = defaultdict(set)
    for resource in rows("resource_shows.csv"):
        show_resource_ids[resource["show_id"]].add(resource["resource_id"])
    performance_resource_ids: dict[str, set[str]] = defaultdict(set)
    for resource in rows("resource_performances.csv"):
        performance_resource_ids[resource["performance_id"]].add(resource["resource_id"])
    release_ids_by_performance: dict[str, set[str]] = defaultdict(set)
    for track in rows("official_release_tracks.csv"):
        if track["performance_id"]:
            release_ids_by_performance[track["performance_id"]].add(track["release_id"])

    candidates: list[dict[str, object]] = []
    for position, (show_id, editorial_rationale) in enumerate(FEATURED_SHOWS, start=1):
        show = shows_by_id.get(show_id)
        if not show:
            raise ValueError(f"Featured show {show_id!r} is not canonical.")
        performances = performances_by_show[show_id]
        performance_ids = {performance["performance_id"] for performance in performances}
        mapped_count = len(performance_ids & mapped_performance_ids)
        direct_context_ids = set(show_resource_ids[show_id])
        for performance_id in performance_ids:
            direct_context_ids.update(performance_resource_ids[performance_id])
        release_ids: set[str] = set()
        for performance_id in performance_ids:
            release_ids.update(release_ids_by_performance[performance_id])
        venue = venue_by_id.get(show["venue_id"], {})
        performance_count = len(performances)
        assignment_count = len(assignments_by_show[show_id])
        candidates.append({
            "queue_position": position,
            "show_id": show_id,
            "show_date": show["show_date"],
            "venue_id": show["venue_id"],
            "venue_name": venue.get("name", ""),
            "city": venue.get("city", ""),
            "state_region": venue.get("state_region", ""),
            "country": venue.get("country", ""),
            "editorial_rationale": editorial_rationale,
            "source": {
                "source_key": show.get("source_key", ""),
                "source_record_id": show.get("source_record_id", ""),
            },
            "coverage": {
                "performance_count": performance_count,
                "performer_assignment_count": assignment_count,
                "recording_count": len(recordings_by_show[show_id]),
                "recording_mapped_performance_count": mapped_count,
                "direct_context_resource_count": len(direct_context_ids),
                "official_release_count": len(release_ids),
                "setlist_status": "available" if performance_count else "missing",
                "performer_status": "available" if assignment_count else "missing",
            },
            "enhancement_targets": enhancement_targets(
                performance_count=performance_count,
                performer_assignment_count=assignment_count,
                mapped_performance_count=mapped_count,
                direct_context_count=len(direct_context_ids),
                official_release_count=len(release_ids),
            ),
        })
    return candidates


def document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "editorial_featured_show_candidates",
        "status": "first_pass_review_queue",
        "purpose": (
            "A bounded, cross-era work queue for show enrichment. It is editorial "
            "planning only: canonical coverage fields are recalculated from the "
            "current CSV snapshot, while selection rationales are not factual claims."
        ),
        "selection_policy": {
            "scope": "20 cross-era show anchors from 1969 through 1991",
            "not_a_ranking": True,
            "runtime_visible": False,
            "required_review": [
                "source provenance and raw-record availability",
                "setlist and performer coverage state",
                "recording-to-performance mappings",
                "official-release mappings",
                "direct show or performance context",
            ],
        },
        "candidates": make_candidates(),
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(FEATURED_SHOWS)} candidates to {OUTPUT}")


if __name__ == "__main__":
    main()
