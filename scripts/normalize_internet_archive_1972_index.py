#!/usr/bin/env python3
"""Add metadata-index recording rows for the pinned Internet Archive search."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "recordings" / "internet-archive-1972-search-all.jsonl"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def read_csv(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def main() -> None:
    fields, existing = read_csv("recordings.csv")
    shows_fields, shows = read_csv("shows.csv")
    show_by_date = {row["show_date"]: row["show_id"] for row in shows}
    rows_by_archive = {row["archive_identifier"]: row for row in existing}
    payload = json.loads(RAW.read_text(encoding="utf-8"))["raw_payload"]["response"]
    unmatched_dates: set[str] = set()

    for item in payload["docs"]:
        date = item["date"][:10]
        show_id = show_by_date.get(date)
        if not show_id:
            unmatched_dates.add(date)
            continue
        identifier = item["identifier"]
        if identifier in rows_by_archive:
            continue
        source_type = ""
        if ".sbd." in identifier.casefold():
            source_type = "SBD"
        elif ".aud." in identifier.casefold():
            source_type = "AUD"
        rows_by_archive[identifier] = {
            "recording_id": f"recording-archive-{slugify(identifier)}",
            "show_id": show_id,
            "source_type": source_type,
            "taper": "",
            "transferer": "",
            "shnid": "",
            "archive_identifier": identifier,
            "source_description": item.get("title", ""),
            "lineage": "",
            "source_url": f"https://archive.org/details/{identifier}",
            "notes": "Internet Archive search-index metadata only; full item metadata pending.",
        }

    rows = sorted(rows_by_archive.values(), key=lambda row: (row["show_id"], row["archive_identifier"]))
    seen_ids: set[str] = set()
    for row in rows:
        if row["recording_id"] in seen_ids:
            suffix = hashlib.sha1(row["archive_identifier"].encode("utf-8")).hexdigest()[:8]
            row["recording_id"] = f"{row['recording_id']}-{suffix}"
        seen_ids.add(row["recording_id"])
    with (CANONICAL / "recordings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"Indexed {len(rows)} recordings across {len({row['show_id'] for row in rows})} shows; "
        f"skipped {len(unmatched_dates)} dates not present in canonical shows: "
        f"{', '.join(sorted(unmatched_dates)) or 'none'}."
    )


if __name__ == "__main__":
    main()
