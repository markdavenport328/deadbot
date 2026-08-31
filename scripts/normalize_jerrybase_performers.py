#!/usr/bin/env python3
"""Promote reviewed JerryBase performer records into canonical CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "performers"


def read_csv(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(name: str, fields: list[str], rows: list[dict[str, str]]) -> None:
    with (CANONICAL / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def append_note(value: str, addition: str) -> str:
    return value if addition in value else f"{value}; {addition}" if value else addition


def person_name_and_scope(value: str) -> tuple[str, str | None]:
    """Separate JerryBase participation notes from a person's identity."""

    match = re.search(r"\s+\((complete show)\)\s*$", value, re.IGNORECASE)
    if not match:
        return value.strip(), None
    return value[: match.start()].strip(), match.group(1).casefold()


def instruments(value: str) -> list[str]:
    """Split source instrument prose into the schema's one-instrument rows."""

    value = value.strip()
    value = value.replace(" and ", ", ")
    value = value.replace("electric guitar (lead)", "lead guitar")
    value = value.replace("electric guitar (rhythm)", "rhythm guitar")
    value = value.replace("electric bass", "bass")
    value = re.sub(r"\bperc\b", "percussion", value)
    value = re.sub(r"\bkeys\b", "keyboards", value)
    result: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if item and item not in result:
            result.append(item)
    return result or ["unspecified"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, nargs="?", default=1972)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--all", action="store_true", help="normalize each collected year from 1965 through 1995")
    args = parser.parse_args()
    if args.all:
        if args.input:
            parser.error("--input cannot be combined with --all")
        for year in range(1965, 1996):
            main_for_year(year)
        return
    main_for_year(args.year, args.input)


def main_for_year(year: int, input_path: Path | None = None) -> None:
    input_path = input_path or RAW / f"jerrybase-{year}.jsonl"
    if not input_path.exists():
        raise SystemExit(f"Raw performer snapshot not found: {input_path}")

    people_fields, people_rows = read_csv("people.csv")
    performer_fields, performer_rows = read_csv("show_performers.csv")
    show_fields, show_rows = read_csv("shows.csv")
    people_by_key = {key(row["name"]): row for row in people_rows}
    shows = {row["show_id"] for row in show_rows}
    existing = {
        (row["show_id"], row["person_id"], row["role"], row["instrument"]): row
        for row in performer_rows
    }
    aliases = {
        "ron mckernan": "person-ron-pigpen-mckernan",
    }
    promoted = 0
    new_people = 0
    held = 0
    raw_records = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for record in raw_records:
        payload = record.get("raw_payload") or {}
        show_id = payload.get("show_id")
        if show_id not in shows:
            raise RuntimeError(f"Raw performer record references unknown show: {show_id}")
        source_id = record.get("source_record_id", "unknown")
        for group, role in (("musicians", "performer"), ("guests", "guest")):
            for assignment in payload.get(group, []):
                raw_source_name = str(assignment.get("name") or "").strip()
                source_name, participation_scope = person_name_and_scope(raw_source_name)
                if not source_name or source_name.endswith("?") or source_name.startswith("unidentified-"):
                    held += 1
                    continue
                person_key = key(source_name)
                person = people_by_key.get(person_key)
                person_id = aliases.get(person_key) or (person or {}).get("person_id")
                if not person_id:
                    person_id = f"person-{slugify(source_name)}"
                    person = {
                        "person_id": person_id,
                        "name": source_name,
                        "birth_date": "",
                        "death_date": "",
                        "notes": f"Added from JerryBase {year} performer enrichment; biographical fields not collected in this pass.",
                    }
                    people_rows.append(person)
                    people_by_key[person_key] = person
                    new_people += 1
                source_instrument = str(assignment.get("instrument") or "").strip()
                participation_note = (
                    f"JerryBase source participation scope: {participation_scope}."
                    if participation_scope
                    else ""
                )
                for instrument in instruments(str(assignment.get("instrument") or "")):
                    row_key = (show_id, person_id, role, instrument)
                    if row_key in existing:
                        existing[row_key]["notes"] = append_note(
                            existing[row_key].get("notes", ""),
                            f"JerryBase source instrument: {source_instrument}",
                        )
                        if participation_note:
                            existing[row_key]["notes"] = append_note(
                                existing[row_key].get("notes", ""),
                                participation_note,
                            )
                        continue
                    performer_rows.append(
                        {
                            "show_id": show_id,
                            "person_id": person_id,
                            "role": role,
                            "instrument": instrument,
                            "notes": (
                                f"JerryBase source event {source_id}; raw snapshot {input_path.name}; "
                                f"JerryBase source instrument: {source_instrument}."
                                f"{' ' + participation_note if participation_note else ''}"
                            ),
                        }
                    )
                    existing[row_key] = performer_rows[-1]
                    promoted += 1

    write_csv("people.csv", people_fields, sorted(people_rows, key=lambda row: row["person_id"]))
    write_csv(
        "show_performers.csv",
        performer_fields,
        sorted(performer_rows, key=lambda row: (row["show_id"], row["role"], row["person_id"], row["instrument"])),
    )
    print(
        f"Promoted {promoted} performer assignments for {year}; "
        f"added {new_people} people; held {held} uncertain or unidentified assignments."
    )


if __name__ == "__main__":
    main()
