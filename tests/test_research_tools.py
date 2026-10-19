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


def test_get_album_returns_the_tracklist_on_request():
    store = CanonicalStore()
    payload = json.loads(_tool_by_name(store, "get_album").invoke({"release_id_or_title": "American Beauty", "include": ["tracks"]}))
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


def test_aggregate_data_performances_result_carries_setlist_counts():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "song-dark-star"}
        )
    )
    coverage = payload["setlist_counts"]
    assert coverage["shows_played"] > 0
    assert coverage["shows_with_setlist"] > 0
    assert coverage["shows_with_setlist"] <= coverage["shows_played"]
    assert coverage["by_year"], "expected at least one year bucket"
    for entry in coverage["by_year"]:
        assert entry["shows_with_setlist"] <= entry["shows_played"]
    years = [entry["year"] for entry in coverage["by_year"]]
    assert years == sorted(years)


def test_aggregate_data_shows_result_has_no_setlist_counts():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "shows", "group_by": "year", "measure": "count"}
        )
    )
    assert "setlist_counts" not in payload


def test_aggregate_data_response_has_no_scope_note():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "aggregate_data").invoke(
            {"dataset": "shows", "group_by": "year", "measure": "count"}
        )
    )
    assert "scope_note" not in payload


def test_enum_parameters_reach_the_tool_schema_and_bad_values_still_get_the_tools_own_error():
    from langchain_core.utils.function_calling import convert_to_openai_tool

    store = CanonicalStore()
    parameters = convert_to_openai_tool(_tool_by_name(store, "aggregate_data"))["function"]["parameters"]["properties"]
    assert parameters["dataset"]["enum"] == ["shows", "performances", "guest_appearances"]
    assert parameters["group_by"]["enum"] == ["year", "song", "venue", "city", "guest"]
    assert parameters["measure"]["enum"] == ["count", "distinct_shows", "distinct_songs"]
    assert "value_desc" in parameters["sort"]["enum"]
    for name, field, values in (
        ("get_selections_for", "entity_type", ["song", "show"]),
        ("get_media_links", "entity_type", ["show", "performance"]),
        ("get_segue_pairing", "transition", ["segue", "any"]),
    ):
        schema = convert_to_openai_tool(_tool_by_name(store, name))["function"]["parameters"]["properties"]
        assert schema[field]["enum"] == values
    # A value outside the enum still reaches the tool, whose error names the valid values.
    payload = json.loads(_tool_by_name(store, "get_media_links").invoke({"entity_type": "venue", "entity_id": "x"}))
    assert payload["error"] == "entity_type must be 'show' or 'performance'"


def test_get_grid_is_registered_and_resolves_titles():
    store = CanonicalStore()
    result = json.loads(
        _tool_by_name(store, "get_grid").invoke(
            {
                "row_kind": "song",
                "rows": ["Dark Star", "song-playing-in-the-band"],
                "column_kind": "year",
                "year_from": 1968,
                "year_to": 1974,
            }
        )
    )
    assert result["grid_id"].startswith("grid:")
    assert [row["id"] for row in result["rows"]] == ["song-dark-star", "song-playing-in-the-band"]
    assert result["columns"][0]["id"] == "year:1968"


def test_get_grid_tour_selects_show_rows():
    store = CanonicalStore()
    result = json.loads(
        _tool_by_name(store, "get_grid").invoke(
            {"row_kind": "show", "tour": "Europe 1972", "column_kind": "song", "columns": ["Dark Star", "The Other One"]}
        )
    )
    assert len(result["rows"]) == 22


def test_get_grid_reports_what_it_could_not_resolve():
    store = CanonicalStore()
    tool = _tool_by_name(store, "get_grid")
    missing_song = json.loads(tool.invoke({"row_kind": "song", "rows": ["Not A Song Zzz"], "column_kind": "year", "year_from": 1970, "year_to": 1971}))
    assert missing_song["error"] == "Song not found or ambiguous"
    no_nights = json.loads(tool.invoke({"row_kind": "show", "column_kind": "song", "columns": ["Dark Star"]}))
    assert "error" in no_nights
    no_years = json.loads(tool.invoke({"row_kind": "song", "rows": ["Dark Star"], "column_kind": "year"}))
    # Year columns left out span the band's whole touring life.
    assert [column["id"] for column in no_years["columns"]][::30] == ["year:1965", "year:1995"]


def test_get_grid_accepts_years_as_columns_and_the_tour_as_rows_by_id():
    store = CanonicalStore()
    result = json.loads(
        _tool_by_name(store, "get_grid").invoke(
            {"row_kind": "song", "rows": ["song-dark-star"], "column_kind": "year", "columns": ["1969", "year:1970"]}
        )
    )
    assert [column["id"] for column in result["columns"]] == ["year:1969", "year:1970"]


def test_get_grid_tour_selects_the_same_nights_on_sqlite(built_sqlite, tmp_path):
    from deadbot.sqlite_store import SqliteCanonicalStore

    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    try:
        result = json.loads(
            _tool_by_name(store, "get_grid").invoke(
                {"row_kind": "show", "tour": "Europe 1972", "column_kind": "song", "columns": ["Dark Star"]}
            )
        )
    finally:
        store.close()
    assert len(result["rows"]) == 22


def test_get_grid_kinds_are_an_enum_in_the_schema_and_a_bad_kind_reaches_the_tool():
    from langchain_core.utils.function_calling import convert_to_openai_tool

    store = CanonicalStore()
    tool = _tool_by_name(store, "get_grid")
    properties = convert_to_openai_tool(tool)["function"]["parameters"]["properties"]
    assert properties["row_kind"]["enum"] == ["song", "show", "release", "guest"]
    assert properties["column_kind"]["enum"] == ["year", "song"]
    payload = json.loads(tool.invoke({"row_kind": "venue", "column_kind": "song", "rows": ["x"], "columns": ["Dark Star"]}))
    assert payload["error"] == "Unsupported grid"
    assert "show x song" in payload["valid"] and "song x year" in payload["valid"]


def test_get_grid_misspelled_tour_suggests_known_tours():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "get_grid").invoke(
            {"row_kind": "show", "tour": "Europ 1972", "column_kind": "song", "columns": ["Dark Star"]}
        )
    )
    assert payload["error"] == "No shows on that tour"
    assert "Europe 1972" in payload["closest_tours"]
    assert len(payload["closest_tours"]) <= 5


def test_get_grid_takes_records_by_id_or_title_against_songs():
    store = CanonicalStore()
    result = json.loads(
        _tool_by_name(store, "get_grid").invoke(
            {
                "row_kind": "release",
                "rows": ["Dick's Picks 36", "release-dicks-picks-volume-16-1969-11-08"],
                "column_kind": "song",
                "columns": ["Dark Star"],
            }
        )
    )
    assert result["rows_are"] == "release" and result["measure"] == "minutes"
    assert [row["id"] for row in result["rows"]] == ["release-dicks-picks-volume-36-1972-09-21", "release-dicks-picks-volume-16-1969-11-08"]
    assert ["release-dicks-picks-volume-36-1972-09-21", "song-dark-star", 37, 1, "value"] in result["cells"]["rows"]


def test_get_grid_names_the_records_it_could_not_resolve_with_close_titles():
    store = CanonicalStore()
    payload = json.loads(
        _tool_by_name(store, "get_grid").invoke(
            {"row_kind": "release", "rows": ["Dicks Pics 36"], "column_kind": "song", "columns": ["Dark Star"]}
        )
    )
    assert payload["error"] == "Release not found or ambiguous"
    assert payload["query"] == ["Dicks Pics 36"]
    assert any(entry["release_id"] == "release-dicks-picks-volume-36-1972-09-21" for entry in payload["closest"])


def test_get_grid_takes_guests_by_name_across_years():
    store = CanonicalStore()
    tool = _tool_by_name(store, "get_grid")
    result = json.loads(
        tool.invoke({"row_kind": "guest", "rows": ["Bruce Hornsby"], "column_kind": "year", "year_from": 1988, "year_to": 1995})
    )
    assert result["rows"] == [{"id": "person-bruce-hornsby", "label": "Bruce Hornsby", "total": 16}]
    assert ["person-bruce-hornsby", "year:1989", 3, 0, "value"] in result["cells"]["rows"]
    missing = json.loads(tool.invoke({"row_kind": "guest", "rows": ["Nobody Zzz"], "column_kind": "year", "year_from": 1988, "year_to": 1989}))
    assert missing["error"] == "Guest not found or ambiguous"
    folded = json.loads(tool.invoke({"row_kind": "guest", "rows": ["Hamza El Din"], "column_kind": "year", "year_from": 1978, "year_to": 1979}))
    assert folded["rows"][0]["id"] == "person-hamza-el-din"
    near = json.loads(tool.invoke({"row_kind": "guest", "rows": ["Bruce Hornsbee"], "column_kind": "year", "year_from": 1988, "year_to": 1989}))
    assert any(entry["person_id"] == "person-bruce-hornsby" for entry in near["closest"])
