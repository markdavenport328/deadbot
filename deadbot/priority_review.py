"""Loader and validation for the first editorial priority-review queue."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = ROOT / "data/editorial/priority-review-queue.json"
ALLOWED_REASONS = {"data_coverage", "discovery_lead", "lore_source_trail", "transition_suite", "long_tail", "editorial_override"}
REQUIRED_CANDIDATE_FIELDS = {
    "queue_position", "debut_era", "span_band", "first_year", "last_year", "span_years",
    "performance_count", "distinct_recording_count", "recording_linked_performance_count",
    "recording_linked_performance_ratio", "resource_count", "writer_count", "coverage_risk",
}


class PriorityReviewValidationError(ValueError):
    pass


def load_priority_queue(path: Path = DEFAULT_QUEUE_PATH) -> tuple[dict[str, Any], ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PriorityReviewValidationError(f"cannot read priority queue: {exc}") from exc
    return validate_priority_queue(document)


def validate_priority_queue(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    if document.get("schema_version") != 1 or document.get("kind") != "editorial_priority_review_queue":
        raise PriorityReviewValidationError("unsupported priority queue document")
    policy = document.get("selection_policy", {})
    if policy.get("remaining_candidates_eligible") is not True:
        raise PriorityReviewValidationError("queue must keep remaining candidates eligible")
    rows = document.get("priorities")
    if not isinstance(rows, list) or not 25 <= len(rows) <= 35:
        raise PriorityReviewValidationError("first queue must contain 25-35 priorities")
    candidate_rows = _candidate_rows()
    canonical_rows = _canonical_profiles()
    lead_ids = _ids(ROOT / "data/editorial/discovery-guide.json", "leads", "id")
    trail_ids = _ids(ROOT / "data/lore-source-trails.json", "trails", "trail_id")
    seen = set()
    for row in rows:
        song_id = row.get("song_id")
        if not isinstance(song_id, str) or song_id in seen or song_id not in canonical_rows:
            raise PriorityReviewValidationError(f"invalid or duplicate candidate: {song_id}")
        seen.add(song_id)
        reasons = row.get("reasons")
        if not isinstance(reasons, list) or not reasons or not set(reasons) <= ALLOWED_REASONS:
            raise PriorityReviewValidationError(f"invalid reasons for {song_id}")
        if not isinstance(row.get("lead_ids"), list) or not set(row["lead_ids"]) <= lead_ids:
            raise PriorityReviewValidationError(f"unknown discovery lead for {song_id}")
        if "editorial_override" in reasons and (not row["lead_ids"] or row.get("candidate", {}).get("queue_position") is not None):
            raise PriorityReviewValidationError(f"editorial override must have a lead and no cohort position: {song_id}")
        if not isinstance(row.get("source_trail_ids"), list) or not set(row["source_trail_ids"]) <= trail_ids:
            raise PriorityReviewValidationError(f"unknown source trail for {song_id}")
        if "discovery_lead" in reasons and not row["lead_ids"]:
            raise PriorityReviewValidationError(f"discovery lead reason needs a lead ID for {song_id}")
        if "lore_source_trail" in reasons and not row["source_trail_ids"]:
            raise PriorityReviewValidationError(f"lore source trail reason needs a trail ID for {song_id}")
        if "transition_suite" in reasons and not row["lead_ids"]:
            raise PriorityReviewValidationError(f"transition suite reason needs a lead ID for {song_id}")
        candidate = row.get("candidate")
        if not isinstance(candidate, dict) or set(REQUIRED_CANDIDATE_FIELDS) - candidate.keys():
            raise PriorityReviewValidationError(f"incomplete factual coverage for {song_id}")
        original = candidate_rows.get(song_id) or canonical_rows[song_id]
        for field in REQUIRED_CANDIDATE_FIELDS:
            if field == "recording_linked_performance_ratio":
                # The materialized CSV stores this ratio to four decimals.
                matches = abs(float(candidate[field]) - float(original[field])) < 0.00005
            else:
                matches = str(candidate[field]) == str(original[field])
            if not matches:
                raise PriorityReviewValidationError(f"coverage mismatch for {song_id}: {field}")
    return tuple(rows)


def _candidate_rows() -> dict[str, dict[str, str]]:
    path = ROOT / "data/editorial/song-cohort-candidates.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["song_id"]: row for row in csv.DictReader(handle)}


def _canonical_profiles() -> dict[str, dict[str, Any]]:
    """Compute the review fields for guide-led songs outside the 72-song CSV."""
    def read(name: str) -> list[dict[str, str]]:
        with (ROOT / "data/canonical" / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    songs = {row["song_id"]: row for row in read("songs.csv")}
    performances = read("performances.csv")
    links = read("performance_recordings.csv")
    resources = read("resource_songs.csv")
    writers = read("song_writers.csv")
    result: dict[str, dict[str, Any]] = {}
    for song_id in songs:
        rows = [row for row in performances if row["song_id"] == song_id]
        if not rows:
            continue
        years = [int(row["show_id"][3:7]) for row in rows]
        performance_ids = {row["performance_id"] for row in rows}
        recording_links = [row for row in links if row["performance_id"] in performance_ids]
        ratio = len(recording_links) / len(rows)
        resource_ids = {row["resource_id"] for row in resources if row["song_id"] == song_id}
        writer_ids = {row["person_id"] for row in writers if row["song_id"] == song_id}
        risk = "high" if ratio < .25 or (not resource_ids and not writer_ids) else ("medium" if ratio < .6 or not resource_ids or not writer_ids else "low")
        first, last = min(years), max(years)
        result[song_id] = {"queue_position": None, "debut_era": f"{(first // 5) * 5:04d}-{(first // 5) * 5 + 4:04d}", "span_band": "10-14" if last-first < 15 else ("15-19" if last-first < 20 else "20+"), "first_year": first, "last_year": last, "span_years": last-first, "performance_count": len(rows), "distinct_recording_count": len({row["recording_id"] for row in recording_links}), "recording_linked_performance_count": len(recording_links), "recording_linked_performance_ratio": ratio, "resource_count": len(resource_ids), "writer_count": len(writer_ids), "coverage_risk": risk}
    return result


def _ids(path: Path, collection: str, field: str) -> set[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {item[field] for item in document[collection]}
