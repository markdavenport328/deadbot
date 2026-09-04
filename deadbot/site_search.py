"""Search a research site through its own search mechanism.

There is no search-engine key. Each site is searched the way its own pages
are: Blogger's post feed, Omeka's item API, archive.org's advanced search, a
WordPress REST search, or the sitemap when a site has none of those. The site
directory in ``data/research_sites.json`` suggests where to look and how; an
unknown host is probed for each mechanism in turn.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlparse

from deadbot.source_reader import DEFAULT_TIMEOUT, FetchedPage, PageTransport, UrlLibPageTransport


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITES_PATH = ROOT / "data" / "research_sites.json"
METHODS = ("blogger_feed", "omeka_api", "archive_search", "wordpress_api", "sitemap", "none")
_MAX_SITEMAP_FILES = 6
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str | None = None
    published: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": self.title, "url": self.url, "snippet": self.snippet, "published": self.published}
        payload.update(self.extra)
        return payload


@dataclass(frozen=True)
class SearchResult:
    state: str  # ok | empty | unavailable | unsupported | invalid
    site: str
    method: str
    query: str
    hits: tuple[SearchHit, ...] = ()
    message: str | None = None
    total: int | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "site": self.site,
            "method": self.method,
            "query": self.query,
            "total": self.total,
            "message": self.message,
            "hits": [hit.as_payload() for hit in self.hits],
        }


def load_sites(path: Path = DEFAULT_SITES_PATH) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    sites = document.get("sites") if isinstance(document, dict) else None
    if not isinstance(sites, list):
        raise ValueError("research_sites.json must contain a 'sites' list")
    for site in sites:
        method = site.get("search", {}).get("method", "none")
        if method not in METHODS:
            raise ValueError(f"site {site.get('site_id')} has unknown search method {method!r}")
    return sites


def _bare_host(value: str) -> str:
    value = value.strip().casefold()
    if "://" in value:
        value = urlparse(value).hostname or value
    value = value.split("/")[0]
    return value[4:] if value.startswith("www.") else value


def resolve_site(name_or_host: str, sites: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match a directory entry by id, name, alias, or host (with or without www)."""

    needle = name_or_host.strip().casefold()
    host_needle = _bare_host(name_or_host)
    for site in sites:
        names = {site.get("site_id", "").casefold(), site.get("name", "").casefold(), *[alias.casefold() for alias in site.get("aliases", [])]}
        if needle in names or host_needle == _bare_host(site.get("host", "")):
            return site
    return None


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG.sub(" ", value))).strip()


def _snippet(text: str, query: str, width: int = 320) -> str:
    text = _strip_html(text)
    if not text:
        return ""
    terms = [term for term in re.findall(r"[a-z0-9][a-z0-9'-]+", query.casefold()) if len(term) >= 3]
    lowered = text.casefold()
    position = min((lowered.find(term) for term in terms if lowered.find(term) >= 0), default=-1)
    if position <= 0:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, position - width // 3)
    end = min(len(text), start + width)
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


class SiteSearcher:
    """Search one site with the mechanism the site itself offers."""

    def __init__(self, transport: PageTransport | None = None, sites: list[dict[str, Any]] | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.transport = transport or UrlLibPageTransport()
        self.sites = sites if sites is not None else load_sites()
        self.timeout = timeout

    def search(self, site: str, query: str, limit: int = 8) -> SearchResult:
        query = re.sub(r"\s+", " ", query or "").strip()
        if not query or len(query) > 200:
            return SearchResult("invalid", site, "none", query, message="A query of 1-200 characters is required.")
        limit = max(1, min(limit, 20))
        entry = resolve_site(site, self.sites)
        # Keep the directory's host exactly as written: some sites (GDAO) only
        # answer on www., and Blogger redirects are handled by the transport.
        host = entry["host"].strip().casefold() if entry else _bare_host(site)
        if not host or "." not in host:
            return SearchResult("invalid", site, "none", query, message="Name a site from the research directory or give a host such as lostlivedead.blogspot.com.")
        label = entry["name"] if entry else host
        if entry:
            method = entry.get("search", {}).get("method", "none")
            if method == "none":
                return SearchResult("unsupported", label, method, query, message=entry.get("search", {}).get("notes") or "This site has no callable search; read its pages directly with read_page.")
            return self._run(method, host, entry, query, limit, label)
        # Unknown host: probe the mechanisms a site is likely to have.
        for method in ("wordpress_api", "blogger_feed", "sitemap"):
            result = self._run(method, host, None, query, limit, label)
            if result.state in {"ok", "empty"} and (result.state == "ok" or method == "sitemap"):
                return result
        return SearchResult("unsupported", label, "none", query, message="No search mechanism answered for this host; if you have a page URL, read it with read_page.")

    # -- dispatch
    def _run(self, method: str, host: str, entry: dict[str, Any] | None, query: str, limit: int, label: str) -> SearchResult:
        try:
            if method == "blogger_feed":
                return self._blogger(host, query, limit, label)
            if method == "omeka_api":
                return self._omeka(host, entry or {}, query, limit, label)
            if method == "archive_search":
                return self._archive(query, limit, label)
            if method == "wordpress_api":
                return self._wordpress(host, query, limit, label)
            if method == "sitemap":
                return self._sitemap(host, query, limit, label)
        except Exception as error:  # a broken site must not kill the turn
            return SearchResult("unavailable", label, method, query, message=f"Search failed: {type(error).__name__}.")
        return SearchResult("unsupported", label, method, query, message="Unknown search method.")

    def _get(self, url: str) -> FetchedPage:
        return self.transport.get(url, timeout=self.timeout)

    @staticmethod
    def _json(page: FetchedPage) -> Any:
        if page.status < 200 or page.status >= 300 or not page.body.strip():
            return None
        try:
            return json.loads(page.body)
        except json.JSONDecodeError:
            return None

    # -- adapters
    def _blogger(self, host: str, query: str, limit: int, label: str) -> SearchResult:
        url = f"https://{host}/feeds/posts/default?q={quote_plus(query)}&alt=json&max-results={limit}"
        page = self._get(url)
        document = self._json(page)
        if document is None:
            return SearchResult("unavailable", label, "blogger_feed", query, message=f"The blog feed returned HTTP {page.status}.")
        feed = document.get("feed", {}) if isinstance(document, dict) else {}
        total_text = feed.get("openSearch$totalResults", {}).get("$t")
        hits = []
        for entry in feed.get("entry", []) or []:
            title = _strip_html(entry.get("title", {}).get("$t", "")) or "(untitled)"
            link = next((item.get("href") for item in entry.get("link", []) if item.get("rel") == "alternate" and item.get("href")), None)
            if not link:
                continue
            body = entry.get("content", {}).get("$t") or entry.get("summary", {}).get("$t") or ""
            published = (entry.get("published", {}).get("$t") or "")[:10] or None
            author = next((a.get("name", {}).get("$t") for a in entry.get("author", []) if a.get("name")), None)
            hits.append(SearchHit(title, link, _snippet(body, query), published, {"author": author} if author else {}))
        total = int(total_text) if isinstance(total_text, str) and total_text.isdigit() else None
        return SearchResult("ok" if hits else "empty", label, "blogger_feed", query, tuple(hits[:limit]), total=total, message=None if hits else "No posts matched.")

    def _omeka(self, host: str, entry: dict[str, Any], query: str, limit: int, label: str) -> SearchResult:
        url = f"https://{host}/api/items?fulltext_search={quote_plus(query)}&per_page={limit}"
        page = self._get(url)
        items = self._json(page)
        if not isinstance(items, list):
            return SearchResult("unavailable", label, "omeka_api", query, message=f"The archive API returned HTTP {page.status}.")
        item_url = entry.get("search", {}).get("item_url") or f"https://{host}/items/show/{{id}}"
        hits = []
        for item in items:
            if not isinstance(item, dict) or not item.get("o:id"):
                continue
            title = item.get("o:title") or "(untitled)"
            description = ""
            for value in item.get("dcterms:description", []) or []:
                if isinstance(value, dict) and value.get("@value"):
                    description = str(value["@value"])
                    break
            created = None
            for value in item.get("dcterms:created", []) or item.get("dcterms:date", []) or []:
                if isinstance(value, dict) and value.get("@value"):
                    created = str(value["@value"])[:40]
                    break
            hits.append(SearchHit(str(title), item_url.format(id=item["o:id"]), _snippet(description, query) or None, created))
        return SearchResult("ok" if hits else "empty", label, "omeka_api", query, tuple(hits), message=None if hits else "No archive items matched.")

    def _archive(self, query: str, limit: int, label: str) -> SearchResult:
        date_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", query)
        if date_match:
            lucene = f"collection:GratefulDead AND date:{query}"
        else:
            safe = re.sub(r'[\\"()\[\]{}:^~*?]', " ", query).strip()
            lucene = f"collection:GratefulDead AND ({safe})"
        fields = "&".join(f"fl%5B%5D={name}" for name in ("identifier", "title", "date", "avg_rating", "num_reviews", "downloads", "source", "description"))
        url = f"https://archive.org/advancedsearch.php?q={quote(lucene)}&{fields}&sort%5B%5D=num_reviews+desc&rows={limit}&output=json"
        page = self._get(url)
        document = self._json(page)
        if not isinstance(document, dict):
            return SearchResult("unavailable", label, "archive_search", query, message=f"archive.org returned HTTP {page.status}.")
        response = document.get("response", {})
        hits = []
        for doc in response.get("docs", []) or []:
            identifier = doc.get("identifier")
            if not identifier:
                continue
            description = doc.get("description")
            if isinstance(description, list):
                description = " ".join(str(part) for part in description)
            extra = {key: doc.get(key) for key in ("avg_rating", "num_reviews", "downloads", "source") if doc.get(key) is not None}
            extra["archive_identifier"] = identifier
            hits.append(SearchHit(str(doc.get("title") or identifier), f"https://archive.org/details/{identifier}", _snippet(str(description or ""), query) or None, str(doc.get("date") or "")[:10] or None, extra))
        total = response.get("numFound") if isinstance(response.get("numFound"), int) else None
        return SearchResult("ok" if hits else "empty", label, "archive_search", query, tuple(hits), total=total, message=None if hits else "No items matched in the Grateful Dead collection.")

    def _wordpress(self, host: str, query: str, limit: int, label: str) -> SearchResult:
        url = f"https://{host}/wp-json/wp/v2/search?search={quote_plus(query)}&per_page={limit}"
        page = self._get(url)
        items = self._json(page)
        if not isinstance(items, list):
            return SearchResult("unavailable", label, "wordpress_api", query, message=f"No WordPress search API (HTTP {page.status}).")
        hits = []
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                title = item.get("title")
                if isinstance(title, dict):
                    title = title.get("rendered")
                hits.append(SearchHit(_strip_html(str(title or "(untitled)")), str(item["url"])))
        return SearchResult("ok" if hits else "empty", label, "wordpress_api", query, tuple(hits), message=None if hits else "No pages matched.")

    def _sitemap(self, host: str, query: str, limit: int, label: str) -> SearchResult:
        locations = self._sitemap_locations(f"https://{host}/sitemap.xml", 0)
        if not locations:
            return SearchResult("unavailable", label, "sitemap", query, message="No sitemap was found for this host.")
        terms = [term for term in re.findall(r"[a-z0-9][a-z0-9'-]+", query.casefold()) if len(term) >= 3]
        scored = []
        for location in locations:
            slug = urlparse(location).path.casefold()
            words = re.findall(r"[a-z0-9]+", slug)
            score = sum(1 for term in terms if term in slug) + sum(0.5 for term in terms for word in words if word == term)
            if score > 0:
                scored.append((score, location))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        hits = []
        for _, location in scored[:limit]:
            tail = urlparse(location).path.rstrip("/").rsplit("/", 1)[-1]
            title = re.sub(r"[-_]+", " ", tail).strip().capitalize() or location
            hits.append(SearchHit(title, location, None, None, {"matched_by": "url slug"}))
        return SearchResult("ok" if hits else "empty", label, "sitemap", query, tuple(hits), total=len(scored), message=None if hits else "No page URLs matched; the site has no full-text search.")

    # -- archive.org listener reviews
    def archive_ratings(self, identifiers: list[str]) -> dict[str, dict[str, Any]]:
        """Star rating, review count and downloads for up to a handful of archive items."""

        wanted = [identifier for identifier in dict.fromkeys(identifiers) if re.fullmatch(r"[A-Za-z0-9._-]+", identifier)][:8]
        if not wanted:
            return {}
        lucene = "identifier:(" + " OR ".join(wanted) + ")"
        fields = "&".join(f"fl%5B%5D={name}" for name in ("identifier", "avg_rating", "num_reviews", "downloads", "source", "title"))
        page = self._get(f"https://archive.org/advancedsearch.php?q={quote(lucene)}&{fields}&rows={len(wanted)}&output=json")
        document = self._json(page)
        ratings: dict[str, dict[str, Any]] = {}
        if isinstance(document, dict):
            for doc in document.get("response", {}).get("docs", []) or []:
                identifier = doc.get("identifier")
                if identifier:
                    ratings[identifier] = {key: doc.get(key) for key in ("avg_rating", "num_reviews", "downloads", "source", "title") if doc.get(key) is not None}
        return ratings

    def archive_reviews(self, identifier: str, limit: int = 8, *, max_chars: int = 700) -> dict[str, Any]:
        """Listener reviews for one archive item, longest first."""

        if not re.fullmatch(r"[A-Za-z0-9._-]+", identifier):
            return {"state": "invalid", "archive_identifier": identifier, "reviews": [], "message": "Not an archive.org identifier."}
        page = self._get(f"https://archive.org/metadata/{quote(identifier)}/reviews")
        document = self._json(page)
        if not isinstance(document, dict):
            return {"state": "unavailable", "archive_identifier": identifier, "reviews": [], "message": f"archive.org returned HTTP {page.status}."}
        raw = document.get("result") or []
        if not isinstance(raw, list) or not raw:
            return {"state": "empty", "archive_identifier": identifier, "url": f"https://archive.org/details/{identifier}", "reviews": [], "review_count": 0, "message": "This recording has no listener reviews."}
        reviews = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            body = re.sub(r"\s+", " ", str(item.get("reviewbody") or "")).strip()
            if not body:
                continue
            stars = item.get("stars")
            try:
                stars_value: int | None = int(stars) if stars not in (None, "", "0") else None
            except (TypeError, ValueError):
                stars_value = None
            reviews.append({
                "title": re.sub(r"\s+", " ", str(item.get("reviewtitle") or "")).strip() or None,
                "reviewer": item.get("reviewer"),
                "date": str(item.get("reviewdate") or item.get("createdate") or "")[:10] or None,
                "stars": stars_value,
                "text": body[:max_chars] + ("…" if len(body) > max_chars else ""),
            })
        reviews.sort(key=lambda review: -len(review["text"]))
        rated = [review["stars"] for review in reviews if review["stars"]]
        return {
            "state": "ok",
            "archive_identifier": identifier,
            "url": f"https://archive.org/details/{identifier}",
            "review_count": len(reviews),
            "stars_histogram": {str(star): rated.count(star) for star in range(5, 0, -1) if rated.count(star)},
            "reviews": reviews[: max(1, min(limit, 20))],
        }

    def _sitemap_locations(self, url: str, depth: int, budget: list[int] | None = None) -> list[str]:
        budget = budget if budget is not None else [_MAX_SITEMAP_FILES]
        if budget[0] <= 0 or depth > 2:
            return []
        budget[0] -= 1
        page = self._get(url)
        if page.status < 200 or page.status >= 300 or not page.body:
            return []
        body = page.body
        if "<sitemapindex" in body[:2000]:
            children = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
            locations: list[str] = []
            for child in children:
                locations.extend(self._sitemap_locations(unescape(child), depth + 1, budget))
            return locations
        return [unescape(match) for match in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)]
