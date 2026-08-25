import json

from deadbot.data import CanonicalStore
from deadbot.tools import build_tools


def tool_by_name(store: CanonicalStore, name: str):
    return next(tool for tool in build_tools(store) if tool.name == name)


def test_every_veneta_song_has_a_context_resource():
    store = CanonicalStore()
    linked_song_ids = {row["song_id"] for row in store.rows("resource_songs")}
    song_ids = {
        row["song_id"]
        for row in store.rows("performances")
        if row["show_id"] == "gd-1972-08-27"
    }
    assert song_ids <= linked_song_ids


def test_song_tool_returns_sugaree_resources_and_arrangement():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_song").invoke({"song_id_or_title": "Sugaree"}))
    assert result["song"]["song_id"] == "song-sugaree"
    assert any(resource["resource_id"] == "resource-rukind-sugaree-tab" for resource in result["resources"])
    assert result["arrangements"][0]["arrangement_id"] == "arrangement-sugaree-rukind-key-b"


def test_1972_song_catalog_has_external_lyric_links_without_lyric_text():
    store = CanonicalStore()
    songs = store.rows("songs")
    assert len(songs) == 80
    linked_song_ids = {
        row["song_id"]
        for row in store.rows("resource_songs")
        if row["relationship_type"] == "lyrics-source"
    }
    assert len(linked_song_ids) == 51
    assert all("lyrics" not in row for row in songs)


def test_performance_tool_preserves_source_attribution():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_performance").invoke({"performance_id": "gd-1972-08-27-playing-in-the-band"}))
    assert result["performance"]["show_id"] == "gd-1972-08-27"
    assert any(resource["resource_id"] == "resource-deadcast-veneta-part-2" for resource in result["resources"])


def test_entity_search_finds_veneta_by_date():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "1972-08-27"}))
    assert {match["id"] for match in result["matches"]} >= {"gd-1972-08-27"}


def test_entity_search_separates_combined_show_and_song_query():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "Veneta Bird Song"}))
    assert {match["id"] for match in result["matches"]} >= {"gd-1972-08-27", "song-bird-song"}


def test_show_tool_returns_performer_role_assignments():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1972-08-27"}))
    assert any(
        assignment["person"]["name"] == "Jerry Garcia" and assignment["instrument"] == "lead guitar"
        for assignment in result["performers"]
    )


def test_show_tool_returns_linkable_official_release_context():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1972-08-27"}))
    assert result["official_releases"][0]["spotify_album_url"].startswith("https://open.spotify.com/album/")


def test_entity_search_does_not_match_stop_words_from_an_unknown_query():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "Help on the Way"}))
    assert result["matches"] == []


def test_show_tool_payload_is_compact_enough_for_local_model_context():
    store = CanonicalStore()
    payload = tool_by_name(store, "get_show").invoke({"show_id_or_date": "1972-08-27"})
    assert len(payload) < 11_000


def test_show_media_lookup_resolves_a_date_to_the_canonical_show():
    store = CanonicalStore()
    result = json.loads(
        tool_by_name(store, "get_media_links").invoke(
            {"entity_type": "show", "entity_id": "1972-08-27"}
        )
    )
    assert result["show_id"] == "gd-1972-08-27"
    assert result["links"][0]["link_type"] == "full-show-video"
