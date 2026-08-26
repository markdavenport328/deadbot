#!/usr/bin/env python3
"""Preserve Internet Archive recording-index metadata for one or more years.

The collector retrieves metadata from the public advanced-search endpoint only;
it never downloads audio or item binaries. Results are preserved as one raw
JSONL record per year and the request is paginated when a year exceeds the
first 1,000 results.
"""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "data" / "raw" / "recordings"
FIELDS = ["identifier", "date", "title"]
ROWS_PER_PAGE = 1000


def query_url(year: int, month: int) -> str:
    last_day = calendar.monthrange(year, month)[1]
    query = f"collection:GratefulDead AND date:[{year}-{month:02d}-01T00:00:00Z TO {year}-{month:02d}-{last_day:02d}T23:59:59Z]"
    params = [
        ("q", query),
        *(('fl[]', field) for field in FIELDS),
        ("sort[]", "identifier asc"),
        ("rows", ROWS_PER_PAGE),
        ("output", "json"),
    ]
    return "https://archive.org/advancedsearch.php?" + urlencode(params)


def fetch_page(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "DeadBot/0.1 (metadata-only collection)"})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def collect_year(year: int, force: bool = False) -> Path:
    output = OUTPUT_DIR / f"internet-archive-{year}-search-all.jsonl"
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {output}; remove it or collect with a new destination")

    pages = []
    docs_by_identifier = {}
    total = 0
    for month in range(1, 13):
        url = query_url(year, month)
        page = fetch_page(url)
        response = page.get("response", {})
        month_total = int(response.get("numFound", 0))
        if month_total > ROWS_PER_PAGE:
            raise RuntimeError(
                f"{year}-{month:02d} has {month_total} results; split this month into smaller date windows"
            )
        total += month_total
        for doc in response.get("docs", []):
            docs_by_identifier[doc["identifier"]] = doc
        pages.append({"month": month, "url": url, "response": response})

    first_url = pages[0]["url"]
    response = pages[0]["response"]
    docs = [docs_by_identifier[identifier] for identifier in sorted(docs_by_identifier)]

    record = {
        "source": "internet-archive",
        "source_record_id": f"advancedsearch:collection=GratefulDead;date={year};rows={ROWS_PER_PAGE}",
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_url": first_url,
        "raw_payload": {
            "query": response.get("responseHeader", {}).get("params", {}).get("query", ""),
            "fields": FIELDS,
            "rows": ROWS_PER_PAGE,
            "response": {"numFound": total, "start": 0, "docs": docs},
            "pages": pages,
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Preserved {len(docs)} Internet Archive index records for {year} at {output}.")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("years", type=int, nargs="+", help="one or more Grateful Dead show years")
    parser.add_argument("--force", action="store_true", help="replace existing year snapshots")
    args = parser.parse_args()
    for year in args.years:
        if year < 1965 or year > 1995:
            parser.error("years must be between 1965 and 1995")
        collect_year(year, force=args.force)


if __name__ == "__main__":
    main()
