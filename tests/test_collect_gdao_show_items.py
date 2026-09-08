"""Tests for the GDAO show-item collector.

No network calls are made: every request goes through a fake
``PageTransport``, the way ``tests/test_collect_blog_post_index.py`` fakes the
Blogger collector and ``tests/test_site_search.py`` fakes ``site_search``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deadbot.source_reader import FetchedPage

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import collect_gdao_show_items as cgs  # noqa: E402


HOST = cgs.HOST
ROBOTS_ALLOW = "User-agent: *\nDisallow: /admin\nAllow: /\n"
ROBOTS_DENY = "User-agent: *\nDisallow: /api\nAllow: /\n"
API_TERMS = "<h1>Omeka S REST API</h1><p>This is the REST API root endpoint. Some resources require authentication.</p>"


class FakeTransport:
    """Exact-URL fake; anything not registered answers HTTP 404."""

    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float = 12.0) -> FetchedPage:
        self.calls.append(url)
        return self.pages.get(url, FetchedPage(404, url, "text/html", "not found"))


def _json_page(url: str, payload) -> FetchedPage:
    return FetchedPage(200, url, "application/json", json.dumps(payload))


def _item(
    item_id: int,
    *,
    title: str = "Poster",
    template: int | None = 26,
    temporal: tuple[str, ...] = ("1977-05-22T00:00:00Z",),
    date: tuple[str, ...] = (),
    sortable: tuple[str, ...] = (),
    description: str = "",
    creator: str = "Kelley, Alton",
    coverage: tuple[str, ...] = ("Sportatorium - May 22, 1977",),
) -> dict:
    """One Omeka S item payload, including the fields that must not be stored."""

    def values(entries: tuple[str, ...], property_id: int) -> list[dict]:
        return [{"type": "literal", "property_id": property_id, "is_public": True, "@value": value} for value in entries]

    item = {
        "@context": f"https://{HOST}/api-context",
        "@id": f"https://{HOST}/api/items/{item_id}",
        "@type": "o:Item",
        "o:id": item_id,
        "o:is_public": True,
        "o:title": title,
        "o:thumbnail": None,
        "thumbnail_display_urls": {"large": f"https://{HOST}/files/large/{item_id}.jpg"},
        "o:primary_media": {"o:id": item_id + 1},
        "o:media": [{"o:id": item_id + 1}],
        "o:item_set": [{"o:id": 1}],
        "dcterms:title": values((title,), 1),
        "dcterms:temporal": values(temporal, 41),
        "dcterms:coverage": values(coverage, 14),
        "dcterms:tableOfContents": values(("Set 1: Jack Straw, Peggy-O",), 18),
    }
    if template is not None:
        item["o:resource_template"] = {"o:id": template}
    if date:
        item["dcterms:date"] = values(date, 7)
    if sortable:
        item["gdao:sortableDate"] = values(sortable, 240)
    if description:
        item["dcterms:description"] = values((description,), 4)
    if creator:
        item["dcterms:creator"] = values((creator,), 2)
    return item


def _base_pages(robots: str = ROBOTS_ALLOW) -> dict[str, FetchedPage]:
    robots_url = f"https://{HOST}/robots.txt"
    terms_url = f"https://{HOST}/api"
    templates_url = cgs.reference_url("resource_templates")
    sets_url = cgs.reference_url("item_sets")
    return {
        robots_url: FetchedPage(200, robots_url, "text/plain", robots),
        terms_url: FetchedPage(200, terms_url, "text/html", API_TERMS),
        templates_url: _json_page(templates_url, [{"o:id": 26, "o:label": "Poster"}, {"o:id": 4, "o:label": "Oral History"}]),
        sets_url: _json_page(sets_url, [{"o:id": 1, "o:title": "Grateful Dead Archive"}]),
    }


def _date_pages(pages: dict[str, FetchedPage], date: str, page_items: list[list[dict]], per_page: int) -> dict[str, FetchedPage]:
    for offset, items in enumerate(page_items):
        url = cgs.items_query_url(date, page=offset + 1, per_page=per_page)
        pages[url] = _json_page(url, items)
    return pages


def _collect(transport: FakeTransport, dates, *, per_page: int = 2, max_pages: int = 5) -> dict:
    return cgs.collect(
        [cgs.RequestedDate(date, "target") for date in dates],
        transport,
        cgs.Throttle(0.0),
        per_page=per_page,
        max_pages=max_pages,
    )


# ---------------------------------------------------------------------------
# Courtesy: robots and the API's own terms
# ---------------------------------------------------------------------------


def test_robots_and_api_terms_are_read_before_any_item_query():
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(1)], []], 2)
    transport = FakeTransport(pages)

    result = _collect(transport, ["1977-05-22"])

    assert result["status"] == "ok"
    assert transport.calls[0] == f"https://{HOST}/robots.txt"
    assert transport.calls[1] == f"https://{HOST}/api"
    assert result["robots"]["path_allowed"] is True
    assert "Disallow: /admin" in result["robots"]["applicable_rules"]
    assert "REST API root endpoint" in result["api_terms"]["description"]


def test_a_missing_robots_file_is_read_as_unrestricted():
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(1)], []], 2)
    del pages[f"https://{HOST}/robots.txt"]
    transport = FakeTransport(pages)

    result = _collect(transport, ["1977-05-22"])

    assert result["robots"]["http_status"] == 404
    assert result["robots"]["path_allowed"] is True
    assert result["status"] == "ok"
    assert len(result["items"]) == 1


def test_robots_disallowing_the_api_stops_the_pass_before_any_item_query():
    transport = FakeTransport(_base_pages(ROBOTS_DENY))

    result = _collect(transport, ["1977-05-22"])

    assert result["status"] == "skipped-robots"
    assert result["items"] == []
    assert not [call for call in transport.calls if "/api/items" in call]


# ---------------------------------------------------------------------------
# Pagination and retry safety
# ---------------------------------------------------------------------------


def test_pagination_walks_pages_until_a_short_page_ends_the_date():
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(1), _item(2)], [_item(3)]], 2)
    transport = FakeTransport(pages)

    result = _collect(transport, ["1977-05-22"])

    assert [call for call in transport.calls if "/api/items" in call] == [
        cgs.items_query_url("1977-05-22", page=1, per_page=2),
        cgs.items_query_url("1977-05-22", page=2, per_page=2),
    ]
    assert [record["raw_payload"]["item_id"] for record in result["items"]] == [1, 2, 3]
    assert result["by_date"]["1977-05-22"]["item_count"] == 3
    assert result["request_count"] == 6  # robots, api terms, two reference lookups, two item pages


def test_an_item_matching_two_requested_dates_is_stored_once_with_both_dates():
    pages = _base_pages()
    _date_pages(pages, "1989-07-17", [[_item(9, temporal=("1989-07-17T00:00:00Z", "1989-07-18T00:00:00Z"))], []], 2)
    _date_pages(pages, "1989-07-18", [[_item(9, temporal=("1989-07-17T00:00:00Z", "1989-07-18T00:00:00Z"))], []], 2)
    transport = FakeTransport(pages)

    result = _collect(transport, ["1989-07-17", "1989-07-18"])

    assert len(result["items"]) == 1
    assert result["items"][0]["raw_payload"]["queried_dates"] == ["1989-07-17", "1989-07-18"]
    assert result["by_date"]["1989-07-18"]["item_count"] == 1


def test_a_failed_page_aborts_the_pass_and_leaves_the_raw_file_untouched(tmp_path):
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(1), _item(2)]], 2)  # page 2 answers 404
    transport = FakeTransport(pages)
    existing = tmp_path / "gdao-show-items.jsonl"
    existing.write_text("previous pass\n", encoding="utf-8")

    result = _collect(transport, ["1977-05-22"])

    assert result["status"] == "aborted"
    assert result["items"] == []
    assert cgs.write_items_file(tmp_path, result) is None
    assert existing.read_text(encoding="utf-8") == "previous pass\n"


def test_a_page_that_is_not_json_aborts_the_pass():
    pages = _base_pages()
    url = cgs.items_query_url("1977-05-22", page=1, per_page=2)
    pages[url] = FetchedPage(200, url, "text/html", "<html>maintenance</html>")
    transport = FakeTransport(pages)

    result = _collect(transport, ["1977-05-22"])

    assert result["status"] == "aborted"
    assert "did not return" in result["note"]


def test_a_date_with_no_items_is_recorded_as_reviewed_and_absent():
    pages = _date_pages(_base_pages(), "1970-05-08", [[]], 2)
    transport = FakeTransport(pages)

    result = _collect(transport, ["1970-05-08"])

    assert result["status"] == "ok"
    assert result["by_date"]["1970-05-08"]["item_count"] == 0
    assert result["by_date"]["1970-05-08"]["status"] == "none-at-source"


# ---------------------------------------------------------------------------
# Record shaping: metadata only
# ---------------------------------------------------------------------------


def test_a_stored_record_keeps_metadata_only_and_never_files_or_set_lists():
    long_description = "A fan's account of the night. " * 20
    pages = _date_pages(
        _base_pages(),
        "1977-05-22",
        [[_item(1, description=long_description, template=4, title="A night in Pembroke Pines")], []],
        2,
    )
    transport = FakeTransport(pages)

    result = _collect(transport, ["1977-05-22"])
    record = result["items"][0]
    payload = record["raw_payload"]

    assert record["source"] == "gdao"
    assert record["source_record_id"] == "1"
    assert record["source_url"] == f"https://{HOST}/items/show/1"
    assert payload["title"] == "A night in Pembroke Pines"
    assert payload["item_type"] == "Oral History"
    assert payload["collections"] == ["Grateful Dead Archive"]
    assert payload["date_fields"]["dcterms:temporal"] == ["1977-05-22T00:00:00Z"]
    assert len(payload["description"]) == cgs.MAX_DESCRIPTION_CHARS
    assert payload["description"] == long_description.strip()[: cgs.MAX_DESCRIPTION_CHARS]
    serialized = json.dumps(record)
    assert "thumbnail" not in serialized
    assert "o:media" not in serialized
    assert "Jack Straw" not in serialized  # dcterms:tableOfContents is a set list, never stored


def test_description_markup_is_stripped_before_it_is_capped():
    pages = _date_pages(
        _base_pages(),
        "1977-05-22",
        [[_item(1, description="<div>Second&nbsp;remaster<br/>of this show.</div>")], []],
        2,
    )
    transport = FakeTransport(pages)

    payload = _collect(transport, ["1977-05-22"])["items"][0]["raw_payload"]

    assert payload["description"] == "Second remaster of this show."


def test_an_item_without_a_resource_template_keeps_an_empty_item_type():
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(1, template=None, creator="")], []], 2)
    transport = FakeTransport(pages)

    payload = _collect(transport, ["1977-05-22"])["items"][0]["raw_payload"]

    assert payload["item_type"] == ""
    assert payload["creator"] == ""


# ---------------------------------------------------------------------------
# The raw file
# ---------------------------------------------------------------------------


def test_the_raw_file_leads_with_the_pass_metadata_then_one_line_per_item(tmp_path):
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(2), _item(1)], []], 2)
    transport = FakeTransport(pages)

    result = _collect(transport, ["1977-05-22"])
    path = cgs.write_items_file(tmp_path, result)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert path.name == "gdao-show-items.jsonl"
    assert lines[0]["raw_payload"]["record_type"] == "pass_metadata"
    assert lines[0]["raw_payload"]["item_count"] == 2
    assert lines[0]["raw_payload"]["requested_dates"][0] == {"date": "1977-05-22", "group": "target", "item_count": 2, "status": "found", "pages": 2}
    assert "metadata only" in lines[0]["raw_payload"]["retention"].casefold()
    assert [line["raw_payload"]["item_id"] for line in lines[1:]] == [1, 2]
    assert all(line["raw_payload"]["record_type"] == "item" for line in lines[1:])


def test_requested_dates_put_the_target_shows_before_the_other_featured_shows():
    targets = {"shows": [{"show_date": "1977-05-22"}, {"show_date": "1989-07-17"}]}
    featured = {"candidates": [{"show_date": "1989-07-17"}, {"show_date": "1972-08-27"}]}

    requested = cgs.requested_dates(targets, featured)

    assert [(entry.date, entry.group) for entry in requested] == [
        ("1977-05-22", "target"),
        ("1989-07-17", "target"),
        ("1972-08-27", "featured"),
    ]


# ---------------------------------------------------------------------------
# A stumble is not an absence
# ---------------------------------------------------------------------------


class FlakyTransport(FakeTransport):
    """Answers the first request for one URL with a transport failure."""

    def __init__(self, pages: dict[str, FetchedPage], flaky_url: str) -> None:
        super().__init__(pages)
        self.flaky_url = flaky_url
        self.failed = False

    def get(self, url: str, *, timeout: float = 12.0) -> FetchedPage:
        if url == self.flaky_url and not self.failed:
            self.failed = True
            self.calls.append(url)
            return FetchedPage(0, url, "", "")
        return super().get(url, timeout=timeout)


def test_one_transport_failure_is_retried_rather_than_read_as_an_absence():
    pages = _date_pages(_base_pages(), "1977-05-22", [[_item(1)], []], 2)
    url = cgs.items_query_url("1977-05-22", page=1, per_page=2)
    transport = FlakyTransport(pages, url)

    result = _collect(transport, ["1977-05-22"])

    assert transport.calls.count(url) == 2
    assert result["status"] == "ok"
    assert result["by_date"]["1977-05-22"]["item_count"] == 1
