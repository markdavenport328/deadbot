"""Tools shaped around the questions visitors actually ask, so a common
question finishes after one structured round instead of seven."""

import json

from deadbot.data import CanonicalStore
from deadbot.tools import build_tools
from test_data import store_with_selection_evidence


def _all_picks(tools):
    """Every selection signal, reached as the picks among all shows of the band's years."""
    return json.loads(tools["get_picks"].invoke({"year_from": 1960, "year_to": 1999}))["picks"]


def _tools(store: CanonicalStore | None = None):
    store = store or CanonicalStore()
    return {tool.name: tool for tool in build_tools(store)}


def test_notable_versions_lead_with_the_most_released_renditions_and_keep_listening_paths():
    payload = json.loads(_tools()["get_song_notable_versions"].invoke({"song_id_or_title": "Franklin's Tower", "limit": 5}))
    assert payload["performance_count"] > 200
    assert len(payload["versions"]) == 5
    first = payload["versions"][0]
    assert first["official_releases"], "a version is here because a source singled it out"
    assert first["source_count"] >= payload["versions"][-1]["source_count"]
    assert first["show_date"] and first["venue_name"]
    assert payload["signal_summary"]["selection_evidence_available"] is False
    assert "coverage_note" not in payload


def test_notable_versions_carry_reviewed_selection_signals_when_the_store_has_them():
    payload = json.loads(
        _tools(store_with_selection_evidence())["get_song_notable_versions"].invoke({"song_id_or_title": "Dark Star", "limit": 30})
    )
    assert payload["signal_summary"]["selection_evidence_available"] is True
    assert payload["signal_summary"]["fan_vote_versions"] > 0
    with_signals = [version for version in payload["versions"] if version["selections"]]
    assert with_signals
    signal = with_signals[0]["selections"][0]
    assert signal["source"] and signal["signal_type"]
    assert signal["names"] in {"this performance", "the whole show"}


def test_notable_versions_report_an_unknown_song():
    payload = json.loads(_tools()["get_song_notable_versions"].invoke({"song_id_or_title": "Qzxvplm"}))
    assert payload["error"] == "Song not found or ambiguous"


def test_selections_for_a_song_return_only_signals_about_it():
    tools = _tools(store_with_selection_evidence())
    everything = _all_picks(tools)
    payload = json.loads(tools["get_picks"].invoke({"song_or_show": "Dark Star"}))
    assert 0 < len(payload["picks"]) < len(everything)
    assert payload["subject"]["song_id"] == "song-dark-star"
    for signal in payload["picks"]:
        assert signal["matches"] in {"a performance of this song", "a show where this song was played"}
    # Critics name Franklin's Tower performances; Rolling Stone's selected shows
    # where it was played arrive labeled as shows.
    indirect = json.loads(tools["get_picks"].invoke({"song_or_show": "Franklin's Tower"}))
    assert 0 < len(indirect["picks"]) < len(everything)
    assert {signal["matches"] for signal in indirect["picks"]} == {"a performance of this song", "a show where this song was played"}
    # A pick of another song's performance is not a pick of this song's show.
    assert all(signal.get("song_id") in (None, "song-franklin-s-tower") for signal in indirect["picks"])
    assert "coverage_note" not in indirect


def test_picks_for_a_show_and_an_unknown_name():
    tools = _tools(store_with_selection_evidence())
    payload = json.loads(tools["get_picks"].invoke({"song_or_show": "1977-05-08"}))
    assert payload["subject"]["entity_type"] == "show"
    assert all(signal["matches"] in {"this show", "a performance at this show"} for signal in payload["picks"])
    bad = json.loads(tools["get_picks"].invoke({"song_or_show": "Qzxvplm"}))
    assert "No song or show matches" in bad["error"]


def test_get_song_caps_a_long_release_inventory_and_points_onward():
    payload = json.loads(_tools()["get_song"].invoke({"song_id_or_title": "Sugar Magnolia"}))
    assert payload["release_count"] > 20
    assert len(payload["releases"]) == 12
    assert "get_song_notable_versions" in payload["releases_note"]
    assert payload["releases"][0]["release_type"] == "studio"


def test_stored_resource_search_needs_the_phrase_or_every_meaningful_word():
    tools = _tools()
    broad = json.loads(tools["search_stories"].invoke({"query": "Franklin's Tower best version performance review"}))
    # Half of the six meaningful words is the bar, so a six-word question
    # returns only resources that really share three of them (the Franklin's
    # Tower listening guide, a post about the best Franklin's of 1980, and a
    # per-song guide whose notes name performances and versions), ranked with
    # the phrase and word-count matches first.
    assert 0 < broad["match_count"] <= 6
    assert "franklin" in broad["resources"][0]["title"].casefold()
    focused = json.loads(tools["search_stories"].invoke({"query": "Veneta"}))
    assert focused["match_count"] == len(focused["resources"]) > 0


def test_stored_resource_search_ranks_fuller_matches_first():
    # In the raw CSV, "resource-deadnet-community-1990-03-29" (matches 4 of
    # the 6 meaningful words) sits ahead of
    # "resource-deadnet-community-1991-09-10" (matches 5), and the one exact
    # phrase match sits after both -- so an unranked result would surface
    # them in that (wrong) order. Confirmed by inspecting data/canonical/resources.csv.
    payload = json.loads(
        _tools()["search_stories"].invoke(
            {"query": "Branford Marsalis's history with the Grateful Dead"}
        )
    )
    resource_ids = [resource["resource_id"] for resource in payload["resources"]]
    assert resource_ids[0] == "resource-branford-history-with-the-dead"
    assert resource_ids.index("resource-deadnet-community-1991-09-10") < resource_ids.index(
        "resource-deadnet-community-1990-03-29"
    )


def test_album_live_legacy_on_request():
    payload = json.loads(_tools()["get_album"].invoke({"release_id_or_title": "American Beauty", "include": ["live_legacy"]}))
    legacy = payload["live_legacy"]["song-truckin"]
    assert legacy["performance_count"] > 400
    assert legacy["first_performance"] < "1971" < legacy["last_performance"]
    assert sum(legacy["by_era"].values()) == legacy["performance_count"]
    assert legacy["most_released_performances"][0]["release_titles"]
    assert "get_song_notable_versions" in payload["live_legacy_note"]


def test_selection_results_leave_out_pipeline_bookkeeping_but_keep_held_signals_visible():
    tools = _tools(store_with_selection_evidence())
    everything = _all_picks(tools)
    for signal in everything:
        assert not {"signal_id", "resolution_state", "collection_state", "identity_state", "source_provenance"} & set(signal)
    assert any("unsure_because" in signal for signal in everything)
    payload = json.loads(tools["get_picks"].invoke({"song_or_show": "Dark Star"}))
    renditions = [p for signal in payload["picks"] for p in signal.get("performances", [])]
    assert renditions and all("show_id" not in p for p in renditions)
    # A Dark Star needs only its ID on Dark Star's own results; the song is the subject.
    assert any(set(p) == {"performance_id"} and "dark-star" in p["performance_id"] for p in renditions)


def test_selections_in_a_span_return_only_signals_about_shows_in_it():
    tools = _tools(store_with_selection_evidence())
    everything = _all_picks(tools)
    payload = json.loads(tools["get_picks"].invoke({"year_from": 1972, "year_to": 1972}))
    assert 0 < len(payload["picks"]) < len(everything)
    assert payload["span"]["year_from"] == 1972
    named = [item["show_date"] for signal in payload["picks"] for item in signal.get("shows", [])]
    assert named and all(date.startswith("1972") for date in named)


def test_picks_in_a_span_can_be_narrowed_to_a_venue_and_default_to_the_critics_lists():
    tools = _tools(store_with_selection_evidence())
    payload = json.loads(tools["get_picks"].invoke({"venue": "Barton Hall"}))
    assert payload["picks"]
    # With nothing named, get_picks returns the critics' lists of essential shows.
    assert "show_selections" in json.loads(tools["get_picks"].invoke({}))


def test_selections_in_a_span_carry_the_critics_show_picks_inside_it():
    tools = _tools(store_with_selection_evidence())
    payload = json.loads(tools["get_picks"].invoke({"year_from": 1977, "year_to": 1977}))
    dates = [item["show_date"] for pick in payload["show_selections"] for item in pick["items"]]
    assert dates and all(date.startswith("1977") for date in dates)


def test_song_life_states_years_and_standouts(built_sqlite, tmp_path):
    from deadbot.sqlite_store import SqliteCanonicalStore

    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tool = _tools(store)["get_song_life"]
    payload = json.loads(tool.invoke({"song_id_or_title": "Terrapin Station"}))
    assert payload["performance_count"] == 302
    assert (payload["years"][0]["year"], payload["years"][0]["count"]) == (1977, 28)
    assert payload["standouts"]["longest"][0]["facts"] == ["longest ever (25:14)"]
    assert payload["years"][0]["longest"]["minutes"] == 14.9
    missing = json.loads(tool.invoke({"song_id_or_title": "Qzxvplm"}))
    assert missing["error"] == "Song not found or ambiguous"


def test_get_song_names_where_the_first_and_last_nights_were_played():
    payload = json.loads(_tools()["get_song"].invoke({"song_id_or_title": "Terrapin Station"}))
    first = payload["performance_summary"]["first_performance"]
    last = payload["performance_summary"]["last_performance"]
    assert (first["show_date"], first["venue_name"], first["city"]) == ("1977-02-26", "Swing Auditorium", "San Bernardino, CA")
    assert (last["show_date"], last["venue_name"]) == ("1995-07-08", "Soldier Field")
    assert "get_song_life" in payload["plays_by_year_chart"]


def test_picks_say_who_picked_what_in_plain_words():
    tools = _tools(store_with_selection_evidence())
    payload = json.loads(tools["get_picks"].invoke({"year_from": 1977, "year_to": 1977}))
    assert payload["picks"] and all(pick["picked_by"] and pick["kind"] for pick in payload["picks"])
    text = json.dumps(payload)
    for bookkeeping in ("signal_type", "candidate_shows", "release_status", "coverage_note", "objective"):
        assert bookkeeping not in text
