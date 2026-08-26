#!/usr/bin/env python3
"""Collect JerryBase musician assignments for the canonical Grateful Dead shows.

JerryBase is used here as a fact-type-specific enrichment source.  The collector
uses its year event index to find the matching Grateful Dead event page, then
stores the page's musician and guest fields as a compact raw JSONL record.  It
does not infer a lineup from a date, a recording, or a presumed band era.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "performers"
BASE_URL = "https://jerrybase.com"
SOURCE_BANDS = {"Grateful Dead", "Warlocks"}


def get(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Deadbot/0.1 (performer-enrichment)"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def retrieved_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


class EventIndexParser(HTMLParser):
    """Extract each event row's link, date, venue, and billed band."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self.row: dict[str, str] | None = None
        self.cell: list[str] = []
        self.link_href = ""
        self.link_text: list[str] = []
        self.in_link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "tr":
            self.row = {"href": "", "date": "", "venue": "", "band": ""}
        elif self.row is not None and tag in {"td", "th"}:
            self.cell = []
        elif self.row is not None and tag == "a":
            self.in_link = True
            self.link_href = attrs_map.get("href") or ""
            self.link_text = []

    def handle_data(self, data: str) -> None:
        if self.row is None:
            return
        if self.in_link:
            self.link_text.append(data)
        else:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.row is None:
            return
        if tag == "a" and self.in_link:
            self.in_link = False
            if re.fullmatch(r"/events/\d{8}-\d+", self.link_href):
                self.row["href"] = self.link_href
                self.row["date"] = clean("".join(self.link_text))[:10]
            else:
                self.cell.append("".join(self.link_text))
        elif tag in {"td", "th"}:
            text = clean("".join(self.cell))
            # The index table is Date / Venue / Band / Songs.
            filled = [key for key in ("date", "venue", "band") if not self.row[key]]
            if filled:
                self.row[filled[0]] = text
            self.cell = []
        elif tag == "tr":
            # JerryBase bills the earliest canonical shows as Warlocks; both
            # names belong to the canonical Grateful Dead history.  Keep
            # unrelated same-date side-project rows out of matching.
            if self.row.get("href") and self.row.get("band") in SOURCE_BANDS:
                self.rows.append(self.row)
            self.row = None


class PerformerPageParser(HTMLParser):
    """Read the source-specific musician and guest lines from an event page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_musicians = False
        self.in_guests = False
        self.in_musician_block = False
        self.in_musician_section = False
        self.block_depth = 0
        self.heading_text: list[str] = []
        self.in_heading = False
        self.current: list[str] = []
        self.musicians: list[str] = []
        self.guests: list[str] = []
        self.event_date = ""
        self.title = ""
        self.venue = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        element_id = attrs_map.get("id") or ""
        if element_id == "musicians-content":
            self.in_musician_section = True
            self.in_musicians = True
            self.in_musician_block = True
            self.block_depth = 1
        elif self.in_musician_section and not self.in_musician_block and tag == "div":
            classes = (attrs_map.get("class") or "").split()
            if "stacked-field" in classes:
                self.in_musician_block = True
                self.in_guests = False
                self.block_depth = 1
        elif self.in_musicians and tag == "br":
            self._flush()
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.in_heading = True
            self.heading_text = []
            self._flush()

    def handle_data(self, data: str) -> None:
        text = clean(data)
        if not text:
            return
        if self.in_heading:
            self.heading_text.append(text)
            return
        if self.in_musician_block:
            if text == "Guests":
                self._flush()
                self.in_guests = True
            else:
                self.current.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4"} and self.in_heading:
            heading = clean(" ".join(self.heading_text))
            self.in_heading = False
            self.heading_text = []
            if heading == "Setlist":
                self._flush()
                self.in_musician_section = False
                self.in_musician_block = False
                self.in_musicians = False
                self.in_guests = False
            return
        if self.in_musician_block and tag == "div":
            self.block_depth -= 1
            if self.block_depth > 0:
                return
            self._flush()
            self.in_musician_block = False
            self.in_guests = False

    def _flush(self) -> None:
        if not self.current:
            return
        line = clean(" ".join(self.current))
        self.current = []
        if " - " not in line:
            return
        (self.guests if self.in_guests else self.musicians).append(line)


def parse_assignment(line: str) -> dict[str, str]:
    name, instrument = line.split(" - ", 1)
    return {"name": clean(name), "instrument": clean(instrument)}


def canonical_shows(year: int) -> list[dict[str, str]]:
    with (CANONICAL / "shows.csv").open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["show_date"].startswith(f"{year:04d}-")]


def canonical_venue(venue_id: str) -> dict[str, str]:
    with (CANONICAL / "venues.csv").open(newline="", encoding="utf-8") as handle:
        return next(row for row in csv.DictReader(handle) if row["venue_id"] == venue_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, nargs="?", default=1972)
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds between requests")
    parser.add_argument("--force", action="store_true", help="replace an existing raw snapshot")
    parser.add_argument("--all", action="store_true", help="collect each canonical year from 1965 through 1995")
    parser.add_argument(
        "--best-effort",
        action="store_true",
        help="write matched records and a coverage report when some shows are held",
    )
    args = parser.parse_args()
    if args.all:
        import subprocess
        import sys

        held_years: list[int] = []
        for year in range(1965, 1996):
            output = RAW / f"jerrybase-{year}.jsonl"
            if output.exists() and not args.force:
                print(f"Skipping {year}; {output} already exists.")
                continue
            command = [sys.executable, str(Path(__file__).resolve()), str(year), "--sleep", str(args.sleep)]
            if args.force:
                command.append("--force")
            command.append("--best-effort")
            result = subprocess.run(command)
            if result.returncode:
                held_years.append(year)
        if held_years:
            raise SystemExit("Collection held years: " + ", ".join(str(year) for year in held_years))
        return
    if not 1965 <= args.year <= 1995:
        parser.error("year must be between 1965 and 1995")

    RAW.mkdir(parents=True, exist_ok=True)
    output = RAW / f"jerrybase-{args.year}.jsonl"
    if output.exists() and not args.force:
        raise SystemExit(f"{output} already exists; use --force to replace it")

    targets = canonical_shows(args.year)
    target_dates = {row["show_date"] for row in targets}
    index_html = get(f"{BASE_URL}/events?year={args.year}")
    index_parser = EventIndexParser()
    index_parser.feed(index_html)
    candidates = [
        row for row in index_parser.rows
        if row["date"] in target_dates
    ]
    by_date: dict[str, list[dict[str, str]]] = {}
    for row in candidates:
        by_date.setdefault(row["date"], []).append(row)

    missing = sorted(target_dates - by_date.keys())

    records: list[dict] = []
    failures: list[str] = []
    for target in targets:
        if target["show_date"] not in by_date:
            failures.append(f"{target['show_id']}: JerryBase index did not expose {target['show_date']}")
            continue
        options = by_date[target["show_date"]]
        # The pilot and current year baseline have one canonical show per date.
        # For a multi-show date, select the matching source sequence when present;
        # otherwise hold the date rather than guessing between event pages.
        venue = canonical_venue(target["venue_id"])
        venue_options = [
            option for option in options
            if venue["name"].casefold() in option["venue"].casefold()
            and venue["city"].casefold() in option["venue"].casefold()
        ]
        if len(venue_options) == 1:
            options = venue_options
        if len(options) != 1:
            failures.append(f"{target['show_id']}: {len(options)} JerryBase candidates after venue match")
            continue
        source_url = BASE_URL + options[0]["href"]
        try:
            page_html = get(source_url)
            page_parser = PerformerPageParser()
            page_parser.feed(page_html)
            if not page_parser.musicians and not page_parser.guests:
                failures.append(f"{target['show_id']}: page has no musician fields")
                continue
            records.append(
                {
                    "source": "jerrybase",
                    "source_record_id": options[0]["href"].rsplit("/", 1)[-1],
                    "retrieved_at": retrieved_at(),
                    "source_url": source_url,
                    "raw_payload": {
                        "event_date": target["show_date"],
                        "show_id": target["show_id"],
                        "band": options[0]["band"],
                        "venue_from_index": options[0]["venue"],
                        "musicians": [parse_assignment(line) for line in page_parser.musicians],
                        "guests": [parse_assignment(line) for line in page_parser.guests],
                    },
                }
            )
        except (HTTPError, URLError, TimeoutError, UnicodeError) as error:
            failures.append(f"{target['show_id']}: {error}")
        time.sleep(max(0, args.sleep))

    if failures and not args.best_effort:
        raise RuntimeError("Collection held without writing a partial snapshot:\n" + "\n".join(failures))
    if len(records) != len(targets) and not args.best_effort:
        raise RuntimeError(f"Collected {len(records)} of {len(targets)} target shows")
    if not records:
        raise RuntimeError(f"Collected no performer records for {args.year}")
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    if failures:
        coverage_path = RAW / f"jerrybase-{args.year}.coverage.json"
        coverage_path.write_text(
            json.dumps(
                {
                    "source": "jerrybase",
                    "year": args.year,
                    "target_show_count": len(targets),
                    "collected_show_count": len(records),
                    "missing_index_dates": missing,
                    "held": failures,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"Collected {len(records)}/{len(targets)} JerryBase performer records for {args.year}; "
            f"coverage report: {coverage_path}."
        )
    else:
        print(f"Collected {len(records)} JerryBase performer records for {args.year} into {output}.")


if __name__ == "__main__":
    main()
