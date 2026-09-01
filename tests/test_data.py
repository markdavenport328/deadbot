import json
from pathlib import Path

from deadbot.data import CanonicalStore
from deadbot.deadnet import MetadataRecord, ResearchResult, ResultState
import deadbot.tools as tools_module
from deadbot.tools import build_tools


def store_with_selection_evidence() -> CanonicalStore:
    document = json.loads(
        (Path(__file__).parents[1] / "data" / "editorial" / "selection-evidence-review.json").read_text(encoding="utf-8")
    )
    entries = [
        {**entry, "review_packet": {"source_constraints": document["source_constraints"]}}
        for entry in document["entries"]
    ]

    class StoreWithSelectionEvidence(CanonicalStore):
        def selection_signal_rows(self):
            return entries

    return StoreWithSelectionEvidence()


def tool_by_name(store: CanonicalStore, name: str):
    return next(tool for tool in build_tools(store) if tool.name == name)


def test_deadnet_song_context_returns_metadata_only_research_packet(monkeypatch):
    store = CanonicalStore()

    class FakeAdapter:
        def read(self, request):
            assert request.identifier == "sugaree"
            return ResearchResult(
                state=ResultState.OK,
                records=(
                    MetadataRecord(
                        entity_type="song",
                        identifier="sugaree",
                        title="Sugaree | Dead.net",
                        url="https://www.dead.net/song/sugaree",
                    ),
                ),
                requested={"operation": "read", "entity_type": "song"},
            )

    monkeypatch.setattr(tools_module, "_reviewed_deadnet_adapter", lambda: FakeAdapter())
    payload = json.loads(
        tool_by_name(store, "get_deadnet_song_context").invoke({"song_id_or_title": "Sugaree"})
    )
    assert payload["song"]["song_id"] == "song-sugaree"
    assert payload["research"]["coverage"] == "metadata_only"
    assert payload["research"]["records"] == [
        {
            "entity_type": "song",
            "identifier": "sugaree",
            "title": "Sugaree | Dead.net",
            "url": "https://www.dead.net/song/sugaree",
            "source": "dead.net",
        }
    ]


def test_deadcast_metadata_returns_bounded_metadata_only_packet(monkeypatch):
    store = CanonicalStore()

    class FakeAdapter:
        def read(self, request):
            assert request.entity_type.value == "deadcast"
            assert request.identifier == "episode-1"
            return ResearchResult(
                state=ResultState.OK,
                records=(MetadataRecord(entity_type="deadcast", identifier="episode-1", title="Deadcast: Veneta", url="https://www.dead.net/deadcast/episode-1"),),
            )

    monkeypatch.setattr(tools_module, "_reviewed_deadcast_adapter", lambda: FakeAdapter())
    payload = json.loads(tool_by_name(store, "get_deadcast_metadata").invoke({"episode_id_or_slug": "episode-1"}))
    assert payload["research"]["state"] == "ok"
    assert payload["research"]["records"][0]["title"] == "Deadcast: Veneta"
    assert "transcript" not in payload["research"]["records"][0]


def test_lore_source_trails_resolve_canonical_song_and_show_scopes():
    store = CanonicalStore()
    tool = tool_by_name(store, "get_lore_source_trails")
    song_payload = json.loads(
        tool.invoke({"entity_type": "song", "entity_id_or_name": "Friend Of The Devil"})
    )
    assert song_payload["entity"]["entity_id"] == "song-friend-of-the-devil"
    assert song_payload["research"]["state"] == "ok"
    assert any(record["source_kind"] == "official" for record in song_payload["research"]["records"])

    show_payload = json.loads(
        tool.invoke({"entity_type": "show", "entity_id_or_name": "1972-08-27"})
    )
    assert show_payload["entity"]["entity_id"] == "gd-1972-08-27"
    assert show_payload["research"]["trail_ids"] == ["show-veneta-heat-context"]


def test_guest_directory_uses_all_guest_credits_not_a_curated_guest_list():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "search_guest_musicians").invoke({"query": "Branford"}))
    assert [guest["name"] for guest in payload["guests"]] == ["Branford Marsalis"]
    branford = payload["guests"][0]
    assert branford["guest_show_count"] == 5
    assert {appearance["show_id"] for appearance in branford["appearances"]} == {
        "gd-1990-03-29",
        "gd-1990-12-31",
        "gd-1991-09-10",
        "gd-1993-12-10",
        "gd-1994-12-16",
    }
    assert all(appearance["show_date"] for appearance in branford["appearances"])
    assert [appearance["venue_name"] for appearance in branford["appearances"]] == [
        "Nassau Veterans Memorial Coliseum",
        "Oakland-Alameda County Coliseum Arena",
        "Madison Square Garden",
        "Los Angeles Memorial Sports Arena",
        "Los Angeles Memorial Sports Arena",
    ]
    enrichment = json.loads(
        tool_by_name(store, "search_stored_resources").invoke({"query": branford["name"]})
    )
    assert {resource["resource_type"] for resource in enrichment["resources"]} >= {
        "community-show-page",
        "artist-hosted-feature",
        "community-forum-thread",
    }
    community_pages = [
        resource for resource in enrichment["resources"]
        if resource["resource_type"] == "community-show-page"
    ]
    assert len(community_pages) == 5
    assert all(resource["notes"].startswith("Visitor context:") for resource in community_pages)


def test_guest_search_accepts_a_natural_language_person_query():
    payload = json.loads(
        tool_by_name(CanonicalStore(), "search_guest_musicians").invoke(
            {"query": "how many times did branford play with them"}
        )
    )

    assert [(guest["name"], guest["guest_show_count"]) for guest in payload["guests"]] == [
        ("Branford Marsalis", 5)
    ]


def test_resource_directory_searches_cataloged_anecdotal_sources_across_scopes():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "search_stored_resources").invoke({"query": "Veneta"}))
    assert payload["resources"]
    assert any(resource["resource_type"] == "eyewitness-memoir" for resource in payload["resources"])
    assert all(resource["url"].startswith("https://") for resource in payload["resources"])


def test_selection_signal_tool_preserves_critic_fan_and_curator_provenance():
    store = store_with_selection_evidence()
    payload = json.loads(tool_by_name(store, "get_selection_signals").invoke({}))
    signal_types = {signal["signal_type"] for signal in payload["selection_signals"]}
    assert {"critic_editorial_show_selection", "fan_ranked_version", "individual_curator_song_selection"} <= signal_types
    assert "headyversion" in payload["source_constraints"]
    assert payload["show_selections"][0]["selector_name"] == "David Fricke / Rolling Stone"


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


def test_song_performance_profile_is_bounded_and_reports_neighbor_denominators():
    store = CanonicalStore()
    result = json.loads(
        tool_by_name(store, "get_song_performance_profile").invoke({"song_id_or_title": "Sugaree"})
    )
    assert result["song"]["song_id"] == "song-sugaree"
    assert result["known_performance_count"] == 364
    assert result["first_known_performance"]["show_date"] == "1971-07-31"
    assert result["last_known_performance"]["show_date"] == "1995-07-08"
    assert result["immediate_predecessors"] == [
        {"song_id": "song-hell-in-a-bucket", "title": "Hell In A Bucket", "count": 66}
    ]
    assert result["predecessor_denominator"] == 338
    assert result["successor_denominator"] == 359
    assert result["coverage"]["scope"] == "current canonical library"
    assert "not band-history-complete" in result["coverage"]["limitations"]


def test_arrangement_tool_finds_only_documented_source_specific_keys():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "find_arrangements").invoke({"key_signature": "B"}))
    assert result["arrangement_search"]["key_signature"] == "B"
    assert result["arrangement_search"]["match_count"] == 1
    assert result["arrangements"][0]["song_id"] == "song-sugaree"
    assert "universal key" in result["arrangement_search"]["coverage_note"]


def test_equipment_history_returns_tiger_first_and_last_documented_shows():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_equipment_history").invoke({"equipment_id_or_name": "Tiger"}))
    assert result["equipment"]["equipment_id"] == "guitar-tiger"
    assert result["first_documented_show"]["show_date"] == "1979-08-04"
    assert result["first_documented_show"]["venue_name"] == "Oakland Auditorium"
    assert result["last_documented_show"]["show_date"] == "1995-07-09"
    assert result["first_documented_show"]["claim_type"] == "date_range"


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


def test_show_tool_returns_named_guitar_claims():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1995-07-09"}))
    assert {item["name"] for item in result["equipment"]} >= {"Rosebud", "Tiger"}
    assert all(item["source_id"] == "source:jerry-garcia-instrument-history" for item in result["equipment"])


def test_1972_canonical_shows_have_source_reviewed_performer_assignments():
    store = CanonicalStore()
    show_ids = {
        row["show_id"]
        for row in store.rows("shows")
        if row["show_date"].startswith("1972-")
    }
    assigned_show_ids = {
        row["show_id"]
        for row in store.rows("show_performers")
        if row["show_id"] in show_ids
    }
    assert assigned_show_ids == show_ids
    assert any(row["role"] == "guest" for row in store.rows("show_performers"))


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
        assert result["error"] == "Show not found"


def test_ambiguous_show_date_returns_candidates_instead_of_a_dead_end():
    store = CanonicalStore()
    assert store.resolve_show("1966-10-08") is None
    assert len(store.show_candidates("1966-10-08")) == 2
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1966-10-08"}))
    assert "Multiple shows match" in result["error"]
    candidate_ids = {candidate["show_id"] for candidate in result["candidates"]}
    assert candidate_ids == {"gd-1966-10-08-0", "gd-1966-10-08-1"}
    venue_names = {candidate["venue_name"] for candidate in result["candidates"]}
    assert len(venue_names) == 2


def test_unknown_show_date_still_reports_not_found_without_candidates():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1999-01-01"}))
    assert result["error"] == "Show not found"
    assert "candidates" not in result


def test_media_links_tool_returns_candidates_for_an_ambiguous_show_date():
    store = CanonicalStore()
    result = json.loads(
        tool_by_name(store, "get_media_links").invoke({"entity_type": "show", "entity_id": "1966-10-08"})
    )
    assert "Multiple shows match" in result["error"]
    assert len(result["candidates"]) == 2


def test_show_payload_keeps_source_setlist_gap_note_without_raw_provenance():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "gd-1965-05-05"}))
    assert result["performances"] == []
    assert "no setlist entries" in result["show"]["setlist_note"]
    assert "notes" not in result["show"]
    assert "source_key" not in result["show"]
