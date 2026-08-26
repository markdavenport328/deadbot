#!/usr/bin/env python3
"""Import explicitly dated Jerry Garcia guitar claims from a cited history page.

The source is a photographic/video-evidence guide rather than a complete
instrument log. Claims are deliberately curated with date ranges and usage
contexts; this script never fills gaps by guessing from an era.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "equipment"
SOURCE_URL = "https://deadessays.blogspot.com/2019/08/jerry-garcia-instrument-history-guest.html"
SOURCE_ID = "source:jerry-garcia-instrument-history"

EQUIPMENT = {
    "guitar-guild-starfire-iii": ("Red Guild Starfire III", "Guild", "Starfire III", "Jerry's early Warlocks/Dead electric guitar."),
    "guitar-les-paul-custom": ("Black Gibson Les Paul Custom", "Gibson", "Les Paul Custom", "The source distinguishes an early and a later black Les Paul Custom."),
    "guitar-les-paul-goldtop": ("Gibson Les Paul Goldtop", "Gibson", "Les Paul Goldtop", "Source dates the early goldtop to late 1967–1968 and notes a later 1971 goldtop sighting."),
    "guitar-gibson-sg-1967": ("Gibson SG Standard", "Gibson", "SG Standard", "The source distinguishes the late-1960s SG from the 1966 SG used in 1970."),
    "guitar-strat-rosewood": ("Rosewood Fender Stratocaster", "Fender", "Stratocaster", "1963 rosewood Stratocaster."),
    "guitar-gibson-sg-1966": ("Gibson SG Standard (1966)", "Gibson", "SG Standard", "1966 Gibson SG Standard used in 1970."),
    "guitar-rick-turner-peanut": ("Rick Turner Peanut", "Rick Turner", "Peanut", "Custom-built guitar associated with the early 1971 period."),
    "guitar-guild-s100": ("Guild S-100", "Guild", "S-100", "Specific 1971 show sighting."),
    "guitar-les-paul-special-tv-yellow": ("Gibson Les Paul Special", "Gibson", "Les Paul Special", "TV Yellow finish."),
    "guitar-les-paul-deluxe-cherry-sunburst": ("Gibson Les Paul Deluxe", "Gibson", "Les Paul Deluxe", "Cherry Sunburst finish."),
    "guitar-alligator": ("Alligator", "Fender", "1955 Stratocaster", "The Graham Nash Stratocaster, named for its alligator sticker."),
    "guitar-veneta-strat": ("Veneta Strat", "Fender", "1956 Sunburst Stratocaster", "The source identifies this as the sunburst Strat used in the August–September 1972 period."),
    "guitar-erlewine-strat": ("Erlewine Stratocaster", "Erlewine", "Stratocaster", "Specific late-1972 and 1973 show evidence."),
    "guitar-irwin-eagle": ("Eagle", "Doug Irwin / Alembic", "Irwin Eagle", "First custom Doug Irwin guitar made for Alembic; specific 1973 show evidence."),
    "guitar-wolf": ("Wolf", "Doug Irwin", "Wolf", "Named for the wolf inlay; the source also records a later modified configuration."),
    "guitar-travis-bean-tb1000a": ("Travis Bean TB1000A", "Travis Bean", "TB1000A", "Aluminum-neck Travis Bean; the source identifies multiple periods and a late-1978 replacement."),
    "guitar-travis-bean-tb500": ("Travis Bean TB500", "Travis Bean", "TB500", "The source identifies two TB500 guitars in the 1976–1977 period."),
    "guitar-tiger": ("Tiger", "Doug Irwin", "Tiger", "Named for the tiger inlay; it became Jerry's principal electric guitar in the 1980s."),
    "guitar-black-strat-midi": ("Black Stratocaster with MIDI", "Fender", "Stratocaster", "Used during Space in the 1989 period before Wolf was used for MIDI."),
    "guitar-rosebud": ("Rosebud", "Doug Irwin", "Rosebud", "Doug Irwin guitar with built-in MIDI controls."),
}


def claim(claim_id: str, start: str, end: str, equipment_id: str, note: str, usage_context: str = "stage guitar") -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "start_date": start,
        "end_date": end,
        "equipment_id": equipment_id,
        "usage_context": usage_context,
        "source_note": note,
    }


CLAIMS = [
    claim("guild-starfire-1965-1967", "1965-05-05", "1967-05-20", "guitar-guild-starfire-iii", "Source range: red 1962 Guild Starfire III."),
    claim("les-paul-custom-1967", "1967-05-29", "1967-10-31", "guitar-les-paul-custom", "Source range: first black 1957 Gibson Les Paul Custom."),
    claim("les-paul-goldtop-1967-1968", "1967-11-01", "1968-05-18", "guitar-les-paul-goldtop", "Source range: 1952 Gibson Les Paul Goldtop."),
    claim("les-paul-custom-1968", "1968-05-24", "1968-10-18", "guitar-les-paul-custom", "Source range: second black 1957 Gibson Les Paul Custom."),
    claim("sg-1968-1969", "1968-10-20", "1969-10-17", "guitar-gibson-sg-1967", "Source range: 1967 Gibson SG Standard."),
    claim("rosewood-strat-1969-1970", "1969-10-24", "1970-04-19", "guitar-strat-rosewood", "Source range: 1963 rosewood Fender Stratocaster."),
    claim("sg-1970", "1970-04-24", "1970-12-31", "guitar-gibson-sg-1966", "Source range: 1966 Gibson SG Standard."),
    claim("peanut-1971", "1971-01-21", "1971-04-29", "guitar-rick-turner-peanut", "Source range: Rick Turner Peanut."),
    claim("les-paul-goldtop-1971-03-17", "1971-03-17", "1971-03-17", "guitar-les-paul-goldtop", "Specific show evidence; source says Garcia played both the Peanut and Goldtop."),
    claim("guild-s100-1971-04-24", "1971-04-24", "1971-04-24", "guitar-guild-s100", "Specific show evidence."),
    claim("alligator-pre-1971", "1971-05-29", "1971-06-21", "guitar-alligator", "Source range: 1955 Fender Stratocaster before the Alligator sticker/name."),
    claim("les-paul-special-1971", "1971-07-02", "1971-08-07", "guitar-les-paul-special-tv-yellow", "Source range: TV Yellow Gibson Les Paul Special."),
    claim("les-paul-deluxe-1971", "1971-08-14", "1971-08-15", "guitar-les-paul-deluxe-cherry-sunburst", "Specific two-show range: 1971 Les Paul Deluxe, Cherry Sunburst."),
    claim("alligator-pre-1972", "1971-08-23", "1972-07-26", "guitar-alligator", "Source range: the Graham Nash Strat, later identified by its Alligator sticker."),
    claim("veneta-strat-1972", "1972-08-12", "1972-09-10", "guitar-veneta-strat", "Source range: 1956 sunburst Fender Stratocaster, called the Veneta Strat."),
    claim("alligator-1972-1973", "1972-09-15", "1973-09-02", "guitar-alligator", "Source range: Alligator, the Graham Nash Stratocaster."),
    claim("erlewine-1972", "1972-11-18", "1972-12-12", "guitar-erlewine-strat", "Source range: Erlewine Stratocaster; Alligator was also used on some of these dates."),
    claim("eagle-1973-05-13", "1973-05-13", "1973-05-13", "guitar-irwin-eagle", "Specific show evidence; source identifies this as one of three electric guitars played that night."),
    claim("wolf-1973-1975", "1973-09-05", "1975-08-13", "guitar-wolf", "Source range: Wolf."),
    claim("travis-bean-tb1000a-1975-1976", "1975-09-28", "1976-07-21", "guitar-travis-bean-tb1000a", "Source range: Travis Bean TB1000A."),
    claim("travis-bean-tb500-1976-1977", "1976-08-02", "1977-09-03", "guitar-travis-bean-tb500", "Source range: Travis Bean TB500."),
    claim("wolf-modified-1977-1979", "1977-09-28", "1979-07-01", "guitar-wolf", "Source range: modified Wolf with single-coil pickups and effects loop.", "stage guitar (modified)"),
    claim("travis-bean-tb1000a-replacement-1978", "1978-12-13", "1978-12-17", "guitar-travis-bean-tb1000a", "Specific five-show range: replacement Travis Bean TB1000A briefly substituted for Wolf."),
    claim("tiger-1979-1989", "1979-08-04", "1989-08-19", "guitar-tiger", "Source range: Tiger; the source dates its debut to 1979-08-04."),
    claim("black-strat-midi-1989", "1989-01-01", "1989-07-11", "guitar-black-strat-midi", "1989 evidence: black Stratocaster with MIDI during Space; use context is limited to Space.", "during Space"),
    claim("wolf-1989", "1989-09-29", "1989-12-30", "guitar-wolf", "Source range: Wolf, after its MIDI modifications."),
    claim("rosebud-1989-1993", "1989-12-31", "1993-06-26", "guitar-rosebud", "Source range: Rosebud."),
    claim("wolf-1990-07-23", "1990-07-23", "1990-07-23", "guitar-wolf", "Specific show evidence; older guitars continued to appear."),
    claim("wolf-1993-02-23", "1993-02-23", "1993-02-23", "guitar-wolf", "Specific show evidence; older guitars continued to appear."),
    claim("rosebud-final-show", "1995-07-09", "1995-07-09", "guitar-rosebud", "Specific final-show evidence; Rosebud was played before the switch to Tiger."),
    claim("tiger-final-show", "1995-07-09", "1995-07-09", "guitar-tiger", "Specific final-show evidence; Tiger was used after Rosebud developed problems."),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_source() -> tuple[str, str]:
    request = Request(SOURCE_URL, headers={"User-Agent": "Deadbot/0.1 (guitar-history-enrichment)"})
    with urlopen(request, timeout=20) as response:
        content = response.read()
    return hashlib.sha256(content).hexdigest(), content.decode("utf-8", errors="replace")


def load_shows() -> list[dict[str, str]]:
    with (CANONICAL / "shows.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="replace the raw source snapshot")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    raw_path = RAW / "jerry-garcia-instrument-history.jsonl"
    if raw_path.exists() and not args.force:
        raise SystemExit(f"{raw_path} already exists; use --force to replace it")

    digest, _ = fetch_source()
    raw_record = {
        "source": "dead-essays",
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "retrieved_at": now(),
        "source_content_sha256": digest,
        "claims": CLAIMS,
    }
    raw_path.write_text(json.dumps(raw_record, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    equipment_rows = [
        {
            "equipment_id": equipment_id,
            "name": values[0],
            "category": "guitar",
            "manufacturer": values[1],
            "model": values[2],
            "notes": values[3],
        }
        for equipment_id, values in sorted(EQUIPMENT.items())
    ]
    write_csv(CANONICAL / "equipment.csv", ["equipment_id", "name", "category", "manufacturer", "model", "notes"], equipment_rows)

    show_rows: list[dict[str, str]] = []
    for show in load_shows():
        show_date = date.fromisoformat(show["show_date"])
        for item in CLAIMS:
            if date.fromisoformat(item["start_date"]) <= show_date <= date.fromisoformat(item["end_date"]):
                show_rows.append(
                    {
                        "show_id": show["show_id"],
                        "equipment_id": item["equipment_id"],
                        "usage_context": item["usage_context"],
                        "claim_type": "show" if item["start_date"] == item["end_date"] else "date_range",
                        "claim_id": item["claim_id"],
                        "source_id": SOURCE_ID,
                        "source_url": SOURCE_URL,
                        "source_note": item["source_note"],
                    }
                )
    show_rows.sort(key=lambda row: (row["show_id"], row["equipment_id"], row["claim_id"]))
    write_csv(
        CANONICAL / "show_equipment.csv",
        ["show_id", "equipment_id", "usage_context", "claim_type", "claim_id", "source_id", "source_url", "source_note"],
        show_rows,
    )
    print(f"Imported {len(CLAIMS)} source claims, {len(equipment_rows)} equipment entities, and {len(show_rows)} show-equipment links.")


if __name__ == "__main__":
    main()
