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


def test_an_era_performance_carries_its_track_length_and_venue(store):
    item = composition._era_performance_item(store.performance_context(RFK_EYES), store)
    assert item.audio_url == RFK_EYES_TRACK
    assert item.duration_seconds == 1305
    assert item.venue_name == "Robert F. Kennedy Stadium"


def test_song_history_and_representatives_carry_tracks(store):
    song = store.one("songs", "song-playing-in-the-band")
    block = composition._song_overview(
        store.song_context(song),
        store,
        visible_facets=["representatives", "history"],
        representative_performance_ids=["gd-1972-08-27-playing-in-the-band"],
    )
    history = block.history
    assert history.last.audio_url and history.last.audio_url.startswith("https://archive.org/download/")
    assert history.last.duration_seconds == 636
    assert history.last.venue_name == "Riverport Amphitheatre"
    # A rendition with no tape stays unplayable rather than borrowing another's.
    assert history.first.audio_url is None
    assert all(item.audio_url == item.listen_url for item in history.by_year if item.audio_url)
    assert any(item.audio_url for item in history.by_year)
    representative = block.representative_performances[0]
    assert representative.audio_url and representative.venue_name == "Old Renaissance Faire Grounds"


def test_guest_songs_carry_tracks_when_a_store_is_given(store):
    guest = {
        "person_id": "p",
        "name": "A guest",
        "appearances": [
            {
                "show_id": "gd-1973-06-10",
                "show_date": "1973-06-10",
                "venue_name": "Robert F. Kennedy Stadium",
                "instruments": ["guitar"],
                "songs": [{"performance_id": RFK_EYES, "song_title": "Eyes Of The World"}],
            }
        ],
    }
    [block] = composition._guest_appearance_blocks({"guests": [guest]}, store)
    song = block.items[0].songs[0]
    assert song.audio_url == RFK_EYES_TRACK and song.duration_seconds == 1305
    [bare] = composition._guest_appearance_blocks({"guests": [guest]})
    assert bare.items[0].songs[0].audio_url is None


def test_show_selection_items_carry_the_show_tape(store):
    selection = {
        "selection_id": "s",
        "title": "Picks",
        "source_url": "https://example.org/picks",
        "items": [{"show_id": "gd-1973-06-10", "show_date": "1973-06-10", "venue_name": "Robert F. Kennedy Stadium"}],
    }
    blocks, _ = composition._show_selection_blocks({"show_selections": [selection]}, store)
    item = blocks[0].items[0]
    assert item.tracks and all(track.audio_url.startswith("https://archive.org/download/") for track in item.tracks)
    assert item.recording_identifier and item.tracks[0].audio_url.split("/")[4] == item.recording_identifier


def test_a_live_record_maps_its_tracks_to_their_tapes(store):
    release = store.resolve_release("release-veneta-or-1972-08-27-complete-sunshine-daydream-concert")
    block, _ = composition._album_unit(store.album_context(release), store)
    playable = [track for track in block.tracks if track.audio_url]
    assert playable, "a live record of a taped show has playable tracks"
    assert all(track.show_date == "1972-08-27" and track.venue_name for track in playable)
    assert all(track.audio_url.startswith("https://archive.org/download/") for track in playable)
