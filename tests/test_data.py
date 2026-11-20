import csv
import json
import re
from pathlib import Path

from deadbot.data import CanonicalStore, _archive_identifier
from deadbot.people_names import QUALIFIER
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


def test_archive_identifier_parses_a_download_track_url():
    url = "https://archive.org/download/gd1977-05-08.148737.SBD.Betty.Anon.Noel.t-flac2448/gd77-05-08.s2t02.mp3"
    assert _archive_identifier(url) == "gd1977-05-08.148737.SBD.Betty.Anon.Noel.t-flac2448"


def test_archive_identifier_accepts_a_www_host():
    assert _archive_identifier("https://www.archive.org/download/gd1977-05-08.sbd/file.mp3") == "gd1977-05-08.sbd"


def test_archive_identifier_rejects_a_non_archive_host():
    assert _archive_identifier("https://example.com/download/gd1977-05-08.sbd/file.mp3") is None


def test_archive_identifier_ignores_a_details_url():
    # /details/ is the recording's own page, not a download track link, and
    # carries no file segment after the identifier for this parser to trust.
    assert _archive_identifier("https://archive.org/details/gd1977-05-08.sbd") is None


def test_archive_identifier_rejects_a_malformed_url():
    assert _archive_identifier("not a url") is None
    assert _archive_identifier("") is None


def test_song_context_adds_a_compact_listening_path_per_performance():
    store = CanonicalStore()
    song = store.resolve_song("Deal")
    payload = store.song_context(song)
    performances_by_id = {row["performance_id"]: row for row in payload["performances"]}

    both_kinds = performances_by_id["gd-1979-11-06-deal-1-11"]
    assert both_kinds["listen"] == {
        "archive_track_url": "https://archive.org/download/gd1979-11-06.137296.sbd.GEMS.flac16/gd1979-11-06s1t17.mp3",
        "archive_identifier": "gd1979-11-06.137296.sbd.GEMS.flac16",
        "archive_track_duration_seconds": 401,
        "release_track_url": "https://open.spotify.com/track/5ePRqn1CsdffrUXEvqtEiW",
    }

    archive_only = performances_by_id["gd-1971-03-20-deal-1-6"]
    assert archive_only["listen"] == {
        "archive_track_url": "https://archive.org/download/gd71-03-20.sbd.barbella.5582.sbeok.shnf/gd71-03-20d1t06.mp3",
        "archive_identifier": "gd71-03-20.sbd.barbella.5582.sbeok.shnf",
        "archive_track_duration_seconds": 290,
    }
    assert "release_track_url" not in archive_only["listen"]

    no_links = performances_by_id["gd-1971-11-06-deal-1-12"]
    assert "listen" not in no_links






def test_lore_source_trails_resolve_canonical_song_and_show_scopes():
    store = CanonicalStore()
    tool = tool_by_name(store, "search_stories")
    song_payload = json.loads(tool.invoke({"song_or_show": "Friend Of The Devil"}))
    assert song_payload["about"]["entity_id"] == "song-friend-of-the-devil"
    assert any(record["source_kind"] == "official" for record in song_payload["trails"])

    show_payload = json.loads(tool.invoke({"song_or_show": "1972-08-27"}))
    assert show_payload["about"]["entity_id"] == "gd-1972-08-27"
    assert show_payload["trails"]
    assert all(record["entity_id"] == "gd-1972-08-27" for record in show_payload["trails"])
    assert any("show-veneta-heat-context" in record["resource_id"] for record in show_payload["trails"])


def test_guest_directory_uses_all_guest_credits_not_a_curated_guest_list():
    store = CanonicalStore()
    payload = json.loads(
        tool_by_name(store, "search_guest_musicians").invoke(
            {"query": "Branford", "include": ["appearances"]}
        )
    )
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
        tool_by_name(store, "search_stories").invoke({"query": branford["name"]})
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


def test_guest_directory_folds_any_jerrybase_name_qualifier_onto_the_plain_person():
    """Marvin Boxley is one harmonica player, not one per qualifier form.

    JerryBase lists him both as ``Marvin Boxley`` and as ``Marvin Boxley
    (songs unknown)``; the canonical data folds the second onto
    ``person-marvin-boxley``, and the directory folds it too should a qualified
    row ever reappear. "(songs unknown)" describes how
    complete the source record is, so it folds the identity without claiming
    anything about the appearance the way "(complete show)" does.
    """

    payload = json.loads(
        tool_by_name(CanonicalStore(), "search_guest_musicians").invoke(
            {"query": "Marvin Boxley", "include": ["appearances"]}
        )
    )

    assert [guest["name"] for guest in payload["guests"]] == ["Marvin Boxley"]
    boxley = payload["guests"][0]
    assert boxley["person_id"] == "person-marvin-boxley"
    assert boxley["guest_show_count"] == 2
    assert [appearance["show_id"] for appearance in boxley["appearances"]] == [
        "gd-1966-12-01",
        "gd-1967-01-14-0",
    ]
    assert sorted(boxley["appearances"][0]["instruments"]) == ["harmonica", "vocals"]
    assert boxley["appearances"][1]["instruments"] == ["harmonica"]
    # The payload drops empty values, so an absent key is the absent scope:
    # "songs unknown" folds the identity without describing the appearance.
    assert [appearance.get("participation_scope") for appearance in boxley["appearances"]] == [None, None]


def test_guest_directory_reports_no_person_under_a_qualified_name():
    """Every legacy qualifier row in the people table folds, not just one form."""

    payload = json.loads(
        tool_by_name(CanonicalStore(), "search_guest_musicians").invoke({"query": ""})
    )

    reported_ids = {guest["person_id"] for guest in payload["guests"]}
    assert not [guest for guest in payload["guests"] if QUALIFIER.search(guest["name"])]
    assert not [
        person_id
        for person_id in reported_ids
        if person_id.endswith(("-complete-show", "-songs-unknown"))
    ]
    assert {"person-airto-moreira", "person-marvin-boxley", "person-tom-constanten"} <= reported_ids


def test_complete_show_qualifier_still_reaches_the_reader_as_a_participation_scope():
    payload = json.loads(
        tool_by_name(CanonicalStore(), "search_guest_musicians").invoke(
            {"query": "Ned Lagin", "include": ["appearances"]}
        )
    )

    lagin = payload["guests"][0]
    assert lagin["person_id"] == "person-ned-lagin"
    scopes = {appearance.get("participation_scope") for appearance in lagin["appearances"]}
    assert "complete show" in scopes


def test_guest_search_accepts_a_natural_language_person_query():
    payload = json.loads(
        tool_by_name(CanonicalStore(), "search_guest_musicians").invoke(
            {"query": "how many times did branford play with them"}
        )
    )

    assert [(guest["name"], guest["guest_show_count"]) for guest in payload["guests"]] == [
        ("Branford Marsalis", 5)
    ]


def test_guest_directory_names_the_songs_a_guest_played_when_the_catalog_knows_them():
    """A show-level credit says Santana was there; performance_performers says on what."""

    payload = json.loads(
        tool_by_name(CanonicalStore(), "search_guest_musicians").invoke(
            {"query": "Santana", "include": ["appearances"]}
        )
    )

    assert [guest["name"] for guest in payload["guests"]] == ["Carlos Santana"]
    santana = payload["guests"][0]
    assert santana["guest_show_count"] == 7
    by_show = {appearance["show_id"]: appearance for appearance in santana["appearances"]}
    assert [song["song_title"] for song in by_show["gd-1993-01-26"]["songs"]] == [
        "The Other One",
        "Stella Blue",
        "Turn On Your Lovelight",
        "Gloria",
    ]
    assert by_show["gd-1993-01-26"]["songs"][1]["performance_id"] == "gd-1993-01-26-stella-blue-2-9"
    assert [song["song_title"] for song in by_show["gd-1987-08-23"]["songs"]] == [
        "Iko Iko",
        "All Along The Watchtower",
    ]
    # Where no source pins down the songs, the appearance stays show-level
    # rather than guessing: the payload drops empty values, so no key.
    assert "songs" not in by_show["gd-1976-12-31"]


def test_performance_context_lists_the_guests_credited_on_that_performance():
    context = CanonicalStore().performance_context("gd-1993-01-26-stella-blue-2-9")

    assert context is not None
    performers = context["performers"]
    assert [(row["person_id"], row["role"], row["instrument"]) for row in performers] == [
        ("person-carlos-santana", "guest", "guitar")
    ]
    assert performers[0]["name"] == "Carlos Santana"
    assert "resource-jambase-weir-teaches-santana-stella-blue-1993" in {
        resource["resource_id"] for resource in context["resources"]
    }


def test_resource_directory_searches_cataloged_anecdotal_sources_across_scopes():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "search_stories").invoke({"query": "Veneta"}))
    assert payload["resources"]
    assert any(resource["resource_type"] == "eyewitness-memoir" for resource in payload["resources"])
    assert all(resource["url"].startswith("https://") for resource in payload["resources"])




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




def test_arrangement_tool_finds_source_specific_keys():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "find_arrangements").invoke({"key_signature": "B"}))
    assert result["arrangement_search"]["key_signature"] == "B"
    assert result["arrangement_search"]["match_count"] == 1
    assert result["arrangements"][0]["song_id"] == "song-sugaree"
    assert "one source's chart" in result["arrangement_search"]["coverage_note"]


def test_equipment_history_returns_tiger_first_and_last_shows():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_equipment_history").invoke({"equipment_id_or_name": "Tiger"}))
    assert result["equipment"]["equipment_id"] == "guitar-tiger"
    assert result["first_show"]["show_date"] == "1979-08-04"
    assert result["first_show"]["venue_name"] == "Oakland Auditorium"
    assert result["last_show"]["show_date"] == "1995-07-09"
    assert result["first_show"]["claim_type"] == "date_range"
    assert result["show_count"] > 0
    assert "coverage_note" not in result


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
    assert result["listen"]["archive_track_url"] in {link["url"] for link in result["links"]}


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
        assignment["name"] == "Jerry Garcia" and "lead guitar" in assignment["instruments"]
        for assignment in result["performers"]
    )


def test_show_tool_merges_one_performers_multiple_instrument_rows():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1990-03-29"}))
    people = [assignment["person_id"] for assignment in result["performers"]]
    assert len(people) == len(set(people)), "each person should appear once, with merged instruments"
    kreutzmann = next(
        assignment for assignment in result["performers"] if assignment["person_id"] == "person-bill-kreutzmann"
    )
    assert set(kreutzmann["instruments"]) >= {"drums", "percussion"}
    assert set(kreutzmann) == {"person_id", "name", "role", "instruments"}


def test_show_tool_compacts_recordings_to_a_count_and_lists_ids_only_when_few():
    store = CanonicalStore()
    show = store.resolve_show("1990-03-29")
    full_recording_count = len(store.show_context(show)["recordings"])
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1990-03-29"}))
    assert result["recordings"]["count"] == full_recording_count
    # A long inventory is a count; get_recording_reviews lists its tapes with their IDs.
    assert full_recording_count > 8 and "recording_ids" not in result["recordings"]
    veneta = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1972-08-27"}))
    assert "recording-gd-1972-08-27-sbd-4682" in veneta["recordings"]["recording_ids"]


def test_show_tool_setlist_rows_carry_real_booleans_and_an_audio_length_not_track_urls():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1972-08-27"}))
    rows = {row["performance_id"]: row for row in result["performances"]}
    assert rows["gd-1972-08-27-china-cat-sunflower"]["segue_into_next"] is True
    assert "segue_into_next" not in rows["gd-1972-08-27-sugaree"]
    assert rows["gd-1972-08-27-one-more-saturday-night"]["encore"] is True
    assert all("listen" not in row and "archive_track_url" not in row for row in result["performances"])
    assert any(row.get("audio") for row in result["performances"])
    # Lengths read as clock time, the way a fan says them.
    assert all(re.fullmatch(r"\d+:\d\d(:\d\d)?", row["length"]) for row in result["performances"] if "length" in row)
    assert result["stories"] and all({"title", "url"} <= set(story) and "relationships" not in story for story in result["stories"])
    assert all("notes" not in link for link in result["show_links"])
    # Every member of the band that night is among the performers, so the membership rows are left out.
    assert "band_memberships" not in result


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


def test_show_tool_payload_is_compact_json():
    """Compactness is a shape contract, not a byte budget that data growth breaks."""

    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "1972-08-27"}))

    def assert_no_empty_values(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                assert nested not in (None, ""), f"{key} should have been compacted away"
                assert_no_empty_values(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_empty_values(nested)

    assert_no_empty_values(payload)
    with (store.canonical_dir / "show_links.csv").open(encoding="utf-8") as source:
        show_link_columns = set(csv.DictReader(source).fieldnames)
    for link in payload["show_links"]:
        assert set(link) <= show_link_columns




def test_branford_debut_has_verified_show_and_performance_video_links():
    store = CanonicalStore()
    show = store.show_context(store.resolve_show("1990-03-29"))
    assert any(link["platform"] == "youtube" and link["link_type"] == "full-show-video" for link in show["show_links"])

    eyes = next(item for item in show["performances"] if item["song_id"] == "song-eyes-of-the-world")
    assert eyes["listen"]["video_url"] == "https://www.youtube.com/watch?v=LEu6gCv8UPc"


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






def test_context_tools_return_a_safe_error_for_unknown_show_without_fetching(monkeypatch):
    store = CanonicalStore()
    monkeypatch.setattr(tools_module, "_fetch_json", lambda _url: (_ for _ in ()).throw(AssertionError("should not fetch")))
    result = json.loads(tool_by_name(store, "get_historical_weather").invoke({"show_id_or_date": "1900-01-01"}))
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




def test_show_payload_keeps_source_setlist_gap_note_without_raw_provenance():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_show").invoke({"show_id_or_date": "gd-1965-05-05"}))
    assert result["performances"] == []
    assert result["show"]["setlist_note"] == "No setlist survives from this show."
    assert "notes" not in result["show"]
    assert "source_key" not in result["show"]


def test_resolve_release_matches_on_id_and_on_title():
    store = CanonicalStore()
    by_id = store.resolve_release("release-american-beauty")
    by_title = store.resolve_release("American Beauty")
    assert by_id is not None
    assert by_id == by_title
    assert by_id["release_type"] == "studio"


def test_resolve_release_returns_none_for_an_unknown_name():
    assert CanonicalStore().resolve_release("Kind of Blue") is None


def test_album_context_returns_an_ordered_tracklist_with_resolved_songs():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))

    assert payload["release"]["title"] == "American Beauty"
    numbers = [track["track_number"] for track in payload["tracks"]]
    assert numbers == sorted(numbers)
    assert numbers[0] == 1

    truckin = next(track for track in payload["tracks"] if track["song_id"] == "song-truckin")
    assert truckin["song_title"] == "Truckin'"
    assert truckin["performance_id"] is None
    assert "spotify_track_url" in truckin


def test_album_context_personnel_carry_resolved_names():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    for entry in payload["personnel"]:
        assert entry["name"]
        assert entry["instrument"]


def test_song_context_lists_the_records_that_carried_the_song():
    store = CanonicalStore()
    payload = store.song_context(store.resolve_song("Truckin'"))

    releases = payload["releases"]
    assert releases, "Truckin' should appear on at least one record"

    studio = next(r for r in releases if r["release_type"] == "studio")
    assert studio["title"] == "American Beauty"
    assert studio["track_number"] == 10


def test_song_releases_are_ordered_by_date_with_studio_first_on_a_tie():
    store = CanonicalStore()
    releases = store.song_context(store.resolve_song("Truckin'"))["releases"]

    dated = [r for r in releases if r["release_date"]]
    assert [r["release_date"] for r in dated] == sorted(r["release_date"] for r in dated)
    assert all(r["release_date"] for r in releases[: len(dated)])


def test_a_song_never_released_has_an_empty_release_list():
    store = CanonicalStore()
    payload = store.song_context(store.resolve_song("song-a-mind-to-give-up-livin"))
    assert payload["releases"] == []


def test_band_lineup_covers_a_date_within_a_tenure_and_excludes_a_gap():
    store = CanonicalStore()

    # 1972-08-27 (Veneta) falls after Pigpen's last documented performance
    # (1972-06-17) and before Mickey Hart's return (1975-03-23): both are core
    # members elsewhere in the catalog but neither belongs in this lineup.
    veneta_lineup = {row["person_id"] for row in store.band_lineup("1972-08-27")}
    assert "person-jerry-garcia" in veneta_lineup
    assert "person-bob-weir" in veneta_lineup
    assert "person-phil-lesh" in veneta_lineup
    assert "person-bill-kreutzmann" in veneta_lineup
    assert "person-keith-godchaux" in veneta_lineup
    assert "person-donna-jean-godchaux" in veneta_lineup
    assert "person-ron-pigpen-mckernan" not in veneta_lineup
    assert "person-mickey-hart" not in veneta_lineup

    # 1977-05-08 (Cornell) falls inside Mickey Hart's second tenure.
    cornell_lineup = {row["person_id"] for row in store.band_lineup("1977-05-08")}
    assert "person-mickey-hart" in cornell_lineup
    assert "person-keith-godchaux" in cornell_lineup

    assert store.band_lineup("") == []
    assert store.band_lineup("1977-05-08", act="some-other-act") == []


def test_show_context_carries_the_derived_band_lineup():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    payload = store.show_context(show)
    lineup_ids = {row["person_id"] for row in payload["band_memberships"]}
    assert "person-jerry-garcia" in lineup_ids
    assert "person-mickey-hart" not in lineup_ids
    for row in payload["band_memberships"]:
        assert row["name"]
        assert row["role"]


def test_person_band_memberships_orders_multiple_tenures_by_start_date():
    store = CanonicalStore()
    tenures = store.person_band_memberships("person-mickey-hart")
    assert [row["start_date"] for row in tenures] == sorted(row["start_date"] for row in tenures)
    assert len(tenures) == 2
    assert tenures[0]["end_date"] < tenures[1]["start_date"]


def test_search_entities_surfaces_band_memberships_for_a_core_member():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "Jerry Garcia"}))
    person_match = next(
        match for match in result["matches"] if match["entity_type"] == "person" and match["id"] == "person-jerry-garcia"
    )
    assert person_match["band_memberships"] == [
        {
            "act": "grateful-dead",
            "role": "guitar, vocals",
            "start_date": "1965-05-05",
            "end_date": "1995-07-09",
        }
    ]


def test_canonical_csv_values_pass_the_importer_converters():
    """The catalog build rejects a bare year or year-month in a date column; name the row here first."""
    import csv
    from pathlib import Path

    from deadbot.canonical_import import TABLE_SPECS

    canonical = Path(__file__).parents[1] / "data" / "canonical"
    bad = []
    for spec in TABLE_SPECS:
        path = canonical / spec.csv_name
        if not spec.converters or not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                for column, convert in spec.converters.items():
                    value = row.get(column, "")
                    if not value:
                        continue
                    try:
                        convert(value)
                    except (ValueError, TypeError) as error:
                        bad.append(f"{spec.csv_name}:{line_number} {column}={value!r}: {error}")
    assert bad == []


def test_canonical_resources_satisfy_the_unique_and_foreign_key_constraints():
    """The importer inserts with ON CONFLICT DO NOTHING, so a resource sharing a source_url
    with another vanishes silently and its links then fail the foreign key in CI."""
    import collections
    import csv
    from pathlib import Path

    canonical = Path(__file__).parents[1] / "data" / "canonical"

    def rows(name: str) -> list[dict[str, str]]:
        with (canonical / f"{name}.csv").open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    resources = rows("resources")
    urls = collections.Counter(row["source_url"] for row in resources if row["source_url"])
    assert [url for url, count in urls.items() if count > 1] == []
    ids = collections.Counter(row["resource_id"] for row in resources)
    assert [rid for rid, count in ids.items() if count > 1] == []
    known = set(ids)
    for table in ("resource_shows", "resource_songs", "resource_performances"):
        dangling = sorted({row["resource_id"] for row in rows(table)} - known)
        assert dangling == [], table


def test_tool_output_states_lengths_as_clock_time():
    payload = json.loads(tools_module._json({"length_seconds": 545, "rows": [[1, 3760]], "columns": ["pair_id", "first_seconds"], "start_seconds": 65}))
    assert payload == {"length": "9:05", "rows": [[1, "1:02:40"]], "columns": ["pair_id", "first_length"], "starts_at": "1:05"}


def test_a_guest_carries_the_stories_the_library_holds_about_them():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "search_guest_musicians").invoke({"query": "Branford Marsalis"}))
    stories = result["guests"][0]["stories"]
    assert any("branfordmarsalis.com" in story["url"] for story in stories)
    assert all(not story.get("covers", "").startswith("Visitor context") for story in stories)


def test_a_performance_states_one_length():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "get_performance").invoke({"performance_id": "gd-1977-05-08-estimated-prophet-2-3"}))
    # The Betty tape track that plays; each official release keeps its own length under its own title.
    assert result["length"] == "8:45"
    assert sorted(release["length"] for release in result["official_releases"]) == ["8:49", "9:05"]
    assert all("length" not in row for key in ("links", "recordings") for row in result.get(key, []))
