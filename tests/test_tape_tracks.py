"""A song plays from its start to its end, and the length shown is the length heard."""

from __future__ import annotations

from deadbot import composition, listening, song_life
from deadbot.data import CanonicalStore
from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tape import tape_tracks

TAPE = "https://archive.org/download/gd1970-02-13.aud/"


def _link(performance_id: str, file: str, seconds: str, suffix: str = "", start: str = "", tape: str = TAPE) -> dict[str, str]:
    return {
        "performance_link_id": f"performance-link-{performance_id}-archive-track{suffix}",
        "performance_id": performance_id,
        "platform": "archive",
        "link_type": "recording-track",
        "url": tape + file,
        "start_seconds": start,
        "duration_seconds": seconds,
    }


def test_one_whole_file_needs_no_parts():
    track = tape_tracks([_link("p", "d1t01.mp3", "300")])["p"]
    assert track.url == TAPE + "d1t01.mp3" and track.duration_seconds == 300
    assert track.audio_parts() is None


def test_a_song_cut_across_files_plays_them_in_order_and_states_their_sum():
    links = [
        _link("dark-star", "d2t02.mp3", "123", "-part-02"),
        _link("dark-star", "d2t01.mp3", "1670"),
    ]
    track = tape_tracks(links)["dark-star"]
    assert track.url == TAPE + "d2t01.mp3"
    assert track.duration_seconds == 1793
    assert track.audio_parts() == [
        {"audio_url": TAPE + "d2t01.mp3", "start_seconds": 0, "end_seconds": 1670},
        {"audio_url": TAPE + "d2t02.mp3", "start_seconds": 0, "end_seconds": 123},
    ]


def test_a_part_without_a_length_leaves_the_song_without_one():
    links = [_link("p", "a.mp3", "600"), _link("p", "b.mp3", "", "-part-02")]
    assert tape_tracks(links)["p"].duration_seconds is None


def test_a_song_inside_a_shared_file_plays_its_window():
    track = tape_tracks([_link("rider", "d1t08.mp3", "312", start="281")])["rider"]
    assert track.duration_seconds == 312
    assert track.audio_parts() == [{"audio_url": TAPE + "d1t08.mp3", "start_seconds": 281, "end_seconds": 593}]


def test_parts_come_from_the_tape_of_the_first_link_only():
    links = [_link("p", "t01.mp3", "500"), _link("p", "x.mp3", "40", "-part-02", tape="https://archive.org/download/other/")]
    assert len(tape_tracks(links)["p"].parts) == 1


def test_the_one_length_rule_states_a_split_songs_whole_length():
    track = tape_tracks([_link("p", "a.mp3", "1670"), _link("p", "b.mp3", "123", "-part-02")])["p"]
    length = song_life.stated_length(track, [song_life.ReleaseLength("release", "Album", 900)], "p")
    assert length is not None and (length.seconds, length.source) == (1793, "tape")


def _assert_dark_star_plays_both_files(store):
    tracks, _identifier = listening.playable_show_tracks("gd-1970-02-13-1", store)
    dark_star = next(track for track in tracks if track.performance_id == "gd-1970-02-13-1-dark-star-1-12")
    assert dark_star.duration_seconds == 1670 + 123
    assert [part.audio_url.rsplit("/", 1)[1] for part in dark_star.audio_parts] == ["d2t01.mp3", "d2t02.mp3"]
    listen = store.performance_context("gd-1970-02-13-1-dark-star-1-12")["listen"]
    audio = composition._audio(listen)
    assert audio["duration_seconds"] == 1793 and len(audio["audio_parts"]) == 2


def test_the_split_dark_star_plays_both_files_from_the_csv_store():
    _assert_dark_star_plays_both_files(CanonicalStore())


def test_the_split_dark_star_plays_both_files_from_the_sqlite_store(built_sqlite, tmp_path):
    _assert_dark_star_plays_both_files(SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite"))


def test_a_set_queues_every_playable_song_whichever_tape_it_comes_from():
    store = CanonicalStore()
    show_id = "gd-1972-05-11"
    tracks, identifier = listening.playable_show_tracks(show_id, store)
    linked = set(tape_tracks(store.rows_in("performance_links", "performance_id", [row["performance_id"] for row in store.filtered_rows("performances", show_id=show_id)])))
    assert {track.performance_id for track in tracks} == linked
    tapes = {track.audio_url.split("/download/")[1].split("/")[0] for track in tracks}
    assert len(tapes) >= 2
    # The tape that carries the most songs names the show's picture.
    assert identifier == "gd72-05-11.sbd.ashley-bertha.7364.sbefail.shnf"
    ids = [track.performance_id for track in tracks]
    assert ids.index("gd-1972-05-11-dark-star-2-7") < ids.index("gd-1972-05-11-dark-star-2-9") < ids.index("gd-1972-05-11-one-more-saturday-night-3-1")
