#!/usr/bin/env python3
"""Find Internet Archive tapes for shows that have a setlist but no track audio.

Shows whose date no earlier index pass could assign to a single canonical show
(an early/late pair, or a date the year index missed) never reached the
representative-item collectors.  This collector goes back to Archive for them,
using only the public search and metadata endpoints:

1. For every distinct date of a canonical show that has performances but no
   ``archive`` / ``recording-track`` link, it runs one advanced search of the
   GratefulDead collection (matching the date field, or an identifier that
   carries the date in ``gd1969-09-30`` / ``gd69-09-30`` form) and preserves the
   result as one record in ``data/raw/recordings/internet-archive-gap-search.jsonl``.
2. For each item found (plus any item already attached to a target show in
   ``recordings.csv``) whose metadata is not preserved yet, it fetches
   ``https://archive.org/metadata/<identifier>`` and appends the response to
   ``internet-archive-alternate-items.jsonl``, the file the track normalizers
   already read.  Items are taken in the pipeline's representative order
   (soundboard, then audience, then identifier).  On a date with one canonical
   show the search stops as soon as an item aligns every performance; on a
   date shared by several shows every item is fetched, because a tape that
   aligns to two shows (an early-and-late tape) does not settle either.

Requests are sequential with a delay and retries with backoff.  Output is
appended one record at a time, so an interrupted run resumes where it stopped;
records whose request failed are retried on the next run.  No audio is
retrieved, and nothing in ``data/canonical`` is changed here: run
``normalize_internet_archive_gap_shows.py`` next.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import normalize_internet_archive_tracks as ia_tracks  # noqa: E402

ROOT = SCRIPTS_DIR.parent
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "recordings"
SEARCH_OUTPUT = RAW / "internet-archive-gap-search.jsonl"
ITEM_OUTPUT = ia_tracks.ALTERNATES_PATH
USER_AGENT = "Deadbot/0.1 (historical-show-context)"
SEARCH_FIELDS = ["identifier", "date", "title", "downloads"]
SEARCH_ROWS = 200
OMITTED_FIELDS = ("reviews", "alternate_locations", "workable_servers", "d1", "d2", "server", "dir")


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def target_shows() -> dict[str, list[str]]:
    """Map show date -> canonical shows with performances but no archive track link."""

    def read(name: str) -> list[dict]:
        with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    performances = read("performances.csv")
    show_of = {row["performance_id"]: row["show_id"] for row in performances}
    with_performances = {row["show_id"] for row in performances}
    with_tracks = {
        show_of[row["performance_id"]]
        for row in read("performance_links.csv")
        if row["platform"] == "archive" and row["link_type"] == "recording-track" and row["performance_id"] in show_of
    }
    by_date: dict[str, list[str]] = defaultdict(list)
    for row in read("shows.csv"):
        if row["show_id"] in with_performances and row["show_id"] not in with_tracks:
            by_date[row["show_date"]].append(row["show_id"])
    return {date: sorted(ids) for date, ids in sorted(by_date.items())}


def shows_per_date() -> dict[str, int]:
    """Count every canonical show on each date, whether or not it has a setlist."""

    counts: dict[str, int] = defaultdict(int)
    with (CANONICAL / "shows.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            counts[row["show_date"]] += 1
    return counts


def search_url(date: str) -> str:
    year, month, day = date.split("-")
    query = (
        f"collection:GratefulDead AND (date:{date} OR identifier:gd{date}* "
        f"OR identifier:gd{year[2:]}-{month}-{day}*)"
    )
    params = [("q", query), *(("fl[]", field) for field in SEARCH_FIELDS), ("sort[]", "identifier asc")]
    params += [("rows", SEARCH_ROWS), ("output", "json")]
    return "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params)


def get_json(url: str, retries: int, delay: float, require: str) -> tuple[dict, str]:
    """GET a JSON document, retrying with backoff; return (payload, error)."""

    error = ""
    for attempt in range(retries):
        if attempt:
            time.sleep(delay * (2**attempt))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = str(exc)
            continue
        if isinstance(payload, dict) and require in payload:
            return payload, ""
        error = f"response has no {require}"
    return {}, error


def fetch_search(date: str, retries: int, delay: float) -> dict:
    url = search_url(date)
    payload, error = get_json(url, retries, delay, "response")
    if error:
        payload = {"http_status": 0, "error": error}
    return {
        "source": "internet-archive",
        "source_record_id": f"advancedsearch:collection=GratefulDead;date={date}",
        "retrieved_at": now(),
        "source_url": url,
        "raw_payload": {
            "date": date,
            "fields": SEARCH_FIELDS,
            "rows": SEARCH_ROWS,
            **({"response": payload["response"]} if "response" in payload else payload),
        },
    }


def fetch_item(identifier: str, retries: int, delay: float) -> dict:
    url = f"https://archive.org/metadata/{urllib.parse.quote(identifier)}"
    payload, error = get_json(url, retries, delay, "files")
    if error:
        payload = {"http_status": 0, "error": error}
    omitted = [field for field in OMITTED_FIELDS if field in payload]
    for field in omitted:
        payload.pop(field)
    record = {
        "source": "internet-archive",
        "source_record_id": identifier,
        "retrieved_at": now(),
        "source_url": f"https://archive.org/metadata/{identifier}",
        "raw_payload": payload,
    }
    if omitted:
        record["omitted_payload_fields"] = omitted
    return record


def drop_failed(path: Path, ok) -> dict[str, dict]:
    """Read a JSONL file keyed by source_record_id, rewriting it without failed records."""

    records = {record["source_record_id"]: record for record in ia_tracks.read_item_records(path)}
    kept = {key: record for key, record in records.items() if ok(record)}
    if len(kept) != len(records):
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in kept.values()),
            encoding="utf-8",
        )
    return kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-date", type=int, default=30, help="most item metadata fetches for one date")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many requests (0 = no limit)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--retries", type=int, default=4)
    args = parser.parse_args()

    songs, recordings_by_identifier, performances, _ = ia_tracks.load_rows()
    catalog_keys: set[str] = set()
    for title in songs.values():
        catalog_keys |= ia_tracks.title_keys(title)
    targets = target_shows()
    date_counts = shows_per_date()
    print(f"{sum(len(ids) for ids in targets.values())} target shows on {len(targets)} dates")

    searches = drop_failed(SEARCH_OUTPUT, lambda record: "response" in record["raw_payload"]) if SEARCH_OUTPUT.exists() else {}
    items: dict[str, dict] = {}
    for path in sorted(RAW.glob("internet-archive-*-representatives.jsonl")):
        for record in ia_tracks.read_item_records(path):
            items.setdefault(record["source_record_id"], record)
    for identifier, record in drop_failed(ITEM_OUTPUT, lambda record: "files" in record["raw_payload"]).items():
        items.setdefault(identifier, record)

    attached: dict[str, list[str]] = defaultdict(list)
    for identifier, row in recordings_by_identifier.items():
        attached[row["show_id"]].append(identifier)

    requests = 0
    stats = {"searches": 0, "search_failed": 0, "items": 0, "item_failed": 0, "dates_with_items": 0}

    def throttle() -> bool:
        nonlocal requests
        if args.limit and requests >= args.limit:
            return False
        if requests:
            time.sleep(args.delay)
        requests += 1
        return True

    with SEARCH_OUTPUT.open("a", encoding="utf-8") as search_out, ITEM_OUTPUT.open("a", encoding="utf-8") as item_out:
        for date, show_ids in targets.items():
            key = f"advancedsearch:collection=GratefulDead;date={date}"
            record = searches.get(key)
            if record is None:
                if not throttle():
                    print(f"request limit reached after {requests} requests; rerun to continue")
                    break
                record = fetch_search(date, args.retries, args.delay)
                search_out.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                search_out.flush()
                if "response" in record["raw_payload"]:
                    searches[key] = record
                    stats["searches"] += 1
                else:
                    stats["search_failed"] += 1
                    print(f"search failed\t{date}\t{record['raw_payload'].get('error', '')}")
                    continue
            found = {doc["identifier"] for doc in record["raw_payload"]["response"].get("docs", [])}
            found |= {identifier for show_id in show_ids for identifier in attached.get(show_id, [])}
            if not found:
                continue
            stats["dates_with_items"] += 1
            full = {show_id: False for show_id in show_ids}
            fetched = 0
            for identifier in sorted(found, key=ia_tracks.representative_rank):
                item = items.get(identifier)
                if item is None:
                    if fetched >= args.per_date:
                        break
                    if not throttle():
                        print(f"request limit reached after {requests} requests; rerun to continue")
                        print(stats)
                        return 0
                    item = fetch_item(identifier, args.retries, args.delay)
                    fetched += 1
                    item_out.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                    item_out.flush()
                    if "files" in item["raw_payload"]:
                        items[identifier] = item
                        stats["items"] += 1
                    else:
                        stats["item_failed"] += 1
                        print(f"item failed\t{date}\t{identifier}\t{item['raw_payload'].get('error', '')}")
                        continue
                for show_id in show_ids:
                    if full[show_id]:
                        continue
                    status, *_ = ia_tracks.evaluate_item(item, performances.get(show_id, []), songs, catalog_keys)
                    full[show_id] = status == "accepted_full"
                if date_counts[date] == 1 and all(full.values()):
                    break
    print(f"{requests} requests: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
