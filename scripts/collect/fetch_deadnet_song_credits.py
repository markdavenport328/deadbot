#!/usr/bin/env python3
"""Collect concise writer-credit metadata from Dead.net song pages.

Runs catalog-wide by default: every canonical song not already covered by an
existing `data/raw/songs/deadnet-song-credits-*.jsonl` record (from any prior
year-scoped or catalog run) is fetched and appended to a new run-specific
output file, `deadnet-song-credits-catalog.jsonl`. Pass `--year YEAR` to
reproduce the original year-scoped behavior instead.

Retry-safe per docs/collection-methodology.md: requests are made serially at
the Dead.net editorial rate policy (one request per six seconds, per
`data/source_registry.json`'s `deadnet-editorial` entry, requests_per_minute:
10), progress is flushed to a `.partial` file after every song so an
interrupted run can resume, and a prior successful fetch is never
overwritten by a later failure.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SONGS = ROOT / "data" / "canonical" / "songs.csv"
PERFORMANCES = ROOT / "data" / "canonical" / "performances.csv"
SHOWS = ROOT / "data" / "canonical" / "shows.csv"
RAW_DIR = ROOT / "data" / "raw" / "songs"
FILE_PREFIX = "deadnet-song-credits"
# requests_per_minute: 10 in data/source_registry.json's deadnet-editorial
# rate_policy averages to one request per six seconds for a sustained run.
MIN_INTERVAL_SECONDS = 6.0


def candidates(slug: str) -> list[str]:
    values = [slug]
    for old, new in (
        ("don-t-", "dont-"),
        ("it-s-", "its-"),
        ("he-s-", "hes-"),
        ("uncle-john-s-", "uncle-johns-"),
    ):
        if old in slug:
            values.append(slug.replace(old, new))
    return list(dict.fromkeys(values))


def strip_markup(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def extract_names(page: str, field: str) -> list[str]:
    section = re.search(
        rf'field--name-field-{field}[^>]*>(.*?)(?=field--name-field-|</article>)',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return []
    names = re.findall(r'<div class="field__item">(.*?)</div>', section.group(1), flags=re.DOTALL)
    return [name for name in (strip_markup(item) for item in names) if name]


def fetch_song(song: dict[str, str]) -> dict:
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    attempts = []
    for slug in candidates(song["slug"]):
        url = f"https://www.dead.net/song/{slug}"
        result = subprocess.run(
            [
                "curl",
                "-L",
                "--silent",
                "--show-error",
                "--max-time",
                "30",
                "--write-out",
                "\n__STATUS__%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
        )
        output = result.stdout
        body, marker, status_text = output.rpartition("\n__STATUS__")
        status = int(status_text) if marker and status_text.isdigit() else 0
        attempts.append({"slug": slug, "url": url, "status": status})
        if status != 200:
            continue
        title_match = re.search(r"<title>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        payload = {
            "song_id": song["song_id"],
            "canonical_title": song["title"],
            "canonical_slug": song["slug"],
            "resolved_slug": slug,
            "page_title": strip_markup(title_match.group(1)) if title_match else "",
            "lyrics_by": extract_names(body, "lyrics-by"),
            "music_by": extract_names(body, "music-by"),
            "has_lyrics": bool(re.search(r"field--name-field-lyrics\b", body, flags=re.IGNORECASE)),
            "has_credits": bool(extract_names(body, "lyrics-by") or extract_names(body, "music-by")),
            "attempts": attempts,
        }
        return {
            "source": "deadnet",
            "source_record_id": f"song-page:{song['song_id']}",
            "retrieved_at": retrieved_at,
            "source_url": url,
            "raw_payload": payload,
        }

    return {
        "source": "deadnet",
        "source_record_id": f"song-page:{song['song_id']}",
        "retrieved_at": retrieved_at,
        "source_url": f"https://www.dead.net/song/{song['slug']}",
        "raw_payload": {
            "song_id": song["song_id"],
            "canonical_title": song["title"],
            "canonical_slug": song["slug"],
            "page_title": "",
            "lyrics_by": [],
            "music_by": [],
            "has_lyrics": False,
            "has_credits": False,
            "attempts": attempts,
        },
    }


def read_songs() -> dict[str, dict[str, str]]:
    with SONGS.open(newline="", encoding="utf-8") as handle:
        return {row["song_id"]: row for row in csv.DictReader(handle)}


def songs_for_year(year: int) -> list[dict[str, str]]:
    songs = read_songs()
    with SHOWS.open(newline="", encoding="utf-8") as handle:
        show_ids = {
            row["show_id"] for row in csv.DictReader(handle) if row["show_date"].startswith(f"{year}-")
        }
    with PERFORMANCES.open(newline="", encoding="utf-8") as handle:
        song_ids = {row["song_id"] for row in csv.DictReader(handle) if row["show_id"] in show_ids}
    return [songs[song_id] for song_id in sorted(song_ids)]


def already_covered_song_ids() -> set[str]:
    """Song ids present in any existing raw record from a prior run.

    Scans every `deadnet-song-credits-*.jsonl` file (year-scoped or catalog),
    excluding in-progress `.partial` files. A song is "covered" once any
    attempt (success or failure) has been recorded for it; failures are
    preserved as evidence rather than re-requested silently, per
    docs/collection-methodology.md.
    """
    covered: set[str] = set()
    for path in RAW_DIR.glob(f"{FILE_PREFIX}-*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            covered.add(record["raw_payload"]["song_id"])
    return covered


def songs_for_catalog() -> list[dict[str, str]]:
    songs = read_songs()
    covered = already_covered_song_ids()
    pending = [songs[song_id] for song_id in sorted(songs) if song_id not in covered]
    return pending


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="limit collection to one show year's song set (legacy mode); "
        "default is catalog-wide over songs not yet covered by any raw record",
    )
    args = parser.parse_args()

    if args.year is not None:
        songs = songs_for_year(args.year)
        output = RAW_DIR / f"{FILE_PREFIX}-{args.year}.jsonl"
    else:
        songs = songs_for_catalog()
        output = RAW_DIR / f"{FILE_PREFIX}-catalog.jsonl"

    partial = output.with_name(output.name + ".partial")
    existing: dict[str, dict] = {}
    for prior_path in (path for path in (output, partial) if path.exists()):
        for line in prior_path.read_text(encoding="utf-8").splitlines():
            if line:
                record = json.loads(line)
                existing[record["raw_payload"]["song_id"]] = record

    records = [existing[song["song_id"]] for song in songs if song["song_id"] in existing]
    pending = [song for song in songs if song["song_id"] not in existing]

    for index, song in enumerate(pending):
        if index:
            time.sleep(MIN_INTERVAL_SECONDS)
        record = fetch_song(song)
        records.append(record)
        with partial.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        status = record["raw_payload"]["attempts"][-1]["status"] if record["raw_payload"]["attempts"] else 0
        print(f"{len(records)}/{len(songs)} {song['title']}: HTTP {status}")

    records.sort(key=lambda record: record["raw_payload"]["song_id"])
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    partial.unlink(missing_ok=True)

    successful = sum(record["raw_payload"]["attempts"][-1]["status"] == 200 for record in records)
    credited = sum(record["raw_payload"]["has_credits"] for record in records)
    label = args.year if args.year is not None else "catalog"
    print(
        f"Preserved {len(records)} {label} song records at {output}; "
        f"{successful} pages resolved and {credited} contain credits."
    )


if __name__ == "__main__":
    main()
