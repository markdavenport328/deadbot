"""Tests for the Deadhead High sitemap index collector.

No network calls are made: every request goes through a fake ``PageTransport``
the way ``tests/test_site_search.py`` fakes ``deadbot.site_search``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deadbot.source_reader import FetchedPage

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import collect_deadheadhigh_index as dhh  # noqa: E402


ROBOTS_ALLOW = "User-agent: *\nAllow: /\n\nSitemap: https://deadheadhigh.com/sitemap.xml\n"
ROBOTS_DENY = "User-agent: *\nDisallow: /\n"
SECRET = "Guide prose that must never reach a stored record."

TARGET_SONGS = [
    {"song_id": "song-box-of-rain", "title": "Box Of Rain", "slug": "box-of-rain"},
    {"song_id": "song-quinn-the-eskimo", "title": "Quinn The Eskimo", "slug": "quinn-the-eskimo"},
]
TARGET_DATES = ["1982-07-27", "1970-05-08"]


class FakeTransport:
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


def _sitemap(paths: list[str]) -> str:
    locations = "".join(f"<url><loc>https://deadheadhigh.com{path}</loc></url>" for path in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locations}</urlset>'


def _page(title: str, description: str = "A listening guide.") -> str:
    return (
        f"<html><head><title>{title}</title>"
        f'<meta name="description" content="{description}" /></head>'
        f"<body><h1>{title}</h1><p>{SECRET}</p></body></html>"
    )


PATHS = [
    "/",
    "/privacy",
    "/songs/box-of-rain",
    "/songs/dark-star",
    "/venues/red-rocks-amphitheatre",
    "/shows/1982-07-27",
    "/shows/1971-04-05",
    "/guides/how-to-get-into-the-grateful-dead",
    "/paths/dark-star",
]


def _pages(paths: list[str] = PATHS, *, robots: str = ROBOTS_ALLOW) -> dict[str, str]:
    pages = {f"https://{dhh.HOST}/robots.txt": robots, dhh.SITEMAP_URL: _sitemap(paths)}
    for path in paths:
        pages[f"https://{dhh.HOST}{path}"] = _page(f"Grateful Dead {path.strip('/')} | Deadhead High")
    return pages


def _collect(pages: dict[str, str], *, statuses=None, songs=None, dates=None, featured=None):
    transport = FakeTransport(pages, statuses=statuses)
    result = dhh.collect(
        transport,
        songs if songs is not None else TARGET_SONGS,
        dates if dates is not None else TARGET_DATES,
        featured if featured is not None else ["1971-04-05"],
    )
    return result, transport


# --- robots ------------------------------------------------------------------


def test_robots_is_read_first_and_recorded():
    result, transport = _collect(_pages())
    assert transport.calls[0] == f"https://{dhh.HOST}/robots.txt"
    assert result["robots"]["http_status"] == 200
    assert result["robots"]["paths"] == dict.fromkeys(dhh.ROBOTS_PATHS, True)
    assert "permits" in result["robots"]["note"]


def test_a_disallowed_site_is_skipped():
    result, transport = _collect(_pages(robots=ROBOTS_DENY))
    assert result["status"] == "skipped-robots"
    assert result["pages"] == []
    assert transport.calls == [f"https://{dhh.HOST}/robots.txt"]


# --- what the sitemap walk keeps --------------------------------------------


def test_every_song_page_is_kept_and_unrelated_sections_are_not():
    result, transport = _collect(_pages())
    kept = {record["raw_payload"]["url_path"]: record["raw_payload"] for record in result["pages"]}
    assert "/songs/box-of-rain" in kept
    assert "/songs/dark-star" in kept
    assert "/venues/red-rocks-amphitheatre" not in kept
    assert "/privacy" not in kept
    assert kept["/songs/box-of-rain"]["resource_type"] == dhh.SONG_RESOURCE_TYPE
    assert kept["/songs/box-of-rain"]["kept_because"] == "song page"
    assert result["sitemap"]["location_count"] == len(PATHS)


def test_a_target_show_date_and_a_featured_show_date_are_kept():
    result, _ = _collect(_pages())
    kept = {record["raw_payload"]["url_path"]: record["raw_payload"] for record in result["pages"]}
    assert kept["/shows/1982-07-27"]["kept_because"] == "target show date"
    assert kept["/shows/1982-07-27"]["resource_type"] == dhh.GUIDE_RESOURCE_TYPE
    assert kept["/shows/1971-04-05"]["kept_because"] == "featured show date"
    # 1970-05-08 has no page on the site, and that is an absence, not a request.
    assert not any("1970-05-08" in call for call in _collect(_pages())[1].calls)


def test_the_editorial_guide_sections_are_kept_whole_and_typed_as_listener_guides():
    result, _ = _collect(_pages())
    kept = {record["raw_payload"]["url_path"]: record["raw_payload"] for record in result["pages"]}
    assert kept["/guides/how-to-get-into-the-grateful-dead"]["resource_type"] == dhh.GUIDE_RESOURCE_TYPE
    assert kept["/guides/how-to-get-into-the-grateful-dead"]["kept_because"] == "guide page"
    assert kept["/paths/dark-star"]["kept_because"] == "guide page"


def test_a_page_outside_those_sections_is_kept_only_when_its_slug_names_a_target_song():
    pages = _pages([*PATHS, "/venues/box-of-rain"])
    result, _ = _collect(pages)
    kept = {record["raw_payload"]["url_path"]: record["raw_payload"] for record in result["pages"]}
    assert kept["/venues/box-of-rain"]["kept_because"] == "target song slug"
    assert "/venues/red-rocks-amphitheatre" not in kept


def test_one_request_per_kept_page_and_no_page_text_stored(tmp_path):
    result, transport = _collect(_pages())
    fetched = [call for call in transport.calls if call.startswith(f"https://{dhh.HOST}/") and "robots" not in call and "sitemap" not in call]
    assert len(fetched) == len(result["pages"])
    assert len(set(fetched)) == len(fetched)
    path = dhh.write_raw_file(tmp_path, result)
    assert SECRET not in path.read_text(encoding="utf-8")


def test_a_page_metadata_record_keeps_title_and_a_short_description():
    pages = _pages()
    pages[f"https://{dhh.HOST}/songs/box-of-rain"] = _page("Grateful Dead Box of Rain live versions | Deadhead High", "y" * 400)
    result, _ = _collect(pages)
    record = [page["raw_payload"] for page in result["pages"] if page["raw_payload"]["url_path"] == "/songs/box-of-rain"][0]
    assert record["title"] == "Grateful Dead Box of Rain live versions"
    assert len(record["description"]) == dhh.MAX_DESCRIPTION
    assert record["url_slug"] == "box-of-rain"
    assert record["section"] == "songs"
    assert record["http_status"] == 200


def test_targets_report_their_outcome():
    result, _ = _collect(_pages())
    assert result["targets"]["song-box-of-rain"] == "found"
    assert result["targets"]["song-quinn-the-eskimo"] == "not found at source"
    assert result["target_shows"]["1982-07-27"] == "found"
    assert result["target_shows"]["1970-05-08"] == "not found at source"


# --- retry safety ------------------------------------------------------------


def test_an_unreadable_sitemap_aborts_the_pass():
    result, _ = _collect(_pages(), statuses={dhh.SITEMAP_URL: 503})
    assert result["status"] == "aborted"
    assert result["pages"] == []


def test_a_failed_page_request_aborts_rather_than_reporting_an_absence(tmp_path):
    result, _ = _collect(_pages(), statuses={f"https://{dhh.HOST}/songs/dark-star": 500})
    assert result["status"] == "aborted"
    assert result["pages"] == []
    assert dhh.write_raw_file(tmp_path, result) is None


def test_a_sitemap_index_is_followed():
    child = f"https://{dhh.HOST}/sitemap-songs.xml"
    pages = {
        f"https://{dhh.HOST}/robots.txt": ROBOTS_ALLOW,
        dhh.SITEMAP_URL: f"<sitemapindex><sitemap><loc>{child}</loc></sitemap></sitemapindex>",
        child: _sitemap(["/songs/box-of-rain"]),
        f"https://{dhh.HOST}/songs/box-of-rain": _page("Box of Rain | Deadhead High"),
    }
    result, _ = _collect(pages)
    assert [record["raw_payload"]["url_path"] for record in result["pages"]] == ["/songs/box-of-rain"]


# --- raw file ----------------------------------------------------------------


def test_the_raw_file_leads_with_pass_metadata(tmp_path):
    result, _ = _collect(_pages())
    path = dhh.write_raw_file(tmp_path, result)
    assert path == tmp_path / "deadheadhigh-index.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    head = lines[0]["raw_payload"]
    assert head["record_type"] == "pass_metadata"
    assert head["page_count"] == len(result["pages"])
    assert head["user_agent"] == dhh.USER_AGENT
    assert "metadata only" in head["retention"].casefold()
    assert lines[1]["raw_payload"]["record_type"] == "page"
    assert lines[1]["raw_payload"]["source_name"] == dhh.SOURCE_NAME


def test_a_rerun_over_the_same_site_writes_the_same_bytes(tmp_path):
    first, _ = _collect(_pages())
    second, _ = _collect(_pages())
    for result in (first, second):
        result["retrieved_at"] = "2026-09-08T00:00:00Z"
        for record in result["pages"]:
            record["retrieved_at"] = "2026-09-08T00:00:00Z"
    assert dhh.write_raw_file(tmp_path / "one", first).read_bytes() == dhh.write_raw_file(tmp_path / "two", second).read_bytes()
