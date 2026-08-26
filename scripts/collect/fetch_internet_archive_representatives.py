#!/usr/bin/env python3
"""Preserve one representative Internet Archive item-metadata record per show."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "recordings"


def fetch(identifier: str) -> dict:
    url = f"https://archive.org/metadata/{identifier}"
    result = subprocess.run(
        ["curl", "-L", "--silent", "--show-error", "--max-time", "60", url],
        capture_output=True,
        text=True,
    )
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if result.returncode:
        return {
            "source": "internet-archive",
            "source_record_id": identifier,
            "retrieved_at": retrieved_at,
            "source_url": url,
            "raw_payload": {"http_status": 0, "error": result.stderr.strip()},
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        payload = {"http_status": 0, "error": f"invalid JSON: {error}"}
    return {
        "source": "internet-archive",
        "source_record_id": identifier,
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": payload,
    }


def choose(rows: list[dict[str, str]]) -> dict[str, str]:
    return sorted(
        rows,
        key=lambda row: (
            ".sbd." not in row["archive_identifier"].casefold(),
            ".aud." not in row["archive_identifier"].casefold(),
            row["archive_identifier"],
        ),
    )[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("years", type=int, nargs="+", help="one or more show years")
    parser.add_argument("--force", action="store_true", help="replace existing representative files")
    args = parser.parse_args()

    with (CANONICAL / "shows.csv").open(newline="", encoding="utf-8") as handle:
        show_year = {row["show_id"]: row["show_date"][:4] for row in csv.DictReader(handle)}
    with (CANONICAL / "recordings.csv").open(newline="", encoding="utf-8") as handle:
        recordings = list(csv.DictReader(handle))
    by_show: dict[str, list[dict[str, str]]] = {}
    for row in recordings:
        year = show_year.get(row["show_id"])
        if year in {str(value) for value in args.years}:
            by_show.setdefault(row["show_id"], []).append(row)

    for year in args.years:
        output = RAW / f"internet-archive-{year}-representatives.jsonl"
        if output.exists() and not args.force:
            parser.error(f"refusing to overwrite {output}; use --force")
        selected = [choose(rows) for show_id, rows in sorted(by_show.items()) if show_year[show_id] == str(year)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda row: fetch(row["archive_identifier"]), selected))
        results.sort(key=lambda row: row["source_record_id"])
        output.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in results),
            encoding="utf-8",
        )
        successes = sum("metadata" in row["raw_payload"] for row in results)
        print(f"Preserved {len(results)} representative metadata records for {year}; {successes} returned metadata.")


if __name__ == "__main__":
    main()
