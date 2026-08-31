#!/usr/bin/env python3
"""Build source-scoped queues for unresolved canonical relationship coverage."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_PERFORMERS = ROOT / "data" / "raw" / "performers"
OUTPUT = ROOT / "data" / "coverage" / "reconciliation-queue.json"


def rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def held_performer_records() -> dict[str, dict[str, str]]:
    """Read known JerryBase holds without guessing a replacement credit."""

    result: dict[str, dict[str, str]] = {}
    for path in sorted(RAW_PERFORMERS.glob("jerrybase-*.coverage.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for held in payload.get("held", []):
            show_id, separator, reason = held.partition(": ")
            if not separator:
                continue
            result[show_id] = {
                "reason": reason,
                "raw_coverage_path": str(path.relative_to(ROOT)),
            }
    return result


def performer_hold_kind(reason: str) -> str:
    lower = reason.lower()
    if "candidates after venue match" in lower:
        return "ambiguous_source_candidates"
    if "did not expose" in lower:
        return "source_index_missing"
    if "no musician fields" in lower:
        return "source_page_without_musicians"
    return "held_for_manual_review"


def show_summary(show: dict[str, str], venue: dict[str, str]) -> dict[str, str]:
    return {
        "show_id": show["show_id"],
        "show_date": show["show_date"],
        "venue_id": show["venue_id"],
        "venue_name": venue.get("name", ""),
        "city": venue.get("city", ""),
        "state_region": venue.get("state_region", ""),
        "country": venue.get("country", ""),
        "source_key": show.get("source_key", ""),
        "source_record_id": show.get("source_record_id", ""),
    }


def document() -> dict[str, object]:
    shows = rows("shows.csv")
    venues = {row["venue_id"]: row for row in rows("venues.csv")}
    performance_show_ids = {row["show_id"] for row in rows("performances.csv")}
    assignment_show_ids = {row["show_id"] for row in rows("show_performers.csv")}
    held_performers = held_performer_records()

    setlist_queue = []
    performer_queue = []
    for show in sorted(shows, key=lambda row: (row["show_date"], row["show_id"])):
        summary = show_summary(show, venues.get(show["venue_id"], {}))
        year = int(show["show_date"][:4])
        if show["show_id"] not in performance_show_ids:
            source_empty = "Source record contains no setlist entries." in show.get("notes", "")
            setlist_queue.append({
                **summary,
                "coverage_type": "setlist",
                "status": "source_empty" if source_empty else "held_for_review",
                "priority": "high" if year <= 1970 else "medium",
                "raw_source_path": f"data/raw/shows/gdshowsdb-{year}.jsonl",
                "next_action": (
                    "Review an approved secondary source before adding performances; "
                    "retain source_empty if no supported setlist is found."
                ),
            })
        if show["show_id"] not in assignment_show_ids:
            held = held_performers.get(show["show_id"], {})
            reason = held.get("reason", "No source coverage report entry was found.")
            performer_queue.append({
                **summary,
                "coverage_type": "show_performers",
                "status": performer_hold_kind(reason),
                "priority": "high" if year <= 1970 else "medium",
                "raw_coverage_path": held.get("raw_coverage_path", ""),
                "held_reason": reason,
                "next_action": (
                    "Resolve the documented source ambiguity or review an approved "
                    "secondary source; do not infer the lineup from nearby shows."
                ),
            })

    all_queue = [*setlist_queue, *performer_queue]
    status_counts = Counter(row["status"] for row in all_queue)
    by_year: dict[int, Counter[str]] = defaultdict(Counter)
    for row in all_queue:
        by_year[int(row["show_date"][:4])][row["coverage_type"]] += 1
    return {
        "schema_version": 1,
        "kind": "canonical_relationship_reconciliation_queue",
        "status": "open",
        "purpose": (
            "A generated, source-scoped work queue for missing setlist and "
            "show-performer relationships. It preserves the reason a current "
            "source did not establish the relationship and never supplies a "
            "replacement fact."
        ),
        "queue_counts": {
            "setlist_reconciliation": len(setlist_queue),
            "show_performer_reconciliation": len(performer_queue),
            "total": len(all_queue),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "coverage_by_year": [
            {"year": year, **dict(sorted(counts.items()))}
            for year, counts in sorted(by_year.items())
        ],
        "setlist_reconciliation": setlist_queue,
        "show_performer_reconciliation": performer_queue,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote reconciliation queue to {OUTPUT}")


if __name__ == "__main__":
    main()
