import json

from deadbot.data import CanonicalStore
import deadbot.tools as tools_module
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
    assert any(resource["source_name"] == "MusicBrainz" for resource in result["resources"])
    assert len(result["resources"]) == len({resource["resource_id"] for resource in result["resources"]})


def test_song_credit_cleanup_removes_legacy_generic_sugaree_rows():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_song").invoke({"song_id_or_title": "Sugaree"}))
    assert {(row["person_id"], row["writer_role"]) for row in result["writers"]} == {
        ("person-jerry-garcia", "music"),
        ("person-robert-hunter", "lyrics"),
    }


def test_1972_song_catalog_has_external_lyric_links_without_lyric_text():
    store = CanonicalStore()
    show_ids = {
        row["show_id"]
        for row in store.rows("shows")
        if row["show_date"].startswith("1972-")
    }
    song_ids = {
        row["song_id"]
        for row in store.rows("performances")
        if row["show_id"] in show_ids
    }
    songs = [row for row in store.rows("songs") if row["song_id"] in song_ids]
    assert len(songs) == 80
    linked_song_ids = {
        row["song_id"]
        for row in store.rows("resource_songs")
        if row["relationship_type"] == "lyrics-source" and row["song_id"] in song_ids
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
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "Qzxvplm"}))
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


def test_historical_weather_resolves_show_venue_and_returns_reanalysis(monkeypatch):
    store = CanonicalStore()
    tools_module._geocode.cache_clear()

    def fake_fetch(url):
        if url.startswith(tools_module.OPEN_METEO_GEOCODING_URL):
            return {
                "results": [{
                    "name": "Veneta",
                    "latitude": 44.05,
                    "longitude": -123.35,
                    "timezone": "America/Los_Angeles",
                    "country": "United States",
                }]
            }
        assert url.startswith(tools_module.OPEN_METEO_ARCHIVE_URL)
        return {
            "daily": {
                "time": ["1972-08-27"],
                "weather_code": [63],
                "temperature_2m_max": [74.1],
                "temperature_2m_min": [51.2],
                "precipitation_sum": [0.08],
                "rain_sum": [0.08],
                "snowfall_sum": [0],
                "precipitation_hours": [2],
                "wind_speed_10m_max": [11.4],
            }
        }

    monkeypatch.setattr(tools_module, "_fetch_json", fake_fetch)
    result = json.loads(tool_by_name(store, "get_historical_weather").invoke({"show_id_or_date": "1972-08-27"}))
    assert result["show"]["show_id"] == "gd-1972-08-27"
    assert result["location"]["name"] == "Veneta"
    assert result["weather"]["weather_description"] == "moderate rain"
    assert result["source"]["name"] == "Open-Meteo Historical Weather API"
    assert "not a station observation" in result["source"]["note"]


def test_astronomy_returns_local_sun_moon_events_and_source(monkeypatch):
    store = CanonicalStore()
    tools_module._geocode.cache_clear()

    def fake_fetch(url):
        if url.startswith(tools_module.OPEN_METEO_GEOCODING_URL):
            return {
                "results": [{
                    "name": "Veneta",
                    "latitude": 44.05,
                    "longitude": -123.35,
                    "timezone": "America/Los_Angeles",
                }]
            }
        assert url.startswith(tools_module.USNO_RISE_SET_URL)
        return {
            "properties": {
                "data": {
                    "curphase": "Waxing crescent",
                    "fracillum": 0.22,
                    "closestphase": {"phase": "First Quarter", "month": 8, "day": 29, "year": 1972, "time": "11:20"},
                    "sundata": [{"phen": "Begin civil twilight", "time": "05:12"}, {"phen": "Sunset", "time": "20:02"}],
                    "moondata": [{"phen": "Moonrise", "time": "12:11"}, {"phen": "Moonset", "time": "22:14"}],
                }
            }
        }

    monkeypatch.setattr(tools_module, "_fetch_json", fake_fetch)
    result = json.loads(tool_by_name(store, "get_astronomy").invoke({"show_id_or_date": "1972-08-27"}))
    assert result["astronomy"]["timezone_offset_hours"] == -7
    assert result["astronomy"]["sun"][1] == {"event": "Sunset", "time": "20:02"}
    assert result["astronomy"]["moon_phase"] == "Waxing crescent"
    assert result["source"]["name"].startswith("U.S. Naval Observatory")


def test_astrology_is_date_based_and_explicitly_interpretive():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_astrology").invoke({"show_id_or_date": "1972-08-27"}))
    assert result["astrology"]["sun_sign"] == "Virgo"
    assert result["astrology"]["system"] == "Western tropical zodiac"
    assert "not scientific evidence" in result["disclaimer"]


def test_context_tools_return_a_safe_error_for_unknown_show_without_fetching(monkeypatch):
    store = CanonicalStore()
    monkeypatch.setattr(tools_module, "_fetch_json", lambda _url: (_ for _ in ()).throw(AssertionError("should not fetch")))
    for name in ("get_historical_weather", "get_astronomy", "get_astrology"):
        result = json.loads(tool_by_name(store, name).invoke({"show_id_or_date": "1900-01-01"}))
        assert result["error"] == "Show not found or ambiguous"
