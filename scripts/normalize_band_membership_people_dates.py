#!/usr/bin/env python3
"""Fill people.csv birth_date/death_date for the reviewed band-membership pass.

Input: `data/raw/people/wikidata-grateful-dead-members.jsonl`, written by
`scripts/collect/fetch_band_membership_sources.py`.

Output: `data/canonical/people.csv` with `birth_date`/`death_date` filled for
the twelve people resolved by `scripts/normalize_band_membership.py`, plus
their two JerryBase `(complete show)` duplicate identities
(`person-bruce-hornsby-complete-show`, `person-tom-constanten-complete-show`),
which name the same person under a second id. Every other column, and every
other row, is left untouched -- no row is added -- so a concurrent pass
adding new people rows to the same file merges cleanly.

This is a one-time, reviewed mapping from Wikidata label to canonical
person_id (Wikidata does not know Deadbot's internal ids), not a generic
label-matching heuristic; see docs/collection-status-band-membership.md for
the full source comparison this mapping is drawn from.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "people" / "wikidata-grateful-dead-members.jsonl"
PEOPLE_CSV = ROOT / "data" / "canonical" / "people.csv"

# Wikidata label -> every canonical person_id it should fill. Two labels
# resolve to two ids apiece because JerryBase's "(complete show)" participation
# qualifier created a second person_id for the same human being.
LABEL_TO_PERSON_IDS: dict[str, tuple[str, ...]] = {
    "Jerry Garcia": ("person-jerry-garcia",),
    "Bob Weir": ("person-bob-weir",),
    "Phil Lesh": ("person-phil-lesh",),
    "Bill Kreutzmann": ("person-bill-kreutzmann",),
    "Mickey Hart": ("person-mickey-hart",),
    'Ron "Pigpen" McKernan': ("person-ron-pigpen-mckernan",),
    "Tom Constanten": ("person-tom-constanten", "person-tom-constanten-complete-show"),
    "Keith Godchaux": ("person-keith-godchaux",),
    "Donna Jean Godchaux": ("person-donna-jean-godchaux",),
    "Brent Mydland": ("person-brent-mydland",),
    "Vince Welnick": ("person-vince-welnick",),
    "Bruce Hornsby": ("person-bruce-hornsby", "person-bruce-hornsby-complete-show"),
}


def _iso_date(wikidata_time: str | None) -> str:
    """Wikidata day-precision time ("+1942-08-01T00:00:00Z") to "1942-08-01"."""

    if not wikidata_time:
        return ""
    return wikidata_time.lstrip("+")[:10]


def build_updates() -> dict[str, tuple[str, str]]:
    updates: dict[str, tuple[str, str]] = {}
    with RAW_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            person_ids = LABEL_TO_PERSON_IDS.get(record["label"])
            if not person_ids:
                raise SystemExit(f"no person_id mapping for Wikidata label {record['label']!r}")
            birth = _iso_date(record.get("date_of_birth_raw"))
            death = _iso_date(record.get("date_of_death_raw"))
            for person_id in person_ids:
                updates[person_id] = (birth, death)
    return updates


def apply_updates(updates: dict[str, tuple[str, str]]) -> int:
    with PEOPLE_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    if header != ["person_id", "name", "birth_date", "death_date", "notes"]:
        raise SystemExit(f"unexpected people.csv header: {header!r}")

    changed = 0
    seen: set[str] = set()
    for row in rows[1:]:
        person_id = row[0]
        if person_id in updates:
            birth, death = updates[person_id]
            row[2] = birth
            row[3] = death
            changed += 1
            seen.add(person_id)

    missing = set(updates) - seen
    if missing:
        raise SystemExit(f"person_id(s) not found in people.csv: {sorted(missing)}")

    with PEOPLE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)
    return changed


def main() -> None:
    updates = build_updates()
    changed = apply_updates(updates)
    print(f"updated birth_date/death_date for {changed} people.csv rows")


if __name__ == "__main__":
    main()
