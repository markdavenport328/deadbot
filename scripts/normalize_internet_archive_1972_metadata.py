#!/usr/bin/env python3
"""Enrich canonical recording rows from preserved full item metadata."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "recordings" / "internet-archive-1972-representatives.jsonl"


def source_type(value: str) -> str:
    normalized = value.casefold()
    if "soundboard" in normalized or normalized.startswith("sbd"):
        return "SBD"
    if "audience" in normalized or normalized.startswith("aud"):
        return "AUD"
    return ""


def main() -> None:
    path = CANONICAL / "recordings.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    metadata_by_identifier = {}
    for line in RAW.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        metadata = record["raw_payload"].get("metadata", {})
        metadata_by_identifier[record["source_record_id"]] = metadata

    enriched = 0
    for row in rows:
        metadata = metadata_by_identifier.get(row["archive_identifier"])
        if not metadata:
            continue
        if metadata.get("source"):
            inferred_type = source_type(metadata["source"])
            if inferred_type:
                row["source_type"] = inferred_type
            elif ".sbd." in row["archive_identifier"].casefold():
                row["source_type"] = "SBD"
            elif ".aud." in row["archive_identifier"].casefold():
                row["source_type"] = "AUD"
            else:
                row["source_type"] = ""
            row["source_description"] = metadata["source"]
        for field in ("taper", "transferer", "shnid", "lineage"):
            if metadata.get(field):
                row[field] = metadata[field]
        row["notes"] = (
            "Full Internet Archive item metadata preserved in "
            "data/raw/recordings/internet-archive-1972-representatives.jsonl; "
            "track descriptions remain source-attributed."
        )
        enriched += 1

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Enriched {enriched} canonical recording rows from full item metadata.")


if __name__ == "__main__":
    main()
