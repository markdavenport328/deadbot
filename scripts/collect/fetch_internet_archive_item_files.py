#!/usr/bin/env python3
"""Preserve the audio file list of Internet Archive items, compactly.

Two jobs use it:

``--linked``
    every item a ``performance_links.csv`` archive track link plays, so the
    stored length of each link can be checked against the file the URL plays;

``--gaps``
    the other ``recordings.csv`` items of shows that still have a song with
    no track link, in representative order (soundboard, then audience, then
    identifier), so ``normalize_internet_archive_gap_tracks.py`` can look for
    the missing songs on another tape of the same show.

It requests ``https://archive.org/metadata/<identifier>/files`` (the file
list only: no reviews, no item description), one request per second, with
retries.  Each full response is cached under ``--cache-dir`` (outside git) so
a rerun never refetches, and a compact record is appended to
``data/raw/recordings/internet-archive-item-files.jsonl`` holding, for the
audio files only (the lossless originals and the MP3 derivatives), the fields
the normalizers read: name, source, format, original, track, title, length.
Records keep the shape of the other preserved item metadata
(``raw_payload.files``), so the same normalizers read them.  A failed fetch is
recorded as a failure, never as an empty item, and is retried on the next run.
No audio is retrieved.
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
OUTPUT = RAW / "internet-archive-item-files.jsonl"
USER_AGENT = "archive-item-file-list/0.1"
KEPT_FILE_FIELDS = ("name", "source", "format", "original", "track", "title", "length")


def is_audio_file(file_record: dict) -> bool:
    """A lossless original or an MP3 derivative: the files a track link can name."""

    format_name = (file_record.get("format") or "").casefold()
    if "mp3" in format_name:
        return True
    return file_record.get("source") == "original" and any(
        part in format_name for part in ia_tracks.AUDIO_FORMAT_PRIORITY
    )


def compact_files(files: list[dict]) -> list[dict]:
    return [
        {field: file_record[field] for field in KEPT_FILE_FIELDS if file_record.get(field) not in (None, "")}
        for file_record in files
        if is_audio_file(file_record)
    ]


def cache_path(cache_dir: Path, identifier: str) -> Path:
    return cache_dir / f"{urllib.parse.quote(identifier, safe='')}.json"


def fetch(identifier: str, cache_dir: Path, retries: int, delay: float) -> tuple[dict, bool]:
    """Return (record, requested).  A cached response is reused without a request."""

    url = f"https://archive.org/metadata/{identifier}/files"
    cached = cache_path(cache_dir, identifier)
    if cached.exists():
        saved = json.loads(cached.read_text(encoding="utf-8"))
        return compact_record(identifier, url, saved["retrieved_at"], saved["response"]), False
    error = ""
    response_payload: dict = {}
    for attempt in range(retries):
        if attempt:
            time.sleep(delay * (2**attempt))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            if isinstance(response_payload.get("result"), list) and response_payload["result"]:
                break
            error = "response has no files"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = str(exc)
        response_payload = {}
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not response_payload:
        return (
            {
                "source": "internet-archive",
                "source_record_id": identifier,
                "retrieved_at": retrieved_at,
                "source_url": url,
                "raw_payload": {"http_status": 0, "error": error},
            },
            True,
        )
    cached.write_text(json.dumps({"retrieved_at": retrieved_at, "response": response_payload}), encoding="utf-8")
    return compact_record(identifier, url, retrieved_at, response_payload), True


def compact_record(identifier: str, url: str, retrieved_at: str, response_payload: dict) -> dict:
    files = response_payload.get("result") or []
    return {
        "source": "internet-archive",
        "source_record_id": identifier,
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": {"files": compact_files(files)},
        "kept": {"files": "lossless originals and MP3 derivatives", "file_fields": list(KEPT_FILE_FIELDS)},
        "source_file_count": len(files),
    }


def linked_identifiers() -> list[str]:
    identifiers: set[str] = set()
    with (CANONICAL / "performance_links.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["platform"] == "archive" and "/download/" in row["url"]:
                identifiers.add(row["url"].split("/download/")[1].split("/", 1)[0])
    return sorted(identifiers)


def gap_identifiers(per_show: int, soundboards_only: bool) -> list[str]:
    """Other tapes of shows that still have an unlinked song, best candidates first per show."""

    with (CANONICAL / "performances.csv").open(newline="", encoding="utf-8") as handle:
        performances = list(csv.DictReader(handle))
    linked: set[str] = set()
    with (CANONICAL / "performance_links.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["platform"] == "archive" and row["link_type"] == "recording-track":
                linked.add(row["performance_id"])
    gap_shows = {row["show_id"] for row in performances if row["performance_id"] not in linked}
    preserved = preserved_identifiers()
    by_show: dict[str, list[str]] = defaultdict(list)
    with (CANONICAL / "recordings.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            identifier = row["archive_identifier"]
            if row["show_id"] in gap_shows and identifier and identifier not in preserved:
                if soundboards_only and "sbd" not in identifier.casefold():
                    continue
                by_show[row["show_id"]].append(identifier)
    ordered: list[str] = []
    for show_id in sorted(by_show):
        candidates = sorted(by_show[show_id], key=ia_tracks.representative_rank)
        ordered.extend(candidates[:per_show] if per_show else candidates)
    return ordered


def preserved_identifiers() -> set[str]:
    """Items whose full metadata an earlier collector already preserved."""

    preserved: set[str] = set()
    paths = sorted(RAW.glob("internet-archive-*-representatives.jsonl")) + [ia_tracks.ALTERNATES_PATH]
    for path in paths:
        for record in ia_tracks.read_item_records(path):
            if "files" in record.get("raw_payload", {}):
                preserved.add(record["source_record_id"])
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache-dir", type=Path, required=True, help="directory outside git for full responses")
    parser.add_argument("--linked", action="store_true", help="fetch every item a track link plays")
    parser.add_argument("--gaps", action="store_true", help="fetch other tapes of shows with an unlinked song")
    parser.add_argument("--per-show", type=int, default=0, help="most gap items to fetch for one show (0 = all)")
    parser.add_argument("--soundboards-only", action="store_true", help="gap items whose identifier says sbd")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="compact JSONL to append to")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many requests (0 = no limit)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if not args.linked and not args.gaps:
        parser.error("choose --linked, --gaps or both")
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    targets: list[str] = []
    if args.gaps:
        targets += gap_identifiers(args.per_show, args.soundboards_only)
    if args.linked:
        targets += linked_identifiers()
    targets = list(dict.fromkeys(targets))

    existing = {record["source_record_id"]: record for record in ia_tracks.read_item_records(args.output)}
    done = {identifier for identifier, record in existing.items() if "files" in record["raw_payload"]}
    if len(done) != len(existing):
        # Drop failed fetches so they are retried below.
        args.output.write_text(
            "".join(
                json.dumps(existing[identifier], ensure_ascii=False, separators=(",", ":")) + "\n"
                for identifier in existing
                if identifier in done
            ),
            encoding="utf-8",
        )

    requests = fetched = failed = 0
    last_request = 0.0
    with args.output.open("a", encoding="utf-8") as output:
        for identifier in targets:
            if identifier in done:
                continue
            if args.limit and requests >= args.limit:
                print(f"request limit reached after {requests} requests; rerun to continue")
                break
            if not cache_path(args.cache_dir, identifier).exists():
                # At most one request per ``delay`` seconds, start to start.
                time.sleep(max(0.0, last_request + args.delay - time.monotonic()))
                last_request = time.monotonic()
            record, requested = fetch(identifier, args.cache_dir, args.retries, args.delay)
            requests += requested
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            output.flush()
            if "files" in record["raw_payload"]:
                fetched += 1
                done.add(identifier)
            else:
                failed += 1
                print(f"failed\t{identifier}\t{record['raw_payload'].get('error', '')}", flush=True)
            if (fetched + failed) % 100 == 0:
                print(f"{fetched + failed} of {len(targets)} done", flush=True)
    print(f"{len(targets)} targets; {requests} requests; preserved {fetched}, failed {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
