#!/usr/bin/env python3
"""Collect compact MusicBrainz metadata for the Grateful Dead's official live albums.

The collector follows the same conventions as ``fetch_musicbrainz_song_works.py``:
one request per second, a descriptive User-Agent, compact JSONL raw records,
and a checkpoint that lets an interrupted run resume without repeating
completed requests.

Requests, in order:

1. Artist search to resolve the artist MBID (never trusted from memory).
2. Release-group browse for the artist filtered to primary type Album and
   secondary type Live.  Every release group is preserved, including groups
   whose only releases are bootlegs, so the normalizer can report them.
3. Release browse for the artist filtered to official Album+Live releases with
   ``inc=recordings+url-rels+release-groups+recording-level-rels``.  This
   returns every official release in the enumerated groups with its track list
   and URL relationships (Spotify links appear as ``streaming`` /
   ``free streaming`` URL relationships when MusicBrainz has them).  Browsing
   by artist covers the whole catalog in a few dozen paged requests instead of
   one lookup per release group; the normalizer chooses one release per group.

Only compact fields are kept: MBIDs, titles, dates, disambiguations, statuses,
track titles and lengths, recording disambiguations (which carry the
``live, YYYY-MM-DD: venue`` performance date when editors supplied it), medium
titles, and URL relationships.  No cover art or annotation text is stored.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "releases"
RELEASE_GROUPS_PATH = RAW_DIR / "musicbrainz-release-groups.jsonl"
RELEASES_PATH = RAW_DIR / "musicbrainz-releases.jsonl"
CHECKPOINT_PATH = RAW_DIR / "musicbrainz-live-releases.checkpoint.json"
API = "https://musicbrainz.org/ws/2/"
USER_AGENT = "DeadBot/0.1 (local official-release collection; contact unavailable)"
REQUEST_INTERVAL_SECONDS = 1.1
RELEASE_INC = "recordings+url-rels+release-groups+recording-level-rels"
RELEASE_GROUP_PAGE_SIZE = 100
RELEASE_PAGE_SIZE = 25
MIN_RELEASE_PAGE_SIZE = 5
MAX_ATTEMPTS = 6


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Client:
    """Paced MusicBrainz JSON client with bounded retries."""

    def __init__(self) -> None:
        self.request_count = 0
        self._last_request_at = 0.0

    def get(self, entity: str, params: dict[str, str]) -> tuple[int, str, dict]:
        query = dict(params)
        query["fmt"] = "json"
        # MusicBrainz expects literal "+" and "|" separators in inc/type values.
        url = API + entity + "?" + urllib.parse.urlencode(query, safe="+|")
        status, payload = 0, {}
        for attempt in range(MAX_ATTEMPTS):
            wait = self._last_request_at + REQUEST_INTERVAL_SECONDS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            self._last_request_at = time.monotonic()
            self.request_count += 1
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    status = response.status
                    payload = json.loads(response.read().decode("utf-8"))
                return status, url, payload
            except urllib.error.HTTPError as error:
                status = error.code
                try:
                    payload = json.loads(error.read().decode("utf-8"))
                except (ValueError, OSError):
                    payload = {"error": str(error)}
                if status not in (429, 503):
                    return status, url, payload
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                status, payload = 0, {"error": str(error)}
            backoff = min(2 ** (attempt + 1), 30)
            print(f"  retry {attempt + 1}/{MAX_ATTEMPTS} after HTTP {status} in {backoff}s", file=sys.stderr)
            time.sleep(backoff)
        return status, url, payload


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {
        "artist": None,
        "release_group_offset": 0,
        "release_group_count": None,
        "release_groups_done": False,
        "release_offset": 0,
        "release_count": None,
        "release_page_size": RELEASE_PAGE_SIZE,
        "releases_done": False,
        "release_requests": 0,
        "request_log": [],
    }


def save_checkpoint(state: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def append_records(path: Path, records: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def finalize(partial: Path, output: Path) -> int:
    records = {record["source_record_id"]: record for record in read_records(partial)}
    ordered = [records[key] for key in sorted(records)]
    with output.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    partial.unlink(missing_ok=True)
    return len(ordered)


def resolve_artist(client: Client, name: str, state: dict) -> dict:
    if state["artist"]:
        return state["artist"]
    status, url, payload = client.get("artist/", {"query": f'artist:"{name}"', "limit": "5"})
    if status != 200:
        raise SystemExit(f"artist search failed with HTTP {status}: {payload}")
    candidates = [
        artist
        for artist in payload.get("artists", [])
        if artist.get("name", "").casefold() == name.casefold() and artist.get("type") == "Group"
    ]
    if not candidates:
        raise SystemExit(f"no Group artist named {name!r} in MusicBrainz search results")
    candidates.sort(key=lambda artist: -int(artist.get("score", 0)))
    top = candidates[0]
    state["artist"] = {
        "id": top["id"],
        "name": top["name"],
        "score": top.get("score"),
        "type": top.get("type"),
        "disambiguation": top.get("disambiguation", ""),
        "search_url": url,
        "retrieved_at": now_iso(),
    }
    state["request_log"].append({"step": "artist-search", "url": url, "http_status": status, "at": now_iso()})
    save_checkpoint(state)
    print(f"Resolved artist {top['name']} -> {top['id']} (score {top.get('score')})")
    return state["artist"]


def compact_release_group(group: dict) -> dict:
    return {
        "id": group.get("id", ""),
        "title": group.get("title", ""),
        "disambiguation": group.get("disambiguation", ""),
        "primary_type": group.get("primary-type", ""),
        "secondary_types": group.get("secondary-types", []),
        "first_release_date": group.get("first-release-date", ""),
    }


def compact_url_relations(entity: dict) -> list[dict]:
    relations = []
    for relation in entity.get("relations", []):
        if relation.get("target-type") != "url":
            continue
        relations.append({"type": relation.get("type", ""), "url": relation.get("url", {}).get("resource", "")})
    return relations


def compact_release(release: dict) -> dict:
    media = []
    for medium in release.get("media", []):
        tracks = []
        for track in medium.get("tracks", []):
            recording = track.get("recording", {})
            tracks.append(
                {
                    "id": track.get("id", ""),
                    "position": track.get("position"),
                    "number": track.get("number", ""),
                    "title": track.get("title", ""),
                    "length_ms": track.get("length"),
                    "recording": {
                        "id": recording.get("id", ""),
                        "title": recording.get("title", ""),
                        "disambiguation": recording.get("disambiguation", ""),
                        "length_ms": recording.get("length"),
                        "url_relations": compact_url_relations(recording),
                    },
                }
            )
        media.append(
            {
                "position": medium.get("position"),
                "format": medium.get("format", ""),
                "title": medium.get("title", ""),
                "track_count": medium.get("track-count"),
                "tracks": tracks,
            }
        )
    return {
        "id": release.get("id", ""),
        "title": release.get("title", ""),
        "disambiguation": release.get("disambiguation", ""),
        "status": release.get("status", ""),
        "date": release.get("date", ""),
        "country": release.get("country", ""),
        "barcode": release.get("barcode", ""),
        "release_group": compact_release_group(release.get("release-group", {})),
        "url_relations": compact_url_relations(release),
        "media": media,
    }


def collect_release_groups(client: Client, artist: dict, state: dict, partial: Path) -> None:
    while not state["release_groups_done"]:
        offset = state["release_group_offset"]
        params = {
            "artist": artist["id"],
            "type": "album|live",
            "limit": str(RELEASE_GROUP_PAGE_SIZE),
            "offset": str(offset),
        }
        status, url, payload = client.get("release-group", params)
        state["request_log"].append({"step": "release-group-browse", "url": url, "http_status": status, "at": now_iso()})
        if status != 200:
            save_checkpoint(state)
            raise SystemExit(f"release-group browse failed at offset {offset} with HTTP {status}: {payload}")
        groups = payload.get("release-groups", [])
        retrieved_at = now_iso()
        append_records(
            partial,
            [
                {
                    "source": "musicbrainz",
                    "source_record_id": group["id"],
                    "retrieved_at": retrieved_at,
                    "source_url": f"https://musicbrainz.org/release-group/{group['id']}",
                    "raw_payload": {
                        "http_status": status,
                        "query": {"entity": "release-group", **params},
                        "browse_offset": offset,
                        "artist_id": artist["id"],
                        "release_group": compact_release_group(group),
                    },
                }
                for group in groups
            ],
        )
        state["release_group_count"] = payload.get("release-group-count", 0)
        state["release_group_offset"] = offset + len(groups)
        if not groups or state["release_group_offset"] >= state["release_group_count"]:
            state["release_groups_done"] = True
        save_checkpoint(state)
        print(f"release groups {state['release_group_offset']}/{state['release_group_count']}")


def collect_releases(client: Client, artist: dict, state: dict, partial: Path, max_requests: int) -> None:
    while not state["releases_done"]:
        if state["release_requests"] >= max_requests:
            print(
                f"Stopping at the release request cap ({max_requests}); "
                f"{state['release_offset']}/{state['release_count']} releases fetched. Rerun to resume."
            )
            return
        offset = state["release_offset"]
        params = {
            "artist": artist["id"],
            "type": "album|live",
            "status": "official",
            "inc": RELEASE_INC,
            "limit": str(state["release_page_size"]),
            "offset": str(offset),
        }
        status, url, payload = client.get("release", params)
        state["release_requests"] += 1
        state["request_log"].append({"step": "release-browse", "url": url, "http_status": status, "at": now_iso()})
        if status != 200:
            if status in (0, 429, 503) and state["release_page_size"] > MIN_RELEASE_PAGE_SIZE:
                # Heavy pages time out on the MusicBrainz side; ask for fewer releases.
                state["release_page_size"] = max(MIN_RELEASE_PAGE_SIZE, state["release_page_size"] // 2)
                save_checkpoint(state)
                print(f"  reducing release page size to {state['release_page_size']} after HTTP {status}")
                continue
            save_checkpoint(state)
            raise SystemExit(f"release browse failed at offset {offset} with HTTP {status}: {payload}")
        releases = payload.get("releases", [])
        retrieved_at = now_iso()
        append_records(
            partial,
            [
                {
                    "source": "musicbrainz",
                    "source_record_id": release["id"],
                    "retrieved_at": retrieved_at,
                    "source_url": f"https://musicbrainz.org/release/{release['id']}",
                    "raw_payload": {
                        "http_status": status,
                        "query": {"entity": "release", **params},
                        "browse_offset": offset,
                        "artist_id": artist["id"],
                        "release": compact_release(release),
                    },
                }
                for release in releases
            ],
        )
        state["release_count"] = payload.get("release-count", 0)
        state["release_offset"] = offset + len(releases)
        if not releases or state["release_offset"] >= state["release_count"]:
            state["releases_done"] = True
        save_checkpoint(state)
        print(f"releases {state['release_offset']}/{state['release_count']} ({len(releases)} in page)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artist-name", default="Grateful Dead")
    parser.add_argument("--max-release-requests", type=int, default=300, help="cap on paged release requests per run")
    parser.add_argument("--force", action="store_true", help="refetch even when final raw files already exist")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rg_partial = RELEASE_GROUPS_PATH.with_name(RELEASE_GROUPS_PATH.name + ".partial")
    release_partial = RELEASES_PATH.with_name(RELEASES_PATH.name + ".partial")
    resuming = CHECKPOINT_PATH.exists()
    if not resuming and RELEASE_GROUPS_PATH.exists() and RELEASES_PATH.exists() and not args.force:
        raise SystemExit(
            f"{RELEASE_GROUPS_PATH.relative_to(ROOT)} and {RELEASES_PATH.relative_to(ROOT)} already exist; "
            "pass --force to refetch."
        )
    if not resuming:
        rg_partial.unlink(missing_ok=True)
        release_partial.unlink(missing_ok=True)

    state = load_checkpoint()
    client = Client()
    artist = resolve_artist(client, args.artist_name, state)
    collect_release_groups(client, artist, state, rg_partial)
    collect_releases(client, artist, state, release_partial, args.max_release_requests)

    if not state["releases_done"]:
        remaining = (state["release_count"] or 0) - state["release_offset"]
        print(f"Checkpoint kept at {CHECKPOINT_PATH.relative_to(ROOT)}; {remaining} releases remain.")
        return

    group_total = finalize(rg_partial, RELEASE_GROUPS_PATH)
    release_total = finalize(release_partial, RELEASES_PATH)
    summary = {
        "artist": artist,
        "release_group_count": group_total,
        "release_count": release_total,
        "release_requests": state["release_requests"],
        "total_requests": len(state["request_log"]),
        "completed_at": now_iso(),
        "request_log": state["request_log"],
    }
    (RAW_DIR / "musicbrainz-live-releases.run.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    CHECKPOINT_PATH.unlink(missing_ok=True)
    print(
        f"Preserved {group_total} release groups at {RELEASE_GROUPS_PATH.relative_to(ROOT)} and "
        f"{release_total} releases at {RELEASES_PATH.relative_to(ROOT)} using {len(state['request_log'])} requests."
    )


if __name__ == "__main__":
    main()
