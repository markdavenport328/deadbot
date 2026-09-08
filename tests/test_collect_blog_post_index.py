"""Tests for the Blogger post-index collector.

No network calls are made: every request goes through a fake ``PageTransport``
the way ``tests/test_site_search.py`` fakes ``deadbot.site_search``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deadbot.source_reader import FetchedPage

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import collect_blog_post_index as cbi  # noqa: E402


HOST = "lostlivedead.blogspot.com"
SITE = {
    "site_id": "lost-live-dead",
    "name": "Lost Live Dead",
    "host": HOST,
    "search": {"method": "blogger_feed"},
}
ROBOTS_ALLOW = "User-agent: *\nDisallow: /search\nAllow: /\n\nSitemap: https://x/sitemap.xml\n"
ROBOTS_DENY = "User-agent: *\nDisallow: /feeds\nAllow: /\n"


class FakeTransport:
    """Exact-URL fake; anything not registered answers HTTP 404."""

    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float = 12.0) -> FetchedPage:
        self.calls.append(url)
        return self.pages.get(url, FetchedPage(404, url, "text/html", "not found"))


def _text_page(url: str, body: str) -> FetchedPage:
    return FetchedPage(200, url, "text/plain", body)


def _entry(index: int, *, title: str | None = None, labels: tuple[str, ...] = ("1972",), author: str | None = "Corry342") -> dict:
    slug = f"post-{index}"
    entry = {
        "id": {"$t": f"tag:blogger.com,1999:blog-1.post-{index}"},
        "published": {"$t": f"2012-08-{(index % 28) + 1:02d}T09:00:00.000-07:00"},
        "updated": {"$t": f"2013-01-{(index % 28) + 1:02d}T09:00:00.000-07:00"},
        "category": [{"scheme": "http://www.blogger.com/atom/ns#", "term": term} for term in labels],
        "title": {"type": "text", "$t": title or f"Post number {index}"},
        "content": {"type": "html", "$t": "<p>Post body that must never be stored.</p>"},
        "summary": {"$t": "A summary that must never be stored."},
        "link": [
            {"rel": "replies", "href": f"https://{HOST}/feeds/{index}/comments/default"},
            {"rel": "alternate", "href": f"https://{HOST}/2012/08/{slug}.html"},
        ],
        "media$thumbnail": {"url": "https://img.blogblog.com/x.jpg"},
    }
    if author:
        entry["author"] = [{"name": {"$t": author}, "email": {"$t": "noreply@blogger.com"}}]
    return entry


def _feed_page(url: str, entries: list[dict], total: int) -> FetchedPage:
    document = {
        "feed": {
            "title": {"$t": "Lost Live Dead"},
            "openSearch$totalResults": {"$t": str(total)},
            "entry": entries,
        }
    }
    return FetchedPage(200, url, "application/json", json.dumps(document))


def _pages(page_size: int, counts: list[int], total: int) -> dict[str, FetchedPage]:
    """Register one feed page per entry count, paged the way Blogger pages.

    Blogger returns as many entries as fit its own response budget rather than
    the requested ``max-results``, so the next ``start-index`` is the previous
    one plus the number of entries that actually came back.
    """

    pages: dict[str, FetchedPage] = {
        f"https://{HOST}/robots.txt": _text_page(f"https://{HOST}/robots.txt", ROBOTS_ALLOW)
    }
    index = 1
    made = 0
    for count in counts:
        url = cbi.feed_page_url(HOST, index, page_size)
        pages[url] = _feed_page(url, [_entry(made + offset) for offset in range(count)], total)
        made += count
        index += count
    return pages


def _collect(transport: FakeTransport, *, page_size: int = 3, site: dict | None = None) -> dict:
    return cbi.collect_host(site or SITE, transport, cbi.Throttle(0.0), page_size=page_size, max_pages=6)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_pagination_walks_pages_until_the_reported_total_is_reached():
    transport = FakeTransport(_pages(3, [3, 3, 2], 8))

    result = _collect(transport)

    assert result["status"] == "ok"
    assert [call for call in transport.calls if "robots" in call] == [f"https://{HOST}/robots.txt"]
    assert [call for call in transport.calls if "feeds" in call] == [
        cbi.feed_page_url(HOST, 1, 3),
        cbi.feed_page_url(HOST, 4, 3),
        cbi.feed_page_url(HOST, 7, 3),
    ]
    assert result["page_count"] == 3
    assert result["entry_count"] == 8
    assert len(result["posts"]) == 8
    assert result["total_results_reported"] == 8


def test_pagination_advances_by_the_entries_a_page_actually_returned():
    # Blogger ignores max-results when its response budget is smaller, so a
    # page of 150 can come back with two entries and the walk must continue.
    transport = FakeTransport(_pages(150, [2, 2, 1], 5))

    result = _collect(transport, page_size=150)

    assert [call for call in transport.calls if "feeds" in call] == [
        cbi.feed_page_url(HOST, 1, 150),
        cbi.feed_page_url(HOST, 3, 150),
        cbi.feed_page_url(HOST, 5, 150),
    ]
    assert result["entry_count"] == 5 and len(result["posts"]) == 5


def test_a_first_page_holding_every_post_stops_after_one_request():
    transport = FakeTransport(_pages(3, [2], 2))

    result = _collect(transport)

    assert result["page_count"] == 1 and result["entry_count"] == 2
    assert [call for call in transport.calls if "feeds" in call] == [cbi.feed_page_url(HOST, 1, 3)]


def test_an_empty_page_ends_a_host_whose_total_is_never_reached():
    transport = FakeTransport(_pages(3, [3, 0], 9))

    result = _collect(transport)

    assert result["status"] == "ok"
    assert result["page_count"] == 2 and result["entry_count"] == 3
    assert len(result["posts"]) == 3


def test_duplicate_post_urls_across_pages_are_kept_once():
    pages = _pages(3, [3, 2], 5)
    repeat_url = cbi.feed_page_url(HOST, 4, 3)
    pages[repeat_url] = _feed_page(repeat_url, [_entry(2), _entry(3)], 5)
    transport = FakeTransport(pages)

    result = _collect(transport)

    urls = [post["source_url"] for post in result["posts"]]
    assert len(urls) == len(set(urls)) == 4


def test_posts_are_sorted_by_url_for_a_stable_raw_file():
    transport = FakeTransport(_pages(3, [3, 1], 4))

    result = _collect(transport)

    urls = [post["source_url"] for post in result["posts"]]
    assert urls == sorted(urls)


# ---------------------------------------------------------------------------
# Record shaping: metadata only
# ---------------------------------------------------------------------------


def test_post_record_keeps_metadata_and_never_post_text():
    entry = _entry(1, title="Dark Star &amp; <b>Veneta</b>, 8/27/72", labels=("1972", "Veneta"))
    url = cbi.feed_page_url(HOST, 1, 3)
    transport = FakeTransport(
        {
            f"https://{HOST}/robots.txt": _text_page(f"https://{HOST}/robots.txt", ROBOTS_ALLOW),
            url: _feed_page(url, [entry], 1),
        }
    )

    post = _collect(transport)["posts"][0]

    assert post["source"] == "lost-live-dead"
    assert post["source_record_id"] == "tag:blogger.com,1999:blog-1.post-1"
    assert post["source_url"] == f"https://{HOST}/2012/08/post-1.html"
    assert post["retrieved_at"].endswith("Z")
    payload = post["raw_payload"]
    assert payload["record_type"] == "post"
    assert payload["title"] == "Dark Star & Veneta, 8/27/72"
    assert payload["published"] == "2012-08-02T09:00:00.000-07:00"
    assert payload["updated"] == "2013-01-02T09:00:00.000-07:00"
    assert payload["labels"] == ["1972", "Veneta"]
    assert payload["author"] == "Corry342"
    assert payload["host"] == HOST
    assert payload["site_name"] == "Lost Live Dead"
    assert payload["resource_type"] == "show-history-post"
    assert payload["http_status"] == 200
    assert payload["request_url"] == url
    assert set(payload) == {
        "record_type",
        "host",
        "site_name",
        "resource_type",
        "title",
        "published",
        "updated",
        "labels",
        "author",
        "request_url",
        "http_status",
    }
    serialized = json.dumps(post)
    for forbidden in ("must never be stored", "img.blogblog", "blogblog.com"):
        assert forbidden not in serialized


def test_a_post_without_an_author_stores_an_empty_creator():
    url = cbi.feed_page_url(HOST, 1, 3)
    transport = FakeTransport(
        {
            f"https://{HOST}/robots.txt": _text_page(f"https://{HOST}/robots.txt", ROBOTS_ALLOW),
            url: _feed_page(url, [_entry(1, author=None)], 1),
        }
    )

    assert _collect(transport)["posts"][0]["raw_payload"]["author"] == ""


def test_an_entry_without_an_alternate_link_is_skipped():
    entry = _entry(1)
    entry["link"] = [{"rel": "replies", "href": "https://x/comments"}]
    url = cbi.feed_page_url(HOST, 1, 3)
    transport = FakeTransport(
        {
            f"https://{HOST}/robots.txt": _text_page(f"https://{HOST}/robots.txt", ROBOTS_ALLOW),
            url: _feed_page(url, [entry, _entry(2)], 2),
        }
    )

    result = _collect(transport)
    assert len(result["posts"]) == 1
    assert result["skipped_entries"] == 1


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


def test_robots_is_requested_before_the_feed_and_recorded():
    transport = FakeTransport(_pages(3, [1], 1))

    result = _collect(transport)

    assert transport.calls[0] == f"https://{HOST}/robots.txt"
    robots = result["robots"]
    assert robots["url"] == f"https://{HOST}/robots.txt"
    assert robots["http_status"] == 200
    assert robots["feed_path_allowed"] is True
    assert "Disallow: /search" in robots["applicable_rules"]
    assert robots["crawl_delay"] is None


def test_a_disallowed_feed_path_skips_the_host_without_fetching_it():
    transport = FakeTransport(
        {f"https://{HOST}/robots.txt": _text_page(f"https://{HOST}/robots.txt", ROBOTS_DENY)}
    )

    result = _collect(transport)

    assert result["status"] == "skipped-robots"
    assert result["robots"]["feed_path_allowed"] is False
    assert result["posts"] == []
    assert transport.calls == [f"https://{HOST}/robots.txt"]
    assert "robots.txt" in result["note"]


def test_a_missing_robots_file_is_treated_as_allowed_and_noted():
    pages = _pages(3, [1], 1)
    pages.pop(f"https://{HOST}/robots.txt")
    transport = FakeTransport(pages)

    result = _collect(transport)

    assert result["status"] == "ok"
    assert result["robots"]["http_status"] == 404
    assert result["robots"]["feed_path_allowed"] is True
    assert "no robots.txt" in result["robots"]["note"]


def test_an_unreachable_robots_file_skips_the_host():
    transport = FakeTransport({f"https://{HOST}/robots.txt": FetchedPage(0, f"https://{HOST}/robots.txt", "", "")})

    result = _collect(transport)

    assert result["status"] == "skipped-robots"
    assert result["posts"] == []


def test_a_crawl_delay_longer_than_the_floor_is_honored(monkeypatch):
    monkeypatch.setattr(cbi.time, "sleep", lambda seconds: None)
    body = "User-agent: *\nCrawl-delay: 7\nAllow: /\n"
    pages = _pages(3, [1], 1)
    pages[f"https://{HOST}/robots.txt"] = _text_page(f"https://{HOST}/robots.txt", body)
    transport = FakeTransport(pages)
    throttle = cbi.Throttle(2.0)

    result = cbi.collect_host(SITE, transport, throttle, page_size=3)

    assert result["robots"]["crawl_delay"] == 7.0
    assert throttle.min_interval == 7.0


# ---------------------------------------------------------------------------
# Retry safety
# ---------------------------------------------------------------------------


def test_a_failing_page_aborts_the_host_and_keeps_no_partial_posts():
    pages = _pages(3, [3, 3], 9)
    broken = cbi.feed_page_url(HOST, 4, 3)
    pages[broken] = FetchedPage(503, broken, "text/html", "")
    transport = FakeTransport(pages)

    result = _collect(transport)

    assert result["status"] == "aborted"
    assert result["posts"] == []
    assert "503" in result["note"]


def test_a_feed_that_never_ends_aborts_at_the_page_ceiling():
    transport = FakeTransport(_pages(3, [1] * 8, 500))

    result = _collect(transport)

    assert result["status"] == "aborted"
    assert result["posts"] == []
    assert "--max-pages" in result["note"]


def test_unparsable_json_aborts_the_host():
    pages = _pages(3, [1], 1)
    url = cbi.feed_page_url(HOST, 1, 3)
    pages[url] = FetchedPage(200, url, "application/json", "<html>not json</html>")
    transport = FakeTransport(pages)

    result = _collect(transport)

    assert result["status"] == "aborted"
    assert result["posts"] == []


def test_an_aborted_host_leaves_an_existing_raw_file_untouched(tmp_path):
    out = tmp_path / "blog-post-index-lostlivedead.jsonl"
    out.write_text('{"kept": true}\n', encoding="utf-8")
    pages = _pages(3, [1], 1)
    url = cbi.feed_page_url(HOST, 1, 3)
    pages[url] = FetchedPage(500, url, "text/html", "")

    written = cbi.write_host_file(tmp_path, _collect(FakeTransport(pages)))

    assert written is None
    assert out.read_text(encoding="utf-8") == '{"kept": true}\n'


# ---------------------------------------------------------------------------
# Output file
# ---------------------------------------------------------------------------


def test_the_raw_file_leads_with_pass_metadata_then_one_line_per_post(tmp_path):
    result = _collect(FakeTransport(_pages(3, [3, 1], 4)))

    path = cbi.write_host_file(tmp_path, result)

    assert path == tmp_path / "blog-post-index-lostlivedead.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    head = lines[0]["raw_payload"]
    assert head["record_type"] == "pass_metadata"
    assert head["host"] == HOST
    assert head["page_count"] == 2 and head["entry_count"] == 4
    assert head["user_agent"] == cbi.USER_AGENT
    assert head["robots"]["feed_path_allowed"] is True
    assert [page["http_status"] for page in head["pages"]] == [200, 200]
    assert lines[0]["retrieved_at"].endswith("Z")
    assert len(lines) == 5
    assert {line["raw_payload"]["record_type"] for line in lines[1:]} == {"post"}


def test_rewriting_the_same_pass_replaces_the_file_completely(tmp_path):
    small = _collect(FakeTransport(_pages(3, [1], 1)))
    cbi.write_host_file(tmp_path, small)
    bigger = _collect(FakeTransport(_pages(3, [3, 1], 4)))

    path = cbi.write_host_file(tmp_path, bigger)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 5


# ---------------------------------------------------------------------------
# Site selection and slugs
# ---------------------------------------------------------------------------


def test_the_summary_feed_is_the_default_path_and_the_one_robots_is_checked_for():
    assert cbi.FEED_PATH == "/feeds/posts/summary"
    assert cbi.feed_page_url(HOST, 1) == f"https://{HOST}/feeds/posts/summary?alt=json&max-results=150&start-index=1"

    result = _collect(FakeTransport(_pages(3, [1], 1)))

    assert result["feed_path"] == "/feeds/posts/summary"
    assert result["robots"]["feed_path"] == "/feeds/posts/summary"


def test_the_full_feed_path_can_be_requested_instead():
    pages = {f"https://{HOST}/robots.txt": _text_page(f"https://{HOST}/robots.txt", ROBOTS_ALLOW)}
    url = cbi.feed_page_url(HOST, 1, 3, "/feeds/posts/default")
    pages[url] = _feed_page(url, [_entry(1)], 1)
    transport = FakeTransport(pages)

    result = cbi.collect_host(SITE, transport, cbi.Throttle(0.0), page_size=3, feed_path="/feeds/posts/default")

    assert result["status"] == "ok" and len(result["posts"]) == 1
    assert transport.calls[1] == url


def test_host_slug_and_resource_type_come_from_the_url_and_the_site():
    assert cbi.host_slug("lostlivedead.blogspot.com") == "lostlivedead"
    assert cbi.host_slug("www.deadessays.blogspot.com") == "deadessays"
    assert cbi.resource_type_for("dead-sources") == "press-transcription"
    assert cbi.resource_type_for("grateful-seconds") == "statistics-post"
    assert cbi.resource_type_for("hooterollin") == "editorial-blog-post"


def test_default_selection_is_the_five_blogger_research_sites():
    sites = cbi.select_sites([])
    assert [site["site_id"] for site in sites] == [
        "lost-live-dead",
        "hooterollin",
        "dead-essays",
        "dead-sources",
        "grateful-seconds",
    ]


def test_a_named_site_or_host_selects_one_entry():
    assert [site["site_id"] for site in cbi.select_sites(["deadessays"])] == ["dead-essays"]
    assert [site["site_id"] for site in cbi.select_sites(["deadsources.blogspot.com"])] == ["dead-sources"]


def test_a_site_without_a_blogger_feed_is_refused():
    try:
        cbi.select_sites(["archive.org"])
    except SystemExit as exit_error:
        assert "blogger" in str(exit_error).casefold()
    else:  # pragma: no cover - the call must fail
        raise AssertionError("a non-Blogger site must be refused")


def test_throttle_waits_the_minimum_interval_between_requests(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(cbi.time, "sleep", lambda seconds: slept.append(seconds))
    clock = iter([0.0, 0.5, 2.0, 10.0, 10.0])
    monkeypatch.setattr(cbi.time, "monotonic", lambda: next(clock))
    throttle = cbi.Throttle(2.0)

    throttle.wait()
    throttle.wait()
    throttle.wait()

    assert slept == [1.5]
