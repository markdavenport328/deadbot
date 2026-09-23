import json

from deadbot.data import CanonicalStore
from deadbot.site_search import SiteSearcher
from deadbot.source_reader import FetchedPage, PageReader
from deadbot.tools import build_tools


class FakeTransport:
    def __init__(self, pages: dict[str, FetchedPage]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float) -> FetchedPage:
        self.calls.append(url)
        for key, page in self.pages.items():
            if key in url:
                return page
        return FetchedPage(404, url, "text/html", "")


CORNELL_MATRIX = "gd1977-05-08.111493.mtx.seamons.sbeok.flac16"


def _tools(transport: FakeTransport):
    store = CanonicalStore()
    tools = build_tools(store, page_reader=PageReader(transport), site_searcher=SiteSearcher(transport))
    return store, {tool.name: tool for tool in tools}


def _tool_by_name(store: CanonicalStore, name: str):
    return next(tool for tool in build_tools(store) if tool.name == name)


def test_research_tools_are_registered_and_directory_lists_sites():
    _, tools = _tools(FakeTransport({}))
    assert {"search_site", "read_page", "get_recording_reviews", "get_research_source_directory"} <= set(tools)
    directory = json.loads(tools["get_research_source_directory"].invoke({}))
    sites = {site["site_id"]: site for site in directory["research_sites"]}
    assert sites["lost-live-dead"]["search_method"] == "blogger_feed"
    assert sites["dead-net"]["search_method"] == "none" and sites["dead-net"]["read_hints"]
    assert "read_page" in directory["research_tools"]


def test_read_page_tool_returns_readable_text_and_grounds_the_url():
    html = "<html><head><title>Veneta</title></head><body><nav>Home</nav><article><p>The creamery benefit was played in brutal heat.</p><p>Bird Song was the second set highlight.</p></article></body></html>"
    transport = FakeTransport({"veneta": FetchedPage(200, "https://lostlivedead.blogspot.com/2012/08/veneta.html", "text/html", html)})
    _, tools = _tools(transport)
    payload = json.loads(tools["read_page"].invoke({"url": "https://lostlivedead.blogspot.com/2012/08/veneta.html", "focus": "Bird Song"}))
    assert payload["state"] == "ok"
    assert payload["final_url"] == "https://lostlivedead.blogspot.com/2012/08/veneta.html"
    assert "Bird Song" in payload["text"] and "Home" not in payload["text"]
    assert payload["focus_matches"] == 1


def test_search_site_tool_returns_hits():
    feed = {"feed": {"entry": [{"title": {"$t": "Veneta"}, "published": {"$t": "2012-08-27T09:00:00.000-07:00"}, "link": [{"rel": "alternate", "href": "https://lostlivedead.blogspot.com/2012/08/veneta.html"}], "content": {"$t": "Hot day, creamery benefit."}}]}}
    transport = FakeTransport({"feeds/posts": FetchedPage(200, "", "application/json", json.dumps(feed))})
    _, tools = _tools(transport)
    payload = json.loads(tools["search_site"].invoke({"site": "Lost Live Dead", "query": "veneta"}))
    assert payload["state"] == "ok" and payload["hits"][0]["url"].endswith("veneta.html")


def test_recording_reviews_for_a_show_pick_the_most_reviewed_recording():
    store = CanonicalStore()
    identifiers = [row["archive_identifier"] for row in store.filtered_rows("recordings", show_id="gd-1977-05-08") if row.get("archive_identifier")]
    assert CORNELL_MATRIX in identifiers and len(identifiers) >= 2
    other = next(identifier for identifier in identifiers if identifier != CORNELL_MATRIX)
    ratings = {"response": {"docs": [
        {"identifier": CORNELL_MATRIX, "avg_rating": 4.91, "num_reviews": 35, "downloads": 136304, "source": "Matrix"},
        {"identifier": other, "avg_rating": 4.5, "num_reviews": 2, "downloads": 10, "source": "Audience"},
    ]}}
    reviews = {"result": [{"reviewbody": "Glassy Garcia tone, perfect mix.", "reviewtitle": "Essential", "reviewer": "b", "reviewdate": "2015-05-08 10:00:00", "stars": "5"}]}
    transport = FakeTransport({"advancedsearch.php": FetchedPage(200, "", "application/json", json.dumps(ratings)), "/reviews": FetchedPage(200, "", "application/json", json.dumps(reviews))})
    _, tools = _tools(transport)
    payload = json.loads(tools["get_recording_reviews"].invoke({"recording": "1977-05-08"}))
    assert payload["show"]["show_id"] == "gd-1977-05-08"
    assert payload["recording"]["archive_identifier"] == CORNELL_MATRIX
    assert payload["rating"]["num_reviews"] == 35
    assert payload["reviews"][0]["title"] == "Essential"
    assert payload["url"] == f"https://archive.org/details/{CORNELL_MATRIX}"
    assert any(entry["archive_identifier"] == other and entry["avg_rating"] == 4.5 for entry in payload["other_recordings"])
    assert f"/metadata/{CORNELL_MATRIX}/reviews" in "".join(transport.calls)


def test_recording_reviews_accept_a_bare_archive_identifier():
    reviews = {"result": [{"reviewbody": "Fine AUD.", "reviewer": "z", "reviewdate": "2010-01-01 00:00:00", "stars": "4"}]}
    ratings = {"response": {"docs": [{"identifier": "gd72-08-27.aud.x", "avg_rating": 4.0, "num_reviews": 1}]}}
    transport = FakeTransport({"advancedsearch.php": FetchedPage(200, "", "application/json", json.dumps(ratings)), "/reviews": FetchedPage(200, "", "application/json", json.dumps(reviews))})
    _, tools = _tools(transport)
    payload = json.loads(tools["get_recording_reviews"].invoke({"recording": "gd72-08-27.aud.x", "limit": 3}))
    assert payload["state"] == "ok" and payload["review_count"] == 1
    assert payload["rating"]["avg_rating"] == 4.0
    assert "show" not in payload


def test_search_entities_resolves_an_album_title():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "search_entities").invoke({"query": "American Beauty"}))
    releases = [item for item in payload["matches"] if item["entity_type"] == "release"]
    assert any(item["id"] == "release-american-beauty" for item in releases)


def test_search_entities_resolves_ace_despite_show_matches_crowding_the_cap():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "search_entities").invoke({"query": "Ace"}))
    releases = [item for item in payload["matches"] if item["entity_type"] == "release"]
    assert any(item["id"] == "release-ace" for item in releases)


def test_get_album_returns_the_tracklist():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "get_album").invoke({"release_id_or_title": "American Beauty"}))
    assert payload["release"]["release_type"] == "studio"
    assert any(track["song_id"] == "song-truckin" for track in payload["tracks"])


def test_get_album_reports_an_unknown_release_rather_than_guessing():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "get_album").invoke({"release_id_or_title": "Kind of Blue"}))
    assert payload["error"] == "Release not found or ambiguous"


def test_get_song_carries_the_records_that_hold_it():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "get_song").invoke({"song_id_or_title": "Truckin'"}))
    assert any(release["release_type"] == "studio" for release in payload["releases"])
    assert "performances" not in payload
    assert payload["performance_summary"]["performance_count"] > 0


def test_get_song_keeps_a_long_lived_song_compact():
    store = CanonicalStore()
    payload = _tool_by_name(store, "get_song").invoke({"song_id_or_title": "Eyes of the World"})
    parsed = json.loads(payload)
    assert parsed["performance_summary"]["performance_count"] == 382
    assert len(payload) < 35_000


def test_list_song_performances_pages_chronologically_with_listening_paths():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "list_song_performances").invoke(
            {"song_id_or_title": "Eyes of the World", "offset": 1, "limit": 2}
        )
    )
    assert payload["performance_count"] == 382
    assert payload["offset"] == 1
    assert len(payload["performances"]) == 2
    assert [row["show_date"] for row in payload["performances"]] == sorted(
        row["show_date"] for row in payload["performances"]
    )
    assert payload["next_offset"] == 3


def test_aggregate_data_is_registered():
    store = CanonicalStore()
    assert "aggregate_data" in {tool.name for tool in build_tools(store)}


def test_aggregate_data_counts_dark_star_performances_by_year():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "song-dark-star"}
        )
    )
    assert payload["rows"]
    assert payload["metric_label"] == "Performances"


def test_aggregate_data_rejects_an_invalid_combination_without_raising():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "shows", "group_by": "song", "measure": "count"}
        )
    )
    assert payload["error"] == "Invalid aggregation request"


def test_aggregate_data_does_not_resolve_a_name_filter():
    # A title instead of a canonical ID passes schema validation (the tool
    # doesn't know what an ID is supposed to look like) but matches nothing,
    # documenting that resolving names to IDs is the caller's job.
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "Dark Star"}
        )
    )
    assert payload["rows"] == []
    assert payload["empty_reason"]


def test_aggregate_data_no_longer_accepts_a_performance_id_parameter():
    # performance_id filtered performances to a single performance, which
    # always counts exactly 1 -- dead surface area, removed everywhere,
    # including the tool's own parameter list.
    store = CanonicalStore()
    assert "performance_id" not in _tool_by_name(store, "aggregate_data").args


def test_aggregate_data_performances_result_carries_setlist_coverage():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "song-dark-star"}
        )
    )
    coverage = payload["setlist_coverage"]
    assert coverage["shows_on_record"] > 0
    assert coverage["shows_with_setlist"] > 0
    assert coverage["shows_with_setlist"] <= coverage["shows_on_record"]
    assert coverage["by_year"], "expected at least one year bucket"
    for entry in coverage["by_year"]:
        assert entry["shows_with_setlist"] <= entry["shows_on_record"]
    years = [entry["year"] for entry in coverage["by_year"]]
    assert years == sorted(years)


def test_aggregate_data_shows_result_has_no_setlist_coverage():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "shows", "group_by": "year", "measure": "count"}
        )
    )
    assert "setlist_coverage" not in payload


def test_aggregate_data_response_has_no_scope_note():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "shows", "group_by": "year", "measure": "count"}
        )
    )
    assert "scope_note" not in payload
