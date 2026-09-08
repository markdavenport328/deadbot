#!/usr/bin/env python3
"""Index Deadhead High's song and listener guides, metadata only.

Deadhead High (``deadheadhigh.com``) publishes a per-song listening guide at
``/songs/<slug>``, a per-show page at ``/shows/<YYYY-MM-DD>``, and editorial
guides under ``/guides/`` and ``/paths/``. The site has no search, so this
collector walks its sitemap the way ``deadbot.site_search`` does, keeps the
URLs this pass is for, and makes one metadata request per kept URL.

What is kept, and why:

- every ``/songs/`` page — the pass's whole point, and the sitemap lists 350;
- every ``/guides/`` and ``/paths/`` page — the site's editorial writing, 46
  pages, kept because it costs 46 requests at the same pace;
- a ``/shows/`` page whose slug is a target or featured show date;
- any other page whose slug names a target song.

``/venues/`` pages (500 of them) are not requested: this pass has no venue
mapping rule, so asking for them would be traffic without a use.

Metadata only. A stored record keeps the page URL, its title, at most 200
characters of the page's own meta description, the HTTP status and the
retrieval time. No guide text is written to any file.

Host courtesy: ``https://deadheadhigh.com/robots.txt`` is read first and its
finding is preserved in the raw file. Requests go one at a time, at least two
seconds apart, with ``User-Agent: Deadbot/0.1 (metadata index; contact via
repository)``, and a longer ``Crawl-delay`` is honored.

Retry safety: the raw file is rewritten only from a complete successful pass.
An unreadable sitemap or any non-200 page aborts the pass and leaves the
previous file untouched, so a transient failure can never turn a collected
page into an apparent absence.

Usage::

    PYTHONPATH=. python scripts/collect/collect_deadheadhigh_index.py
    PYTHONPATH=. python scripts/collect/collect_deadheadhigh_index.py \
        --out data/raw/resources/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "collect"))
sys.path.insert(0, str(ROOT / "scripts" / "normalize"))

from deadbot.source_reader import DEFAULT_TIMEOUT, FetchedPage  # noqa: E402

from collect_blog_post_index import (  # noqa: E402
    MIN_SECONDS_BETWEEN_REQUESTS,
    USER_AGENT,
    Throttle,
    plain_text,
    timestamp,
)
from collect_deadnet_song_essays import read_robots  # noqa: E402
from normalize_song_guide_resources import match_key  # noqa: E402


HOST = "deadheadhigh.com"
SOURCE_ID = "deadheadhigh"
SOURCE_NAME = "Deadhead High"
SITEMAP_URL = f"https://{HOST}/sitemap.xml"
SONG_SECTION = "songs"
SHOW_SECTION = "shows"
GUIDE_SECTIONS = ("guides", "paths")
SONG_RESOURCE_TYPE = "listening-guide"
GUIDE_RESOURCE_TYPE = "listener-guide"
ROBOTS_PATHS = ("/songs/", "/shows/", "/guides/")
OUTPUT_DIR = ROOT / "data" / "raw" / "resources"
RAW_FILENAME = "deadheadhigh-index.jsonl"
TARGETS_PATH = ROOT / "data" / "editorial" / "lore-targets-2026-09-08.json"
FEATURED_PATH = ROOT / "data" / "editorial" / "featured-show-candidates.json"
MAX_DESCRIPTION = 200
MAX_PAGE_BYTES = 400_000
MAX_SITEMAP_FILES = 8
MAX_PAGES = 1200
RETENTION = (
    "Metadata only: page URL, title, at most 200 characters of the page's own meta description "
    "and HTTP status. No guide text is stored."
)

_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
_DESCRIPTION = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_TITLE_SUFFIX = re.compile(r"\s*\|\s*Deadhead High\s*$", re.IGNORECASE)
_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")


# --- transport ---------------------------------------------------------------


class MetadataPageTransport:
    """A ``PageTransport`` that reads at the pass's pace and caps the read."""

    def __init__(self, throttle: Throttle, max_bytes: int = MAX_PAGE_BYTES) -> None:
        self.throttle = throttle
        self.max_bytes = max_bytes

    def get(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> FetchedPage:
        self.throttle.wait()
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.5"})
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content_type = response.headers.get("Content-Type", "") or ""
                body = response.read(self.max_bytes).decode(charset, errors="replace")
                return FetchedPage(getattr(response, "status", 200), response.geturl(), content_type, body)
        except HTTPError as error:
            return FetchedPage(error.code, url, "", "")
        except (URLError, TimeoutError, OSError, ValueError):
            return FetchedPage(0, url, "", "")


# --- helpers -----------------------------------------------------------------


def clean_title(value: str) -> str:
    return _TITLE_SUFFIX.sub("", plain_text(value)).strip()


def page_metadata(body: str) -> dict[str, str]:
    title = _TITLE.search(body)
    description = _DESCRIPTION.search(body)
    return {
        "title": clean_title(title.group(1)) if title else "",
        "description": plain_text(unescape(description.group(1)))[:MAX_DESCRIPTION] if description else "",
    }


def load_targets(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return list(document.get("songs", [])), [show["show_date"] for show in document.get("shows", [])]


def load_featured_dates(path: Path) -> list[str]:
    if not path.exists():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    return [candidate["show_date"] for candidate in document.get("candidates", []) if candidate.get("show_date")]


def sitemap_locations(transport: Any, timeout: float, url: str = SITEMAP_URL, budget: int = MAX_SITEMAP_FILES) -> dict[str, Any]:
    """Every page URL the sitemap lists, following a sitemap index.

    This is ``SiteSearcher._sitemap_locations``' logic, kept here so the pass
    can record each sitemap file's HTTP status alongside the locations.
    """

    findings: dict[str, Any] = {"url": url, "http_status": 0, "files": [], "locations": [], "location_count": 0, "note": ""}
    queue = [(url, 0)]
    locations: list[str] = []
    while queue and len(findings["files"]) < budget:
        current, depth = queue.pop(0)
        page = transport.get(current, timeout=timeout)
        entry = {"url": current, "http_status": page.status, "location_count": 0}
        findings["files"].append(entry)
        if current == url:
            findings["http_status"] = page.status
        if page.status != 200 or not page.body:
            continue
        found = [unescape(location) for location in _LOC.findall(page.body)]
        entry["location_count"] = len(found)
        if "<sitemapindex" in page.body[:2000] and depth < 2:
            queue.extend((child, depth + 1) for child in found)
            continue
        locations.extend(found)
    findings["locations"] = sorted(dict.fromkeys(locations))
    findings["location_count"] = len(findings["locations"])
    findings["note"] = (
        f"{findings['location_count']} page URL(s) across {len(findings['files'])} sitemap file(s)."
        if findings["http_status"] == 200
        else f"The sitemap returned HTTP {findings['http_status']}."
    )
    return findings


def keep_reason(path: str, target_keys: dict[tuple[str, ...], str], target_dates: set[str], featured_dates: set[str]) -> str | None:
    """Why this pass wants a page, or None when it does not."""

    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return None
    section, slug = parts[0], parts[-1]
    if section == SONG_SECTION and len(parts) > 1:
        return "song page"
    if section in GUIDE_SECTIONS and len(parts) > 1:
        return "guide page"
    dates = set(_ISO_DATE.findall(slug))
    if dates & target_dates:
        return "target show date"
    if dates & featured_dates:
        return "featured show date"
    if match_key(slug) in target_keys:
        return "target song slug"
    return None


def resource_type_for(section: str) -> str:
    return SONG_RESOURCE_TYPE if section == SONG_SECTION else GUIDE_RESOURCE_TYPE


# --- collection --------------------------------------------------------------


def page_record(url: str, metadata: dict[str, str], retrieved_at: str, reason: str, http_status: int) -> dict[str, Any]:
    path = urlparse(url).path or "/"
    parts = [part for part in path.strip("/").split("/") if part]
    section = parts[0] if parts else ""
    return {
        "source": SOURCE_ID,
        "source_record_id": path.strip("/"),
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": {
            "record_type": "page",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "resource_type": resource_type_for(section),
            "url_path": path,
            "url_slug": parts[-1] if parts else "",
            "section": section,
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "byline": "",
            "published_date": "",
            "http_status": http_status,
            "kept_because": reason,
        },
    }


def collect(
    transport: Any,
    target_songs: list[dict[str, str]],
    target_dates: list[str],
    featured_dates: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_pages: int = MAX_PAGES,
) -> dict[str, Any]:
    """Run one complete pass, or return the refusal that stopped it."""

    retrieved_at = timestamp()
    result: dict[str, Any] = {
        "host": HOST,
        "source_id": SOURCE_ID,
        "source_name": SOURCE_NAME,
        "retrieved_at": retrieved_at,
        "user_agent": USER_AGENT,
        "robots": {},
        "sitemap": {},
        "kept_by_reason": {},
        "sections_seen": {},
        "pages": [],
        "targets": {song["song_id"]: "not found at source" for song in target_songs},
        "target_shows": dict.fromkeys(target_dates, "not found at source"),
        "status": "ok",
        "note": "",
    }
    robots = read_robots(HOST, transport, timeout, ROBOTS_PATHS)
    result["robots"] = robots
    if not all(robots["paths"].values()):
        result["status"] = "skipped-robots"
        result["note"] = robots["note"]
        return result

    sitemap = sitemap_locations(transport, timeout)
    result["sitemap"] = {key: value for key, value in sitemap.items() if key != "locations"}
    if sitemap["http_status"] != 200 or not sitemap["locations"]:
        result["status"] = "aborted"
        result["note"] = f"{sitemap['note']} The raw file was left unchanged."
        return result

    target_keys = {match_key(song["slug"]): song["song_id"] for song in target_songs}
    target_keys.update({match_key(song["title"]): song["song_id"] for song in target_songs})
    wanted: list[tuple[str, str]] = []
    for location in sitemap["locations"]:
        parsed = urlparse(location)
        if (parsed.hostname or "").casefold().removeprefix("www.") != HOST:
            continue
        path = parsed.path or "/"
        section = path.strip("/").split("/")[0]
        result["sections_seen"][section] = result["sections_seen"].get(section, 0) + 1
        reason = keep_reason(path, target_keys, set(target_dates), set(featured_dates))
        if reason is None:
            continue
        wanted.append((f"https://{HOST}{path}", reason))
        result["kept_by_reason"][reason] = result["kept_by_reason"].get(reason, 0) + 1

    if len(wanted) > max_pages:
        result["status"] = "aborted"
        result["note"] = f"{len(wanted)} pages matched, above the {max_pages}-page ceiling; raise --max-pages and rerun."
        return result

    records: list[dict[str, Any]] = []
    for url, reason in wanted:
        page = transport.get(url, timeout=timeout)
        if page.status != 200:
            result["status"] = "aborted"
            result["note"] = f"{url} returned HTTP {page.status}; the raw file was left unchanged."
            result["pages"] = []
            return result
        records.append(page_record(url, page_metadata(page.body), retrieved_at, reason, page.status))

    result["pages"] = sorted(records, key=lambda record: record["source_url"])
    for record in result["pages"]:
        payload = record["raw_payload"]
        if payload["section"] == SONG_SECTION:
            song_id = target_keys.get(match_key(payload["url_slug"]))
            if song_id:
                result["targets"][song_id] = "found"
        for date in _ISO_DATE.findall(payload["url_slug"]):
            if date in result["target_shows"]:
                result["target_shows"][date] = "found"
    result["note"] = f"{len(result['pages'])} page(s) indexed from {result['sitemap']['location_count']} sitemap location(s)."
    return result


def pass_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": result["source_id"],
        "source_record_id": f"deadheadhigh-index:{result['host']}",
        "retrieved_at": result["retrieved_at"],
        "source_url": SITEMAP_URL,
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": result["host"],
            "source_name": result["source_name"],
            "user_agent": result["user_agent"],
            "robots": result["robots"],
            "sitemap": result["sitemap"],
            "sections_seen": result["sections_seen"],
            "kept_by_reason": result["kept_by_reason"],
            "page_count": len(result["pages"]),
            "targets": result["targets"],
            "target_shows": result["target_shows"],
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
        for line in [pass_record(result), *result["pages"]]:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="directory for the raw JSONL file")
    parser.add_argument("--targets", type=Path, default=TARGETS_PATH, help="the pass's target song and show list")
    parser.add_argument("--featured", type=Path, default=FEATURED_PATH, help="the featured-show candidate list")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="ceiling on pages requested in one pass")
    parser.add_argument("--min-interval", type=float, default=MIN_SECONDS_BETWEEN_REQUESTS, help="minimum seconds between requests")
    parser.add_argument("--max-bytes", type=int, default=MAX_PAGE_BYTES, help="bytes read per page before the parse")
    args = parser.parse_args()

    throttle = Throttle(max(args.min_interval, MIN_SECONDS_BETWEEN_REQUESTS))
    transport = MetadataPageTransport(throttle, args.max_bytes)
    target_songs, target_dates = load_targets(args.targets)
    result = collect(transport, target_songs, target_dates, load_featured_dates(args.featured), max_pages=args.max_pages)

    print(f"{HOST}: robots HTTP {result['robots'].get('http_status')}, {result['robots'].get('note')}")
    print(f"  sitemap: {result['sitemap'].get('note')}")
    print(f"  sections: {result['sections_seen']}")
    print(f"  kept: {result['kept_by_reason']}")
    path = write_raw_file(args.out, result)
    if path is None:
        print(f"  {result['status']}: {result['note']}")
        raise SystemExit(1)
    print(f"  {len(result['pages'])} pages -> {path}")
    print(f"  target songs found: {sum(1 for outcome in result['targets'].values() if outcome == 'found')} of {len(result['targets'])}")
    print(f"  target shows found: {sum(1 for outcome in result['target_shows'].values() if outcome == 'found')} of {len(result['target_shows'])}")


if __name__ == "__main__":
    main()
