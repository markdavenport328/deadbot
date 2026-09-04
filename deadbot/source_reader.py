"""Request-time page reading for the research tools.

Fetch one public web page and return its readable text: title, byline, date,
description and the main body with navigation, footers, comment threads and
other boilerplate removed. Nothing is stored beyond a short in-process cache
that stops one conversation from fetching the same page twice.

The transport is injectable so tests read fixture HTML instead of the network.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Deadbot/0.2 (+https://deadbot-ten.vercel.app; research reader)"
MAX_DOWNLOAD_BYTES = 2_500_000
DEFAULT_TIMEOUT = 12.0
DEFAULT_MAX_CHARS = 12_000
CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_MAX_ENTRIES = 200


@dataclass(frozen=True)
class FetchedPage:
    status: int
    url: str
    content_type: str
    body: str


class PageTransport(Protocol):
    def get(self, url: str, *, timeout: float) -> FetchedPage:
        """Perform one GET request and return the decoded body."""


class UrlLibPageTransport:
    """Fetch a page with the standard library; no third-party HTTP dependency."""

    def get(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> FetchedPage:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,text/plain;q=0.8,*/*;q=0.5",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_DOWNLOAD_BYTES)
                charset = response.headers.get_content_charset() or "utf-8"
                content_type = response.headers.get("Content-Type", "") or ""
                return FetchedPage(getattr(response, "status", 200), response.geturl(), content_type, raw.decode(charset, errors="replace"))
        except HTTPError as error:
            return FetchedPage(error.code, url, "", "")
        except (URLError, TimeoutError, OSError, ValueError):
            return FetchedPage(0, url, "", "")


# --- HTML to readable text ---------------------------------------------------

_SKIP_TAGS = frozenset({
    "script", "style", "noscript", "svg", "template", "iframe", "head", "nav", "footer",
    "form", "button", "select", "option", "canvas", "video", "audio", "object", "embed",
})
_BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "main", "aside", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "td", "th", "tr", "table", "dd", "dt", "dl", "figcaption", "summary", "details", "body",
})
_CONTAINER_TAGS = frozenset({"article", "main", "div", "section", "td", "body"})
_BOILERPLATE = re.compile(
    r"(comment|sidebar|menu|navbar|\bnav\b|nav-|-nav|footer|share|social|related|cookie|subscribe|"
    r"newsletter|breadcrumb|promo|advert|banner|popup|modal|toolbar|pager|pagination|masthead|site-header|"
    r"skip-link|login|signup|search-form|feed-links|post-footer|blog-pager|profile|attribution|disclaimer)",
    re.IGNORECASE,
)
_CONTENT_HINT = re.compile(
    r"(post-body|entry-content|field--name-body|node__content|article-body|post-content|content-body|"
    r"article__body|story-body|entry-body|main-content|page-content)",
    re.IGNORECASE,
)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_VOID_TAGS = frozenset({"area", "base", "col", "embed", "hr", "img", "input", "link", "param", "source", "track", "wbr"})


@dataclass
class _Node:
    node_id: int
    tag: str
    parent: int | None
    depth: int
    skip: bool
    content_hint: bool


@dataclass
class _Block:
    ancestors: tuple[int, ...]
    text: str
    heading: bool


@dataclass(frozen=True)
class ExtractedPage:
    title: str | None
    byline: str | None
    published: str | None
    description: str | None
    paragraphs: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: dict[int, _Node] = {}
        self.stack: list[int] = []
        self.blocks: list[_Block] = []
        self._buffer: list[str] = []
        self._buffer_heading = False
        self._next_id = 1
        self.title: str | None = None
        self.og_title: str | None = None
        self.description: str | None = None
        self.byline: str | None = None
        self.published: str | None = None
        self._in_title = False
        self._author_depth: int | None = None
        self._author_text: list[str] = []

    # -- helpers
    def _current_skip(self) -> bool:
        return bool(self.stack) and self.nodes[self.stack[-1]].skip

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
        self._buffer = []
        heading = self._buffer_heading
        self._buffer_heading = False
        if len(text) < 2:
            return
        if not self.stack:
            return
        self.blocks.append(_Block(tuple(self.stack), text, heading))

    # -- parser callbacks
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        if tag == "meta":
            self._meta(attributes)
            return
        if tag == "br":
            self._buffer.append("\n")
            self._flush()
            return
        if tag in _VOID_TAGS:
            # Void elements have no end tag; pushing them would make every
            # later element look like their child.
            return
        if tag == "time" and attributes.get("datetime") and not self.published:
            self.published = attributes["datetime"][:40]
        if tag == "abbr" and "published" in attributes.get("class", "") and attributes.get("title") and not self.published:
            self.published = attributes["title"][:40]
        if tag == "title":
            self._in_title = True
        if tag == "body":
            # Blogger and some hand-written pages hide </head> inside an HTML
            # comment; without this the whole document would inherit head's skip.
            self._flush()
            self.stack = [node_id for node_id in self.stack if self.nodes[node_id].tag == "html"]
        classes = f'{attributes.get("class", "")} {attributes.get("id", "")} {attributes.get("role", "")}'
        parent_skip = self._current_skip()
        skip = parent_skip or tag in _SKIP_TAGS or tag == "aside" or bool(_BOILERPLATE.search(classes)) or attributes.get("hidden") is not None
        if attributes.get("rel") == "author" or re.search(r"\b(author|byline)\b", classes, re.IGNORECASE):
            if self._author_depth is None and not self.byline:
                self._author_depth = len(self.stack)
                self._author_text = []
            skip = skip or tag not in _BLOCK_TAGS  # author inline text is metadata, not body
        if tag in _BLOCK_TAGS and not skip:
            self._flush()
        node = _Node(self._next_id, tag, self.stack[-1] if self.stack else None, len(self.stack), skip, bool(_CONTENT_HINT.search(classes)) or tag in {"article", "main"})
        self.nodes[node.node_id] = node
        self._next_id += 1
        self.stack.append(node.node_id)
        if tag in _HEADING_TAGS and not skip:
            self._buffer_heading = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"meta", "br"}:
            self.handle_starttag(tag, attrs)
        # Other void elements (img, hr, input) carry no text; nothing to track.

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            return
        if tag in {"meta", "br", "img", "hr", "input", "link", "source", "wbr"}:
            return
        # Pop to the nearest matching open tag; unclosed elements are common.
        for index in range(len(self.stack) - 1, -1, -1):
            node = self.nodes[self.stack[index]]
            if node.tag == tag:
                if tag in _BLOCK_TAGS:
                    self._flush()
                if self._author_depth is not None and index <= self._author_depth:
                    author = re.sub(r"\s+", " ", "".join(self._author_text)).strip(" :|-–—")
                    if 1 < len(author) <= 120:
                        self.byline = re.sub(r"^(by|posted by|written by)\s+", "", author, flags=re.IGNORECASE)
                    self._author_depth = None
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if self._author_depth is not None and len(self.stack) > self._author_depth:
            self._author_text.append(data)
        if not self.stack or self._current_skip():
            return
        self._buffer.append(data)

    def _meta(self, attributes: dict[str, str]) -> None:
        name = (attributes.get("property") or attributes.get("name") or attributes.get("itemprop") or "").lower()
        content = attributes.get("content", "").strip()
        if not content:
            return
        if name == "og:title" and not self.og_title:
            self.og_title = content
        elif name in {"description", "og:description", "twitter:description"} and not self.description:
            self.description = content
        elif name in {"author", "article:author", "dc.creator", "parsely-author"} and not self.byline and not content.startswith("http"):
            self.byline = content
        elif name in {"article:published_time", "datepublished", "date", "dc.date", "parsely-pub-date", "og:article:published_time"} and not self.published:
            self.published = content[:40]

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def _choose_container(extractor: _Extractor) -> int | None:
    """Pick the element holding the article body.

    Prefer an ``article``/``main``/known content container that holds a
    substantial share of the page's text; otherwise take the deepest element
    holding most of the text.
    """

    blocks = extractor.blocks
    if not blocks:
        return None
    total = sum(len(block.text) for block in blocks)
    if total == 0:
        return None
    chars: dict[int, int] = {}
    for block in blocks:
        for ancestor in block.ancestors:
            chars[ancestor] = chars.get(ancestor, 0) + len(block.text)

    hinted = [
        (chars[node_id], node)
        for node_id, node in extractor.nodes.items()
        if node.content_hint and node_id in chars and chars[node_id] >= total * 0.25
    ]
    if hinted:
        hinted.sort(key=lambda pair: (-pair[0], pair[1].depth))
        best_chars = hinted[0][0]
        # Among hinted containers with the same text, the deepest is tightest.
        return max((node for count, node in hinted if count == best_chars), key=lambda node: node.depth).node_id

    candidates = [
        node for node_id, node in extractor.nodes.items()
        if node.tag in _CONTAINER_TAGS and node_id in chars and chars[node_id] >= total * 0.6
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda node: node.depth).node_id


def extract_page(html: str) -> ExtractedPage:
    """Turn raw HTML into a title, metadata, and readable body paragraphs."""

    extractor = _Extractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:  # pragma: no cover - the stdlib parser is lenient, but never let a page kill a turn
        pass
    container = _choose_container(extractor)
    paragraphs: list[str] = []
    for block in extractor.blocks:
        if container is not None and container not in block.ancestors:
            continue
        text = unescape(block.text).strip()
        if not text:
            continue
        if block.heading:
            text = f"## {text}"
        paragraphs.append(text)
    # Merge the very short fragments Blogger and hand-written HTML produce
    # around <br> tags into their neighbours so paging boundaries fall on prose.
    merged: list[str] = []
    for text in paragraphs:
        if merged and len(text) < 40 and not text.startswith("## ") and not merged[-1].startswith("## ") and len(merged[-1]) < 400:
            merged[-1] = f"{merged[-1]} {text}"
        else:
            merged.append(text)
    title = extractor.og_title or (re.sub(r"\s+", " ", unescape(extractor.title)).strip() if extractor.title else None)
    return ExtractedPage(
        title=title or None,
        byline=extractor.byline or None,
        published=extractor.published or None,
        description=unescape(extractor.description) if extractor.description else None,
        paragraphs=tuple(merged),
    )


# --- focus and paging -------------------------------------------------------

_STOP = frozenset({"the", "and", "for", "with", "that", "this", "from", "into", "what", "when", "where", "which", "about", "their", "there", "were", "was", "are", "has", "have", "had", "how", "why", "did", "does", "grateful", "dead", "show", "shows", "song", "songs"})


def _focus_terms(focus: str) -> list[str]:
    terms = [term for term in re.findall(r"[a-z0-9][a-z0-9'/-]+", focus.casefold()) if len(term) >= 3 and term not in _STOP]
    return list(dict.fromkeys(terms))


def focus_paragraphs(paragraphs: tuple[str, ...], focus: str, max_chars: int) -> tuple[str, int]:
    """Return the passages around ``focus`` first, in document order, within ``max_chars``.

    Returns the text and the number of paragraphs that matched. A paragraph
    scores by the distinct focus terms it contains; each matching paragraph
    brings its neighbours along for context.
    """

    terms = _focus_terms(focus)
    if not terms or not paragraphs:
        return "", 0
    lowered = [paragraph.casefold() for paragraph in paragraphs]
    scores = [sum(1 for term in terms if term in text) for text in lowered]
    matched = [index for index, score in enumerate(scores) if score > 0]
    if not matched:
        return "", 0
    ranked = sorted(matched, key=lambda index: (-scores[index], index))
    chosen: set[int] = set()
    budget = max_chars
    # Always orient the reader with the opening paragraph.
    if paragraphs and len(paragraphs[0]) < 600:
        chosen.add(0)
        budget -= len(paragraphs[0])
    for index in ranked:
        window = [i for i in (index - 1, index, index + 1) if 0 <= i < len(paragraphs)]
        cost = sum(len(paragraphs[i]) for i in window if i not in chosen)
        if cost > budget:
            if index not in chosen and len(paragraphs[index]) <= budget:
                chosen.add(index)
                budget -= len(paragraphs[index])
            continue
        chosen.update(window)
        budget -= cost
        if budget <= 0:
            break
    ordered = sorted(chosen)
    pieces: list[str] = []
    previous: int | None = None
    for index in ordered:
        if previous is not None and index != previous + 1:
            pieces.append("[…]")
        pieces.append(paragraphs[index])
        previous = index
    if ordered and ordered[-1] < len(paragraphs) - 1:
        pieces.append("[…]")
    return "\n\n".join(pieces), len(matched)


def page_text(paragraphs: tuple[str, ...], offset: int, max_chars: int) -> tuple[str, int | None]:
    """Return the slice of the body starting at ``offset`` characters, cut on a paragraph boundary."""

    full = "\n\n".join(paragraphs)
    offset = max(0, min(offset, len(full)))
    while offset < len(full) and full[offset] == "\n":
        offset += 1
    if offset >= len(full):
        return "", None
    end = offset + max_chars
    if end >= len(full):
        return full[offset:], None
    cut = full.rfind("\n\n", offset + max_chars // 2, end)
    if cut == -1:
        cut = end
    return full[offset:cut].rstrip(), cut


# --- reader -----------------------------------------------------------------

@dataclass(frozen=True)
class ReadResult:
    state: str  # ok | empty | unavailable | invalid
    url: str
    final_url: str | None = None
    title: str | None = None
    byline: str | None = None
    published: str | None = None
    description: str | None = None
    text: str = ""
    total_chars: int = 0
    offset: int = 0
    next_offset: int | None = None
    focus: str | None = None
    focus_matches: int | None = None
    message: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state": self.state,
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "byline": self.byline,
            "published": self.published,
            "description": self.description,
            "total_chars": self.total_chars,
            "offset": self.offset,
            "next_offset": self.next_offset,
            "focus": self.focus,
            "focus_matches": self.focus_matches,
            "message": self.message,
            "text": self.text,
        }
        return payload


def validate_url(url: str) -> str | None:
    """Return a reason the URL cannot be read, or None when it can."""

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return "Only http and https URLs can be read."
    host = parsed.hostname
    if not host:
        return "The URL has no host."
    if host in {"localhost"} or host.endswith(".local") or host.endswith(".internal"):
        return "Local addresses cannot be read."
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
        return "Private network addresses cannot be read."
    return None


class PageReader:
    """Read a public page's text at request time, with a short in-process cache."""

    def __init__(self, transport: PageTransport | None = None, *, timeout: float = DEFAULT_TIMEOUT, clock=time.monotonic) -> None:
        self.transport = transport or UrlLibPageTransport()
        self.timeout = timeout
        self._clock = clock
        self._cache: dict[str, tuple[float, FetchedPage, ExtractedPage | None]] = {}

    def _fetch(self, url: str) -> tuple[FetchedPage, ExtractedPage | None]:
        now = self._clock()
        cached = self._cache.get(url)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1], cached[2]
        page = self.transport.get(url, timeout=self.timeout)
        extracted = extract_page(page.body) if page.body and _is_html(page) else None
        if len(self._cache) >= CACHE_MAX_ENTRIES:
            oldest = min(self._cache, key=lambda key: self._cache[key][0])
            del self._cache[oldest]
        self._cache[url] = (now, page, extracted)
        return page, extracted

    def read(self, url: str, *, focus: str | None = None, offset: int = 0, max_chars: int = DEFAULT_MAX_CHARS) -> ReadResult:
        url = url.strip()
        reason = validate_url(url)
        if reason:
            return ReadResult(state="invalid", url=url, message=reason)
        page, extracted = self._fetch(url)
        if page.status == 0:
            return ReadResult(state="unavailable", url=url, message="The page could not be fetched (network error or timeout).")
        if page.status < 200 or page.status >= 300:
            return ReadResult(state="unavailable", url=url, final_url=page.url, message=f"The site returned HTTP {page.status}.")
        if not page.body.strip():
            return ReadResult(state="empty", url=url, final_url=page.url, message="The page had no readable content.")

        if extracted is None:
            body = _non_html_text(page)
            text, next_offset = page_text((body,), offset, max_chars)
            return ReadResult(state="ok" if text else "empty", url=url, final_url=page.url, text=text, total_chars=len(body), offset=offset, next_offset=next_offset)

        paragraphs = extracted.paragraphs
        total = len(extracted.text)
        if not paragraphs:
            return ReadResult(state="empty", url=url, final_url=page.url, title=extracted.title, byline=extracted.byline, published=extracted.published, description=extracted.description, message="The page had no readable body text.")
        focus_matches: int | None = None
        if focus and focus.strip():
            text, focus_matches = focus_paragraphs(paragraphs, focus, max_chars)
            next_offset: int | None = None
            if focus_matches == 0:
                text, next_offset = page_text(paragraphs, offset, max_chars)
        else:
            text, next_offset = page_text(paragraphs, offset, max_chars)
        return ReadResult(
            state="ok" if text else "empty",
            url=url,
            final_url=page.url,
            title=extracted.title,
            byline=extracted.byline,
            published=extracted.published,
            description=extracted.description,
            text=text,
            total_chars=total,
            offset=offset,
            next_offset=next_offset,
            focus=focus.strip() if focus and focus.strip() else None,
            focus_matches=focus_matches,
            message=None if focus_matches is None or focus_matches else "The focus phrase was not found; returning the page from the start.",
        )


def _is_html(page: FetchedPage) -> bool:
    content_type = page.content_type.lower()
    if "json" in content_type or "text/plain" in content_type or "xml" in content_type and "html" not in content_type:
        return False
    if content_type and "html" not in content_type and "text/" not in content_type:
        return False
    return "<" in page.body[:2000]


def _non_html_text(page: FetchedPage) -> str:
    body = page.body
    if "json" in page.content_type.lower() or body.lstrip()[:1] in "[{":
        try:
            return json.dumps(json.loads(body), ensure_ascii=False, indent=1)
        except json.JSONDecodeError:
            pass
    return body


_default_reader: PageReader | None = None


def default_reader() -> PageReader:
    """One process-wide reader so the cache is shared across turns."""

    global _default_reader
    if _default_reader is None:
        _default_reader = PageReader()
    return _default_reader
