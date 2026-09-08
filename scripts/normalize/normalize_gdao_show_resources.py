#!/usr/bin/env python3
"""Catalog the collected GDAO items as stored resources mapped to shows.

Reads ``data/raw/resources/gdao-show-items.jsonl`` written by
``scripts/collect/collect_gdao_show_items.py`` and writes one
``resources.csv`` row per archive item plus a conservative ``about``
relationship to the canonical show the item's own date field names.

Mapping rules
-------------
GDAO records a date in three places and they do not mean the same thing, so
they are read in the order the archive means them:

1. ``dcterms:temporal`` (Temporal Coverage) -- the date the item is *about*.
   A ticket-request envelope postmarked in June carries the July show here.
2. ``dcterms:date`` (Date) -- the item's own date.
3. ``gdao:sortableDate`` (Sortable Date) -- the archive's sort key.

The first of those fields that gives a day-precision date decides the
mapping. One such date matching exactly one canonical show is a mapping; a
date carrying two canonical shows is a hold; a field naming more than one date
(a run of shows, a range value) is a hold; only a partial date such as
``1977-00-00`` is a hold. A full date that no canonical show sits on leaves
the item cataloged and unmapped -- reviewed and absent is not the same as
ambiguous. An item with no date at all is stored unmapped when its title names
the band or a canonical venue, and skipped otherwise.

Resource type follows the Omeka item type: recollections, letters and
interviews (``Oral History``, ``Story``, ``Email``) are a
``first-person-account``; posters, tickets, envelopes, photographs and
everything else, including an item type the source does not give, are an
``archive-artifact``.

Canonical safety: this normalizer never writes ``data/canonical`` unless told
to. ``--canonical-dir`` is read; ``--out-dir`` is written. Point ``--out-dir``
at a scratch directory for review, and at ``data/canonical`` to land the rows.
Existing rows are copied through byte for byte and never modified, this pass's
rows are appended sorted by id, and a rerun over an unchanged raw file
reproduces byte-identical output.

Usage::

    PYTHONPATH=. python scripts/normalize/normalize_gdao_show_resources.py \
        --out-dir /tmp/gdao-review
    PYTHONPATH=. python scripts/normalize/normalize_gdao_show_resources.py \
        --out-dir data/canonical
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAW_NAME = "gdao-show-items.jsonl"
RAW_PATH = ROOT / "data" / "raw" / "resources" / RAW_NAME
CANONICAL = ROOT / "data" / "canonical"
HELD_PATH = ROOT / "data" / "editorial" / "lore-mapping-held-gdao.jsonl"

RELATIONSHIP = "about"
SOURCE_NAME = "Grateful Dead Archive Online / UC Santa Cruz Library"
ITEM_URL = "https://www.gdao.org/items/show/{id}"

RESOURCE_FIELDS = ["resource_id", "resource_type", "title", "creator", "source_name", "source_url", "published_date", "notes"]
RESOURCE_SHOW_FIELDS = ["resource_id", "show_id", "relationship_type", "notes"]

# The date fields, in the order the archive means them, with the label the
# relationship note uses.
DATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("dcterms:temporal", "Temporal Coverage"),
    ("dcterms:date", "Date field"),
    ("gdao:sortableDate", "Sortable Date"),
)

# Omeka item types that are somebody's own account of something.
FIRST_PERSON_ITEM_TYPES = frozenset({"oral history", "story", "email"})
FIRST_PERSON_KEYWORDS = ("oral history", "interview", "letter", "correspondence", "recollection", "memoir", "reminiscence")
ARCHIVE_ARTIFACT = "archive-artifact"
FIRST_PERSON_ACCOUNT = "first-person-account"

BAND_NAMES = ("grateful dead", "the dead", "warlocks")
MIN_VENUE_NAME_LETTERS = 4
MAX_COVERAGE_IN_NOTES = 3

_FULL_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_RETENTION_NOTE = "Cataloged from the GDAO Omeka item API; metadata only, no files are stored."


# --- small file helpers ------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_output(canonical_path: Path, out_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    """Carry the canonical file through to ``out_path`` and append this pass's rows.

    When ``out_path`` is the canonical file itself the existing bytes are left
    alone and the rows are appended, which matters because a few reviewed rows
    were written with quoting this writer would not choose. When it is a
    scratch copy the existing bytes are copied first, so the output is the file
    the canonical directory *would* hold.
    """

    out_path.parent.mkdir(parents=True, exist_ok=True)
    same_file = out_path.exists() and canonical_path.exists() and out_path.samefile(canonical_path)
    existing = canonical_path.read_bytes() if canonical_path.exists() else b""
    if not same_file:
        if not existing:
            with out_path.open("w", newline="", encoding="utf-8") as handle:
                csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n").writeheader()
            existing = out_path.read_bytes()
        else:
            out_path.write_bytes(existing)
    if not rows:
        return
    with out_path.open("a", newline="", encoding="utf-8") as handle:
        if existing and not existing.endswith(b"\n"):
            handle.write("\n")
        csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n").writerows(rows)


# --- typing and text ---------------------------------------------------------


def match_text(value: str) -> str:
    value = value.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    return re.sub(r"\s+", " ", value.casefold()).strip()


def resource_type_for(item_type: str, dcterms_type: str = "", item_format: str = "") -> str:
    """``first-person-account`` for an account of something; else an artifact."""

    if match_text(item_type) in FIRST_PERSON_ITEM_TYPES:
        return FIRST_PERSON_ACCOUNT
    haystack = match_text(" ".join((item_type, dcterms_type, item_format)))
    if any(keyword in haystack for keyword in FIRST_PERSON_KEYWORDS):
        return FIRST_PERSON_ACCOUNT
    return ARCHIVE_ARTIFACT


def full_dates(values: list[str]) -> list[str]:
    """The day-precision dates a field's values name, sorted and deduplicated.

    ``1977-00-00T00:00:00Z`` is a year the archive wrote in a date-shaped slot,
    not a day, so a zero month or day is not a date.
    """

    found: set[str] = set()
    for value in values:
        for match in _FULL_DATE.finditer(value):
            year, month, day = (int(part) for part in match.groups())
            if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                found.add(f"{year:04d}-{month:02d}-{day:02d}")
    return sorted(found)


class VenueIndex:
    """Canonical venue names compiled into one whole-phrase matcher."""

    def __init__(self, venues: list[dict[str, str]]) -> None:
        names = sorted({match_text(venue.get("name", "")) for venue in venues})
        usable = [name for name in names if sum(character.isalpha() for character in name) >= MIN_VENUE_NAME_LETTERS]
        self.pattern = (
            re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(name) for name in sorted(usable, key=len, reverse=True)) + r")(?![a-z0-9])")
            if usable
            else None
        )

    def named_in(self, title: str) -> bool:
        return bool(self.pattern and self.pattern.search(match_text(title)))


# --- mapping -----------------------------------------------------------------


def chosen_date_field(date_fields: dict[str, list[str]]) -> tuple[str, str, list[str]]:
    """The field that decides the mapping: ``(term, label, its full dates)``.

    The first field with a day-precision date wins. When no field has one the
    first field with any value at all is returned, so the hold can say what the
    archive actually recorded.
    """

    for term, label in DATE_FIELDS:
        dates = full_dates(date_fields.get(term) or [])
        if dates:
            return term, label, dates
    for term, label in DATE_FIELDS:
        if date_fields.get(term):
            return term, label, []
    return "", "", []


def show_mapping(
    date_fields: dict[str, list[str]],
    shows_by_date: dict[str, list[str]],
) -> tuple[list[tuple[str, str]], dict[str, Any] | None, str]:
    """Resolve one item's show reference.

    Returns the ``(show_id, note)`` rows to write, a hold record when the
    reference is ambiguous, and an outcome name for the counters:
    ``mapped``, ``held``, ``no-canonical-show`` or ``undated``.
    """

    term, label, dates = chosen_date_field(date_fields)
    if not term:
        return [], None, "undated"
    if not dates:
        recorded = [f"{field}={value}" for field, _ in DATE_FIELDS for value in date_fields.get(field) or []]
        return [], {"reason": "The item's date fields give only a partial date.", "candidates": recorded}, "held"
    if len(dates) > 1:
        candidates = [f"{date} ({', '.join(shows_by_date.get(date, [])) or 'no canonical show'})" for date in dates]
        return [], {"reason": f"The item's {label} names more than one date.", "candidates": candidates}, "held"
    date = dates[0]
    show_ids = sorted(shows_by_date.get(date, []))
    if not show_ids:
        return [], None, "no-canonical-show"
    if len(show_ids) > 1:
        return [], {"reason": f"{date} matches more than one canonical show.", "candidates": show_ids}, "held"
    return [(show_ids[0], f"The item's {label} names this show date ({date}).")], None, "mapped"


def resource_notes(payload: dict[str, Any]) -> str:
    parts = [f"GDAO item type: {payload.get('item_type') or 'not given by the source'}."]
    collections = [name for name in payload.get("collections") or [] if name]
    if collections:
        parts.append(f"Item sets: {', '.join(collections)}.")
    coverage = [value for value in payload.get("coverage") or [] if value][:MAX_COVERAGE_IN_NOTES]
    if coverage:
        parts.append(f"Coverage: {'; '.join(coverage)}.")
    parts.append(_RETENTION_NOTE)
    return " ".join(parts)


def published_date_for(payload: dict[str, Any]) -> str:
    """The item's own date, when GDAO gives exactly one, else blank."""

    dates = full_dates((payload.get("date_fields") or {}).get("dcterms:date") or [])
    return dates[0] if len(dates) == 1 else ""


# --- normalization -----------------------------------------------------------


def normalize(
    raw_path: Path,
    canonical_dir: Path,
    out_dir: Path,
    held_path: Path,
    *,
    skip_item_types: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Catalog every collected item; write the output CSVs and the held queue."""

    if raw_path.is_dir():
        raw_path = raw_path / RAW_NAME

    shows_by_date: dict[str, list[str]] = {}
    for show in read_csv(canonical_dir / "shows.csv"):
        shows_by_date.setdefault(show["show_date"], []).append(show["show_id"])
    venues = VenueIndex(read_csv(canonical_dir / "venues.csv"))

    resources = read_csv(canonical_dir / "resources.csv")
    resource_shows = read_csv(canonical_dir / "resource_shows.csv")
    known_ids = {row["resource_id"] for row in resources}
    known_urls = {row["source_url"] for row in resources}
    known_show_links = {(row["resource_id"], row["show_id"], row["relationship_type"]) for row in resource_shows}

    new_resources: list[dict[str, str]] = []
    new_show_rows: list[dict[str, str]] = []
    held: list[dict[str, Any]] = []
    pass_resource_ids: set[str] = set()
    summary: dict[str, Any] = {
        "raw_file": str(raw_path),
        "pass_status": "",
        "items_read": 0,
        "resources_written": 0,
        "resources_already_present": 0,
        "urls_already_cataloged": 0,
        "show_rows_written": 0,
        "shows_mapped": 0,
        "held": 0,
        "unmapped": 0,
        "dates_without_a_canonical_show": 0,
        "undated_stored": 0,
        "skipped_undated": 0,
        "skipped_by_item_type": 0,
        "held_reasons": {},
        "by_item_type": {},
        "by_resource_type": {},
        "by_date": {},
    }

    records = read_jsonl(raw_path) if raw_path.exists() else []
    if not records:
        summary["pass_status"] = "missing"
        write_output(canonical_dir / "resources.csv", out_dir / "resources.csv", [], RESOURCE_FIELDS)
        write_output(canonical_dir / "resource_shows.csv", out_dir / "resource_shows.csv", [], RESOURCE_SHOW_FIELDS)
        _write_held(held_path, held)
        return summary

    head = records[0]["raw_payload"]
    summary["pass_status"] = str(head.get("status") or "")
    requested = head.get("requested_dates") or []
    for entry in requested:
        summary["by_date"][entry["date"]] = {
            "date": entry["date"],
            "group": entry.get("group", "target"),
            "items_found": 0,
            "mapped_to_this_show": 0,
            "held": 0,
            "status": "none-at-source",
        }
    if head.get("record_type") != "pass_metadata" or head.get("status") != "ok":
        print(f"  skipping {raw_path.name}: the raw file holds no complete pass ({summary['pass_status'] or 'unknown status'})")
        write_output(canonical_dir / "resources.csv", out_dir / "resources.csv", [], RESOURCE_FIELDS)
        write_output(canonical_dir / "resource_shows.csv", out_dir / "resource_shows.csv", [], RESOURCE_SHOW_FIELDS)
        _write_held(held_path, held)
        return summary

    for record in records[1:]:
        payload = record["raw_payload"]
        if payload.get("record_type") != "item":
            continue
        item_type = str(payload.get("item_type") or "")
        if match_text(item_type) in skip_item_types:
            summary["skipped_by_item_type"] += 1
            continue
        summary["items_read"] += 1
        item_id = payload["item_id"]
        resource_id = f"resource-gdao-item-{item_id}"
        url = record.get("source_url") or ITEM_URL.format(id=item_id)
        title = payload.get("title") or f"GDAO item {item_id}"
        queried = [date for date in payload.get("queried_dates") or [] if date in summary["by_date"]]
        for date in queried:
            summary["by_date"][date]["items_found"] += 1
        summary["by_item_type"][item_type or "(not given)"] = summary["by_item_type"].get(item_type or "(not given)", 0) + 1

        show_rows, hold, outcome = show_mapping(payload.get("date_fields") or {}, shows_by_date)
        if outcome == "undated":
            if any(name in match_text(title) for name in BAND_NAMES) or venues.named_in(title):
                summary["undated_stored"] += 1
            else:
                summary["skipped_undated"] += 1
                summary["items_read"] -= 1
                for date in queried:
                    summary["by_date"][date]["items_found"] -= 1
                continue

        resource_type = resource_type_for(item_type, payload.get("dcterms_type", ""), payload.get("format", ""))
        summary["by_resource_type"][resource_type] = summary["by_resource_type"].get(resource_type, 0) + 1
        pass_resource_ids.add(resource_id)
        if resource_id in known_ids:
            summary["resources_already_present"] += 1
        elif url in known_urls:
            # Already cataloged by hand under another id: leave that row alone
            # and do not attach this pass's relationship to it.
            summary["urls_already_cataloged"] += 1
            pass_resource_ids.discard(resource_id)
            continue
        else:
            new_resources.append(
                {
                    "resource_id": resource_id,
                    "resource_type": resource_type,
                    "title": title,
                    "creator": payload.get("creator", ""),
                    "source_name": payload.get("source_name") or SOURCE_NAME,
                    "source_url": url,
                    "published_date": published_date_for(payload),
                    "notes": resource_notes(payload),
                }
            )
            known_ids.add(resource_id)
            known_urls.add(url)
            summary["resources_written"] += 1

        for show_id, basis in show_rows:
            key = (resource_id, show_id, RELATIONSHIP)
            if key not in known_show_links:
                known_show_links.add(key)
                new_show_rows.append({"resource_id": resource_id, "show_id": show_id, "relationship_type": RELATIONSHIP, "notes": basis})
                summary["show_rows_written"] += 1
        for show_id, _basis in show_rows:
            show_date = next((date for date, ids in shows_by_date.items() if show_id in ids), "")
            if show_date in summary["by_date"]:
                summary["by_date"][show_date]["mapped_to_this_show"] += 1

        if hold:
            held.append(
                {
                    "resource_id": resource_id,
                    "item_id": item_id,
                    "host": payload.get("host", "www.gdao.org"),
                    "url": url,
                    "title": title,
                    "item_type": item_type,
                    "reason": hold["reason"],
                    "candidates": hold["candidates"],
                }
            )
            summary["held"] += 1
            summary["held_reasons"][hold["reason"]] = summary["held_reasons"].get(hold["reason"], 0) + 1
            for date in queried:
                summary["by_date"][date]["held"] += 1
        elif outcome == "no-canonical-show":
            summary["dates_without_a_canonical_show"] += 1
            summary["unmapped"] += 1
        elif outcome == "undated":
            summary["unmapped"] += 1

    new_resources.sort(key=lambda row: row["resource_id"])
    new_show_rows.sort(key=lambda row: (row["resource_id"], row["show_id"]))
    write_output(canonical_dir / "resources.csv", out_dir / "resources.csv", new_resources, RESOURCE_FIELDS)
    write_output(canonical_dir / "resource_shows.csv", out_dir / "resource_shows.csv", new_show_rows, RESOURCE_SHOW_FIELDS)
    held.sort(key=lambda row: (row["resource_id"], row["reason"]))
    _write_held(held_path, held)

    summary["shows_mapped"] = len(
        {
            row["show_id"]
            for row in resource_shows + new_show_rows
            if row["resource_id"] in pass_resource_ids and row["relationship_type"] == RELATIONSHIP
        }
    )
    for entry in summary["by_date"].values():
        if entry["mapped_to_this_show"]:
            entry["status"] = "mapped"
        elif entry["held"]:
            entry["status"] = "held"
        elif entry["items_found"]:
            entry["status"] = "found-unmapped"
        else:
            entry["status"] = "none-at-source"
    return summary


def _write_held(held_path: Path, held: list[dict[str, Any]]) -> None:
    held_path.parent.mkdir(parents=True, exist_ok=True)
    with held_path.open("w", encoding="utf-8") as handle:
        for row in held:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_PATH, help="the raw JSONL file (or the directory holding it)")
    parser.add_argument("--canonical-dir", type=Path, default=CANONICAL, help="canonical CSV directory to read")
    parser.add_argument("--out-dir", type=Path, required=True, help="directory to write resources.csv and resource_shows.csv into")
    parser.add_argument("--held", type=Path, default=HELD_PATH, help="path for the held-mapping queue")
    parser.add_argument("--skip-item-types", nargs="*", default=[], help="Omeka item types to leave out (for example: 'Fan Tape')")
    args = parser.parse_args()

    summary = normalize(
        args.raw,
        args.canonical_dir,
        args.out_dir,
        args.held,
        skip_item_types=frozenset(match_text(name) for name in args.skip_item_types),
    )
    print(f"{summary['items_read']} item(s) read from {summary['raw_file']} (pass status: {summary['pass_status'] or 'unknown'})")
    print(f"  resources: {summary['resources_written']} written, {summary['resources_already_present']} already present, {summary['urls_already_cataloged']} url(s) already cataloged elsewhere")
    print(f"  relationships: {summary['show_rows_written']} show row(s) across {summary['shows_mapped']} distinct show(s)")
    print(f"  held: {summary['held']}; unmapped: {summary['unmapped']} (dates with no canonical show: {summary['dates_without_a_canonical_show']}, undated but stored: {summary['undated_stored']})")
    print(f"  skipped: {summary['skipped_undated']} undated without a venue or band in the title, {summary['skipped_by_item_type']} by item type")
    for reason, count in sorted(summary["held_reasons"].items(), key=lambda pair: (-pair[1], pair[0])):
        print(f"    {count} x {reason}")
    for item_type, count in sorted(summary["by_item_type"].items(), key=lambda pair: (-pair[1], pair[0])):
        print(f"  item type {item_type}: {count}")
    for entry in summary["by_date"].values():
        print(f"  {entry['date']} ({entry['group']}): {entry['items_found']} found, {entry['mapped_to_this_show']} mapped, {entry['held']} held -> {entry['status']}")


if __name__ == "__main__":
    main()
