#!/usr/bin/env python3
"""Preserve item metadata for further recordings of shows that still lack full track links.

`fetch_internet_archive_representatives.py` preserves one representative item
per show.  When `normalize_internet_archive_tracks.py` cannot align every
canonical performance of a show to that item (its fallback pass records this
in `internet-archive-track-mapping-review.jsonl`), this collector fetches
public item metadata (https://archive.org/metadata/<identifier>) for the
show's other `recordings.csv` items, in the same representative order
(soundboard, then audience, then identifier), and appends each response to
`data/raw/recordings/internet-archive-alternate-items.jsonl`.

It stops for a show as soon as a fetched item aligns every canonical
performance, and never fetches more than ``--per-show`` items for one show.
Requests are sequential with a delay and retries.  The output is appended one
record at a time, so an interrupted run resumes where it stopped; records
whose fetch failed are retried on the next run.  No audio is retrieved.

To keep the file a manageable size the per-item ``reviews`` (user comments)
and server-location fields are omitted; every other field of the response
is preserved as returned.

Run order: normalize_internet_archive_tracks.py, this collector, then
normalize_internet_archive_tracks.py and normalize_internet_archive_track_links.py again.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
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
OUTPUT = ia_tracks.ALTERNATES_PATH
USER_AGENT = "Deadbot/0.1 (historical-show-context)"
OMITTED_FIELDS = ("reviews", "alternate_locations", "workable_servers", "d1", "d2", "server", "dir")


def fetch(identifier: str, retries: int, delay: float) -> dict:
    url = f"https://archive.org/metadata/{identifier}"
    error = ""
    for attempt in range(retries):
        if attempt:
            time.sleep(delay * (2**attempt))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if "files" in payload:
                break
            error = "response has no files"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = str(exc)
        payload = {}
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if "files" not in payload:
        payload = {"http_status": 0, "error": error}
    omitted = [field for field in OMITTED_FIELDS if field in payload]
    for field in omitted:
        payload.pop(field)
    record = {
        "source": "internet-archive",
        "source_record_id": identifier,
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": payload,
    }
    if omitted:
        record["omitted_payload_fields"] = omitted
    return record


def target_shows() -> set[str]:
    """Shows the fallback pass mapped only partly or not at all."""

    if not ia_tracks.REVIEW_PATH.exists():
        raise SystemExit("run normalize_internet_archive_tracks.py first")
    by_show: dict[str, list[dict]] = defaultdict(list)
    for record in ia_tracks.read_item_records(ia_tracks.REVIEW_PATH):
        if record.get("pass") == "fallback":
            by_show[record["show_id"]].append(record)
    return {
        show_id
        for show_id, records in by_show.items()
        if not any(record["chosen_for_show"] and record["status"] == "accepted_full" for record in records)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-show", type=int, default=3, help="most alternate items to fetch for one show")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many requests (0 = no limit)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    songs, recordings_by_identifier, performances, _ = ia_tracks.load_rows()
    catalog_keys: set[str] = set()
    for title in songs.values():
        catalog_keys |= ia_tracks.title_keys(title)

    cached: dict[str, dict] = {}
    for path in sorted(RAW.glob("internet-archive-*-representatives.jsonl")):
        for record in ia_tracks.read_item_records(path):
            cached.setdefault(record["source_record_id"], record)
    alternates = {record["source_record_id"]: record for record in ia_tracks.read_item_records(OUTPUT)}
    failed = {identifier for identifier, record in alternates.items() if "files" not in record["raw_payload"]}
    if failed:
        # Drop failed fetches so they are retried below.
        alternates = {identifier: record for identifier, record in alternates.items() if identifier not in failed}
        OUTPUT.write_text(
            "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in alternates.values()),
            encoding="utf-8",
        )

    by_show: dict[str, list[str]] = defaultdict(list)
    with (CANONICAL / "recordings.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["archive_identifier"]:
                by_show[row["show_id"]].append(row["archive_identifier"])

    requests = 0
    fetched_ok = fetched_failed = full_shows = 0
    with OUTPUT.open("a", encoding="utf-8") as output:
        for show_id in sorted(target_shows()):
            show_performances = performances.get(show_id, [])
            ordered = sorted(
                (identifier for identifier in by_show.get(show_id, []) if identifier not in cached),
                key=ia_tracks.representative_rank,
            )[: args.per_show]
            for identifier in ordered:
                record = alternates.get(identifier)
                if record is None:
                    if args.limit and requests >= args.limit:
                        print(f"request limit reached after {requests} requests; rerun to continue")
                        print(f"fetched {fetched_ok}, failed {fetched_failed}, shows now fully aligned {full_shows}")
                        return 0
                    if requests:
                        time.sleep(args.delay)
                    record = fetch(identifier, args.retries, args.delay)
                    requests += 1
                    output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                    output.flush()
                    alternates[identifier] = record
                    if "files" in record["raw_payload"]:
                        fetched_ok += 1
                    else:
                        fetched_failed += 1
                        print(f"failed\t{show_id}\t{identifier}\t{record['raw_payload'].get('error', '')}")
                status, *_ = ia_tracks.evaluate_item(record, show_performances, songs, catalog_keys)
                if status == "accepted_full":
                    full_shows += 1
                    break
    print(f"{requests} requests: fetched {fetched_ok}, failed {fetched_failed}; shows now fully aligned {full_shows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
