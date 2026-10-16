import json

import pytest

from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools

BOX = "release-europe-72-the-complete-recordings-2011"


@pytest.fixture
def album(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tool = next(t for t in build_tools(store) if t.name == "get_album")
    yield lambda **args: json.loads(tool.invoke(args))
    store.close()


def test_live_box_set_summary_lists_shows_not_tracks(album):
    payload = album(release_id_or_title=BOX)
    assert "tracks" not in payload and "live_legacy" not in payload
    shows = payload["contents"]["shows"]
    assert shows[0]["show_date"] == "1972-04-07" and shows[-1]["show_id"] == "gd-1972-05-26"
    assert sum(show["track_count"] for show in shows) + payload["contents"].get("tracks_without_a_show", 0) == payload["track_count"]
    assert payload["available"]["tracks"]["count"] == payload["track_count"]
    assert "include" in payload["available"]["tracks"]["ask"]
    assert len(json.dumps(payload)) < 12_000


def test_studio_summary_lists_songs(album):
    payload = album(release_id_or_title="American Beauty")
    assert payload["release"]["release_type"] == "studio"
    assert any(song["song_id"] == "song-truckin" for song in payload["contents"]["songs"])
    assert "tracks" not in payload


def test_tracks_on_request_and_narrowed_to_one_show(album):
    full = album(release_id_or_title=BOX, include=["tracks"])
    one = album(release_id_or_title=BOX, show="1972-05-26")
    assert "tracks" not in full and "_truncated" not in full
    assert len(json.dumps(full)) < 80_000
    nights = full["nights"]
    assert len(nights) == len(full["contents"]["shows"]) == 22
    assert nights[0]["tour"] == "Europe 1972" and nights[0]["show_id"] and nights[0]["track_count"]
    assert list(full)[:2] == ["release", "tour"]
    assert all(night["tracks"] and "performance_id" in night["tracks"][0] for night in nights)
    assert "first 5 tracks" in full["tracks_note"] and "show=" in full["tracks_note"]
    assert max(len(night["tracks"]) for night in nights) == 5
    assert 0 < len(one["tracks"]) < full["track_count"] and "nights" not in one
    assert "tracks" not in one["available"]


def test_unresolvable_show_errors_rather_than_returning_unattributed_tracks(album):
    payload = album(release_id_or_title=BOX, show="not-a-real-show-xyz")
    assert payload["error"] == "Show not on this release"
    assert "1972-04-07" in payload["shows"]
    assert "tracks" not in payload


def test_live_legacy_on_request_keyed_by_song(album):
    payload = album(release_id_or_title="American Beauty", include=["live_legacy"])
    truckin = payload["live_legacy"]["song-truckin"]
    assert truckin["performance_count"] > 400
    assert sum(truckin["by_era"].values()) == truckin["performance_count"]
    assert "get_song_notable_versions" in payload["live_legacy_note"]


def test_bad_requests_explain_themselves(album):
    assert album(release_id_or_title=BOX, include=["lyrics"])["valid"] == ["live_legacy", "tracks"]
    assert "shows" in album(release_id_or_title=BOX, show="1977-05-08")


def test_live_box_set_names_its_tour_right_after_the_release(album):
    payload = album(release_id_or_title=BOX)
    assert list(payload)[:2] == ["release", "tour"]
    assert payload["tour"]["names"] == ["Europe 1972"]
    assert "look_up" in payload["tour"]["nights"] and "get_grid" in payload["tour"]["nights"]


def test_studio_album_has_no_tour_pointer(album):
    assert "tour" not in album(release_id_or_title="American Beauty")


def test_a_small_multi_show_release_lists_every_track_by_night(album):
    payload = album(release_id_or_title="release-dicks-picks-volume-4-fillmore-east-1996", include=["tracks"])
    assert len(payload["nights"]) == 2 and "tracks" not in payload
    assert sum(len(night["tracks"]) for night in payload["nights"]) + payload["contents"]["tracks_without_a_show"] == payload["track_count"]
    assert "every track" in payload["tracks_note"]


def test_tracks_from_no_known_show_stay_on_the_record(album):
    payload = album(release_id_or_title=BOX, include=["tracks"])
    listed = sum(len(night["tracks"]) for night in payload["nights"]) + len(payload.get("tracks_without_a_show", []))
    assert payload["contents"]["tracks_without_a_show"] == len(payload.get("tracks_without_a_show", []))
    if "first" not in payload["tracks_note"]:
        assert listed == payload["track_count"]
    if payload["contents"]["tracks_without_a_show"]:
        assert "no known show" in payload["tracks_note"]


def test_a_compilation_across_many_tours_gets_no_tour_pointer(album):
    payload = album(release_id_or_title="release-thankfully-grateful-2024")
    assert "tour" not in payload


def test_a_release_keeps_the_partial_date_its_source_gives(album):
    payload = album(release_id_or_title="release-dicks-picks-volume-32-1982-08-07")
    assert payload["release"]["release_date"]
    assert "notes" not in payload["release"]
