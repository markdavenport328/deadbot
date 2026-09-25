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
    assert sum(show["track_count"] for show in shows) + payload["contents"].get("unattributed_track_count", 0) == payload["track_count"]
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
    # This box set's full tracklist (578 tracks) is 130,627 raw JSON characters,
    # over the 80,000-char tool result ceiling (Task 3's _json safety net), so
    # the untruncated case only applies to releases small enough to fit.
    if "_truncated" in full:
        assert len(full["tracks"]) < full["track_count"]
    else:
        assert len(full["tracks"]) == full["track_count"]
    assert 0 < len(one["tracks"]) < full["track_count"]
    assert "tracks" not in one["available"]
    assert "narrow to one show" in full["tracks_note"]


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
