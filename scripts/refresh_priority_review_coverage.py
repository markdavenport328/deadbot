#!/usr/bin/env python3
"""Refresh factual coverage snapshots without changing editorial priorities."""

from __future__ import annotations

import json

from deadbot.priority_review import (
    DEFAULT_QUEUE_PATH,
    REQUIRED_CANDIDATE_FIELDS,
    _candidate_rows,
    _canonical_profiles,
    validate_priority_queue,
)


INTEGER_FIELDS = {
    "queue_position",
    "first_year",
    "last_year",
    "span_years",
    "performance_count",
    "distinct_recording_count",
    "recording_linked_performance_count",
    "resource_count",
    "writer_count",
}


def main() -> None:
    document = json.loads(DEFAULT_QUEUE_PATH.read_text(encoding="utf-8"))
    cohort = _candidate_rows()
    canonical = _canonical_profiles()
    for priority in document["priorities"]:
        source = cohort.get(priority["song_id"]) or canonical[priority["song_id"]]
        refreshed = {}
        for field in REQUIRED_CANDIDATE_FIELDS:
            value = source[field]
            if field in INTEGER_FIELDS:
                value = None if value in (None, "") else int(value)
            elif field == "recording_linked_performance_ratio":
                value = float(value)
            refreshed[field] = value
        priority["candidate"] = refreshed
    validate_priority_queue(document)
    # Keep the hand-reviewed queue readable without expanding every factual
    # snapshot over dozens of lines.
    metadata = {key: value for key, value in document.items() if key != "priorities"}
    prefix = json.dumps(metadata, indent=2)
    rows = ",\n".join(f"    {json.dumps(priority, separators=(',', ':'))}" for priority in document["priorities"])
    rendered = f'{prefix[:-2]},\n  "priorities": [\n{rows}\n  ]\n}}\n'
    DEFAULT_QUEUE_PATH.write_text(rendered, encoding="utf-8")
    print(f"refreshed {len(document['priorities'])} priorities in {DEFAULT_QUEUE_PATH}")


if __name__ == "__main__":
    main()
