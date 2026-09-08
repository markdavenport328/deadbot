#!/usr/bin/env python3
"""Index the public Blogger post feeds of the Grateful Dead research blogs.

The five Blogger sites in ``data/research_sites.json`` (Lost Live Dead,
Hooterollin' Around, Grateful Dead Guide / Deadessays, Dead Sources and
Grateful Seconds) publish an Atom feed listing every post. This collector
walks that feed and preserves one compact raw record per post so the
normalizer can catalog the posts as stored resources.

Metadata only. A stored record keeps the post title, its URL, the published
and updated timestamps, the post labels, the feed's author name, the request
URL, the HTTP status and the retrieval time. Post bodies, summaries and
excerpts are read past and never written to disk.

Host courtesy: ``https://{host}/robots.txt`` is fetched before anything else
and its finding is preserved in the raw file; a host whose robots file
disallows the feed path (or cannot be read) is skipped rather than guessed at.
Requests are made one at a time, at least two seconds apart, with a plain
descriptive User-Agent, and a longer ``Crawl-delay`` is honored.

Retry safety: a host's raw file is rewritten only from a complete successful
pass. Any non-200 page, or a page that is not the expected JSON, aborts that
host and leaves the previous raw file exactly as it was, so a transient
failure can never turn collected posts into an apparent absence.

Usage::

    PYTHONPATH=. python scripts/collect/collect_blog_post_index.py
    PYTHONPATH=. python scripts/collect/collect_blog_post_index.py deadessays \
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
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from deadbot.site_search import load_sites, resolve_site  # noqa: E402
from deadbot.source_reader import DEFAULT_TIMEOUT, FetchedPage, PageTransport  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "raw" / "resources"
USER_AGENT = "Deadbot/0.1 (metadata index; contact via repository)"
ROBOTS_AGENT = "Deadbot"
# Blogger answers a feed request with as many entries as fit its own response
# budget, not with the requested max-results: lostlivedead.blogspot.com returns
# 36 entries for max-results=150 and 54 for the next page. So pagination
# advances by the number of entries a page actually returned and stops on an
# empty page or once the feed's reported total has been reached.
#
# The summary feed carries the same post metadata as
# ``/feeds/posts/default`` while sending roughly a twenty-fifth of the bytes
# (95 KB against 2.4 MB for one page of Lost Live Dead), so it is the default
# path here: identical stored fields, far less taken from the host. Pass
# ``--feed-path /feeds/posts/default`` to use the full feed instead. Post text
# is discarded either way.
FEED_PATH = "/feeds/posts/summary"
PAGE_SIZE = 150
MIN_SECONDS_BETWEEN_REQUESTS = 2.0
MAX_PAGES = 40

# The five Blogger research sites, in the order the directory lists them.
BLOGGER_SITE_IDS = ("lost-live-dead", "hooterollin", "dead-essays", "dead-sources", "grateful-seconds")

# Each site's editorial character decides the canonical resource_type.
RESOURCE_TYPES = {
    "lost-live-dead": "show-history-post",
    "hooterollin": "editorial-blog-post",
    "dead-essays": "editorial-blog-post",
    "dead-sources": "press-transcription",
    "grateful-seconds": "statistics-post",
}

_TAG = re.compile(r"<[^>]+>")


# --- transport ---------------------------------------------------------------


class MetadataIndexTransport:
    """A ``PageTransport`` that names this pass in its User-Agent.

    ``deadbot.source_reader.UrlLibPageTransport`` identifies the runtime
    research reader; a collection pass should say what it is, so this transport
    sends the User-Agent this collector's policy documents.
    """

    def get(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> FetchedPage:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*;q=0.5"})
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                content_type = response.headers.get("Content-Type", "") or ""
                body = response.read(4_000_000).decode(charset, errors="replace")
                return FetchedPage(getattr(response, "status", 200), response.geturl(), content_type, body)
        except HTTPError as error:
            return FetchedPage(error.code, url, "", "")
        except (URLError, TimeoutError, OSError, ValueError):
            return FetchedPage(0, url, "", "")


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


# --- helpers -----------------------------------------------------------------


def timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def plain_text(value: str) -> str:
    """Unescape a feed title and drop the markup Blogger allows inside it.

    Tags are removed rather than replaced with a space so an emphasized word
    keeps its punctuation: ``<b>Veneta</b>,`` reads as ``Veneta,``.
    """

    return re.sub(r"\s+", " ", unescape(_TAG.sub("", value))).strip()


def host_slug(host: str) -> str:
    """The blog's own name: the first label of its host, without ``www.``."""

    host = host.strip().casefold()
    if host.startswith("www."):
        host = host[4:]
    return re.sub(r"[^a-z0-9]+", "-", host.split(".")[0]).strip("-")


def resource_type_for(site_id: str) -> str:
    return RESOURCE_TYPES.get(site_id, "editorial-blog-post")


def feed_page_url(host: str, start_index: int, page_size: int = PAGE_SIZE, feed_path: str = FEED_PATH) -> str:
    query = urlencode({"alt": "json", "max-results": page_size, "start-index": start_index})
    return f"https://{host}{feed_path}?{query}"


def _text(node: Any) -> str:
    return node.get("$t", "") if isinstance(node, dict) else ""


def select_sites(names: list[str]) -> list[dict[str, Any]]:
    """Resolve site names or hosts to Blogger-feed directory entries."""

    directory = load_sites()
    if not names:
        by_id = {site["site_id"]: site for site in directory}
        return [by_id[site_id] for site_id in BLOGGER_SITE_IDS if site_id in by_id]
    chosen: list[dict[str, Any]] = []
    for name in names:
        site = resolve_site(name, directory)
        if site is None:
            raise SystemExit(f"{name!r} is not in data/research_sites.json; name a site or host from the directory.")
        if site.get("search", {}).get("method") != "blogger_feed":
            raise SystemExit(f"{site['name']} does not publish a Blogger feed; this collector only indexes blogger_feed sites.")
        if site not in chosen:
            chosen.append(site)
    return chosen


# --- robots.txt --------------------------------------------------------------


def applicable_robots_rules(body: str) -> list[str]:
    """The directive lines of the groups that apply to this collector."""

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


def read_robots(host: str, transport: PageTransport, throttle: Throttle, timeout: float, feed_path: str = FEED_PATH) -> dict[str, Any]:
    """Fetch and interpret one host's robots.txt for the feed path."""

    url = f"https://{host}/robots.txt"
    throttle.wait()
    page = transport.get(url, timeout=timeout)
    finding: dict[str, Any] = {
        "url": url,
        "http_status": page.status,
        "feed_path": feed_path,
        "feed_path_allowed": False,
        "crawl_delay": None,
        "applicable_rules": [],
        "note": "",
    }
    if page.status == 404 or page.status == 410:
        finding["feed_path_allowed"] = True
        finding["note"] = "The host serves no robots.txt (HTTP 404), so the feed path is unrestricted."
        return finding
    if page.status != 200:
        finding["note"] = f"robots.txt could not be read (HTTP {page.status}); the host was skipped rather than crawled unchecked."
        return finding
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(page.body.splitlines())
    parser.modified()  # crawl_delay() reports nothing until the parse is dated
    finding["feed_path_allowed"] = bool(parser.can_fetch(USER_AGENT, f"https://{host}{feed_path}"))
    delay = parser.crawl_delay(USER_AGENT)
    finding["crawl_delay"] = float(delay) if delay is not None else None
    finding["applicable_rules"] = applicable_robots_rules(page.body)
    finding["note"] = (
        f"robots.txt permits {feed_path}." if finding["feed_path_allowed"] else f"robots.txt disallows {feed_path}; the host was skipped."
    )
    return finding


# --- collection --------------------------------------------------------------


def shape_post(entry: dict[str, Any], site: dict[str, Any], request_url: str, retrieved_at: str) -> dict[str, Any] | None:
    """Build one metadata-only raw record, or None when the entry has no link."""

    url = next(
        (link.get("href") for link in entry.get("link", []) or [] if link.get("rel") == "alternate" and link.get("href")),
        None,
    )
    if not url:
        return None
    labels = [
        label
        for label in dict.fromkeys(
            plain_text(str(category.get("term", ""))) for category in entry.get("category", []) or [] if isinstance(category, dict)
        )
        if label
    ]
    author = next((_text(person.get("name")) for person in entry.get("author", []) or [] if _text(person.get("name"))), "")
    return {
        "source": site["site_id"],
        "source_record_id": _text(entry.get("id")),
        "retrieved_at": retrieved_at,
        "source_url": url,
        "raw_payload": {
            "record_type": "post",
            "host": site["host"],
            "site_name": site["name"],
            "resource_type": resource_type_for(site["site_id"]),
            "title": plain_text(_text(entry.get("title"))),
            "published": _text(entry.get("published")),
            "updated": _text(entry.get("updated")),
            "labels": labels,
            "author": plain_text(author),
            "request_url": request_url,
            "http_status": 200,
        },
    }


def collect_host(
    site: dict[str, Any],
    transport: PageTransport,
    throttle: Throttle,
    *,
    page_size: int = PAGE_SIZE,
    max_pages: int = MAX_PAGES,
    timeout: float = DEFAULT_TIMEOUT,
    feed_path: str = FEED_PATH,
) -> dict[str, Any]:
    """Walk one host's post feed and return a complete pass, or a refusal."""

    host = site["host"].strip().casefold()
    retrieved_at = timestamp()
    result: dict[str, Any] = {
        "site_id": site["site_id"],
        "site_name": site["name"],
        "host": host,
        "host_slug": host_slug(host),
        "resource_type": resource_type_for(site["site_id"]),
        "retrieved_at": retrieved_at,
        "user_agent": USER_AGENT,
        "feed_path": feed_path,
        "robots": {},
        "pages": [],
        "page_count": 0,
        "entry_count": 0,
        "skipped_entries": 0,
        "total_results_reported": None,
        "status": "ok",
        "note": "",
        "posts": [],
    }
    robots = read_robots(host, transport, throttle, timeout, feed_path)
    result["robots"] = robots
    if not robots["feed_path_allowed"]:
        result["status"] = "skipped-robots"
        result["note"] = robots["note"]
        return result
    if robots["crawl_delay"] and robots["crawl_delay"] > throttle.min_interval:
        throttle.min_interval = robots["crawl_delay"]

    posts: dict[str, dict[str, Any]] = {}
    start_index = 1
    for _ in range(max_pages):
        url = feed_page_url(host, start_index, page_size, feed_path)
        throttle.wait()
        page = transport.get(url, timeout=timeout)
        if page.status != 200:
            result["status"] = "aborted"
            result["note"] = f"{url} returned HTTP {page.status}; the host's raw file was left unchanged."
            result["posts"] = []
            return result
        try:
            document = json.loads(page.body)
        except json.JSONDecodeError:
            result["status"] = "aborted"
            result["note"] = f"{url} did not return the expected JSON feed; the host's raw file was left unchanged."
            result["posts"] = []
            return result
        feed = document.get("feed", {}) if isinstance(document, dict) else {}
        entries = feed.get("entry") or []
        total = _text(feed.get("openSearch$totalResults"))
        if total.isdigit():
            result["total_results_reported"] = int(total)
        for entry in entries:
            record = shape_post(entry, {**site, "host": host}, url, retrieved_at)
            if record is None:
                result["skipped_entries"] += 1
                continue
            posts.setdefault(record["source_url"], record)
        result["pages"].append({"url": url, "http_status": page.status, "entry_count": len(entries)})
        result["page_count"] += 1
        result["entry_count"] += len(entries)
        if not entries:
            break
        start_index += len(entries)
        total_reported = result["total_results_reported"]
        if total_reported is not None and start_index > total_reported:
            break
    else:
        result["status"] = "aborted"
        result["note"] = f"{host} was still returning entries after {max_pages} requests; raise --max-pages and rerun."
        result["posts"] = []
        return result
    result["posts"] = [posts[url] for url in sorted(posts)]
    result["note"] = f"{len(result['posts'])} posts indexed from {result['page_count']} feed page(s)."
    return result


def pass_record(result: dict[str, Any]) -> dict[str, Any]:
    """The raw file's first line: what this pass asked for and what it found."""

    return {
        "source": result["site_id"],
        "source_record_id": f"blog-post-index:{result['host']}",
        "retrieved_at": result["retrieved_at"],
        "source_url": f"https://{result['host']}{FEED_PATH}",
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": result["host"],
            "site_name": result["site_name"],
            "resource_type": result["resource_type"],
            "user_agent": result["user_agent"],
            "feed_path": result["feed_path"],
            "robots": result["robots"],
            "pages": result["pages"],
            "page_count": result["page_count"],
            "entry_count": result["entry_count"],
            "skipped_entries": result["skipped_entries"],
            "total_results_reported": result["total_results_reported"],
            "post_count": len(result["posts"]),
            "status": result["status"],
            "note": result["note"],
            "retention": "Metadata only: post title, URL, dates, labels and author. No post content, summary or excerpt is stored.",
        },
    }


def write_host_file(out_dir: Path, result: dict[str, Any]) -> Path | None:
    """Write a host's raw file from a complete pass; keep the old file otherwise."""

    if result["status"] != "ok":
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"blog-post-index-{result['host_slug']}.jsonl"
    lines = [pass_record(result), *result["posts"]]
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sites", nargs="*", help="site names or hosts to index (default: the five Blogger research sites)")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="directory for the raw JSONL files")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE, help="feed max-results per request")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="request ceiling per host")
    parser.add_argument("--min-interval", type=float, default=MIN_SECONDS_BETWEEN_REQUESTS, help="minimum seconds between requests")
    parser.add_argument("--feed-path", default=FEED_PATH, help="Blogger feed path to walk (the summary feed carries the same metadata for far fewer bytes)")
    args = parser.parse_args()

    sites = select_sites(args.sites)
    transport = MetadataIndexTransport()
    throttle = Throttle(max(args.min_interval, MIN_SECONDS_BETWEEN_REQUESTS))
    failures = 0
    for site in sites:
        result = collect_host(site, transport, throttle, page_size=args.page_size, max_pages=args.max_pages, feed_path=args.feed_path)
        path = write_host_file(args.out, result)
        robots = result["robots"]
        print(f"{result['site_name']} ({result['host']}): robots HTTP {robots.get('http_status')}, feed allowed={robots.get('feed_path_allowed')}")
        if path is None:
            failures += 1
            print(f"  {result['status']}: {result['note']}")
            continue
        print(f"  {len(result['posts'])} posts across {result['page_count']} page(s) -> {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    if failures:
        print(f"{failures} of {len(sites)} host(s) were skipped or aborted; their raw files were left unchanged.")


if __name__ == "__main__":
    main()
