"""Bounded, metadata-only research access to Dead.net and Deadcast.

This module deliberately is not a general web client.  Callers provide an
entity-shaped search or read request; the adapter constructs the URL from its
configuration and returns only metadata.  ``HttpTransport`` is injected so
unit tests (and a future connector) never need to make network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from html import unescape
import re
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


class EntityType(StrEnum):
    SONG = "song"
    SHOW = "show"
    PERSON = "person"
    VENUE = "venue"
    ALBUM = "album"
    DEADCAST = "deadcast"


class ResultState(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class DeadnetConfig:
    """Allowlist and request bounds for the Dead.net adapter."""

    base_url: str = "https://www.dead.net"
    allowed_hosts: frozenset[str] = frozenset({"dead.net", "www.dead.net"})
    allowed_paths: tuple[str, ...] = (
        "/search", "/song", "/show", "/person", "/venue", "/album", "/deadcast", "/deadcast/"
    )
    search_path: str = "/search"
    max_query_length: int = 160
    max_results: int = 10
    timeout_seconds: float = 8.0
    max_metadata_length: int = 280

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise ValueError("base_url must be an HTTPS URL on an allowed Dead.net host")
        if not self.allowed_paths or any(not p.startswith("/") or ".." in p.split("/") for p in self.allowed_paths):
            raise ValueError("allowed_paths must be absolute paths without traversal")
        if self.search_path not in self.allowed_paths:
            raise ValueError("search_path must be included in allowed_paths")
        if self.max_query_length < 1 or self.max_results < 1 or self.max_metadata_length < 1:
            raise ValueError("request bounds must be positive")


@dataclass(frozen=True)
class EntitySearchRequest:
    query: str
    entity_type: EntityType
    limit: int = 10


@dataclass(frozen=True)
class EntityReadRequest:
    entity_type: EntityType
    identifier: str


@dataclass(frozen=True)
class MetadataRecord:
    entity_type: str
    identifier: str
    title: str | None = None
    url: str | None = None
    description: str | None = None
    published_at: str | None = None
    source: str = "dead.net"


@dataclass(frozen=True)
class ResearchResult:
    state: ResultState
    records: tuple[MetadataRecord, ...] = ()
    coverage: str = "metadata_only"
    source: str = "dead.net"
    message: str | None = None
    requested: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.state in {ResultState.OK, ResultState.EMPTY, ResultState.PARTIAL}


@dataclass(frozen=True)
class HttpResponse:
    status: int
    payload: Any


class HttpTransport(Protocol):
    def get(self, url: str, *, params: Mapping[str, str], timeout: float) -> HttpResponse:
        """Perform one read-only request."""


class UrlLibMetadataTransport:
    """Fetch a Dead.net page and retain only its link metadata.

    This is intentionally not a general page reader: it sends one GET request,
    caps the response read, and extracts just a page title and optional metadata
    description. The adapter owns URL validation before this transport is used;
    the transport validates the final redirect target again before returning a
    record. Article body, lyrics, transcripts, and audio never enter the agent
    packet or local storage.
    """

    _TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
    _DESCRIPTION = re.compile(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self.allowed_hosts = allowed_hosts

    def get(self, url: str, *, params: Mapping[str, str], timeout: float) -> HttpResponse:
        request_url = f"{url}?{urlencode(params)}" if params else url
        request = Request(
            request_url,
            headers={"User-Agent": "Deadbot/0.1 (metadata-only source research)", "Accept": "text/html"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                parsed = urlparse(final_url)
                if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
                    return HttpResponse(status=403, payload={"results": []})
                body = response.read(96_000).decode("utf-8", errors="replace")
                status = getattr(response, "status", 200)
        except HTTPError as error:
            return HttpResponse(status=error.code, payload={"results": []})
        except (URLError, TimeoutError, OSError):
            return HttpResponse(status=503, payload={"results": []})

        title_match = self._TITLE.search(body)
        title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip() if title_match else parsed.path.rsplit("/", 1)[-1]
        description_match = self._DESCRIPTION.search(body)
        description = (
            unescape(re.sub(r"\s+", " ", description_match.group(1))).strip()
            if description_match
            else None
        )
        identifier = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        return HttpResponse(
            status=status,
            payload={
                "results": [
                    {
                        "id": identifier,
                        "title": title,
                        "url": final_url,
                        "description": description,
                    }
                ]
            },
        )


class DeadnetResearchAdapter:
    """Entity-focused, allowlisted Dead.net research adapter."""

    def __init__(self, transport: HttpTransport, config: DeadnetConfig | None = None) -> None:
        self.transport = transport
        self.config = config or DeadnetConfig()

    def search(self, request: EntitySearchRequest) -> ResearchResult:
        query = request.query.strip()
        if not query or len(query) > self.config.max_query_length:
            return self._invalid("query is empty or exceeds the configured limit", request.entity_type.value)
        limit = min(max(request.limit, 1), self.config.max_results)
        return self._request(
            self.config.search_path,
            {"q": query, "type": request.entity_type.value, "limit": str(limit)},
            {"operation": "search", "entity_type": request.entity_type.value, "query": query},
        )

    def read(self, request: EntityReadRequest) -> ResearchResult:
        identifier = request.identifier.strip()
        if (
            not identifier
            or len(identifier) > self.config.max_query_length
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._~-]*", identifier)
        ):
            return self._invalid("identifier is empty, too long, or contains a path delimiter", request.entity_type.value)
        path = "/deadcast/" + identifier if request.entity_type == EntityType.DEADCAST else "/" + request.entity_type.value + "/" + identifier
        if not any(path == allowed or path.startswith(allowed.rstrip("/") + "/") for allowed in self.config.allowed_paths):
            return ResearchResult(ResultState.BLOCKED, message="requested entity path is outside the configured allowlist", requested={"operation": "read", "entity_type": request.entity_type.value})
        return self._request(path, {}, {"operation": "read", "entity_type": request.entity_type.value, "identifier": identifier})

    def _request(self, path: str, params: Mapping[str, str], requested: Mapping[str, str]) -> ResearchResult:
        url = self._allowed_url(path)
        if url is None:
            return ResearchResult(ResultState.BLOCKED, message="request path is outside the configured allowlist", requested=requested)
        try:
            response = self.transport.get(url, params=params, timeout=self.config.timeout_seconds)
        except Exception:
            return ResearchResult(ResultState.UNAVAILABLE, message="Dead.net research service was unavailable", requested=requested)
        if response.status < 200 or response.status >= 300:
            return ResearchResult(ResultState.UNAVAILABLE, message=f"Dead.net returned HTTP {response.status}", requested=requested)
        records, had_unusable_items = self._metadata(response.payload, requested.get("entity_type", ""))
        state = ResultState.PARTIAL if records and had_unusable_items else ResultState.OK if records else ResultState.EMPTY
        return ResearchResult(state, records, requested=requested)

    def _allowed_url(self, path: str) -> str | None:
        if not path.startswith("/") or ".." in path.split("/"):
            return None
        if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.config.allowed_paths):
            return None
        return urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/"))

    def _metadata(self, payload: Any, entity_type: str) -> tuple[tuple[MetadataRecord, ...], bool]:
        items = payload if isinstance(payload, list) else payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return (), bool(items)
        records = []
        had_unusable_items = False
        for item in items:
            if not isinstance(item, dict):
                had_unusable_items = True
                continue
            identifier = str(item.get("id") or item.get("slug") or item.get("url") or "").strip()
            title = item.get("title") or item.get("name")
            if not identifier or not isinstance(title, str):
                had_unusable_items = True
                continue
            # Keep the packet deliberately small and reject markup/control data.
            identifier = self._short_text(identifier, self.config.max_metadata_length)
            title = self._short_text(title, self.config.max_metadata_length)
            raw_url = item.get("url") if isinstance(item.get("url"), str) else None
            safe_url = self._metadata_url(raw_url)
            if raw_url and safe_url is None:
                had_unusable_items = True
            description = item.get("description") if isinstance(item.get("description"), str) else None
            published_at = item.get("published_at") if isinstance(item.get("published_at"), str) else None
            records.append(MetadataRecord(entity_type=entity_type, identifier=identifier, title=title, url=safe_url, description=self._short_text(description, self.config.max_metadata_length) if description else None, published_at=self._short_text(published_at, 80) if published_at else None))
        return tuple(records[: self.config.max_results]), had_unusable_items or len(records) > self.config.max_results

    def _metadata_url(self, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc:
            if (
                parsed.scheme != "https"
                or parsed.hostname not in self.config.allowed_hosts
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
            ):
                return None
            path = parsed.path or "/"
        else:
            path = value if value.startswith("/") else "/" + value
        return self._allowed_url(path)

    @staticmethod
    def _invalid(message: str, entity_type: str) -> ResearchResult:
        return ResearchResult(ResultState.INVALID, message=message, requested={"entity_type": entity_type})

    @staticmethod
    def _short_text(value: str, limit: int) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r"[\x00-\x1f\x7f]", "", value)
        return value[:limit]
