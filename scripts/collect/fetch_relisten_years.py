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
overwrite an existing raw file without ``--force`` so a failed retry can never
erase a successful earlier run.
"""

from __future__ import annotations

import argparse
import json
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
    url = year_url(year)
    record = {
        "source": "relisten",
        "source_record_id": f"relisten:artists/grateful-dead/years/{year}",
        "retrieved_at": timestamp(),
        "source_url": url,
        "status": None,
        "error": None,
        "raw_payload": None,
    }
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=60) as response:
            record["status"] = response.status
            record["raw_payload"] = compact_payload(json.load(response))
    except HTTPError as error:
        record["status"] = error.code
        record["error"] = f"HTTP {error.code}: {error.reason}"
    except (URLError, TimeoutError, ValueError) as error:
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
    return record


def collect(years: list[int], force: bool = False) -> Path:
    if OUTPUT.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {OUTPUT}; rerun with --force to replace it")

    records = []
    for index, year in enumerate(years):
        if index:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS)
        record = fetch_year(year)
        records.append(record)
        payload = record["raw_payload"] or {}
        print(f"{year}: status={record['status']} shows={payload.get('show_count_returned', 0)} {record['error'] or ''}".rstrip())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    successful = sum(1 for record in records if record["status"] == 200)
    print(f"Preserved {len(records)} Relisten year records ({successful} successful) at {OUTPUT}.")
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
