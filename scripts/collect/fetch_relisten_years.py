#!/usr/bin/env python3
"""Preserve compact Relisten year listings for Grateful Dead shows.

The collector calls the public Relisten API year endpoint
(``/api/v2/artists/grateful-dead/years/<year>``) once per year, waits at least
one second between requests, and preserves one raw JSONL record per year in
``data/raw/recordings/relisten-years.jsonl``. Each record keeps the show dates,
display dates, source counts, and ratings needed to build whole-show listening
links; it does not store track lists, audio, or item binaries.

Relisten is a free, non-commercial, open-source platform that itself streams
from Archive.org (see https://relisten.net/about). This collector fetches
metadata only, identifies itself with a descriptive User-Agent, and refuses to
overwrite an existing raw file without ``--force``. Each request retries on
HTTP 429/503 with capped exponential backoff. ``--force`` merges its results
into the existing file year by year, preferring whichever record for a year
has ``status == 200``, so a failed retry (or a rerun with the network down)
can never erase a successful earlier year.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "data" / "raw" / "recordings"
OUTPUT = OUTPUT_DIR / "relisten-years.jsonl"
API_BASE = "https://api.relisten.net/api/v2/artists/grateful-dead/years"
USER_AGENT = "Deadbot/0.1 (historical-show-context)"
FIRST_YEAR = 1965
LAST_YEAR = 1995
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
MAX_ATTEMPTS = 6

YEAR_FIELDS = ("year", "show_count", "source_count", "avg_rating", "avg_duration", "uuid", "id", "updated_at")
SHOW_FIELDS = (
    "display_date",
    "date",
    "source_count",
    "avg_rating",
    "avg_duration",
    "has_soundboard_source",
    "has_streamable_flac_source",
    "uuid",
    "id",
    "updated_at",
)
VENUE_FIELDS = ("name", "location", "slug", "uuid")


def year_url(year: int) -> str:
    return f"{API_BASE}/{year}"


def timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_show(show: dict) -> dict:
    record = {field: show.get(field) for field in SHOW_FIELDS}
    venue = show.get("venue") or {}
    record["venue"] = {field: venue.get(field) for field in VENUE_FIELDS} if venue else None
    return record


def compact_payload(payload: dict) -> dict:
    shows = payload.get("shows") or []
    return {
        "year": {field: payload.get(field) for field in YEAR_FIELDS},
        "show_count_returned": len(shows),
        "shows": sorted((compact_show(show) for show in shows), key=lambda item: (item["display_date"] or "", item["uuid"] or "")),
    }


def fetch_year(year: int) -> dict:
    """Fetch one year with bounded retry and backoff on 429/503 (a transient
    error is never written as a permanent one on the first attempt)."""

    url = year_url(year)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    status: int | str | None = None
    error: str | None = None
    raw_payload: dict | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urlopen(request, timeout=60) as response:
                status = response.status
                raw_payload = compact_payload(json.load(response))
                error = None
            break
        except HTTPError as exc:
            status = exc.code
            error = f"HTTP {exc.code}: {exc.reason}"
            raw_payload = None
            if status not in (429, 503):
                break
        except (URLError, TimeoutError, ValueError) as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            raw_payload = None
        if attempt + 1 >= MAX_ATTEMPTS:
            break
        backoff = min(2 ** (attempt + 1), 30)
        print(f"  retry {attempt + 1}/{MAX_ATTEMPTS} for {year} after status {status} in {backoff}s", file=sys.stderr)
        time.sleep(backoff)
    return {
        "source": "relisten",
        "source_record_id": f"relisten:artists/grateful-dead/years/{year}",
        "retrieved_at": timestamp(),
        "source_url": url,
        "status": status,
        "error": error,
        "raw_payload": raw_payload,
    }


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def merge_year_records(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge freshly fetched year records into the previously preserved ones.

    A newly successful record always replaces what was there. A newly failed
    record never overwrites an existing successful one, so ``--force`` can
    retry failed years (even every year) without erasing prior successes.
    Records for years not present in ``new`` are kept unchanged. The result
    is sorted by year.
    """

    by_id = {record["source_record_id"]: record for record in existing}
    for record in new:
        key = record["source_record_id"]
        current = by_id.get(key)
        if record.get("status") == 200 or current is None or current.get("status") != 200:
            by_id[key] = record
    return [by_id[key] for key in sorted(by_id, key=lambda source_record_id: int(source_record_id.rsplit("/", 1)[-1]))]


def collect(years: list[int], force: bool = False) -> Path:
    if OUTPUT.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {OUTPUT}; rerun with --force to replace it")
    existing_records = read_records(OUTPUT) if OUTPUT.exists() else []

    new_records = []
    for index, year in enumerate(years):
        if index:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS)
        record = fetch_year(year)
        new_records.append(record)
        payload = record["raw_payload"] or {}
        print(f"{year}: status={record['status']} shows={payload.get('show_count_returned', 0)} {record['error'] or ''}".rstrip())

    merged = merge_year_records(existing_records, new_records)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    partial = OUTPUT.with_name(OUTPUT.name + ".partial")
    with partial.open("w", encoding="utf-8") as handle:
        for record in merged:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    partial.replace(OUTPUT)

    successful = sum(1 for record in merged if record["status"] == 200)
    print(f"Preserved {len(merged)} Relisten year records ({successful} successful) at {OUTPUT}.")
    return OUTPUT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "years",
        type=int,
        nargs="*",
        help=f"years to fetch (default: every year {FIRST_YEAR}-{LAST_YEAR})",
    )
    parser.add_argument("--force", action="store_true", help="replace the existing raw file")
    args = parser.parse_args()
    years = args.years or list(range(FIRST_YEAR, LAST_YEAR + 1))
    for year in years:
        if year < FIRST_YEAR or year > LAST_YEAR:
            parser.error(f"years must be between {FIRST_YEAR} and {LAST_YEAR}")
    collect(years, force=args.force)


if __name__ == "__main__":
    main()
