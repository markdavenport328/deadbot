"""Tools shaped around the questions visitors actually ask, so a common
question finishes after one structured round instead of seven."""

import json

from deadbot.data import CanonicalStore
from deadbot.tools import build_tools
from test_data import store_with_selection_evidence


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
    assert "not complete band history or a ranking" in payload["coverage_note"]


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
    everything = json.loads(tools["get_selection_signals"].invoke({}))["selection_signals"]
    payload = json.loads(tools["get_selections_for"].invoke({"entity_type": "song", "entity_id_or_name": "Dark Star"}))
    assert 0 < payload["signal_count"] < len(everything)
    assert payload["subject"]["song_id"] == "song-dark-star"
    for signal in payload["selection_signals"]:
        assert signal["matches"] in {"a performance of this song", "a show where this song was played"}
    # No reviewed source names a Franklin's Tower performance, but critics did
    # select whole shows where it was played; those arrive labeled as such.
    indirect = json.loads(tools["get_selections_for"].invoke({"entity_type": "song", "entity_id_or_name": "Franklin's Tower"}))
    assert 0 < indirect["signal_count"] < len(everything)
    assert {signal["matches"] for signal in indirect["selection_signals"]} == {"a show where this song was played"}
    assert "not that it is unremarkable" in indirect["coverage_note"]


def test_selections_for_a_show_and_a_bad_entity_type():
    tools = _tools(store_with_selection_evidence())
    payload = json.loads(tools["get_selections_for"].invoke({"entity_type": "show", "entity_id_or_name": "1977-05-08"}))
    assert payload["subject"]["entity_type"] == "show"
    assert all(signal["matches"] in {"this show", "a performance at this show"} for signal in payload["selection_signals"])
    bad = json.loads(tools["get_selections_for"].invoke({"entity_type": "venue", "entity_id_or_name": "x"}))
    assert "entity_type" in bad["error"]


def test_get_song_caps_a_long_release_inventory_and_points_onward():
    payload = json.loads(_tools()["get_song"].invoke({"song_id_or_title": "Sugar Magnolia"}))
    assert payload["release_count"] > 20
    assert len(payload["releases"]) == 20
    assert "get_song_notable_versions" in payload["releases_note"]
    assert payload["releases"][0]["release_type"] == "studio"


def test_stored_resource_search_needs_the_phrase_or_every_meaningful_word():
    tools = _tools()
    broad = json.loads(tools["search_stored_resources"].invoke({"query": "Franklin's Tower best version performance review"}))
    # Half of the six meaningful words is the bar, so a six-word question
    # returns only resources that really share three of them: of 2,040
    # cataloged resources exactly one does, a post about the best
    # Franklin's Tower of 1980.
    assert broad["match_count"] <= 3
    assert all(
        "franklin" in resource["title"].casefold() or "best" in resource["title"].casefold()
        for resource in broad["resources"]
    )
    focused = json.loads(tools["search_stored_resources"].invoke({"query": "Veneta"}))
    assert focused["match_count"] == len(focused["resources"]) > 0


def test_stored_resource_search_ranks_fuller_matches_first():
    # In the raw CSV, "resource-deadnet-community-1990-03-29" (matches 4 of
    # the 6 meaningful words) sits ahead of
    # "resource-deadnet-community-1991-09-10" (matches 5), and the one exact
    # phrase match sits after both -- so an unranked result would surface
    # them in that (wrong) order. Confirmed by inspecting data/canonical/resources.csv.
    payload = json.loads(
        _tools()["search_stored_resources"].invoke(
            {"query": "Branford Marsalis's history with the Grateful Dead"}
        )
    )
    resource_ids = [resource["resource_id"] for resource in payload["resources"]]
    assert resource_ids[0] == "resource-branford-history-with-the-dead"
    assert resource_ids.index("resource-deadnet-community-1991-09-10") < resource_ids.index(
        "resource-deadnet-community-1990-03-29"
    )


def test_album_tracks_carry_their_live_legacy():
    payload = json.loads(_tools()["get_album"].invoke({"release_id_or_title": "American Beauty"}))
    truckin = next(track for track in payload["tracks"] if track["song_id"] == "song-truckin")
    legacy = truckin["live_legacy"]
    assert legacy["performance_count"] > 400
    assert legacy["first_performance"] < "1971" < legacy["last_performance"]
    assert sum(legacy["by_era"].values()) == legacy["performance_count"]
    assert legacy["most_released_performances"][0]["release_titles"]
    assert "get_song_notable_versions" in payload["live_legacy_note"]
