"""Tests for the Dead.net "Greatest Stories Ever Told" essay collector.

No network calls are made: every request goes through a fake ``PageTransport``
(and a fake Dead.net ``HttpTransport`` for the reviewed song-page adapter) the
way ``tests/test_collect_blog_post_index.py`` and ``tests/test_site_search.py``
fake theirs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deadbot.deadnet import DeadnetResearchAdapter, HttpResponse
from deadbot.source_reader import FetchedPage

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import collect_deadnet_song_essays as cdn  # noqa: E402


ROBOTS_ALLOW = "User-agent: *\nDisallow: /admin/\nDisallow: /search/\nAllow: /\n"
ROBOTS_DENY_FEATURES = "User-agent: *\nDisallow: /features/\nAllow: /\n"
SITEMAP_WITHOUT_ESSAYS = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
 <url><loc>https://www.dead.net/</loc></url>
 <url><loc>https://www.dead.net/archives</loc></url>
 <url><loc>https://www.dead.net/deadcast</loc></url>
</urlset>
"""
SECRET = "This essay body must never reach a stored record."


class FakeTransport:
    """Exact-URL fake; anything not registered answers HTTP 404."""

    def __init__(self, pages: dict[str, str], *, statuses: dict[str, int] | None = None) -> None:
        self.pages = pages
        self.statuses = statuses or {}
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float = 12.0) -> FetchedPage:
        self.calls.append(url)
        if url in self.statuses:
            return FetchedPage(self.statuses[url], url, "text/html", "")
        if url not in self.pages:
            return FetchedPage(404, url, "text/html", "not found")
        return FetchedPage(200, url, "text/html", self.pages[url])


class FakeDeadnetTransport:
    """A Dead.net ``HttpTransport`` answering /song/<slug> reads."""

    def __init__(self, songs: dict[str, dict[str, str]]) -> None:
        self.songs = songs
        self.calls: list[str] = []

    def get(self, url: str, *, params=None, timeout: float = 8.0) -> HttpResponse:
        self.calls.append(url)
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if slug not in self.songs:
            return HttpResponse(status=404, payload={"results": []})
        song = self.songs[slug]
        return HttpResponse(
            status=200,
            payload={"results": [{"id": slug, "title": song["title"], "url": url, "description": song.get("description")}]},
        )


def _teaser(slug: str, title: str, *, byline: str = "David Dodd", date: str = "2013-12-12") -> str:
    path = f"/features/greatest-stories-ever-told/greatest-stories-ever-told-{slug}"
    return f"""
    <div class="views-row">
    <article data-history-node-id="374636" about="{path}" class="node node--type-story node--view-mode-teaser">
      <h2><a href="{path}" rel="bookmark"><span class="field field--name-title field--type-string field--label-hidden">{title}</span></a></h2>
      <footer class="node__meta">
        <article typeof="schema:Person" about="/member/lilgoldie" class="profile">
          <div class="field field--name-field-user-picture"><img src="/x.jpg" /></div>
        </article>
        <div class="node__submitted">Submitted by <span>lilgoldie</span> on
          <span class="field field--name-created"><time datetime="{date}T12:25:19-08:00" class="datetime">Thu, 12/12/2013 - 12:25</time></span>
        </div>
      </footer>
      <div class="clearfix text-formatted field field--name-body field__item"><p><span><strong>By {byline}</strong></span></p>
      <p>{SECRET}</p></div>
    </article>
    </div>
    """


def _index_page(teasers: list[str]) -> str:
    return "<html><head><title>Greatest Stories Ever Told | Grateful Dead</title></head><body>" + "".join(teasers) + "</body></html>"


def _essay_page(title: str, *, byline: str = "David Dodd", date: str = "2014-01-02") -> str:
    return (
        f"<html><head><title>{title} | Grateful Dead</title>"
        f'<meta property="og:description" content="Official Site Of The Grateful Dead" />'
        "</head><body>"
        f'<div class="node__submitted">on <span class="field field--name-created"><time datetime="{date}T09:00:00-08:00">x</time></span></div>'
        f'<div class="field field--name-body field__item"><p><strong>By {byline}</strong></p><p>{SECRET}</p></div>'
        "</body></html>"
    )


TARGETS = [
    {"song_id": "song-candyman", "title": "Candyman", "slug": "candyman"},
    {"song_id": "song-attics-of-my-life", "title": "Attics Of My Life", "slug": "attics-of-my-life"},
    {"song_id": "song-black-queen", "title": "Black Queen", "slug": "black-queen"},
]


def _pages(*, index_pages: list[str], extra: dict[str, str] | None = None) -> dict[str, str]:
    pages = {
        f"https://{cdn.HOST}/robots.txt": ROBOTS_ALLOW,
        cdn.SITEMAP_URL: SITEMAP_WITHOUT_ESSAYS,
    }
    for number, body in enumerate(index_pages):
        pages[cdn.index_page_url(number)] = body
    pages.update(extra or {})
    return pages


def _collect(pages: dict[str, str], *, statuses: dict[str, int] | None = None, songs: dict[str, dict[str, str]] | None = None, targets=None):
    transport = FakeTransport(pages, statuses=statuses)
    song_transport = FakeDeadnetTransport(songs if songs is not None else {})
    adapter = DeadnetResearchAdapter(song_transport)
    result = cdn.collect(transport, adapter, targets if targets is not None else TARGETS, max_pages=6)
    return result, transport, song_transport


# --- robots ------------------------------------------------------------------


def test_robots_is_the_first_request_and_its_finding_is_kept():
    result, transport, _ = _collect(_pages(index_pages=[_index_page([_teaser("candyman", 'Greatest Stories Ever Told - "Candyman"')]), _index_page([])]))
    assert transport.calls[0] == f"https://{cdn.HOST}/robots.txt"
    robots = result["robots"]
    assert robots["http_status"] == 200
    assert robots["paths"] == {cdn.ESSAY_PATH_PREFIX: True, cdn.SONG_PATH_PREFIX: True}
    assert "Disallow: /search/" in robots["applicable_rules"]


def test_a_disallowed_feature_path_skips_the_pass_without_fetching_pages():
    pages = _pages(index_pages=[_index_page([])])
    pages[f"https://{cdn.HOST}/robots.txt"] = ROBOTS_DENY_FEATURES
    result, transport, _ = _collect(pages)
    assert result["status"] == "skipped-robots"
    assert result["essays"] == []
    assert transport.calls == [f"https://{cdn.HOST}/robots.txt"]


def test_an_unreadable_robots_file_skips_the_pass():
    result, transport, _ = _collect(_pages(index_pages=[_index_page([])]), statuses={f"https://{cdn.HOST}/robots.txt": 500})
    assert result["status"] == "skipped-robots"
    assert "500" in result["note"]


# --- sitemap discovery -------------------------------------------------------


def test_the_sitemap_is_tried_first_and_its_lack_of_essays_is_recorded():
    result, transport, _ = _collect(_pages(index_pages=[_index_page([_teaser("candyman", 'Greatest Stories Ever Told - "Candyman"')]), _index_page([])]))
    sitemap = result["sitemap"]
    assert sitemap["http_status"] == 200
    assert sitemap["location_count"] == 3
    assert sitemap["essay_url_count"] == 0
    assert cdn.SITEMAP_URL in transport.calls
    assert result["discovery"] == "series index"


def test_a_sitemap_index_is_followed_and_essay_urls_are_used_when_present():
    child = "https://www.dead.net/sitemap-1.xml"
    pages = _pages(index_pages=[_index_page([])])
    pages[cdn.SITEMAP_URL] = f"<sitemapindex><sitemap><loc>{child}</loc></sitemap></sitemapindex>"
    pages[child] = (
        "<urlset><url><loc>https://www.dead.net/features/greatest-stories-ever-told/"
        "greatest-stories-ever-told-candyman</loc></url><url><loc>https://www.dead.net/band</loc></url></urlset>"
    )
    pages["https://www.dead.net/features/greatest-stories-ever-told/greatest-stories-ever-told-candyman"] = _essay_page(
        'Greatest Stories Ever Told - "Candyman" | Grateful Dead'
    )
    result, _, _ = _collect(pages)
    assert result["sitemap"]["essay_url_count"] == 1
    assert result["discovery"] == "sitemap"
    assert [essay["raw_payload"]["url_slug"] for essay in result["essays"]] == ["candyman"]
    assert result["essays"][0]["raw_payload"]["discovered_via"] == "sitemap"


# --- the series index --------------------------------------------------------


def test_the_index_walk_shapes_one_metadata_record_per_essay():
    pages = _pages(
        index_pages=[
            _index_page([_teaser("candyman", 'Greatest Stories Ever Told - "Candyman"'), _teaser("attics-my-life", 'Greatest Stories Ever Told - "Attics of My Life"')]),
            _index_page([]),
        ]
    )
    result, _, _ = _collect(pages)
    assert result["status"] == "ok"
    assert result["index"]["page_count"] == 2
    payloads = {essay["raw_payload"]["url_slug"]: essay["raw_payload"] for essay in result["essays"]}
    assert set(payloads) == {"candyman", "attics-my-life"}
    candyman = payloads["candyman"]
    assert candyman["title"] == 'Greatest Stories Ever Told - "Candyman"'
    assert candyman["byline"] == "David Dodd"
    assert candyman["published_date"] == "2013-12-12"
    assert candyman["resource_type"] == cdn.ESSAY_RESOURCE_TYPE
    assert candyman["http_status"] == 200
    assert candyman["discovered_via"] == "series index"
    assert result["essays"][0]["source_url"].startswith("https://www.dead.net/features/greatest-stories-ever-told/")


def test_the_index_walk_stops_on_the_first_page_without_essays():
    pages = _pages(index_pages=[_index_page([_teaser("candyman", "Candyman")]), _index_page([]), _index_page([_teaser("deal", "Deal")])])
    result, transport, _ = _collect(pages)
    assert result["index"]["page_count"] == 2
    assert cdn.index_page_url(2) not in transport.calls


def test_a_failed_index_page_aborts_the_pass_and_keeps_no_essays():
    pages = _pages(index_pages=[_index_page([_teaser("candyman", "Candyman")])])
    result, _, _ = _collect(pages, statuses={cdn.index_page_url(1): 503})
    assert result["status"] == "aborted"
    assert result["essays"] == []
    assert "503" in result["note"]


def test_no_page_text_is_stored_anywhere_in_the_pass(tmp_path):
    pages = _pages(index_pages=[_index_page([_teaser("candyman", 'Greatest Stories Ever Told - "Candyman"')]), _index_page([])])
    result, _, _ = _collect(pages, songs={"candyman": {"title": "Candyman", "description": "Song page"}})
    path = cdn.write_raw_file(tmp_path, result)
    assert path is not None
    assert SECRET not in path.read_text(encoding="utf-8")


def test_a_long_description_is_cut_to_two_hundred_characters():
    long_description = "x" * 400
    body = (
        '<html><head><title>Greatest Stories Ever Told - "Candyman"</title>'
        f'<meta name="description" content="{long_description}" /></head><body>'
        "<p><strong>By David Dodd</strong></p></body></html>"
    )
    metadata = cdn.page_metadata(body)
    assert len(metadata["description"]) == cdn.MAX_DESCRIPTION
    assert metadata["byline"] == "David Dodd"


# --- target coverage ---------------------------------------------------------


def test_a_target_missing_from_the_index_is_confirmed_by_candidate_url():
    essay_url = f"https://{cdn.HOST}{cdn.ESSAY_PATH_PREFIX}greatest-stories-ever-told-black-queen"
    pages = _pages(
        index_pages=[_index_page([_teaser("candyman", 'Greatest Stories Ever Told - "Candyman"'), _teaser("attics-my-life", "Attics of My Life")]), _index_page([])],
        extra={essay_url: _essay_page('Greatest Stories Ever Told - "Black Queen"')},
    )
    result, transport, _ = _collect(pages)
    slugs = {essay["raw_payload"]["url_slug"]: essay["raw_payload"] for essay in result["essays"]}
    assert slugs["black-queen"]["discovered_via"] == "candidate url"
    assert slugs["black-queen"]["published_date"] == "2014-01-02"
    # Only the missing target is probed; the two found in the index are not refetched.
    assert sum(1 for call in transport.calls if call.startswith(f"https://{cdn.HOST}{cdn.ESSAY_PATH_PREFIX}")) == 1


def test_candidate_attempts_are_recorded_and_a_404_is_not_an_essay():
    pages = _pages(index_pages=[_index_page([_teaser("candyman", "Candyman")]), _index_page([])])
    result, _, _ = _collect(pages)
    attempts = {(attempt["song_id"], attempt["http_status"]) for attempt in result["candidate_attempts"]}
    assert ("song-black-queen", 404) in attempts
    assert all(essay["raw_payload"]["url_slug"] != "black-queen" for essay in result["essays"])
    assert result["targets"]["song-black-queen"]["essay"] == "not found at source"
    assert result["targets"]["song-candyman"]["essay"] == "found"


def test_a_target_found_under_drupals_path_counter_counts_as_found():
    pages = _pages(index_pages=[_index_page([_teaser("black-queen-0", 'Greatest Stories Ever Told - "Black Queen"')]), _index_page([])])
    result, transport, _ = _collect(pages)
    assert result["targets"]["song-black-queen"]["essay"] == "found"
    assert not [call for call in transport.calls if "black-queen" in call and call.startswith(f"https://{cdn.HOST}{cdn.ESSAY_PATH_PREFIX}")]


def test_every_song_page_read_is_recorded_with_its_outcome():
    pages = _pages(index_pages=[_index_page([_teaser("candyman", "Candyman")]), _index_page([])])
    result, _, _ = _collect(pages, songs={"candyman": {"title": "Candyman"}})
    attempts = {attempt["song_id"]: attempt for attempt in result["song_page_attempts"]}
    assert set(attempts) == {"song-candyman", "song-attics-of-my-life", "song-black-queen"}
    assert attempts["song-candyman"]["state"] == "ok"
    assert "404" in attempts["song-black-queen"]["message"]
    assert attempts["song-black-queen"]["url"] == f"https://{cdn.HOST}/song/black-queen"


def test_candidate_slugs_drop_the_stopwords_dead_net_drops():
    assert cdn.candidate_essay_slugs({"title": "Attics Of My Life", "slug": "attics-of-my-life"})[:2] == ["attics-of-my-life", "attics-my-life"]
    assert "box-rain" in cdn.candidate_essay_slugs({"title": "Box Of Rain", "slug": "box-of-rain"})
    assert "hes-gone" in cdn.candidate_essay_slugs({"title": "He's Gone", "slug": "he-s-gone"})


# --- song pages --------------------------------------------------------------


def test_song_pages_are_read_through_the_reviewed_adapter():
    pages = _pages(index_pages=[_index_page([_teaser("candyman", "Candyman")]), _index_page([])])
    result, _, song_transport = _collect(pages, songs={"candyman": {"title": "Candyman | Grateful Dead", "description": "Lyrics and credits"}})
    assert song_transport.calls == [
        f"https://{cdn.HOST}/song/candyman",
        f"https://{cdn.HOST}/song/attics-of-my-life",
        f"https://{cdn.HOST}/song/black-queen",
    ]
    song_pages = {page["raw_payload"]["url_slug"]: page["raw_payload"] for page in result["song_pages"]}
    assert set(song_pages) == {"candyman"}
    assert song_pages["candyman"]["title"] == "Candyman | Grateful Dead"
    assert song_pages["candyman"]["description"] == "Lyrics and credits"
    assert song_pages["candyman"]["song_id"] == "song-candyman"
    assert result["targets"]["song-candyman"]["song_page"] == "found"
    assert result["targets"]["song-black-queen"]["song_page"] == "not found at source"


# --- raw file ----------------------------------------------------------------


def test_the_raw_file_leads_with_pass_metadata_and_is_rewritten_only_on_success(tmp_path):
    pages = _pages(index_pages=[_index_page([_teaser("candyman", 'Greatest Stories Ever Told - "Candyman"')]), _index_page([])])
    result, _, _ = _collect(pages)
    path = cdn.write_raw_file(tmp_path, result)
    assert path == tmp_path / "deadnet-greatest-stories.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    head = lines[0]["raw_payload"]
    assert head["record_type"] == "pass_metadata"
    assert head["essay_count"] == 1
    assert head["user_agent"] == cdn.USER_AGENT
    assert "metadata only" in head["retention"].casefold()
    assert lines[1]["raw_payload"]["record_type"] == "essay"

    before = path.read_bytes()
    failed, _, _ = _collect(_pages(index_pages=[_index_page([_teaser("candyman", "Candyman")])]), statuses={cdn.index_page_url(1): 500})
    assert cdn.write_raw_file(tmp_path, failed) is None
    assert path.read_bytes() == before


def test_a_rerun_over_the_same_source_writes_the_same_bytes(tmp_path):
    pages = _pages(index_pages=[_index_page([_teaser("candyman", "Candyman"), _teaser("deal", "Deal")]), _index_page([])])
    first, _, _ = _collect(pages, songs={"candyman": {"title": "Candyman"}})
    second, _, _ = _collect(pages, songs={"candyman": {"title": "Candyman"}})
    for result in (first, second):
        result["retrieved_at"] = "2026-09-08T00:00:00Z"
        for record in [*result["essays"], *result["song_pages"]]:
            record["retrieved_at"] = "2026-09-08T00:00:00Z"
    one = cdn.write_raw_file(tmp_path / "one", first)
    two = cdn.write_raw_file(tmp_path / "two", second)
    assert one.read_bytes() == two.read_bytes()
