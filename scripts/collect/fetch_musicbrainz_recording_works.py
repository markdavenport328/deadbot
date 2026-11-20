#!/usr/bin/env python3
"""Collect MusicBrainz work credits through Grateful Dead recordings.

The title-only work search in `fetch_musicbrainz_song_works.py` cannot tell
apart unrelated works that share a title ("Eyes of the World" matches thirteen
works, only one of them the Garcia/Hunter song). This pass resolves that for
the songs still without a canonical credit: it searches MusicBrainz recordings
credited to the Grateful Dead with the song's exact title, looks up a few of
them with their work relationships (`inc=work-rels+work-level-rels+artist-rels`)
and records the work each recording is linked to, with that work's composer,
lyricist and writer credits. A work that the band's own recording links to is
the work the band played, whatever else shares the title.

Output: `data/raw/songs/musicbrainz-recording-works-catalog.jsonl`, one record
per song. Retry-safe: a song with a 200 search is not requested again; progress
is written after every song. Requests are serial, one per 1.1 seconds, with
the registry's 30 second back-off on a 503.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[2]
SONGS = ROOT / "data" / "canonical" / "songs.csv"
WRITERS = ROOT / "data" / "canonical" / "song_writers.csv"
OUTPUT = ROOT / "data" / "raw" / "songs" / "musicbrainz-recording-works-catalog.jsonl"
USER_AGENT = "song-credit-research/0.1 (local catalog collection)"
GRATEFUL_DEAD_ARTIST_ID = "6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6"
MIN_INTERVAL_SECONDS = 1.1
RETRY_AFTER_SECONDS = 30
MAX_ATTEMPTS = 4
# Stop after this many recordings with a work link (agreement is what matters),
# and never look up more than this many recordings for one song.
LINKED_RECORDINGS_WANTED = 3
LOOKUPS_PER_SONG = 12

_last_request = 0.0


def title_key(value: str) -> str:
    value = value.casefold().replace("&", "and").replace("’", "'")
    value = value.replace("feelin'", "feeling").replace("goin'", "going")
    return re.sub(r"[^a-z0-9]+", "", value)


def get_json(url: str) -> tuple[int, dict]:
    global _last_request
    error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        result = subprocess.run(
            ["curl", "-L", "--fail", "--silent", "--show-error", "--max-time", "20", "-A", USER_AGENT, url],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                return 200, json.loads(result.stdout)
            except json.JSONDecodeError:
                error = "invalid json"
        else:
            error = result.stderr.strip()
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_AFTER_SECONDS if "503" in error else MIN_INTERVAL_SECONDS)
    return 0, {"error": error}


def summarize_work(work: dict) -> dict:
    credits = []
    for relation in work.get("relations", []):
        if relation.get("type") not in {"composer", "lyricist", "writer"}:
            continue
        artist = relation.get("artist", {})
        if artist.get("name"):
            credits.append({"role": relation["type"], "artist_id": artist.get("id", ""), "name": artist["name"]})
    return {
        "work_id": work.get("id", ""),
        "title": work.get("title", ""),
        "work_url": f"https://musicbrainz.org/work/{work.get('id', '')}",
        "iswcs": work.get("iswcs", []),
        "credits": credits,
    }


def collect_song(song: dict[str, str]) -> dict:
    title = song["title"]
    query = f'recording:"{title}" AND arid:{GRATEFUL_DEAD_ARTIST_ID}'
    search_url = "https://musicbrainz.org/ws/2/recording?" + urlencode({"query": query, "fmt": "json", "limit": "100"})
    status, payload = get_json(search_url)
    record = {
        "song_id": song["song_id"],
        "canonical_title": title,
        "search_url": search_url,
        "search_status": status,
        "recording_count": payload.get("count", 0) if status == 200 else 0,
        "recordings": [],
    }
    if status != 200:
        record["error"] = payload.get("error", "")
        return record
    wanted = title_key(title)
    exact = [r for r in payload.get("recordings", []) if title_key(r.get("title", "")) == wanted]
    linked = 0
    for recording in exact[:LOOKUPS_PER_SONG]:
        if linked >= LINKED_RECORDINGS_WANTED:
            break
        url = (
            f"https://musicbrainz.org/ws/2/recording/{recording['id']}?"
            + urlencode({"inc": "work-rels+work-level-rels+artist-rels", "fmt": "json"}, safe="+")
        )
        status, detail = get_json(url)
        entry = {
            "recording_id": recording["id"],
            "recording_url": f"https://musicbrainz.org/recording/{recording['id']}",
            "title": recording.get("title", ""),
            "disambiguation": recording.get("disambiguation", ""),
            "lookup_status": status,
            "works": [],
        }
        if status == 200:
            for relation in detail.get("relations", []):
                if relation.get("work"):
                    entry["works"].append(summarize_work(relation["work"]))
            if entry["works"]:
                linked += 1
        else:
            entry["error"] = detail.get("error", "")
        record["recordings"].append(entry)
    return record


def load_done() -> dict[str, dict]:
    if not OUTPUT.exists():
        return {}
    done = {}
    for line in OUTPUT.read_text(encoding="utf-8").splitlines():
        if line:
            row = json.loads(line)
            done[row["raw_payload"]["song_id"]] = row
    return done


def main() -> None:
    with SONGS.open(newline="", encoding="utf-8") as handle:
        songs = list(csv.DictReader(handle))
    with WRITERS.open(newline="", encoding="utf-8") as handle:
        credited = {row["song_id"] for row in csv.DictReader(handle)}
    todo = [s for s in songs if s["song_id"] not in credited and not s["title"].startswith("unidentified-")]
    done = load_done()
    for song in todo:
        previous = done.get(song["song_id"])
        if previous and previous["raw_payload"]["search_status"] == 200:
            continue
        payload = collect_song(song)
        done[song["song_id"]] = {
            "source": "musicbrainz",
            "source_record_id": f"recording-works:{song['song_id']}",
            "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_url": payload["search_url"],
            "raw_payload": payload,
        }
        ordered = sorted(done.values(), key=lambda row: row["raw_payload"]["song_id"])
        OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered), encoding="utf-8")
        linked = sum(1 for r in payload["recordings"] if r["works"])
        print(f"{song['title']}: {payload['recording_count']} recordings, {linked} linked", flush=True)


if __name__ == "__main__":
    main()
