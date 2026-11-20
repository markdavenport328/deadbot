"""Blocks that point at performances carry what the in-page player needs.

Each item that names a rendition with an Internet Archive track gets its
audio URL and length (and the show's venue) during hydration, read from the
runtime SQLite store, so the browser can play it rather than link out to the
raw file.
"""

import pytest

from deadbot import composition
from deadbot.sqlite_store import SqliteCanonicalStore

RFK_EYES = "gd-1973-06-10-eyes-of-the-world-2-1"
RFK_EYES_TRACK = "https://archive.org/download/gd1973-06-10.sbd.miller.89640.sbeok.flac16/gd73-06-10d2t02.mp3"


@pytest.fixture
def store(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield store
    store.close()


def test_song_representatives_carry_tracks(store):
    song = store.one("songs", "song-playing-in-the-band")
    block = composition._song_overview(
        store.song_context(song),
        store,
        visible_facets=["representatives"],
        representative_performance_ids=["gd-1972-08-27-playing-in-the-band"],
    )
    representative = block.representative_performances[0]
    assert representative.audio_url and representative.venue_name == "Old Renaissance Faire Grounds"


def test_a_live_record_maps_its_tracks_to_their_tapes(store):
    release = store.resolve_release("release-veneta-or-1972-08-27-complete-sunshine-daydream-concert")
    block, _ = composition._album_unit(store.album_context(release), store)
    playable = [track for track in block.tracks if track.audio_url]
    assert playable, "a live record of a taped show has playable tracks"
    assert all(track.show_date == "1972-08-27" and track.venue_name for track in playable)
    assert all(track.audio_url.startswith("https://archive.org/download/") for track in playable)
