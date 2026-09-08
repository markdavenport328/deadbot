#!/usr/bin/env python3
"""Catalog Grateful Dead Archive Online items by show date.

The Grateful Dead Archive Online (GDAO, ``www.gdao.org``) is UC Santa Cruz's
Omeka S archive of posters, tickets, ticket-request envelopes, photographs,
fan art, taped-show metadata and first-person recollections. Its public
``/api/items`` endpoint can be filtered by property, so this collector asks
one question per show: which items carry this date?

For each show date -- the eleven target shows of
``data/editorial/lore-targets-2026-09-08.json`` first, then the rest of
``data/editorial/featured-show-candidates.json`` -- the collector queries the
three date properties GDAO actually populates and preserves one compact raw
record per item.

Metadata only. A stored record keeps the Omeka item id, its title, its item
type (the Omeka resource-template label: ``Poster``, ``Ticket``,
``Oral History``...), the item-set titles, the values of the item's date
fields, its coverage lines, its creator, the item page URL, and the first 200
characters of its description with markup removed. Files, media, thumbnails
and the table-of-contents set lists are read past and never written to disk.

Host courtesy: ``https://www.gdao.org/robots.txt`` and the API's own root
description are read before anything else and both findings are preserved in
the raw file. Requests go one at a time, at least two seconds apart, with a
plain descriptive User-Agent, and a longer ``Crawl-delay`` is honored.

Retry safety: the raw file is rewritten only from a complete successful pass.
Any non-200 page, or a page that is not the expected JSON, aborts the pass and
leaves the previous raw file exactly as it was, so a transient failure can
never turn collected items into an apparent absence. "No items at this date"
and "the request failed" stay distinguishable in the pass metadata.

Usage::

    PYTHONPATH=. python scripts/collect/collect_gdao_show_items.py
    PYTHONPATH=. python scripts/collect/collect_gdao_show_items.py \
        --dates 1977-05-22 1989-07-17 --out data/raw/resources/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadbot.source_reader import DEFAULT_TIMEOUT, PageTransport  # noqa: E402

# The courtesy machinery of the blog-index pass is the same machinery this
# pass needs -- the same User-Agent, the same one-request-at-a-time throttle,
# the same reading of the robots groups that apply to this collector -- so it
# is reused rather than copied.
from collect_blog_post_index import (  # noqa: E402
    MIN_SECONDS_BETWEEN_REQUESTS,
    ROBOTS_AGENT,
    USER_AGENT,
    MetadataIndexTransport,
    Throttle,
    applicable_robots_rules,
    plain_text,
    timestamp,
)


OUTPUT_DIR = ROOT / "data" / "raw" / "resources"
OUTPUT_NAME = "gdao-show-items.jsonl"
TARGETS_PATH = ROOT / "data" / "editorial" / "lore-targets-2026-09-08.json"
FEATURED_PATH = ROOT / "data" / "editorial" / "featured-show-candidates.json"

SITE_ID = "gdao"
SITE_NAME = "Grateful Dead Archive Online"
SOURCE_NAME = "Grateful Dead Archive Online / UC Santa Cruz Library"
HOST = "www.gdao.org"
API_PATH = "/api/items"
ITEM_URL = "https://www.gdao.org/items/show/{id}"

# GDAO stores a date in three places, and they do not mean the same thing.
# ``dcterms:temporal`` is the date the item is *about* -- the show -- and it is
# what a ticket-request envelope postmarked in June carries for a July run.
# ``dcterms:date`` and ``gdao:sortableDate`` are the item's own date, which for
# that envelope is the postmark. All three are queried, so an item is found
# whichever field carries the show date, and all three are stored so the
# normalizer can decide which one names the show.
DATE_PROPERTIES: tuple[tuple[str, int], ...] = (
    ("dcterms:temporal", 41),
    ("dcterms:date", 7),
    ("gdao:sortableDate", 240),
)
MAX_DESCRIPTION_CHARS = 200
MAX_COVERAGE_VALUES = 6
MAX_COVERAGE_CHARS = 120
PER_PAGE = 100
MAX_PAGES = 25
REFERENCE_PER_PAGE = 100
# An Omeka S property query over 37,000 items is slow: a single date page took
# 29 seconds to answer, so the library reader's 12-second default would read a
# healthy archive as an outage.
REQUEST_TIMEOUT = 60.0
# A transport-level failure or a 5xx is a failure of the moment, not an
# absence, so one page is asked for twice before the pass aborts.
RETRY_ATTEMPTS = 2

RETENTION = (
    "Metadata only: Omeka item id, title, item type, item sets, date-field values, coverage lines, "
    "creator and the first 200 characters of the description with markup removed. No files, media, "
    "thumbnails or set lists are stored."
)


# --- requested dates ---------------------------------------------------------


@dataclass(frozen=True)
class RequestedDate:
    date: str
    group: str  # target | featured


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def requested_dates(targets: dict[str, Any], featured: dict[str, Any]) -> list[RequestedDate]:
    """The target shows first, then the featured shows the targets do not cover."""

    ordered: list[RequestedDate] = []
    seen: set[str] = set()
    for group, rows in (("target", targets.get("shows") or []), ("featured", featured.get("candidates") or [])):
        for row in rows:
            date = str(row.get("show_date") or "").strip()
            if not _ISO_DATE.fullmatch(date) or date in seen:
                continue
            seen.add(date)
            ordered.append(RequestedDate(date, group))
    return ordered


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# --- request URLs ------------------------------------------------------------


def items_query_url(date: str, *, page: int = 1, per_page: int = PER_PAGE) -> str:
    """One Omeka S item query: any of the date properties starting with ``date``.

    ``sw`` (starts-with) is exact enough to be safe: the stored values read
    ``1989-07-17T00:00:00Z`` or ``1989-07-17``, so a full ISO date matches the
    day and nothing else. A range value such as ``1977-05-22/1977-05-24`` also
    matches, and the normalizer holds it because it names two dates.
    """

    params: list[tuple[str, str | int]] = []
    for index, (_term, property_id) in enumerate(DATE_PROPERTIES):
        if index:
            params.append((f"property[{index}][joiner]", "or"))
        params.append((f"property[{index}][property]", property_id))
        params.append((f"property[{index}][type]", "sw"))
        params.append((f"property[{index}][text]", date))
    params.extend([("sort_by", "id"), ("sort_order", "asc"), ("per_page", per_page), ("page", page)])
    return f"https://{HOST}{API_PATH}?{urlencode(params)}"


def reference_url(resource: str) -> str:
    """The URL of one small reference list (``resource_templates``, ``item_sets``)."""

    return f"https://{HOST}/api/{resource}?{urlencode({'per_page': REFERENCE_PER_PAGE})}"


# --- courtesy ----------------------------------------------------------------


def fetch(transport: PageTransport, throttle: Throttle, url: str, timeout: float) -> Any:
    """One throttled GET, retried once when the transport or the host stumbles."""

    page = None
    for attempt in range(RETRY_ATTEMPTS):
        throttle.wait()
        page = transport.get(url, timeout=timeout)
        if page.status != 0 and not 500 <= page.status < 600:
            return page
        if attempt + 1 < RETRY_ATTEMPTS:
            print(f"  retrying after HTTP {page.status}: {url}")
    return page


def read_robots(transport: PageTransport, throttle: Throttle, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Fetch and interpret ``robots.txt`` for the item API path."""

    url = f"https://{HOST}/robots.txt"
    throttle.wait()
    page = transport.get(url, timeout=timeout)
    finding: dict[str, Any] = {
        "url": url,
        "http_status": page.status,
        "path": API_PATH,
        "path_allowed": False,
        "crawl_delay": None,
        "applicable_rules": [],
        "note": "",
    }
    if page.status in {404, 410}:
        finding["path_allowed"] = True
        finding["note"] = f"The host serves no robots.txt (HTTP {page.status}), so {API_PATH} is unrestricted."
        return finding
    if page.status != 200:
        finding["note"] = f"robots.txt could not be read (HTTP {page.status}); the pass stopped rather than querying unchecked."
        return finding
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(page.body.splitlines())
    parser.modified()  # crawl_delay() reports nothing until the parse is dated
    finding["path_allowed"] = bool(parser.can_fetch(USER_AGENT, f"https://{HOST}{API_PATH}"))
    delay = parser.crawl_delay(USER_AGENT)
    finding["crawl_delay"] = float(delay) if delay is not None else None
    finding["applicable_rules"] = applicable_robots_rules(page.body)
    finding["note"] = f"robots.txt permits {API_PATH}." if finding["path_allowed"] else f"robots.txt disallows {API_PATH}; the pass stopped."
    return finding


def read_api_terms(transport: PageTransport, throttle: Throttle, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Record what the API says about itself, in its own words."""

    url = f"https://{HOST}/api"
    throttle.wait()
    page = transport.get(url, timeout=timeout)
    description = plain_text(page.body)[:400] if page.status == 200 else ""
    return {
        "url": url,
        "http_status": page.status,
        "description": description,
        "note": "The API root states its own terms." if description else f"The API root could not be read (HTTP {page.status}).",
    }


# --- item shaping ------------------------------------------------------------


# A GDAO description is HTML. ``plain_text`` drops a tag without putting a
# space in its place, which is right for a title (``<b>Veneta</b>,`` reads as
# ``Veneta,``) and wrong for a paragraph: ``remaster<br/>of`` would read as one
# word. So a line-breaking tag becomes a space before the rest are dropped.
_BREAK_TAG = re.compile(r"</?(?:br|p|div|li|ul|ol|tr|td|th|h[1-6]|blockquote|pre|section)\b[^>]*>", re.IGNORECASE)


def description_text(value: str) -> str:
    """One line of readable description text: markup out, whitespace collapsed."""

    return plain_text(_BREAK_TAG.sub(" ", value))


def _values(item: dict[str, Any], term: str) -> list[str]:
    return [str(value["@value"]) for value in item.get(term) or [] if isinstance(value, dict) and value.get("@value") not in (None, "")]


def reference_labels(document: Any, label_keys: tuple[str, ...]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for row in document if isinstance(document, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("o:id"), int):
            continue
        for key in label_keys:
            if row.get(key):
                labels[row["o:id"]] = str(row[key])
                break
    return labels


def shape_item(
    item: dict[str, Any],
    *,
    templates: dict[int, str],
    item_sets: dict[int, str],
    retrieved_at: str,
    queried_dates: list[str],
    request_url: str,
) -> dict[str, Any] | None:
    """Build one metadata-only raw record, or None when the item has no id."""

    item_id = item.get("o:id")
    if not isinstance(item_id, int):
        return None
    template = item.get("o:resource_template") or {}
    template_id = template.get("o:id") if isinstance(template, dict) else None
    descriptions = _values(item, "dcterms:description")
    description = description_text(descriptions[0]) if descriptions else ""
    return {
        "source": SITE_ID,
        "source_record_id": str(item_id),
        "retrieved_at": retrieved_at,
        "source_url": ITEM_URL.format(id=item_id),
        "raw_payload": {
            "record_type": "item",
            "host": HOST,
            "site_name": SITE_NAME,
            "source_name": SOURCE_NAME,
            "item_id": item_id,
            "title": plain_text(str(item.get("o:title") or "")),
            "item_type": templates.get(template_id, "") if isinstance(template_id, int) else "",
            "resource_template_id": template_id if isinstance(template_id, int) else None,
            "collections": [
                item_sets[entry["o:id"]]
                for entry in item.get("o:item_set") or []
                if isinstance(entry, dict) and isinstance(entry.get("o:id"), int) and entry["o:id"] in item_sets
            ],
            "dcterms_type": (_values(item, "dcterms:type") or [""])[0],
            "format": (_values(item, "dcterms:format") or [""])[0],
            "creator": "; ".join(_values(item, "dcterms:creator")),
            "date_fields": {term: _values(item, term) for term, _id in DATE_PROPERTIES},
            "coverage": [value[:MAX_COVERAGE_CHARS] for value in _values(item, "dcterms:coverage")[:MAX_COVERAGE_VALUES]],
            "description": description[:MAX_DESCRIPTION_CHARS],
            "queried_dates": queried_dates,
            "request_url": request_url,
            "http_status": 200,
        },
    }


# --- collection --------------------------------------------------------------


def collect(
    requested: list[RequestedDate],
    transport: PageTransport,
    throttle: Throttle,
    *,
    per_page: int = PER_PAGE,
    max_pages: int = MAX_PAGES,
    timeout: float = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    """Query every requested date and return a complete pass, or a refusal."""

    retrieved_at = timestamp()
    result: dict[str, Any] = {
        "site_id": SITE_ID,
        "site_name": SITE_NAME,
        "source_name": SOURCE_NAME,
        "host": HOST,
        "retrieved_at": retrieved_at,
        "user_agent": USER_AGENT,
        "api_path": API_PATH,
        "date_properties": [{"term": term, "property_id": property_id} for term, property_id in DATE_PROPERTIES],
        "robots": {},
        "api_terms": {},
        "requested": [{"date": entry.date, "group": entry.group} for entry in requested],
        "by_date": {},
        "request_count": 0,
        "page_count": 0,
        "item_count": 0,
        "status": "ok",
        "note": "",
        "items": [],
    }

    robots = read_robots(transport, throttle, timeout)
    result["robots"] = robots
    result["request_count"] += 1
    if not robots["path_allowed"]:
        result["status"] = "skipped-robots"
        result["note"] = robots["note"]
        return result
    if robots["crawl_delay"] and robots["crawl_delay"] > throttle.min_interval:
        throttle.min_interval = robots["crawl_delay"]

    result["api_terms"] = read_api_terms(transport, throttle, timeout)
    result["request_count"] += 1

    references: dict[str, dict[int, str]] = {}
    for resource, label_keys in (("resource_templates", ("o:label",)), ("item_sets", ("o:title", "o:label"))):
        url = reference_url(resource)
        page = fetch(transport, throttle, url, timeout)
        result["request_count"] += 1
        if page.status != 200:
            result["status"] = "aborted"
            result["note"] = f"{url} returned HTTP {page.status}; the raw file was left unchanged."
            return result
        try:
            document = json.loads(page.body)
        except json.JSONDecodeError:
            result["status"] = "aborted"
            result["note"] = f"{url} did not return the expected JSON; the raw file was left unchanged."
            return result
        references[resource] = reference_labels(document, label_keys)
    templates = references["resource_templates"]
    item_sets = references["item_sets"]

    items: dict[int, dict[str, Any]] = {}
    for entry in requested:
        date_summary = {"date": entry.date, "group": entry.group, "item_count": 0, "pages": 0, "status": "none-at-source"}
        result["by_date"][entry.date] = date_summary
        for page_number in range(1, max_pages + 1):
            url = items_query_url(entry.date, page=page_number, per_page=per_page)
            page = fetch(transport, throttle, url, timeout)
            result["request_count"] += 1
            if page.status != 200:
                result["status"] = "aborted"
                result["note"] = f"{url} returned HTTP {page.status}; the raw file was left unchanged."
                result["items"] = []
                return result
            try:
                document = json.loads(page.body)
            except json.JSONDecodeError:
                result["status"] = "aborted"
                result["note"] = f"{url} did not return the expected JSON item list; the raw file was left unchanged."
                result["items"] = []
                return result
            if not isinstance(document, list):
                result["status"] = "aborted"
                result["note"] = f"{url} did not return the expected JSON item list; the raw file was left unchanged."
                result["items"] = []
                return result
            date_summary["pages"] += 1
            result["page_count"] += 1
            for raw_item in document:
                if not isinstance(raw_item, dict):
                    continue
                item_id = raw_item.get("o:id")
                if isinstance(item_id, int) and item_id in items:
                    seen_dates = items[item_id]["raw_payload"]["queried_dates"]
                    if entry.date not in seen_dates:
                        seen_dates.append(entry.date)
                    date_summary["item_count"] += 1
                    continue
                record = shape_item(
                    raw_item,
                    templates=templates,
                    item_sets=item_sets,
                    retrieved_at=retrieved_at,
                    queried_dates=[entry.date],
                    request_url=url,
                )
                if record is None:
                    continue
                items[record["raw_payload"]["item_id"]] = record
                date_summary["item_count"] += 1
            if len(document) < per_page:
                break
        else:
            result["status"] = "aborted"
            result["note"] = f"{entry.date} was still returning items after {max_pages} pages; raise --max-pages and rerun."
            result["items"] = []
            return result
        date_summary["status"] = "found" if date_summary["item_count"] else "none-at-source"

    result["items"] = [items[item_id] for item_id in sorted(items)]
    result["item_count"] = len(result["items"])
    result["note"] = f"{result['item_count']} distinct item(s) across {len(requested)} requested date(s)."
    return result


# --- output ------------------------------------------------------------------


def pass_record(result: dict[str, Any]) -> dict[str, Any]:
    """The raw file's first line: what this pass asked for and what it found."""

    return {
        "source": result["site_id"],
        "source_record_id": f"gdao-show-items:{result['host']}",
        "retrieved_at": result["retrieved_at"],
        "source_url": f"https://{result['host']}{result['api_path']}",
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": result["host"],
            "site_name": result["site_name"],
            "source_name": result["source_name"],
            "user_agent": result["user_agent"],
            "api_path": result["api_path"],
            "date_properties": result["date_properties"],
            "robots": result["robots"],
            "api_terms": result["api_terms"],
            "requested_dates": [result["by_date"][entry["date"]] for entry in result["requested"] if entry["date"] in result["by_date"]],
            "request_count": result["request_count"],
            "page_count": result["page_count"],
            "item_count": len(result["items"]),
            "status": result["status"],
            "note": result["note"],
            "retention": RETENTION,
        },
    }


def write_items_file(out_dir: Path, result: dict[str, Any]) -> Path | None:
    """Write the raw file from a complete pass; keep the old file otherwise."""

    if result["status"] != "ok":
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / OUTPUT_NAME
    lines = [pass_record(result), *result["items"]]
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dates", nargs="*", default=None, help="show dates to query (default: the target shows, then the other featured shows)")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="directory for the raw JSONL file")
    parser.add_argument("--targets", type=Path, default=TARGETS_PATH, help="lore target list")
    parser.add_argument("--featured", type=Path, default=FEATURED_PATH, help="featured-show candidate list")
    parser.add_argument("--per-page", type=int, default=PER_PAGE, help="items per API request")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="page ceiling per date")
    parser.add_argument("--min-interval", type=float, default=MIN_SECONDS_BETWEEN_REQUESTS, help="minimum seconds between requests")
    parser.add_argument("--timeout", type=float, default=REQUEST_TIMEOUT, help="seconds to wait for one response (the property query is slow)")
    args = parser.parse_args()

    if args.dates:
        requested = [RequestedDate(date, "target") for date in args.dates if _ISO_DATE.fullmatch(date)]
        if len(requested) != len(args.dates):
            raise SystemExit("every --dates value must be an ISO date such as 1977-05-22.")
    else:
        requested = requested_dates(load_json(args.targets), load_json(args.featured))
    if not requested:
        raise SystemExit("no show dates to query.")

    transport = MetadataIndexTransport()
    throttle = Throttle(max(args.min_interval, MIN_SECONDS_BETWEEN_REQUESTS))
    result = collect(requested, transport, throttle, per_page=args.per_page, max_pages=args.max_pages, timeout=args.timeout)

    robots = result["robots"]
    print(f"{SITE_NAME} ({HOST}): robots HTTP {robots.get('http_status')}, {result['api_path']} allowed={robots.get('path_allowed')}")
    print(f"  API root: HTTP {result['api_terms'].get('http_status')} — {result['api_terms'].get('description', '')[:160]}")
    path = write_items_file(args.out, result)
    if path is None:
        print(f"  {result['status']}: {result['note']}")
        raise SystemExit(1)
    found = sum(1 for summary in result["by_date"].values() if summary["item_count"])
    print(f"  {result['item_count']} distinct items over {result['request_count']} request(s); {found} of {len(requested)} date(s) had items")
    for summary in result["by_date"].values():
        print(f"    {summary['date']} ({summary['group']}): {summary['item_count']} item(s), {summary['status']}")
    print(f"  -> {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


if __name__ == "__main__":
    main()
