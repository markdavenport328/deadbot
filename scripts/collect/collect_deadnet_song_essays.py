#!/usr/bin/env python3
"""Index Dead.net's "Greatest Stories Ever Told" song essays, metadata only.

David Dodd's essay series has one page per song at
``/features/greatest-stories-ever-told/greatest-stories-ever-told-<slug>``.
This collector discovers those pages, keeps one compact record for each, and
also reads the official ``/song/<slug>`` page for each target song so a song
with no essay still gains a first-party link.

Discovery, in the order the plan asks for it:

1. ``https://www.dead.net/sitemap.xml`` (following a sitemap index). The site's
   sitemap lists seven section pages and no essays, so this step normally
   records an absence rather than a list.
2. The series' own index, the taxonomy listing that Dead.net links every essay
   from (``/taxonomy/term/4424``), walked page by page until a page holds no
   essays. Each listing row carries the essay's URL, title, byline and posting
   date, so one request yields ten essays' metadata.
3. For a target song still missing, a constructed candidate URL confirmed by
   one request. Dead.net's path builder drops stopwords ("Attics Of My Life" is
   ``attics-my-life``) and apostrophes ("He's Gone" is ``hes-gone``), so the
   candidates cover those spellings.

Metadata only. A stored record keeps the page URL, its title, at most 200
characters of the page's own meta description, the byline, the posting date,
the HTTP status and the retrieval time. No essay text is written to any file.

Host courtesy: ``https://www.dead.net/robots.txt`` is read first and its
finding is preserved in the raw file; a disallowed path is skipped rather than
crawled unchecked. Requests go one at a time, at least two seconds apart, with
``User-Agent: Deadbot/0.1 (metadata index; contact via repository)``, and a
longer ``Crawl-delay`` is honored.

Retry safety: the raw file is rewritten only from a complete successful pass.
Any non-200 index page aborts the pass and leaves the previous file untouched,
so a transient failure can never turn a collected essay into an apparent
absence.

Usage::

    PYTHONPATH=. python scripts/collect/collect_deadnet_song_essays.py
    PYTHONPATH=. python scripts/collect/collect_deadnet_song_essays.py \
        --out data/raw/resources/ --max-pages 30
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.robotparser
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "collect"))
sys.path.insert(0, str(ROOT / "scripts" / "normalize"))

from deadbot.deadnet import (  # noqa: E402
    DeadnetConfig,
    DeadnetResearchAdapter,
    EntityReadRequest,
    EntityType,
    UrlLibMetadataTransport,
)
from deadbot.source_reader import DEFAULT_TIMEOUT, FetchedPage  # noqa: E402

from collect_blog_post_index import (  # noqa: E402
    MIN_SECONDS_BETWEEN_REQUESTS,
    USER_AGENT,
    Throttle,
    applicable_robots_rules,
    plain_text,
    timestamp,
)
from normalize_song_guide_resources import CONTRACTION_REMNANTS, STOPWORDS, match_key, slug_aliases  # noqa: E402


HOST = "www.dead.net"
SOURCE_ID = "deadnet-editorial"
SOURCE_NAME = "Grateful Dead / Dead.net"
SITEMAP_URL = f"https://{HOST}/sitemap.xml"
# The series index: the taxonomy term Dead.net files every essay under, and the
# only page on the site that enumerates them.
SERIES_TERM_URL = f"https://{HOST}/taxonomy/term/4424"
SERIES_INDEX_LABEL = "series index"
ESSAY_PATH_PREFIX = "/features/greatest-stories-ever-told/"
ESSAY_SLUG_PREFIX = "greatest-stories-ever-told-"
SONG_PATH_PREFIX = "/song/"
ESSAY_RESOURCE_TYPE = "song-history-essay"
SONG_PAGE_RESOURCE_TYPE = "catalog-song-page"
ROBOTS_AGENT = "Deadbot"
ROBOTS_PATHS = (ESSAY_PATH_PREFIX, SONG_PATH_PREFIX)
OUTPUT_DIR = ROOT / "data" / "raw" / "resources"
RAW_FILENAME = "deadnet-greatest-stories.jsonl"
TARGETS_PATH = ROOT / "data" / "editorial" / "lore-targets-2026-09-08.json"
MAX_DESCRIPTION = 200
MAX_INDEX_PAGES = 30
MAX_SITEMAP_FILES = 6
# Dead.net serves about 900 KB of navigation, store and comment markup before a
# story's own byline and date. The read is capped just past that so those two
# fields can be kept; nothing but title, description, byline and date survives
# the parse.
MAX_PAGE_BYTES = 1_200_000
RETENTION = (
    "Metadata only: page URL, title, at most 200 characters of the page's own meta description, "
    "byline, posting date and HTTP status. No essay, lyric or comment text is stored."
)

_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
_DESCRIPTION = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_BYLINE = re.compile(r">\s*By\s+([A-Z][^<>]{1,58}?)\s*<")
_TIME = re.compile(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})')
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_INDEX_ARTICLE = re.compile(r'<article[^>]*about="(' + re.escape(ESSAY_PATH_PREFIX) + r'[^"?#]+)"[^>]*>')
_INDEX_TITLE = re.compile(r"field--name-title[^>]*>(.*?)</span>", re.IGNORECASE | re.DOTALL)
_TITLE_SUFFIX = re.compile(r"\s*\|\s*Grateful Dead\s*$", re.IGNORECASE)


# --- transport ---------------------------------------------------------------


class MetadataPageTransport:
    """A ``PageTransport`` that reads at the pass's pace and caps the read.

    The throttle lives in the transport so every request made through this
    module — robots, sitemap, index page, essay page — is paced, including the
    ones made by borrowed sitemap-walking logic.
    """

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


class ThrottledDeadnetTransport:
    """The reviewed Dead.net metadata transport, at the pass's pace."""

    def __init__(self, throttle: Throttle, allowed_hosts: frozenset[str]) -> None:
        self.throttle = throttle
        self.inner = UrlLibMetadataTransport(allowed_hosts)

    def get(self, url: str, *, params=None, timeout: float = DEFAULT_TIMEOUT):
        self.throttle.wait()
        return self.inner.get(url, params=params or {}, timeout=timeout)


# --- helpers -----------------------------------------------------------------


def index_page_url(page: int) -> str:
    return SERIES_TERM_URL if page <= 0 else f"{SERIES_TERM_URL}?page={page}"


def essay_url(slug: str) -> str:
    return f"https://{HOST}{ESSAY_PATH_PREFIX}{ESSAY_SLUG_PREFIX}{slug}"


def essay_slug(path_or_url: str) -> str:
    tail = path_or_url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    return tail.removeprefix(ESSAY_SLUG_PREFIX)


def clean_title(value: str) -> str:
    return _TITLE_SUFFIX.sub("", plain_text(value)).strip()


def page_metadata(body: str) -> dict[str, str]:
    """Title, short description, byline and posting date; nothing else."""

    title = _TITLE.search(body)
    description = _DESCRIPTION.search(body)
    byline = _BYLINE.search(body)
    posted = _TIME.search(body)
    return {
        "title": clean_title(title.group(1)) if title else "",
        "description": plain_text(unescape(description.group(1)))[:MAX_DESCRIPTION] if description else "",
        "byline": plain_text(byline.group(1)) if byline else "",
        "published_date": posted.group(1) if posted else "",
    }


def candidate_essay_slugs(song: dict[str, str]) -> list[str]:
    """The spellings Dead.net's path builder could have given this song."""

    found: list[str] = []

    def add(value: str) -> None:
        if value and value not in found:
            found.append(value)

    for base in (song.get("slug") or "", re.sub(r"[^a-z0-9]+", "-", (song.get("title") or "").casefold()).strip("-")):
        if not base:
            continue
        add(base)
        tokens: list[str] = []
        for token in base.split("-"):
            if not token:
                continue
            if token in CONTRACTION_REMNANTS and tokens:
                tokens[-1] += token
            else:
                tokens.append(token)
        add("-".join(tokens))
        add("-".join(token for token in tokens if token not in STOPWORDS))
    return found


def load_targets(path: Path) -> list[dict[str, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return list(document.get("songs", []))


# --- robots ------------------------------------------------------------------


def read_robots(host: str, transport: Any, timeout: float = DEFAULT_TIMEOUT, paths: tuple[str, ...] = ROBOTS_PATHS) -> dict[str, Any]:
    """Fetch and interpret one host's robots.txt for the paths this pass uses."""

    url = f"https://{host}/robots.txt"
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
    parser.modified()  # crawl_delay() reports nothing until the parse is dated
    finding["paths"] = {path: bool(parser.can_fetch(USER_AGENT, f"https://{host}{path}")) for path in paths}
    delay = parser.crawl_delay(USER_AGENT)
    finding["crawl_delay"] = float(delay) if delay is not None else None
    finding["applicable_rules"] = applicable_robots_rules(page.body)
    allowed = [path for path, ok in finding["paths"].items() if ok]
    refused = [path for path, ok in finding["paths"].items() if not ok]
    finding["note"] = "robots.txt permits " + ", ".join(allowed) + ("; it disallows " + ", ".join(refused) if refused else ".")
    return finding


# --- discovery ---------------------------------------------------------------


def sitemap_findings(transport: Any, timeout: float = DEFAULT_TIMEOUT, url: str = SITEMAP_URL, budget: int = MAX_SITEMAP_FILES) -> dict[str, Any]:
    """What the site's sitemap says about the essay series."""

    findings: dict[str, Any] = {"url": url, "http_status": 0, "files": [], "location_count": 0, "essay_urls": [], "essay_url_count": 0, "note": ""}
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
    findings["location_count"] = len(locations)
    findings["essay_urls"] = sorted({location for location in locations if ESSAY_PATH_PREFIX in location})
    findings["essay_url_count"] = len(findings["essay_urls"])
    findings["note"] = (
        f"{findings['essay_url_count']} essay URL(s) in {findings['location_count']} sitemap location(s)."
        if findings["http_status"] == 200
        else f"The sitemap returned HTTP {findings['http_status']}."
    )
    return findings


def parse_index_page(body: str) -> list[dict[str, str]]:
    """One record per essay teaser on a series-index page, in page order."""

    matches = list(_INDEX_ARTICLE.finditer(body))
    records: list[dict[str, str]] = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(body)
        segment = body[match.end() : end]
        title = _INDEX_TITLE.search(segment)
        byline = _BYLINE.search(segment)
        posted = _TIME.search(segment)
        records.append(
            {
                "url_path": match.group(1),
                "title": clean_title(title.group(1)) if title else "",
                "byline": plain_text(byline.group(1)) if byline else "",
                "published_date": posted.group(1) if posted else "",
            }
        )
    return records


# --- records -----------------------------------------------------------------


def essay_record(url: str, metadata: dict[str, str], retrieved_at: str, discovered_via: str, http_status: int = 200) -> dict[str, Any]:
    slug = essay_slug(url)
    return {
        "source": SOURCE_ID,
        "source_record_id": f"{ESSAY_SLUG_PREFIX}{slug}",
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": {
            "record_type": "essay",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "resource_type": ESSAY_RESOURCE_TYPE,
            "url_slug": slug,
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "byline": metadata.get("byline", ""),
            "published_date": metadata.get("published_date", ""),
            "http_status": http_status,
            "discovered_via": discovered_via,
        },
    }


def song_page_record(song: dict[str, str], url: str, metadata: dict[str, str], retrieved_at: str) -> dict[str, Any]:
    return {
        "source": SOURCE_ID,
        "source_record_id": f"song/{song['slug']}",
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": {
            "record_type": "song_page",
            "host": HOST,
            "source_name": SOURCE_NAME,
            "resource_type": SONG_PAGE_RESOURCE_TYPE,
            "url_slug": song["slug"],
            "song_id": song["song_id"],
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "byline": "",
            "published_date": "",
            "http_status": 200,
            "discovered_via": "target slug",
        },
    }


# --- collection --------------------------------------------------------------


def collect(
    transport: Any,
    song_adapter: DeadnetResearchAdapter | None,
    targets: list[dict[str, str]],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_pages: int = MAX_INDEX_PAGES,
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
        "index": {"url": SERIES_TERM_URL, "pages": [], "page_count": 0, "essay_count": 0, "note": "not walked"},
        "discovery": "",
        "candidate_attempts": [],
        "song_page_attempts": [],
        "essays": [],
        "song_pages": [],
        "targets": {
            target["song_id"]: {**target, "essay": "not attempted", "song_page": "not attempted"} for target in targets
        },
        "status": "ok",
        "note": "",
    }
    robots = read_robots(HOST, transport, timeout)
    result["robots"] = robots
    if not robots["paths"].get(ESSAY_PATH_PREFIX):
        result["status"] = "skipped-robots"
        result["note"] = robots["note"]
        return result

    result["sitemap"] = sitemap_findings(transport, timeout)
    essays: dict[str, dict[str, Any]] = {}

    if result["sitemap"]["essay_urls"]:
        result["discovery"] = "sitemap"
        for url in result["sitemap"]["essay_urls"]:
            page = transport.get(url, timeout=timeout)
            if page.status != 200:
                continue
            essays[essay_slug(url)] = essay_record(url, page_metadata(page.body), retrieved_at, "sitemap", page.status)
        result["index"]["note"] = "The sitemap listed the essays; the series index was not walked."
    else:
        result["discovery"] = SERIES_INDEX_LABEL
        for page_number in range(max_pages):
            url = index_page_url(page_number)
            page = transport.get(url, timeout=timeout)
            if page.status != 200:
                result["status"] = "aborted"
                result["note"] = f"{url} returned HTTP {page.status}; the raw file was left unchanged."
                result["essays"] = []
                return result
            teasers = parse_index_page(page.body)
            result["index"]["pages"].append({"url": url, "http_status": page.status, "essay_count": len(teasers)})
            result["index"]["page_count"] += 1
            if not teasers:
                break
            for teaser in teasers:
                slug = essay_slug(teaser["url_path"])
                essays.setdefault(
                    slug,
                    essay_record(f"https://{HOST}{teaser['url_path']}", teaser, retrieved_at, SERIES_INDEX_LABEL),
                )
        else:
            result["status"] = "aborted"
            result["note"] = f"The series index still held essays after {max_pages} pages; raise --max-pages and rerun."
            result["essays"] = []
            return result
        result["index"]["essay_count"] = len(essays)
        result["index"]["note"] = f"{len(essays)} essay(s) across {result['index']['page_count']} index page(s)."

    # Every target song is attempted, whatever discovery found.
    collected_keys = {match_key(alias): slug for slug in essays for alias in slug_aliases(slug)}
    for target in targets:
        outcome = result["targets"][target["song_id"]]
        if any(match_key(value) in collected_keys for value in (target.get("slug", ""), target.get("title", "")) if value):
            outcome["essay"] = "found"
            continue
        outcome["essay"] = "not found at source"
        for candidate in candidate_essay_slugs(target):
            if candidate in essays:
                outcome["essay"] = "found"
                break
            url = essay_url(candidate)
            page = transport.get(url, timeout=timeout)
            result["candidate_attempts"].append(
                {"song_id": target["song_id"], "slug": candidate, "url": url, "http_status": page.status}
            )
            if page.status != 200:
                continue
            essays[candidate] = essay_record(url, page_metadata(page.body), retrieved_at, "candidate url", page.status)
            for alias in slug_aliases(candidate):
                collected_keys[match_key(alias)] = candidate
            outcome["essay"] = "found"
            break

    result["essays"] = [essays[slug] for slug in sorted(essays)]

    if song_adapter is not None and robots["paths"].get(SONG_PATH_PREFIX):
        for target in targets:
            outcome = result["targets"][target["song_id"]]
            read = song_adapter.read(EntityReadRequest(EntityType.SONG, target["slug"]))
            result["song_page_attempts"].append(
                {
                    "song_id": target["song_id"],
                    "url": f"https://{HOST}{SONG_PATH_PREFIX}{target['slug']}",
                    "state": str(read.state),
                    "message": read.message or "",
                }
            )
            if not read.is_success or not read.records:
                outcome["song_page"] = "not found at source"
                continue
            record = read.records[0]
            url = record.url or f"https://{HOST}{SONG_PATH_PREFIX}{target['slug']}"
            metadata = {"title": record.title or "", "description": (record.description or "")[:MAX_DESCRIPTION]}
            result["song_pages"].append(song_page_record(target, url, metadata, retrieved_at))
            outcome["song_page"] = "found"
    elif song_adapter is not None:
        result["note"] = f"robots.txt disallows {SONG_PATH_PREFIX}; no song page was read."

    result["note"] = result["note"] or (
        f"{len(result['essays'])} essay(s) and {len(result['song_pages'])} song page(s) indexed; discovery: {result['discovery']}."
    )
    return result


def pass_record(result: dict[str, Any]) -> dict[str, Any]:
    """The raw file's first line: what this pass asked for and what it found."""

    return {
        "source": result["source_id"],
        "source_record_id": f"deadnet-greatest-stories:{result['host']}",
        "retrieved_at": result["retrieved_at"],
        "source_url": SERIES_TERM_URL,
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": result["host"],
            "source_name": result["source_name"],
            "resource_type": ESSAY_RESOURCE_TYPE,
            "user_agent": result["user_agent"],
            "robots": result["robots"],
            "sitemap": result["sitemap"],
            "index": result["index"],
            "discovery": result["discovery"],
            "candidate_attempts": result["candidate_attempts"],
            "song_page_attempts": result["song_page_attempts"],
            "essay_count": len(result["essays"]),
            "song_page_count": len(result["song_pages"]),
            "targets": result["targets"],
            "status": result["status"],
            "note": result["note"],
            "retention": RETENTION,
        },
    }


def write_raw_file(out_dir: Path, result: dict[str, Any]) -> Path | None:
    """Write the raw file from a complete pass; keep the old file otherwise."""

    if result["status"] != "ok":
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RAW_FILENAME
    with path.open("w", encoding="utf-8") as handle:
        for line in [pass_record(result), *result["essays"], *result["song_pages"]]:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="directory for the raw JSONL file")
    parser.add_argument("--targets", type=Path, default=TARGETS_PATH, help="the pass's target song list")
    parser.add_argument("--max-pages", type=int, default=MAX_INDEX_PAGES, help="index-page ceiling")
    parser.add_argument("--min-interval", type=float, default=MIN_SECONDS_BETWEEN_REQUESTS, help="minimum seconds between requests")
    parser.add_argument("--max-bytes", type=int, default=MAX_PAGE_BYTES, help="bytes read per page before the parse")
    parser.add_argument("--skip-song-pages", action="store_true", help="index the essays only")
    args = parser.parse_args()

    throttle = Throttle(max(args.min_interval, MIN_SECONDS_BETWEEN_REQUESTS))
    transport = MetadataPageTransport(throttle, args.max_bytes)
    config = DeadnetConfig()
    adapter = None if args.skip_song_pages else DeadnetResearchAdapter(ThrottledDeadnetTransport(throttle, config.allowed_hosts), config)
    result = collect(transport, adapter, load_targets(args.targets), max_pages=args.max_pages)

    robots = result["robots"]
    print(f"{HOST}: robots HTTP {robots.get('http_status')}, {robots.get('note')}")
    print(f"  sitemap: {result['sitemap'].get('note')}")
    print(f"  discovery: {result['discovery']}; {result['index'].get('note')}")
    if result["candidate_attempts"]:
        print(f"  candidate URLs tried: {len(result['candidate_attempts'])}")
    path = write_raw_file(args.out, result)
    if path is None:
        print(f"  {result['status']}: {result['note']}")
        raise SystemExit(1)
    print(f"  {len(result['essays'])} essays, {len(result['song_pages'])} song pages -> {path}")
    for song_id, outcome in result["targets"].items():
        print(f"    {song_id}: essay {outcome['essay']}, song page {outcome['song_page']}")


if __name__ == "__main__":
    main()
