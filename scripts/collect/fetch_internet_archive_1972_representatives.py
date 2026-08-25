#!/usr/bin/env python3
"""Preserve one Internet Archive metadata record per canonical 1972 show."""

from __future__ import annotations

import concurrent.futures
import csv
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEARCH = ROOT / "data" / "raw" / "recordings" / "internet-archive-1972-search-all.jsonl"
RECORDINGS = ROOT / "data" / "canonical" / "recordings.csv"
OUTPUT = ROOT / "data" / "raw" / "recordings" / "internet-archive-1972-representatives.jsonl"


def fetch(identifier: str) -> dict:
    url = f"https://archive.org/metadata/{identifier}"
    result = subprocess.run(
        ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", "60", url],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return {
        "source": "internet-archive",
        "source_record_id": identifier,
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_url": url,
        "raw_payload": payload,
    }


def main() -> None:
    search = json.loads(SEARCH.read_text(encoding="utf-8"))["raw_payload"]["response"]["docs"]
    with RECORDINGS.open(newline="", encoding="utf-8") as handle:
        existing = list(csv.DictReader(handle))
    preferred_existing = {
        row["show_id"]: row["archive_identifier"]
        for row in existing
        if row["notes"] != "Internet Archive search-index metadata only; full item metadata pending."
    }
    by_date: dict[str, list[dict[str, str]]] = {}
    for item in search:
        by_date.setdefault(item["date"][:10], []).append(item)

    selected: list[tuple[str, str]] = []
    for date, items in sorted(by_date.items()):
        show_id = f"gd-{date}"
        if show_id not in {row["show_id"] for row in existing}:
            continue
        existing_identifier = preferred_existing.get(show_id)
        if existing_identifier:
            choice = next((item for item in items if item["identifier"] == existing_identifier), None)
        else:
            choice = None
        choice = choice or next((item for item in items if ".sbd." in item["identifier"].lower()), None)
        choice = choice or next((item for item in items if ".aud." in item["identifier"].lower()), None)
        choice = choice or items[0]
        selected.append((date, choice["identifier"]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda pair: (pair, fetch(pair[1])), selected))

    results.sort(key=lambda item: item[0][0])
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for _, record in results:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Preserved {len(results)} representative metadata records at {OUTPUT}.")


if __name__ == "__main__":
    main()
