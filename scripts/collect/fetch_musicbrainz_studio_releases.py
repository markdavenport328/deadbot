#!/usr/bin/env python3
"""Collect compact MusicBrainz metadata for the Grateful Dead family's studio albums.

This is the studio counterpart of ``fetch_musicbrainz_live_releases.py`` and
follows the same conventions: one request per second, a descriptive
User-Agent, compact JSONL raw records, and a checkpoint that lets an
interrupted run resume without repeating completed requests.

Where the live collector resolves a single artist (the Grateful Dead), this
collector walks the whole Dead family catalog named in ``STUDIO_ARTISTS`` --
Grateful Dead, Jerry Garcia, Bob Weir, New Riders of the Purple Sage,
Old & In the Way, Kingfish, and Jerry Garcia Band -- one artist at a time, in
that order, resuming mid-artist if interrupted.

Requests, per artist, in order:

1. Artist search to resolve the artist MBID (never trusted from memory).
   Accepts a ``Group`` or ``Person`` type match, since this catalog spans
   bands and individual musicians.
2. Release-group browse for the artist filtered to primary type Album.  Every
   browsed group advances the pagination offset, but only groups
   ``is_studio_release_group`` accepts are written to the raw file --
   this pass is studio albums only; a Live secondary type belongs to the
   2026-09-01 live pass, and Compilation and Single are declared in the
   schema vocabulary but deliberately not collected here.
3. Release browse for the artist filtered to official Album releases with
   ``inc=recordings+url-rels+release-groups+artist-credits+artist-rels``.  Each
   release embeds its release-group, so the same ``is_studio_release_group``
   check decides whether the release is written.  Browsing by artist covers the
   whole catalog in a handful of paged requests instead of one lookup per
   release group; a later normalizer chooses canonical rows.

``--artist-relations`` runs a second, narrow pass instead of the browse above.
``artist-credits`` yields only the album's billed artist ("Jerry Garcia & David
Grisman"); per-instrument performer credits are *relations*, and on MusicBrainz
they usually hang off the recording rather than the release.  This pass looks up
each already-promoted studio release by MBID with
``inc=recordings+artist-rels+recording-level-rels``, so it costs one request per
promoted album rather than a whole re-browse, and writes
``musicbrainz-studio-release-credits.jsonl`` alongside the files above.  It
resumes from its ``.partial`` file, so an interrupted run repeats no request.

Only compact fields are kept: MBIDs, titles, dates, disambiguations,
statuses, medium and track titles and lengths, artist credits, artist
relations, and URL relationships. No cover art or annotation text is stored.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "releases"
RELEASE_GROUPS_PATH = RAW_DIR / "musicbrainz-studio-release-groups.jsonl"
RELEASES_PATH = RAW_DIR / "musicbrainz-studio-releases.jsonl"
CREDITS_PATH = RAW_DIR / "musicbrainz-studio-release-credits.jsonl"
CREDITS_RUN_SUMMARY_PATH = RAW_DIR / "musicbrainz-studio-release-credits.run.json"
CHECKPOINT_PATH = RAW_DIR / "musicbrainz-studio-releases.checkpoint.json"
RUN_SUMMARY_PATH = RAW_DIR / "musicbrainz-studio-releases.run.json"
CANONICAL_RELEASES_CSV = ROOT / "data" / "canonical" / "official_releases.csv"
# Kept in step with STUDIO_MARKER in scripts/normalize_musicbrainz_studio_releases.py.
STUDIO_MARKER = "studio release-group pass"
API = "https://musicbrainz.org/ws/2/"
USER_AGENT = "DeadBot/0.1 (local studio-release collection; contact unavailable)"
REQUEST_INTERVAL_SECONDS = 1.1
# artist-rels carries the per-person relations that artist-credits does not:
# artist-credits is the billed album artist, and a performer credit naming an
# instrument is a relation.
RELEASE_INC = "recordings+url-rels+release-groups+artist-credits+artist-rels"
# The narrow --artist-relations lookup.  recording-level-rels needs recordings,
# and is where MusicBrainz actually keeps most instrument credits for this
# catalog; url-rels and release-groups are omitted because that data is already
# in musicbrainz-studio-releases.jsonl and this pass only adds credits.
CREDITS_INC = "recordings+artist-rels+recording-level-rels"
RELEASE_GROUP_PAGE_SIZE = 100
RELEASE_PAGE_SIZE = 25
MIN_RELEASE_PAGE_SIZE = 5
MAX_ATTEMPTS = 6

STUDIO_ARTISTS: tuple[str, ...] = (
    "Grateful Dead",
    "Jerry Garcia",
    "Bob Weir",
    "New Riders of the Purple Sage",
    "Old & In the Way",
    "Kingfish",
    "Jerry Garcia Band",
)

# Catalog scope is studio albums only.  A Live secondary type belongs to the
# 2026-09-01 live pass; Compilation and Single are declared in the schema
# vocabulary but deliberately not collected.  Demo disqualifies archival
# outtake companions (e.g. the "...: The Angel's Share" release groups) that
# are not themselves studio albums.
_DISQUALIFYING_SECONDARY_TYPES = frozenset(
    {"Live", "Compilation", "Soundtrack", "Interview", "Remix", "DJ-mix", "Demo"}
)


def is_studio_release_group(group: dict) -> bool:
    if (group.get("primary-type") or "") != "Album":
        return False
    secondary = {str(value) for value in group.get("secondary-types") or ()}
    return not (secondary & _DISQUALIFYING_SECONDARY_TYPES)


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


def default_artist_state() -> dict:
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
    }


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {
        "artists": {name: default_artist_state() for name in STUDIO_ARTISTS},
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
    artist_state = state["artists"][name]
    if artist_state["artist"]:
        return artist_state["artist"]
    status, url, payload = client.get("artist/", {"query": f'artist:"{name}"', "limit": "5"})
    state["request_log"].append(
        {"step": "artist-search", "artist_name": name, "url": url, "http_status": status, "at": now_iso()}
    )
    if status != 200:
        save_checkpoint(state)
        raise SystemExit(f"artist search failed for {name!r} with HTTP {status}: {payload}")
    candidates = [
        artist
        for artist in payload.get("artists", [])
        if artist.get("name", "").casefold() == name.casefold() and artist.get("type") in {"Group", "Person"}
    ]
    if not candidates:
        save_checkpoint(state)
        raise SystemExit(f"no Group/Person artist named {name!r} in MusicBrainz search results")
    candidates.sort(key=lambda artist: -int(artist.get("score", 0)))
    top = candidates[0]
    artist_state["artist"] = {
        "id": top["id"],
        "name": top["name"],
        "score": top.get("score"),
        "type": top.get("type"),
        "disambiguation": top.get("disambiguation", ""),
        "search_url": url,
        "retrieved_at": now_iso(),
    }
    save_checkpoint(state)
    print(f"Resolved artist {top['name']} -> {top['id']} (score {top.get('score')}, {top.get('type')})")
    return artist_state["artist"]


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


def compact_artist_relations(entity: dict) -> list[dict]:
    """Keep artist relations verbatim enough to become release_personnel rows.

    ``attributes`` is where the instrument lives ("guitar", "pedal steel
    guitar"), and ``release_personnel.instrument`` is part of that table's
    primary key, so a relation with no attribute cannot be stored and the
    normalizer holds it.  Nothing is inferred here: relation type, attributes
    and artist identity are copied as MusicBrainz gives them.
    """

    relations = []
    for relation in entity.get("relations", []):
        if relation.get("target-type") != "artist":
            continue
        artist = relation.get("artist", {}) or {}
        relations.append(
            {
                "type": relation.get("type", ""),
                "direction": relation.get("direction", ""),
                "attributes": [str(value) for value in relation.get("attributes", []) or []],
                "artist_id": artist.get("id", ""),
                "artist_name": artist.get("name", ""),
                "artist_sort_name": artist.get("sort-name", ""),
            }
        )
    return relations


def compact_artist_credit(entity: dict) -> list[dict]:
    credits = []
    for item in entity.get("artist-credit", []) or []:
        if not isinstance(item, dict):
            continue
        artist = item.get("artist", {}) or {}
        credits.append(
            {
                "name": item.get("name", ""),
                "joinphrase": item.get("joinphrase", ""),
                "artist_id": artist.get("id", ""),
                "artist_name": artist.get("name", ""),
            }
        )
    return credits


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
                        "artist_relations": compact_artist_relations(recording),
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
        "release_group": compact_release_group(release.get("release-group", {}) or {}),
        "artist_credit": compact_artist_credit(release),
        "artist_relations": compact_artist_relations(release),
        "url_relations": compact_url_relations(release),
        "media": media,
    }


def collect_release_groups(client: Client, artist: dict, name: str, state: dict, partial: Path) -> None:
    artist_state = state["artists"][name]
    while not artist_state["release_groups_done"]:
        offset = artist_state["release_group_offset"]
        params = {
            "artist": artist["id"],
            "type": "album",
            "limit": str(RELEASE_GROUP_PAGE_SIZE),
            "offset": str(offset),
        }
        status, url, payload = client.get("release-group", params)
        state["request_log"].append(
            {"step": "release-group-browse", "artist_name": name, "url": url, "http_status": status, "at": now_iso()}
        )
        if status != 200:
            save_checkpoint(state)
            raise SystemExit(f"release-group browse failed for {name} at offset {offset} with HTTP {status}: {payload}")
        groups = payload.get("release-groups", [])
        retrieved_at = now_iso()
        qualifying = [group for group in groups if is_studio_release_group(group)]
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
                        "artist_name": name,
                        "release_group": compact_release_group(group),
                    },
                }
                for group in qualifying
            ],
        )
        artist_state["release_group_count"] = payload.get("release-group-count", 0)
        artist_state["release_group_offset"] = offset + len(groups)
        if not groups or artist_state["release_group_offset"] >= artist_state["release_group_count"]:
            artist_state["release_groups_done"] = True
        save_checkpoint(state)
        print(
            f"{name}: release groups {artist_state['release_group_offset']}/{artist_state['release_group_count']} "
            f"({len(qualifying)} studio in page)"
        )


def collect_releases(client: Client, artist: dict, name: str, state: dict, partial: Path, max_requests: int) -> int:
    artist_state = state["artists"][name]
    used = 0
    while not artist_state["releases_done"]:
        if used >= max_requests:
            print(
                f"Stopping {name} at the release request cap; "
                f"{artist_state['release_offset']}/{artist_state['release_count']} releases fetched. Rerun to resume."
            )
            return used
        offset = artist_state["release_offset"]
        params = {
            "artist": artist["id"],
            "type": "album",
            "status": "official",
            "inc": RELEASE_INC,
            "limit": str(artist_state["release_page_size"]),
            "offset": str(offset),
        }
        status, url, payload = client.get("release", params)
        used += 1
        artist_state["release_requests"] += 1
        state["request_log"].append(
            {"step": "release-browse", "artist_name": name, "url": url, "http_status": status, "at": now_iso()}
        )
        if status != 200:
            if status in (0, 429, 503) and artist_state["release_page_size"] > MIN_RELEASE_PAGE_SIZE:
                # Heavy pages time out on the MusicBrainz side; ask for fewer releases.
                artist_state["release_page_size"] = max(MIN_RELEASE_PAGE_SIZE, artist_state["release_page_size"] // 2)
                save_checkpoint(state)
                print(f"  reducing release page size for {name} to {artist_state['release_page_size']} after HTTP {status}")
                continue
            save_checkpoint(state)
            raise SystemExit(f"release browse failed for {name} at offset {offset} with HTTP {status}: {payload}")
        releases = payload.get("releases", [])
        retrieved_at = now_iso()
        qualifying = [release for release in releases if is_studio_release_group(release.get("release-group", {}) or {})]
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
                        "artist_name": name,
                        "release": compact_release(release),
                    },
                }
                for release in qualifying
            ],
        )
        artist_state["release_count"] = payload.get("release-count", 0)
        artist_state["release_offset"] = offset + len(releases)
        if not releases or artist_state["release_offset"] >= artist_state["release_count"]:
            artist_state["releases_done"] = True
        save_checkpoint(state)
        print(
            f"{name}: releases {artist_state['release_offset']}/{artist_state['release_count']} "
            f"({len(qualifying)} studio in page)"
        )
    return used


def promoted_release_mbids() -> list[str]:
    """The MBIDs of the releases the studio normalizer actually promoted.

    Read from ``official_releases.csv`` rather than from the raw file, so the
    credits pass fetches one request per album in the catalog instead of one per
    release MusicBrainz has for the family.  Only rows carrying the studio pass's
    marker are read; live and hand-curated rows are none of this pass's business.
    """

    if not CANONICAL_RELEASES_CSV.exists():
        raise SystemExit(
            f"{CANONICAL_RELEASES_CSV.relative_to(ROOT)} does not exist; "
            "run scripts/normalize_musicbrainz_studio_releases.py first"
        )
    mbids: list[str] = []
    with CANONICAL_RELEASES_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            notes = row.get("notes", "") or ""
            if STUDIO_MARKER not in notes:
                continue
            found = re.search(r"MusicBrainz release ([0-9a-f-]{36})", notes)
            if found:
                mbids.append(found.group(1))
    return sorted(dict.fromkeys(mbids))


def collect_artist_relations(client: Client, mbids: list[str], partial: Path) -> tuple[int, list[dict]]:
    """Look each promoted release up with artist relations, resuming from partial."""

    done = {record["source_record_id"] for record in read_records(partial)}
    request_log: list[dict] = []
    fetched = 0
    for index, mbid in enumerate(mbids, start=1):
        if mbid in done:
            continue
        params = {"inc": CREDITS_INC}
        status, url, payload = client.get(f"release/{mbid}", params)
        request_log.append({"step": "release-lookup-artist-rels", "release_id": mbid, "url": url, "http_status": status, "at": now_iso()})
        if status != 200:
            # Fail closed: keep what has been written, say what broke, and let a
            # rerun resume rather than writing a half-known credit list.
            raise SystemExit(f"release lookup failed for {mbid} with HTTP {status}: {payload}")
        release = compact_release(payload)
        append_records(
            partial,
            [
                {
                    "source": "musicbrainz",
                    "source_record_id": mbid,
                    "retrieved_at": now_iso(),
                    "source_url": f"https://musicbrainz.org/release/{mbid}",
                    "raw_payload": {
                        "http_status": status,
                        "query": {"entity": f"release/{mbid}", **params},
                        "release": release,
                    },
                }
            ],
        )
        fetched += 1
        credits = len(release["artist_relations"]) + sum(
            len(track["recording"]["artist_relations"]) for medium in release["media"] for track in medium["tracks"]
        )
        print(f"{index}/{len(mbids)} {release['title']}: {credits} artist relations")
    return fetched, request_log


def run_artist_relations() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    partial = CREDITS_PATH.with_name(CREDITS_PATH.name + ".partial")
    mbids = promoted_release_mbids()
    if not mbids:
        raise SystemExit("no promoted studio releases found in official_releases.csv; nothing to fetch")
    client = Client()
    fetched, request_log = collect_artist_relations(client, mbids, partial)
    total = finalize(partial, CREDITS_PATH)
    CREDITS_RUN_SUMMARY_PATH.write_text(
        json.dumps(
            {
                "releases_requested": len(mbids),
                "releases_fetched_this_run": fetched,
                "releases_preserved": total,
                "inc": CREDITS_INC,
                "completed_at": now_iso(),
                "request_log": request_log,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Preserved {total} releases with artist relations at {CREDITS_PATH.relative_to(ROOT)} using {fetched} requests.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--max-release-requests", type=int, default=300, help="cap on paged release requests across the whole run"
    )
    parser.add_argument("--force", action="store_true", help="refetch even when final raw files already exist")
    parser.add_argument(
        "--artist-relations",
        action="store_true",
        help="fetch artist relations for the already-promoted studio releases only, one lookup each",
    )
    args = parser.parse_args()

    if args.artist_relations:
        run_artist_relations()
        return

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

    remaining_release_requests = args.max_release_requests - sum(
        artist_state["release_requests"] for artist_state in state["artists"].values()
    )
    stopped_early = False
    for name in STUDIO_ARTISTS:
        artist = resolve_artist(client, name, state)
        collect_release_groups(client, artist, name, state, rg_partial)
        if remaining_release_requests <= 0:
            print(f"Stopping before releases for {name}; release request cap reached. Rerun to resume.")
            stopped_early = True
            break
        used = collect_releases(client, artist, name, state, release_partial, remaining_release_requests)
        remaining_release_requests -= used
        if not state["artists"][name]["releases_done"]:
            stopped_early = True
            break

    all_done = not stopped_early and all(
        state["artists"][name]["release_groups_done"] and state["artists"][name]["releases_done"]
        for name in STUDIO_ARTISTS
    )
    if not all_done:
        print(f"Checkpoint kept at {CHECKPOINT_PATH.relative_to(ROOT)}; rerun to continue.")
        return

    group_total = finalize(rg_partial, RELEASE_GROUPS_PATH)
    release_total = finalize(release_partial, RELEASES_PATH)
    summary = {
        "artists": [state["artists"][name]["artist"] for name in STUDIO_ARTISTS],
        "release_group_count": group_total,
        "release_count": release_total,
        "release_requests": sum(state["artists"][name]["release_requests"] for name in STUDIO_ARTISTS),
        "total_requests": len(state["request_log"]),
        "completed_at": now_iso(),
        "request_log": state["request_log"],
    }
    RUN_SUMMARY_PATH.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    CHECKPOINT_PATH.unlink(missing_ok=True)
    print(
        f"Preserved {group_total} release groups at {RELEASE_GROUPS_PATH.relative_to(ROOT)} and "
        f"{release_total} releases at {RELEASES_PATH.relative_to(ROOT)} using {len(state['request_log'])} requests."
    )


if __name__ == "__main__":
    main()
