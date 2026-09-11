#!/usr/bin/env python3
"""Collect concise MusicBrainz work-credit metadata for the song catalog.

Runs catalog-wide by default: every canonical song not already covered by an
existing `data/raw/songs/musicbrainz-song-works-*.jsonl` record (from any
prior year-scoped or catalog run) is queried against MusicBrainz's
`/ws/2/work` search and appended to a new run-specific output file,
`musicbrainz-song-works-catalog.jsonl`. Pass `--year YEAR` to reproduce the
original year-scoped behavior instead.

Retry-safe per docs/collection-methodology.md: requests are spaced at the
MusicBrainz rate policy (one request per second, per
`data/source_registry.json`'s `musicbrainz-api` entry), progress is flushed
to a `.partial` file after every song so an interrupted run can resume, and a
prior HTTP 200 response is never overwritten by a later failure.
"""

from __future__ import annotations

import csv
import argparse
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[2]
SONGS = ROOT / "data" / "canonical" / "songs.csv"
PERFORMANCES = ROOT / "data" / "canonical" / "performances.csv"
SHOWS = ROOT / "data" / "canonical" / "shows.csv"
RAW_DIR = ROOT / "data" / "raw" / "songs"
FILE_PREFIX = "musicbrainz-song-works"
USER_AGENT = "DeadBot/0.1 (local song collection; contact unavailable)"
# min_interval_seconds: 1 in data/source_registry.json's musicbrainz-api
# rate_policy; 1.1s of headroom keeps a sustained run under the limit.
MIN_INTERVAL_SECONDS = 1.1
# retry_after_seconds: 30 in the same rate_policy entry, honored on a 503.
RETRY_AFTER_SECONDS = 30
MAX_ATTEMPTS = 3


def title_key(value: str) -> str:
    value = value.casefold().replace("&", "and")
    value = value.replace("feelin'", "feeling").replace("goin'", "going")
    return re.sub(r"[^a-z0-9]+", "", value)


def summarize_work(work: dict) -> dict:
    credits = []
    for relation in work.get("relations", []):
        if relation.get("type") not in {"composer", "lyricist", "writer"}:
            continue
        artist = relation.get("artist", {})
        if artist.get("name"):
            credits.append(
                {
                    "role": relation["type"],
                    "artist_id": artist.get("id", ""),
                    "name": artist["name"],
                }
            )
    return {
        "work_id": work.get("id", ""),
        "title": work.get("title", ""),
        "score": work.get("score", 0),
        "iswcs": work.get("iswcs", []),
        "credits": credits,
    }


def fetch(title: str) -> tuple[int, dict]:
    """Query MusicBrainz for a work title, retrying a transient failure.

    A 503 (rate-limited) response backs off for `RETRY_AFTER_SECONDS`, the
    registry's `retry_after_seconds` for this source, before retrying; a
    timeout retries immediately once. Up to `MAX_ATTEMPTS` are made before
    the failure is recorded as-is.
    """
    query = f'work:"{title}"'
    url = "https://musicbrainz.org/ws/2/work/?" + urlencode(
        {"query": query, "fmt": "json", "limit": "10"}
    )
    error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = subprocess.run(
            [
                "curl",
                "-L",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "10",
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return 200, {"query": query, "url": url, "response": json.loads(result.stdout)}
        error = result.stderr.strip()
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_AFTER_SECONDS if "503" in error else MIN_INTERVAL_SECONDS)
    return 0, {"query": query, "url": url, "error": error}


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

    Scans every `musicbrainz-song-works-*.jsonl` file (year-scoped or
    catalog), excluding in-progress `.partial` files. A song is "covered"
    once any attempt (success or failure) has been recorded for it; failures
    are preserved as evidence rather than re-requested silently.
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
    return [songs[song_id] for song_id in sorted(songs) if song_id not in covered]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="limit collection to one show year's song set (legacy mode); "
        "default is catalog-wide over songs not yet covered by any raw record",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="re-fetch only the non-200 entries already recorded in the catalog "
        "output file, in place, instead of collecting newly-uncovered songs",
    )
    args = parser.parse_args()

    if args.retry_errors:
        songs_by_id = read_songs()
        output = RAW_DIR / f"{FILE_PREFIX}-catalog.jsonl"
        label = "catalog retry"
        prior = {
            json.loads(line)["raw_payload"]["song_id"]: json.loads(line)
            for line in output.read_text(encoding="utf-8").splitlines()
            if line
        }
        records = [record for record in prior.values() if record["raw_payload"].get("http_status") == 200]
        pending = [
            songs_by_id[song_id]
            for song_id, record in prior.items()
            if record["raw_payload"].get("http_status") != 200
        ]
        pending.sort(key=lambda song: song["song_id"])
        songs = list(prior.values())  # for the final "Preserved N of M" print only
        partial = output.with_name(output.name + ".retry.partial")
    else:
        if args.year is not None:
            songs = songs_for_year(args.year)
            output = RAW_DIR / f"{FILE_PREFIX}-{args.year}.jsonl"
            label = str(args.year)
        else:
            songs = songs_for_catalog()
            output = RAW_DIR / f"{FILE_PREFIX}-catalog.jsonl"
            label = "catalog"

        partial = output.with_name(output.name + ".partial")
        existing = {}
        prior_paths = [path for path in (output, partial) if path.exists()]
        for prior_path in prior_paths:
            for line in prior_path.read_text(encoding="utf-8").splitlines():
                if line:
                    record = json.loads(line)
                    if record["raw_payload"].get("http_status") == 200:
                        existing[record["raw_payload"]["song_id"]] = record
        records = [existing[song["song_id"]] for song in songs if song["song_id"] in existing]
        pending = [song for song in songs if song["song_id"] not in existing]
    for index, song in enumerate(pending):
        if index:
            time.sleep(MIN_INTERVAL_SECONDS)
        status, result = fetch(song["title"])
        response = result.get("response", {})
        works = [summarize_work(work) for work in response.get("works", [])]
        exact = [work for work in works if title_key(work["title"]) == title_key(song["title"])]
        records.append(
            record := {
                "source": "musicbrainz",
                "source_record_id": f"work-search:{song['song_id']}",
                "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "source_url": result.get("url", ""),
                "raw_payload": {
                    "song_id": song["song_id"],
                    "canonical_title": song["title"],
                    "http_status": status,
                    "query": result.get("query", ""),
                    "work_count": response.get("count", 0),
                    "exact_title_matches": exact,
                    "top_works": works,
                    "error": result.get("error", ""),
                },
            }
        )
        with partial.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{len(records)}/{len(songs)} {song['title']}: {len(exact)} exact work(s)")

    records.sort(key=lambda record: record["raw_payload"]["song_id"])
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    partial.unlink(missing_ok=True)
    print(f"Preserved {len(records)} MusicBrainz {label} song-work records at {output}.")


if __name__ == "__main__":
    main()
