#!/usr/bin/env python3
"""Promote reviewed JerryBase performer records into canonical CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path

from deadbot.people_names import is_plain_name, participation_scope_for, split_person_qualifier


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
    """Separate JerryBase participation notes from a person's identity.

    A qualifier of any form leaves the identity; only the participation forms
    become a note on the appearance. Both readings come from
    ``deadbot.people_names`` so this pass and the guest directory that queries
    its output cannot disagree about who is one person.
    """

    base_name, qualifier = split_person_qualifier(value)
    return base_name, participation_scope_for(qualifier)


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


PERFORMER_KEY = ("show_id", "person_id", "role", "instrument")


def fold_qualified_people(
    people_rows: list[dict[str, str]], performer_rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    """Fold person rows minted from a qualified JerryBase name onto the plain person.

    Before ``deadbot.people_names`` existed, a name such as ``Bruce Hornsby
    (complete show)`` minted a second person, ``person-bruce-hornsby-complete-show``.
    The qualifier describes the appearance, never a second human being, so each
    such row folds onto the plain row of the same base name: its
    ``show_performers`` rows move to the plain id, a participation qualifier
    (``complete show``) becomes the same note the normalizer writes today, and a
    row that now collides with an existing assignment merges its notes.  A
    qualified row with no plain row of the same name is left alone: a
    parenthetical on its own is never evidence of who someone is.

    Returns the new people rows, the new performer rows, and the
    ``{folded_id: plain_id}`` map.  Idempotent: a second run finds nothing.
    """

    plain_by_name = {
        row["name"].strip().casefold(): row for row in people_rows if is_plain_name(row.get("name", ""))
    }
    folded: dict[str, str] = {}
    qualifier_of: dict[str, str] = {}
    source_name_of: dict[str, str] = {}
    for row in people_rows:
        base_name, qualifier = split_person_qualifier(row.get("name", ""))
        target = plain_by_name.get(base_name.casefold()) if qualifier else None
        if not target or target["person_id"] == row["person_id"]:
            continue
        folded[row["person_id"]] = target["person_id"]
        qualifier_of[row["person_id"]] = qualifier or ""
        source_name_of[row["person_id"]] = row["name"]
        for column in ("birth_date", "death_date"):
            if not target.get(column) and row.get(column):
                target[column] = row[column]
        target["notes"] = append_note(
            target.get("notes", "").rstrip("."),
            f"JerryBase also lists this person as '{row['name']}'; the qualifier describes an appearance, "
            f"so the former {row['person_id']} rows are folded onto this id.",
        )
    if not folded:
        return people_rows, performer_rows, folded

    merged: dict[tuple[str, ...], dict[str, str]] = {}
    result: list[dict[str, str]] = []
    for row in performer_rows:
        old_id = row["person_id"]
        if old_id in folded:
            row = {**row, "person_id": folded[old_id]}
            note = f"JerryBase source name: {source_name_of[old_id]}"
            scope = participation_scope_for(qualifier_of[old_id])
            if scope:
                note = f"{note}. JerryBase source participation scope: {scope}"
            row["notes"] = append_note(row.get("notes", "").rstrip("."), note) + "."
        row_key = tuple(row[column] for column in PERFORMER_KEY)
        if row_key in merged:
            merged[row_key]["notes"] = append_note(merged[row_key].get("notes", ""), row.get("notes", ""))
            continue
        merged[row_key] = row
        result.append(row)
    people = [row for row in people_rows if row["person_id"] not in folded]
    return people, result, folded


def fold_only() -> None:
    people_fields, people_rows = read_csv("people.csv")
    performer_fields, performer_rows = read_csv("show_performers.csv")
    people_rows, performer_rows, folded = fold_qualified_people(people_rows, performer_rows)
    write_csv("people.csv", people_fields, sorted(people_rows, key=lambda row: row["person_id"]))
    write_csv(
        "show_performers.csv",
        performer_fields,
        sorted(performer_rows, key=lambda row: (row["show_id"], row["role"], row["person_id"], row["instrument"])),
    )
    print(f"Folded {len(folded)} qualified person rows: {json.dumps(folded, sort_keys=True)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, nargs="?", default=1972)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--all", action="store_true", help="normalize each collected year from 1965 through 1995")
    parser.add_argument(
        "--fold-qualified-people",
        action="store_true",
        help="only fold people minted from a qualified JerryBase name onto the plain person, then exit",
    )
    args = parser.parse_args()
    if args.fold_qualified_people:
        fold_only()
        return
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
    people_rows, performer_rows, _ = fold_qualified_people(people_rows, performer_rows)
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
