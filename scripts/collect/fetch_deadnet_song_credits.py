#!/usr/bin/env python3
"""Collect concise writer-credit metadata from Dead.net song pages."""

from __future__ import annotations

import concurrent.futures
import csv
import html
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SONGS = ROOT / "data" / "canonical" / "songs.csv"
OUTPUT = ROOT / "data" / "raw" / "songs" / "deadnet-song-credits-1972.jsonl"


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


def main() -> None:
    with SONGS.open(newline="", encoding="utf-8") as handle:
        songs = list(csv.DictReader(handle))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(fetch_song, songs))
    records.sort(key=lambda record: record["raw_payload"]["song_id"])
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    successful = sum(record["raw_payload"]["attempts"][-1]["status"] == 200 for record in records)
    credited = sum(record["raw_payload"]["has_credits"] for record in records)
    print(f"Preserved {len(records)} song records; {successful} pages resolved and {credited} contain credits.")


if __name__ == "__main__":
    main()
