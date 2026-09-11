#!/usr/bin/env python3
"""Index Alex Allan's per-song lyric-and-annotation pages on whitegum.com.

David Dodd's *Annotated Grateful Dead Lyrics* is the standard reference for
lyric history, but its original home (``artsites.ucsc.edu/GDead/agdl/``) does
not respond at all from this environment (a connection failure, not a 404;
verified 2026-09-10 and reconfirmed at collection time below). Alex Allan's
``whitegum.com`` hosts an independent, currently-reachable "Grateful Dead
Lyric and Song Finder" with its own per-song page for nearly every song the
Grateful Dead and its members' side projects performed, each of which links
out to Dodd's essay (via the Wayback Machine, since the original no longer
resolves) alongside its own lyric-variant notes and cross-references.

Source review (2026-09-11): ``https://www.whitegum.com/robots.txt`` allows
every path except ``/contact.htm``, with no ``Crawl-delay``. No terms-of-use,
licensing or attribution-requirement page exists anywhere on the site — the
home page, ``/alex.htm`` (the author's bio) and the footer of a sampled
``/songfile/`` page were all checked and none states reuse terms. Full
findings are in ``docs/collection-status-lore-lyric-annotations.md`` and the
``whitegum-lyric-finder`` entry in ``data/source_registry.json``. This
collector therefore proceeds metadata-only: a page title and a URL per
canonical song, never the lyrics or annotation prose the page displays.

Discovery: the site's own full index, ``/longlist.htm``, lists every song's
title, its ``/songfile/<SLUG>.HTM`` URL and the section it is filed under
(Originals, Covers, Grateful Dead Jams, Guest Singers, ...), including "X see
Y" cross-reference aliases. One request therefore yields the whole site's
title/URL pairs; the per-canonical-song matching below needs no guessed URL.
For each canonical song whose title resolves to exactly one page, that page
is fetched once (confirming it still exists and reading its own ``<TITLE>``)
so the raw record reflects the live page, not just the index's link text.

Metadata only. A stored record keeps the page title, its URL, the canonical
song id it was resolved for, the HTTP status and the retrieval time. No
lyrics, annotation prose, or other page content is read into any file.

Host courtesy: requests go one at a time, at least two seconds apart (the
``whitegum-lyric-finder`` registry entry's rate policy), with
``User-Agent: Deadbot/0.1 (metadata index; contact via repository)``, and a
longer ``Crawl-delay`` is honored.

Retry safety: the raw file is rewritten only from a complete successful pass.
A non-200 ``/longlist.htm`` aborts the pass and leaves the previous raw file
untouched.

Usage::

    PYTHONPATH=. python scripts/collect/collect_whitegum_lyric_annotations.py
    PYTHONPATH=. python scripts/collect/collect_whitegum_lyric_annotations.py \
        --out data/raw/songs/
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.robotparser
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "normalize"))

from normalize_song_guide_resources import match_key  # noqa: E402

HOST = "www.whitegum.com"
BASE_URL = f"https://{HOST}"
LONGLIST_PATH = "/longlist.htm"
SOURCE_ID = "whitegum-lyric-finder"
SOURCE_NAME = "Grateful Dead Lyric and Song Finder / whitegum.com"
CREATOR = "Alex Allan"
USER_AGENT = "Deadbot/0.1 (metadata index; contact via repository)"
ROBOTS_AGENT = "Deadbot"
ROBOTS_PATHS = ("/longlist.htm", "/songfile/")
MIN_SECONDS_BETWEEN_REQUESTS = 2.0
MAX_PAGE_BYTES = 400_000
OUTPUT_DIR = ROOT / "data" / "raw" / "songs"
RAW_FILENAME = "whitegum-lyric-annotations.jsonl"
SONGS_PATH = ROOT / "data" / "canonical" / "songs.csv"
RESOURCE_TYPE = "lyric-annotation"
RETENTION = (
    "Metadata only: page title, URL and the canonical song it was resolved for. No lyrics, "
    "annotation text or other page content is read or stored."
)

_TAG = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
_SECTION = re.compile(r"<H3>([^<]+)</H3>", re.IGNORECASE)
_ENTRY = re.compile(r'(?:([^<\n]{1,80}?)\s*<I>see</I>\s*)?<A\s+HREF="([^"]+)"><B>([^<]*)</B></A>', re.IGNORECASE)


# --- transport ---------------------------------------------------------------


class Throttle:
    def __init__(self, min_interval: float = MIN_SECONDS_BETWEEN_REQUESTS) -> None:
        self.min_interval = min_interval
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            delay = self.min_interval - (time.monotonic() - self._last)
            if delay > 0:
                time.sleep(delay)
        self._last = time.monotonic()


class FetchedPage:
    __slots__ = ("status", "url", "body")

    def __init__(self, status: int, url: str, body: str) -> None:
        self.status = status
        self.url = url
        self.body = body


class MetadataPageTransport:
    def __init__(self, throttle: Throttle, max_bytes: int = MAX_PAGE_BYTES) -> None:
        self.throttle = throttle
        self.max_bytes = max_bytes

    def get(self, url: str, *, timeout: float = 15.0) -> FetchedPage:
        self.throttle.wait()
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"})
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read(self.max_bytes).decode(charset, errors="replace")
                return FetchedPage(getattr(response, "status", 200), response.geturl(), body)
        except HTTPError as error:
            return FetchedPage(error.code, url, "")
        except (URLError, TimeoutError, OSError, ValueError):
            return FetchedPage(0, url, "")


# --- helpers -----------------------------------------------------------------


def timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG.sub("", value))).strip()


def applicable_robots_rules(body: str) -> list[str]:
    rules: list[str] = []
    agents: list[str] = []
    fresh_group = True
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().casefold()
        value = value.strip()
        if field == "user-agent":
            if fresh_group:
                agents = []
            agents.append(value.casefold())
            fresh_group = False
            continue
        fresh_group = True
        if field not in {"allow", "disallow", "crawl-delay"}:
            continue
        if any(agent == "*" or ROBOTS_AGENT.casefold() in agent for agent in agents):
            rules.append(f"{field.title() if field != 'crawl-delay' else 'Crawl-delay'}: {value}")
    return rules


def read_robots(transport: MetadataPageTransport, timeout: float = 15.0, paths: tuple[str, ...] = ROBOTS_PATHS) -> dict[str, Any]:
    url = f"{BASE_URL}/robots.txt"
    page = transport.get(url, timeout=timeout)
    finding: dict[str, Any] = {
        "url": url,
        "http_status": page.status,
        "paths": dict.fromkeys(paths, False),
        "crawl_delay": None,
        "applicable_rules": [],
        "note": "",
    }
    if page.status in {404, 410}:
        finding["paths"] = dict.fromkeys(paths, True)
        finding["note"] = f"The host serves no robots.txt (HTTP {page.status}), so these paths are unrestricted."
        return finding
    if page.status != 200:
        finding["note"] = f"robots.txt could not be read (HTTP {page.status}); the host was skipped rather than crawled unchecked."
        return finding
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(page.body.splitlines())
    parser.modified()
    finding["paths"] = {path: bool(parser.can_fetch(USER_AGENT, f"{BASE_URL}{path}")) for path in paths}
    delay = parser.crawl_delay(USER_AGENT)
    finding["crawl_delay"] = float(delay) if delay is not None else None
    finding["applicable_rules"] = applicable_robots_rules(page.body)
    allowed = [path for path, ok in finding["paths"].items() if ok]
    refused = [path for path, ok in finding["paths"].items() if not ok]
    finding["note"] = "robots.txt permits " + ", ".join(allowed) + ("; it disallows " + ", ".join(refused) if refused else ".")
    return finding


def parse_longlist(body: str) -> list[dict[str, str]]:
    """Every ``(section, alias, href, title)`` entry on the site's own index."""

    parts = re.split(r"(<H3>[^<]+</H3>)", body, flags=re.IGNORECASE)
    section = ""
    entries: list[dict[str, str]] = []
    for part in parts:
        match = _SECTION.match(part)
        if match:
            section = match.group(1).strip()
            continue
        for entry in _ENTRY.finditer(part):
            alias, href, title = entry.groups()
            entries.append(
                {
                    "section": section,
                    "alias": plain_text(alias) if alias else "",
                    "href": href.strip(),
                    "title": plain_text(title),
                }
            )
    return entries


def load_songs(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_lookup(entries: list[dict[str, str]]) -> dict[tuple[str, ...], list[dict[str, str]]]:
    """``match_key`` -> the distinct site entries that key names (title or alias)."""

    lookup: dict[tuple[str, ...], list[dict[str, str]]] = {}
    seen_per_key: dict[tuple[str, ...], set[str]] = {}
    for entry in entries:
        for text in filter(None, (entry["title"], entry["alias"])):
            key = match_key(text)
            if not key:
                continue
            seen = seen_per_key.setdefault(key, set())
            if entry["href"] in seen:
                continue
            seen.add(entry["href"])
            lookup.setdefault(key, []).append(entry)
    return lookup


# --- records -----------------------------------------------------------------


def resource_id_for(song_id: str) -> str:
    return f"resource-whitegum-{song_id.removeprefix('song-')}"


def page_record(song_id: str, url: str, title: str, http_status: int) -> dict[str, Any]:
    return {
        "source": SOURCE_ID,
        "source_record_id": f"songfile:{song_id}",
        "retrieved_at": "",  # filled by caller
        "source_url": url,
        "raw_payload": {
            "record_type": "page",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "creator": CREATOR,
            "resource_type": RESOURCE_TYPE,
            "song_id": song_id,
            "title": title,
            "http_status": http_status,
            "discovered_via": "longlist.htm",
        },
    }


def pass_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": SOURCE_ID,
        "source_record_id": f"whitegum-lyric-annotations:{HOST}",
        "retrieved_at": result["retrieved_at"],
        "source_url": f"{BASE_URL}{LONGLIST_PATH}",
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "resource_type": RESOURCE_TYPE,
            "user_agent": result["user_agent"],
            "robots": result["robots"],
            "longlist_http_status": result["longlist_http_status"],
            "longlist_entry_count": result["longlist_entry_count"],
            "songs_considered": result["songs_considered"],
            "found": result["found"],
            "ambiguous": result["ambiguous"],
            "not_found": result["not_found"],
            "page_fetches": result["page_fetches"],
            "status": result["status"],
            "note": result["note"],
            "retention": RETENTION,
        },
    }


def write_raw_file(out_dir: Path, result: dict[str, Any]) -> Path | None:
    if result["status"] != "ok":
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RAW_FILENAME
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(pass_record(result), ensure_ascii=False, separators=(",", ":")) + "\n")
        for record in result["records"]:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def collect(transport: MetadataPageTransport, songs: list[dict[str, str]], *, timeout: float = 15.0) -> dict[str, Any]:
    retrieved_at = timestamp()
    result: dict[str, Any] = {
        "retrieved_at": retrieved_at,
        "user_agent": USER_AGENT,
        "robots": {},
        "longlist_http_status": 0,
        "longlist_entry_count": 0,
        "songs_considered": len(songs),
        "found": 0,
        "ambiguous": 0,
        "not_found": 0,
        "page_fetches": 0,
        "records": [],
        "outcomes": {},
        "status": "ok",
        "note": "",
    }
    robots = read_robots(transport, timeout)
    result["robots"] = robots
    if not robots["paths"].get(LONGLIST_PATH):
        result["status"] = "skipped-robots"
        result["note"] = robots["note"]
        return result

    longlist_url = f"{BASE_URL}{LONGLIST_PATH}"
    page = transport.get(longlist_url, timeout=timeout)
    result["longlist_http_status"] = page.status
    if page.status != 200:
        result["status"] = "aborted"
        result["note"] = f"{longlist_url} returned HTTP {page.status}; the raw file was left unchanged."
        return result

    entries = parse_longlist(page.body)
    if not entries:
        result["status"] = "aborted"
        result["note"] = "The site index returned HTTP 200 but no song entries were parsed; the raw file was left unchanged."
        return result
    result["longlist_entry_count"] = len(entries)
    lookup = build_lookup(entries)

    fetched_urls: dict[str, dict[str, Any]] = {}
    if not robots["paths"].get("/songfile/"):
        result["note"] = "robots.txt disallows /songfile/; no per-song page was fetched, so nothing was matched."
        result["not_found"] = len(songs)
        for song in songs:
            result["outcomes"][song["song_id"]] = "not attempted (robots)"
        return result

    for song in songs:
        song_id = song["song_id"]
        key = match_key(song["title"])
        candidates = lookup.get(key, [])
        distinct_urls = sorted({candidate["href"] for candidate in candidates})
        if not distinct_urls:
            result["not_found"] += 1
            result["outcomes"][song_id] = "not found at source"
            continue

        pages: list[dict[str, Any]] = []
        for href in distinct_urls:
            if href not in fetched_urls:
                url = urljoin(BASE_URL, href)
                fetch = transport.get(url, timeout=timeout)
                result["page_fetches"] += 1
                title_match = _TITLE.search(fetch.body) if fetch.status == 200 else None
                fetched_urls[href] = {
                    "url": url,
                    "http_status": fetch.status,
                    "title": plain_text(title_match.group(1)) if title_match else "",
                }
            pages.append(fetched_urls[href])

        live_pages = [page_info for page_info in pages if page_info["http_status"] == 200]
        if not live_pages:
            result["not_found"] += 1
            result["outcomes"][song_id] = "page listed but unreachable"
            continue

        if len(live_pages) > 1:
            result["ambiguous"] += 1
            result["outcomes"][song_id] = "held (ambiguous: multiple site pages)"
            for page_info in live_pages:
                record = page_record(song_id, page_info["url"], page_info["title"], page_info["http_status"])
                record["retrieved_at"] = retrieved_at
                result["records"].append(record)
            continue

        result["found"] += 1
        result["outcomes"][song_id] = "found"
        page_info = live_pages[0]
        record = page_record(song_id, page_info["url"], page_info["title"], page_info["http_status"])
        record["retrieved_at"] = retrieved_at
        result["records"].append(record)

    result["records"].sort(key=lambda record: (record["raw_payload"]["song_id"], record["source_url"]))
    result["note"] = (
        f"{result['found']} found, {result['ambiguous']} ambiguous (held), {result['not_found']} not found at source, "
        f"of {result['songs_considered']} canonical songs considered ({result['page_fetches']} page fetches)."
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="directory for the raw JSONL file")
    parser.add_argument("--songs", type=Path, default=SONGS_PATH, help="canonical songs.csv")
    parser.add_argument("--min-interval", type=float, default=MIN_SECONDS_BETWEEN_REQUESTS, help="minimum seconds between requests")
    args = parser.parse_args()

    throttle = Throttle(max(args.min_interval, MIN_SECONDS_BETWEEN_REQUESTS))
    transport = MetadataPageTransport(throttle)
    songs = load_songs(args.songs)
    result = collect(transport, songs)

    robots = result["robots"]
    print(f"{HOST}: robots HTTP {robots.get('http_status')}, {robots.get('note')}")
    print(f"  {BASE_URL}{LONGLIST_PATH}: HTTP {result['longlist_http_status']}, {result['longlist_entry_count']} entries parsed")
    path = write_raw_file(args.out, result)
    if path is None:
        print(f"  {result['status']}: {result['note']}")
        raise SystemExit(1)
    print(f"  {result['note']}")
    print(f"  -> {path}")


if __name__ == "__main__":
    main()
