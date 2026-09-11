#!/usr/bin/env python3
"""Fill ``shows.csv`` ``tour_name`` from Relisten's per-show tour assignment.

Source: ``data/raw/recordings/relisten-tours.jsonl`` (see
``scripts/collect/fetch_relisten_tours.py``). Relisten tags every show with a
``tour`` object; a dedicated ``/tours`` endpoint confirms this is a small,
closed list -- eight named touring runs plus a catch-all "Not Part of a
Tour" that covers the great majority of shows, including many the fanbase
would call an identifiable tour (Egypt '78, Fall '73, and so on). This
normalizer promotes ``tour_name`` only for the eight explicit, named
assignments; every show tagged "Not Part of a Tour", or not present in the
Relisten data at all, is left blank rather than guessed from its date.

Rules:

* A show whose ``tour_name`` is already non-blank (for example the existing
  hand-curated JerryBase-sourced Veneta row) is never touched, whether or not
  it happens to fall on a date Relisten also names a tour for.
* A source tour name not present in ``TOUR_NAME_ALIASES`` is held for review
  rather than promoted under an unreviewed spelling, so a future Relisten
  addition cannot silently introduce a new canonical spelling.
* Re-running the script recomputes every row it owns from scratch: a row's
  own previously-written note is identified by ``NOTE_MARKER`` and stripped
  before recomputing, so reruns are idempotent and never accumulate repeated
  citations.
* Two canonical shows can share one calendar date (an early and a late show).
  Relisten has one record per date, so both canonical rows receive the same
  tour_name; the shared assignment is noted.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_TOURS = ROOT / "data" / "raw" / "recordings" / "relisten-tours.jsonl"
REVIEW_OUTPUT = ROOT / "data" / "raw" / "recordings" / "show-tours-review.jsonl"
SHOWS_FIELDS = ["show_id", "show_date", "venue_id", "tour_name", "event_name", "notes", "source_key", "source_record_id"]

NOT_ON_TOUR = "Not Part of a Tour"

# One canonical spelling per Relisten tour, keyed by the source's own name.
# Relisten's names are already plain and unambiguous, so the canonical
# spelling here is the source spelling unchanged; the table exists so that a
# future source (JerryBase, once reachable, or another tour-naming source)
# can be reconciled to these same eight spellings by adding its own variant
# as another key mapping to the same value, without changing what is already
# on disk.
TOUR_NAME_ALIASES: dict[str, str] = {
    "Spring 1970": "Spring 1970",
    "Europe 1972": "Europe 1972",
    "Summer 1974": "Summer 1974",
    "Summer 1976": "Summer 1976",
    "Spring 1977": "Spring 1977",
    "Summer 1988": "Summer 1988",
    "Spring 1990": "Spring 1990",
    "Fall 1993": "Fall 1993",
}

NOTE_MARKER = "Tour sourced from Relisten"
# Matches the marker whether it follows an earlier "; "-joined fact or is the
# entire notes string (a show with no prior citation).
NOTE_SPLIT_RE = re.compile(r"(?:\s*;\s*)?" + re.escape(NOTE_MARKER) + r".*$", re.DOTALL)


def read_csv(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(name: str, fields: list[str], rows: list[dict[str, str]]) -> None:
    with (CANONICAL / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_named_tour_dates(allow_partial: bool) -> tuple[dict[str, dict], list[tuple[int, str, str | None]]]:
    """Return ``{display_date: tour dict}`` for every explicit named-tour
    show, and the list of (year, status, error) for any failed raw record."""

    if not RAW_TOURS.exists():
        raise SystemExit(f"missing {RAW_TOURS}; run scripts/collect/fetch_relisten_tours.py first")
    by_date: dict[str, dict] = {}
    failed: list[tuple[int, str, str | None]] = []
    with RAW_TOURS.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            year = int(record["source_record_id"].split("/")[-2])
            payload = record.get("raw_payload") or {}
            if record.get("status") != 200 or payload.get("shows") is None:
                failed.append((year, record.get("status"), record.get("error")))
                continue
            for show in payload["shows"]:
                tour = show.get("tour")
                if not tour or tour.get("name") == NOT_ON_TOUR:
                    continue
                display_date = show.get("display_date")
                if display_date:
                    by_date[display_date] = {**tour, "source_url": record["source_url"], "retrieved_at": record["retrieved_at"]}
    if failed:
        summary = ", ".join(f"{year} (status={status}{' ' + error if error else ''})" for year, status, error in failed)
        message = f"Relisten tour-year records without a successful show listing: {summary}"
        if not allow_partial:
            raise SystemExit(message + "; rerun the collector or pass --allow-partial")
        print("WARNING: " + message)
    return by_date, failed


def base_notes(notes: str) -> str:
    """Strip a previously-written tour citation, if this row carries one."""
    return NOTE_SPLIT_RE.sub("", notes or "").rstrip()


def build_note(base: str, tour_name: str, tour: dict, shared_with: list[str]) -> str:
    start = (tour.get("start_date") or "")[:10]
    end = (tour.get("end_date") or "")[:10]
    sentence = (
        f"{NOTE_MARKER} tour listing ({tour['source_url']}, retrieved {tour['retrieved_at'][:10]}): "
        f'"{tour_name}" ({start} to {end}).'
    )
    if shared_with:
        sentence += f" Relisten lists one record per date; the same tour is applied to same-date show(s) {', '.join(shared_with)}."
    return f"{base}; {sentence}" if base else sentence


def normalize(
    shows: list[dict[str, str]],
    named_tour_dates: dict[str, dict],
) -> tuple[list[dict[str, str]], list[dict], dict[str, int]]:
    shows_by_date: dict[str, list[str]] = {}
    for row in shows:
        shows_by_date.setdefault(row["show_date"], []).append(row["show_id"])

    review: list[dict] = []
    counts = {
        "already_had_tour_name": 0,
        "filled_from_relisten": 0,
        "unrecognized_tour_name_held": 0,
        "no_named_tour_for_date": 0,
    }
    unrecognized_names: set[str] = set()

    result: list[dict[str, str]] = []
    for row in shows:
        row = dict(row)
        existing = (row.get("tour_name") or "").strip()
        carries_our_note = NOTE_MARKER in (row.get("notes") or "")

        if existing and not carries_our_note:
            # Foreign, already-sourced tour_name (e.g. the hand-curated
            # JerryBase Veneta row): never overwritten.
            counts["already_had_tour_name"] += 1
            result.append(row)
            continue

        # Either blank, or a value we previously wrote ourselves (safe to
        # recompute from scratch): reset to the pre-normalizer state.
        stripped_notes = base_notes(row.get("notes") or "")
        tour = named_tour_dates.get(row["show_date"])
        if tour is None:
            counts["no_named_tour_for_date"] += 1
            row["tour_name"] = ""
            row["notes"] = stripped_notes
            result.append(row)
            continue

        source_name = tour["name"]
        canonical_name = TOUR_NAME_ALIASES.get(source_name)
        if canonical_name is None:
            unrecognized_names.add(source_name)
            counts["unrecognized_tour_name_held"] += 1
            review.append(
                {
                    "review_type": "unrecognized-relisten-tour-name",
                    "show_id": row["show_id"],
                    "show_date": row["show_date"],
                    "source_tour_name": source_name,
                    "decision": "held; add to TOUR_NAME_ALIASES to promote",
                }
            )
            row["tour_name"] = ""
            row["notes"] = stripped_notes
            result.append(row)
            continue

        siblings = sorted(sid for sid in shows_by_date[row["show_date"]] if sid != row["show_id"])
        row["tour_name"] = canonical_name
        row["notes"] = build_note(stripped_notes, canonical_name, tour, siblings)
        counts["filled_from_relisten"] += 1
        result.append(row)

    if unrecognized_names:
        print("WARNING: unrecognized Relisten tour name(s) held for review: " + ", ".join(sorted(unrecognized_names)))

    return result, review, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="continue when some Relisten tour-year records failed; those years contribute no tour data",
    )
    args = parser.parse_args()

    fields, shows = read_csv("shows.csv")
    if fields != SHOWS_FIELDS:
        raise SystemExit(f"unexpected shows.csv header: {fields}")

    named_tour_dates, failed = load_named_tour_dates(args.allow_partial)
    result, review, counts = normalize(shows, named_tour_dates)

    write_csv("shows.csv", SHOWS_FIELDS, result)

    REVIEW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_OUTPUT.open("w", encoding="utf-8") as handle:
        for entry in sorted(review, key=lambda item: (item["review_type"], item["show_id"])):
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")

    summary = {
        "canonical_shows": len(shows),
        "relisten_tour_years_loaded": 31 - len(failed),
        "named_tour_dates": len(named_tour_dates),
        **counts,
        "held_rows": len(review),
    }
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Wrote shows.csv and {len(review)} review entries to {REVIEW_OUTPUT}.")


if __name__ == "__main__":
    main()
