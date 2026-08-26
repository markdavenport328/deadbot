#!/usr/bin/env python3
"""Collect concise MusicBrainz work-credit metadata for the 1972 song set."""

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
USER_AGENT = "DeadBot/0.1 (local song collection; contact unavailable)"


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
    query = f'work:"{title}"'
    url = "https://musicbrainz.org/ws/2/work/?" + urlencode(
        {"query": query, "fmt": "json", "limit": "10"}
    )
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
    if result.returncode != 0:
        return 0, {"query": query, "url": url, "error": result.stderr.strip()}
    return 200, {"query": query, "url": url, "response": json.loads(result.stdout)}


def songs_for_year(year: int) -> list[dict[str, str]]:
    with SONGS.open(newline="", encoding="utf-8") as handle:
        songs = {row["song_id"]: row for row in csv.DictReader(handle)}
    with SHOWS.open(newline="", encoding="utf-8") as handle:
        show_ids = {
            row["show_id"] for row in csv.DictReader(handle) if row["show_date"].startswith(f"{year}-")
        }
    with PERFORMANCES.open(newline="", encoding="utf-8") as handle:
        song_ids = {row["song_id"] for row in csv.DictReader(handle) if row["show_id"] in show_ids}
    return [songs[song_id] for song_id in sorted(song_ids)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, help="show year whose song labels should be enriched")
    args = parser.parse_args()
    songs = songs_for_year(args.year)
    output = ROOT / "data" / "raw" / "songs" / f"musicbrainz-song-works-{args.year}.jsonl"
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
            time.sleep(1.1)
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
    print(f"Preserved {len(records)} MusicBrainz song-work records at {output}.")


if __name__ == "__main__":
    main()
