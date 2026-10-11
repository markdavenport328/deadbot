"""GET /api/songs/{song_id}/years/{year}: one song's year of performances for See all, from the library alone."""

import pytest
from fastapi.testclient import TestClient

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.sqlite_store import SqliteCanonicalStore


@pytest.fixture
def client(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    with TestClient(create_app(settings=Settings(), store=store, agent=object())) as test_client:
        yield test_client


def test_song_year_lists_one_year_with_its_facts_and_may_be_cached(client):
    response = client.get("/api/songs/song-terrapin-station/years/1979")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"
    body = response.json()
    assert (body["song_id"], body["title"], body["year"]) == ("song-terrapin-station", "Terrapin Station", 1979)
    assert len(body["performances"]) == 23
    first = body["performances"][0]
    assert (first["show_date"], first["venue_name"]) == ("1979-01-08", "Madison Square Garden")
    assert first["next"] == {"song_id": "song-playing-in-the-band", "title": "Playing In The Band", "segued": True}
    assert first["track"]["audio_url"].startswith("https://archive.org/download/")
    assert {"voice": "Charlie Miller", "scope": "show"} in first["signals"]


def test_song_year_unknown_song_and_unplayed_year(client):
    assert client.get("/api/songs/song-no-such-song/years/1979").status_code == 404
    empty = client.get("/api/songs/song-terrapin-station/years/1975")
    assert empty.status_code == 200 and empty.json()["performances"] == []


def test_song_year_shares_the_lookup_rate_limit(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    with TestClient(create_app(settings=Settings(grid_rate_limit_per_minute=1), store=store, agent=object())) as limited:
        assert limited.get("/api/songs/song-terrapin-station/years/1979").status_code == 200
        assert limited.get("/api/songs/song-terrapin-station/years/1980").status_code == 429
