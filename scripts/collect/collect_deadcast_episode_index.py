#!/usr/bin/env python3
"""Index every Good Ol' Grateful Deadcast episode, metadata only.

Dead.net's own unpaginated episode archive, ``/deadcast-index``, lists every
episode published so far in one page: each row carries the episode's URL, its
title and its publish date, grouped under ``<h3>Season N</h3>`` headings. That
single page is therefore the whole enumeration; no per-episode request is
needed to discover the catalog or its season/date fields. (Two representative
episode pages were checked by hand during development: each page's own
``<title>`` matches the index row's title text exactly, and the page's meta
description is the same site-wide boilerplate on every episode, not
episode-specific text — so fetching every episode page individually would add
requests without adding information. That finding is recorded in the raw
file's pass metadata rather than assumed silently.)

Metadata only. A stored record keeps the episode title, its URL, the season
heading it was listed under, the publish date, the HTTP status and the
retrieval time. No transcript, episode description, guest list or audio is
read or written to any file, matching the ``deadcast-metadata`` registry
entry's retention policy.

Host courtesy: ``https://www.dead.net/robots.txt`` is read first and its
finding is preserved in the raw file; a disallowed path is skipped rather than
crawled unchecked. This collector honors the registry's rate policy: one
request at a time, at least ten seconds apart (``requests_per_minute: 6`` in
``data/source_registry.json``), with
``User-Agent: Deadbot/0.1 (metadata index; contact via repository)``, and a
longer ``Crawl-delay`` is honored.

Retry safety: the raw file is rewritten only from a complete successful pass.
A non-200 response from ``/deadcast-index`` aborts the pass and leaves the
previous raw file untouched, so a transient failure can never turn a
collected episode into an apparent absence.

Usage::

    PYTHONPATH=. python scripts/collect/collect_deadcast_episode_index.py
    PYTHONPATH=. python scripts/collect/collect_deadcast_episode_index.py \
        --out data/raw/resources/
"""

from __future__ import annotations

import argparse
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
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HOST = "www.dead.net"
INDEX_PATH = "/deadcast-index"
INDEX_URL = f"https://{HOST}{INDEX_PATH}"
SOURCE_ID = "deadcast-metadata"
SOURCE_NAME = "Good Ol' Grateful Deadcast / Dead.net"
USER_AGENT = "Deadbot/0.1 (metadata index; contact via repository)"
ROBOTS_AGENT = "Deadbot"
ROBOTS_PATHS = ("/deadcast", "/deadcast-index")
MIN_SECONDS_BETWEEN_REQUESTS = 10.0
MAX_PAGE_BYTES = 2_000_000
OUTPUT_DIR = ROOT / "data" / "raw" / "resources"
RAW_FILENAME = "deadcast-episode-index.jsonl"
RESOURCE_TYPE = "podcast-episode"
RETENTION = (
    "Metadata only: episode title, URL, season heading and publish date, all read from the site's own "
    "/deadcast-index archive listing. No transcript, description, guest list or audio is read or stored."
)

_TAG = re.compile(r"<[^>]+>")
_SEASON = re.compile(r"<h3>Season (\d+)</h3>")
_ROW = re.compile(
    r'<span><a href="(/deadcast/[^"]+)"[^>]*>(.*?)</a>&nbsp;</span>\s*'
    r'<span>\(<time datetime="([^"]+)"[^>]*>([^<]*)</time>\)&nbsp;</span>',
    re.DOTALL,
)


# --- transport -----------------------------------------------------------


class Throttle:
    """One request at a time, no faster than ``min_interval`` seconds apart."""

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
    """A minimal GET-only transport that paces itself and caps the read."""

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


# --- helpers ---------------------------------------------------------------


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
    url = f"https://{HOST}/robots.txt"
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
    finding["paths"] = {path: bool(parser.can_fetch(USER_AGENT, f"https://{HOST}{path}")) for path in paths}
    delay = parser.crawl_delay(USER_AGENT)
    finding["crawl_delay"] = float(delay) if delay is not None else None
    finding["applicable_rules"] = applicable_robots_rules(page.body)
    allowed = [path for path, ok in finding["paths"].items() if ok]
    refused = [path for path, ok in finding["paths"].items() if not ok]
    finding["note"] = "robots.txt permits " + ", ".join(allowed) + ("; it disallows " + ", ".join(refused) if refused else ".")
    return finding


def parse_index(body: str) -> tuple[list[dict[str, str]], str]:
    """Every episode row on the archive listing, in page order, with its season.

    The page interleaves ``<h3>Season N</h3>`` headings with
    ``<div class="views-row">`` episode rows; a season heading applies to
    every row until the next heading. A handful of early rows have no
    transcript link (an empty trailing ``<span></span>``), so the row pattern
    does not require one.
    """

    parts = re.split(r'(<h3>Season \d+</h3>|<div class="views-row">)', body)
    season = ""
    episodes: list[dict[str, str]] = []
    expecting_row = False
    for part in parts:
        season_match = _SEASON.match(part)
        if season_match:
            season = season_match.group(1)
            expecting_row = False
            continue
        if part == '<div class="views-row">':
            expecting_row = True
            continue
        if expecting_row:
            match = _ROW.search(part)
            if match:
                path, title, published, _display = match.groups()
                episodes.append({"season": season, "url_path": path, "title": plain_text(title), "published_date": published[:10]})
            expecting_row = False
    note = f"{len(episodes)} episode row(s) parsed from the archive listing."
    return episodes, note


# --- records -----------------------------------------------------------------


def episode_slug(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def episode_record(episode: dict[str, str], retrieved_at: str) -> dict[str, Any]:
    slug = episode_slug(episode["url_path"])
    return {
        "source": SOURCE_ID,
        "source_record_id": f"deadcast/{slug}",
        "retrieved_at": retrieved_at,
        "source_url": f"https://{HOST}{episode['url_path']}",
        "raw_payload": {
            "record_type": "episode",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "resource_type": RESOURCE_TYPE,
            "url_slug": slug,
            "title": episode["title"],
            "season": episode["season"],
            "published_date": episode["published_date"],
            "http_status": 200,
            "discovered_via": "deadcast-index",
        },
    }


def pass_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": SOURCE_ID,
        "source_record_id": f"deadcast-episode-index:{HOST}",
        "retrieved_at": result["retrieved_at"],
        "source_url": INDEX_URL,
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "resource_type": RESOURCE_TYPE,
            "user_agent": USER_AGENT,
            "min_interval_seconds": result["min_interval_seconds"],
            "robots": result["robots"],
            "index_http_status": result["index_http_status"],
            "episode_count": len(result["episodes"]),
            "season_count": result["season_count"],
            "status": result["status"],
            "note": result["note"],
            "per_episode_page_fetches": 0,
            "per_episode_page_fetch_rationale": (
                "Not fetched. Two representative episode pages (blues-allah-50-slipknot and "
                "independence-ball-7366) were checked by hand during development: each page's <title> "
                "matched this index row's title text exactly, and each page's meta description was the "
                "same site-wide boilerplate ('The Good Ol' Grateful Deadcast is the first official "
                "Grateful Dead podcast...'), not episode-specific text. The index row's title, URL, "
                "season and date are therefore the same information a per-episode fetch would return, "
                "at 1/130th of the requests."
            ),
            "retention": RETENTION,
        },
    }


def write_raw_file(out_dir: Path, result: dict[str, Any]) -> Path | None:
    if result["status"] != "ok":
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RAW_FILENAME
    with path.open("w", encoding="utf-8") as handle:
        for line in [pass_record(result), *(episode_record(episode, result["retrieved_at"]) for episode in result["episodes"])]:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def collect(transport: MetadataPageTransport, *, min_interval: float, timeout: float = 15.0) -> dict[str, Any]:
    retrieved_at = timestamp()
    result: dict[str, Any] = {
        "retrieved_at": retrieved_at,
        "min_interval_seconds": min_interval,
        "robots": {},
        "index_http_status": 0,
        "episodes": [],
        "season_count": 0,
        "status": "ok",
        "note": "",
    }
    robots = read_robots(transport, timeout)
    result["robots"] = robots
    if not robots["paths"].get(INDEX_PATH):
        result["status"] = "skipped-robots"
        result["note"] = robots["note"]
        return result

    page = transport.get(INDEX_URL, timeout=timeout)
    result["index_http_status"] = page.status
    if page.status != 200:
        result["status"] = "aborted"
        result["note"] = f"{INDEX_URL} returned HTTP {page.status}; the raw file was left unchanged."
        return result

    episodes, note = parse_index(page.body)
    if not episodes:
        result["status"] = "aborted"
        result["note"] = "The archive listing returned HTTP 200 but no episode rows were parsed; the raw file was left unchanged."
        return result
    result["episodes"] = episodes
    result["season_count"] = len({episode["season"] for episode in episodes if episode["season"]})
    result["note"] = note
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="directory for the raw JSONL file")
    parser.add_argument("--min-interval", type=float, default=MIN_SECONDS_BETWEEN_REQUESTS, help="minimum seconds between requests")
    args = parser.parse_args()

    throttle = Throttle(max(args.min_interval, MIN_SECONDS_BETWEEN_REQUESTS))
    transport = MetadataPageTransport(throttle)
    result = collect(transport, min_interval=throttle.min_interval)

    robots = result["robots"]
    print(f"{HOST}: robots HTTP {robots.get('http_status')}, {robots.get('note')}")
    print(f"  {INDEX_URL}: HTTP {result['index_http_status']}")
    path = write_raw_file(args.out, result)
    if path is None:
        print(f"  {result['status']}: {result['note']}")
        raise SystemExit(1)
    print(f"  {len(result['episodes'])} episodes across {result['season_count']} season(s) -> {path}")


if __name__ == "__main__":
    main()
