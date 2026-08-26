#!/usr/bin/env python3
"""Add metadata-index recording rows from preserved Internet Archive searches."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "recordings"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def read_csv(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "years",
        type=int,
        nargs="*",
        help="years to normalize; defaults to every preserved year search",
    )
    args = parser.parse_args()
    fields, existing = read_csv("recordings.csv")
    shows_fields, shows = read_csv("shows.csv")
    show_by_date: dict[str, list[str]] = {}
    for row in shows:
        show_by_date.setdefault(row["show_date"], []).append(row["show_id"])
    rows_by_archive = {row["archive_identifier"]: row for row in existing}
    paths = [RAW_DIR / f"internet-archive-{year}-search-all.jsonl" for year in args.years]
    if not args.years:
        paths = sorted(RAW_DIR.glob("internet-archive-*-search-all.jsonl"))
    unmatched_dates: set[str] = set()
    ambiguous_dates: set[str] = set()
    indexed_years: set[str] = set()

    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        record = json.loads(path.read_text(encoding="utf-8"))
        payload = record["raw_payload"]
        docs = payload.get("response", {}).get("docs", [])
        indexed_years.add(path.name.split("-")[2])
        for item in docs:
            raw_date = item.get("date", "")
            date = raw_date[:10] if isinstance(raw_date, str) else ""
            show_ids = show_by_date.get(date, [])
            if not show_ids:
                unmatched_dates.add(date)
                continue
            if len(show_ids) != 1:
                ambiguous_dates.add(date)
                continue
            show_id = show_ids[0]
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
                "notes": f"Internet Archive {date[:4]} search-index metadata only; full item metadata pending.",
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
        f"Indexed {len(rows)} recordings across {len({row['show_id'] for row in rows})} shows from "
        f"{', '.join(sorted(indexed_years)) or 'no years'}; skipped "
        f"{len(unmatched_dates)} unmatched and {len(ambiguous_dates)} ambiguous dates."
    )


if __name__ == "__main__":
    main()
