#!/usr/bin/env python3
"""Attach whole-show listening links to canonical shows.

Two link families are written to ``data/canonical/show_links.csv``:

* ``relisten`` / ``streaming-show-page`` for every canonical show whose date
  appears in the preserved Relisten year listings
  (``data/raw/recordings/relisten-years.jsonl``).
* ``archive`` / ``recording-index`` for every canonical show that already has
  at least one row in ``recordings.csv``; the existing recording rows prove that
  Internet Archive items exist for the date.

Both URL patterns are date-level, so two canonical shows on one date (early and
late shows) receive the same URL. ``show_links`` is unique on
``(show_id, platform, url)``, so both rows are written and the ambiguity is
recorded in ``notes`` and in a review JSONL. The script is deterministic and
idempotent: generated rows replace earlier rows with the same
``(show_id, url)``, other existing rows are preserved, and the file is sorted
by ``show_link_id``.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_RELISTEN = ROOT / "data" / "raw" / "recordings" / "relisten-years.jsonl"
REVIEW_OUTPUT = ROOT / "data" / "raw" / "recordings" / "show-listening-links-review.jsonl"
SHOW_LINK_FIELDS = ["show_link_id", "show_id", "platform", "link_type", "url", "title", "is_official", "notes"]

RELISTEN_PLATFORM = "relisten"
RELISTEN_LINK_TYPE = "streaming-show-page"
ARCHIVE_PLATFORM = "archive"
ARCHIVE_LINK_TYPE = "recording-index"


def read_csv(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(name: str, fields: list[str], rows: list[dict[str, str]]) -> None:
    with (CANONICAL / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def relisten_url(show_date: str) -> str:
    year, month, day = show_date.split("-")
    return f"https://relisten.net/grateful-dead/{year}/{month}/{day}"


def archive_index_url(show_date: str) -> str:
    return "https://archive.org/details/GratefulDead?query=" + quote(f"date:{show_date}", safe="")


def load_relisten_years(allow_partial: bool) -> tuple[dict[str, dict], dict[int, dict]]:
    """Return ``{display_date: compact show record}`` and ``{year: raw record}``."""
    if not RAW_RELISTEN.exists():
        raise SystemExit(f"missing {RAW_RELISTEN}; run scripts/collect/fetch_relisten_years.py first")
    by_date: dict[str, dict] = {}
    by_year: dict[int, dict] = {}
    failed = []
    with RAW_RELISTEN.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            year = int(record["source_record_id"].rsplit("/", 1)[-1])
            by_year[year] = record
            payload = record.get("raw_payload") or {}
            if record.get("status") != 200 or not payload.get("shows"):
                failed.append((year, record.get("status"), record.get("error")))
                continue
            for show in payload["shows"]:
                display_date = show.get("display_date")
                if not display_date:
                    continue
                if display_date in by_date:
                    by_date[display_date]["source_count"] = (by_date[display_date].get("source_count") or 0) + (
                        show.get("source_count") or 0
                    )
                    by_date[display_date]["relisten_show_count"] += 1
                else:
                    by_date[display_date] = {**show, "relisten_show_count": 1, "year_record": record}
    if failed:
        summary = ", ".join(f"{year} (status={status}{' ' + error if error else ''})" for year, status, error in failed)
        message = f"Relisten year records without a successful show listing: {summary}"
        if not allow_partial:
            raise SystemExit(message + "; rerun the collector or pass --allow-partial")
        print("WARNING: " + message)
    return by_date, by_year


def build_rows(
    shows: list[dict[str, str]],
    venues: dict[str, dict[str, str]],
    recordings_by_show: Counter,
    relisten_by_date: dict[str, dict],
) -> tuple[list[dict[str, str]], list[dict], Counter]:
    shows_by_date: dict[str, list[str]] = defaultdict(list)
    for show in shows:
        shows_by_date[show["show_date"]].append(show["show_id"])
    for show_ids in shows_by_date.values():
        show_ids.sort()

    rows: list[dict[str, str]] = []
    review: list[dict] = []
    counts: Counter = Counter()

    for show in sorted(shows, key=lambda item: item["show_id"]):
        show_id = show["show_id"]
        show_date = show["show_date"]
        venue_name = venues.get(show["venue_id"], {}).get("name") or show["venue_id"]
        siblings = [other for other in shows_by_date[show_date] if other != show_id]
        ambiguity = ""
        if siblings:
            ambiguity = f" Date-level URL shared with same-date show(s) {', '.join(siblings)}; it cannot single out this show."

        relisten = relisten_by_date.get(show_date)
        if relisten:
            counts["relisten_rows"] += 1
            retrieved = relisten["year_record"]["retrieved_at"][:10]
            api_url = relisten["year_record"]["source_url"]
            source_count = relisten.get("source_count")
            source_text = f"{source_count} source(s)" if source_count is not None else "source count not stated"
            avg_rating = relisten.get("avg_rating")
            rating_text = f", avg rating {avg_rating:.2f}" if isinstance(avg_rating, (int, float)) else ""
            rows.append(
                {
                    "show_link_id": f"show-link-{show_id}-relisten",
                    "show_id": show_id,
                    "platform": RELISTEN_PLATFORM,
                    "link_type": RELISTEN_LINK_TYPE,
                    "url": relisten_url(show_date),
                    "title": f"Listen on Relisten: {show_date} {venue_name}",
                    "is_official": "false",
                    "notes": (
                        f"Relisten API year listing {api_url}: display_date {show_date}, {source_text}{rating_text}; "
                        f"retrieved {retrieved}.{ambiguity}"
                    ),
                }
            )
            if siblings:
                counts["relisten_ambiguous_rows"] += 1
                review.append(
                    {
                        "review_type": "same-date-shows-share-url",
                        "platform": RELISTEN_PLATFORM,
                        "show_id": show_id,
                        "show_date": show_date,
                        "sibling_show_ids": siblings,
                        "url": relisten_url(show_date),
                        "relisten_show_count_for_date": relisten["relisten_show_count"],
                        "decision": "linked; schema allows the same url on different show_ids",
                    }
                )
        else:
            counts["shows_not_on_relisten"] += 1
            review.append(
                {
                    "review_type": "show-date-absent-from-relisten",
                    "show_id": show_id,
                    "show_date": show_date,
                    "venue": venue_name,
                    "decision": "no relisten link written",
                }
            )

        recording_count = recordings_by_show.get(show_id, 0)
        if recording_count:
            counts["archive_rows"] += 1
            rows.append(
                {
                    "show_link_id": f"show-link-{show_id}-archive-index",
                    "show_id": show_id,
                    "platform": ARCHIVE_PLATFORM,
                    "link_type": ARCHIVE_LINK_TYPE,
                    "url": archive_index_url(show_date),
                    "title": f"All recordings on the Internet Archive: {show_date} {venue_name}",
                    "is_official": "false",
                    "notes": (
                        f"Internet Archive GratefulDead collection listing filtered to date:{show_date}; "
                        f"{recording_count} canonical recording row(s) already cite Archive items for this show, so the "
                        f"listing is non-empty.{ambiguity}"
                    ),
                }
            )
            if siblings:
                counts["archive_ambiguous_rows"] += 1
                review.append(
                    {
                        "review_type": "same-date-shows-share-url",
                        "platform": ARCHIVE_PLATFORM,
                        "show_id": show_id,
                        "show_date": show_date,
                        "sibling_show_ids": siblings,
                        "url": archive_index_url(show_date),
                        "decision": "linked; schema allows the same url on different show_ids",
                    }
                )
        else:
            counts["shows_without_recordings"] += 1

        if not relisten and not recording_count:
            counts["shows_with_no_listening_link"] += 1

    return rows, review, counts


def merge_rows(existing: list[dict[str, str]], generated: list[dict[str, str]]) -> list[dict[str, str]]:
    generated_keys = {(row["show_id"], row["url"]) for row in generated}
    generated_ids = {row["show_link_id"] for row in generated}
    kept = [
        row
        for row in existing
        if (row["show_id"], row["url"]) not in generated_keys and row["show_link_id"] not in generated_ids
    ]
    merged = kept + generated
    merged.sort(key=lambda row: row["show_link_id"])
    return merged


def validate(rows: list[dict[str, str]], show_ids: set[str]) -> None:
    ids = [row["show_link_id"] for row in rows]
    duplicate_ids = [item for item, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        raise SystemExit(f"duplicate show_link_id values: {duplicate_ids[:5]}")
    keys = Counter((row["show_id"], row["platform"], row["url"]) for row in rows)
    duplicate_keys = [key for key, count in keys.items() if count > 1]
    if duplicate_keys:
        raise SystemExit(f"duplicate (show_id, platform, url) values: {duplicate_keys[:5]}")
    unknown = sorted({row["show_id"] for row in rows} - show_ids)
    if unknown:
        raise SystemExit(f"show_links reference unknown show_id values: {unknown[:5]}")
    for row in rows:
        if row["is_official"] not in {"true", "false"}:
            raise SystemExit(f"is_official must be true/false: {row['show_link_id']}")
        if not row["url"].startswith("https://"):
            raise SystemExit(f"url must be https: {row['show_link_id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="continue when some Relisten year records failed; those years get no relisten links",
    )
    args = parser.parse_args()

    _, shows = read_csv("shows.csv")
    _, venue_rows = read_csv("venues.csv")
    venues = {row["venue_id"]: row for row in venue_rows}
    _, recordings = read_csv("recordings.csv")
    recordings_by_show = Counter(row["show_id"] for row in recordings)
    link_fields, existing_links = read_csv("show_links.csv")
    if link_fields != SHOW_LINK_FIELDS:
        raise SystemExit(f"unexpected show_links.csv header: {link_fields}")

    relisten_by_date, relisten_years = load_relisten_years(args.allow_partial)
    generated, review, counts = build_rows(shows, venues, recordings_by_show, relisten_by_date)
    merged = merge_rows(existing_links, generated)
    validate(merged, {show["show_id"] for show in shows})
    write_csv("show_links.csv", SHOW_LINK_FIELDS, merged)

    REVIEW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_OUTPUT.open("w", encoding="utf-8") as handle:
        for entry in sorted(review, key=lambda item: (item["review_type"], item.get("platform", ""), item["show_id"])):
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")

    relisten_dates = set(relisten_by_date)
    canonical_dates = {show["show_date"] for show in shows}
    summary = {
        "canonical_shows": len(shows),
        "relisten_years_loaded": sum(1 for record in relisten_years.values() if record.get("status") == 200),
        "relisten_dates": len(relisten_dates),
        "relisten_dates_without_canonical_show": len(relisten_dates - canonical_dates),
        "shows_with_recordings": sum(1 for show in shows if recordings_by_show.get(show["show_id"])),
        "existing_rows_kept": len(merged) - len(generated),
        "generated_rows": len(generated),
        "total_rows": len(merged),
        "held_rows": len(review),
        **counts,
    }
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Wrote {len(merged)} show_links rows and {len(review)} review entries to {REVIEW_OUTPUT}.")


if __name__ == "__main__":
    main()
