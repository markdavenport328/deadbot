"""Guard: a tape link's stored length is the length of the file its URL plays.

The stored length once came from the lossless original's metadata, which for
Shorten (.shn) tapes is roughly half the real length; the MP3 the link plays
carried the right one. This reads the canonical links against the preserved
Internet Archive item metadata, file by file, so a length copied from any
other file fails here. No network.
"""

from __future__ import annotations

import csv
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import normalize_internet_archive_tracks as ia_tracks  # noqa: E402
from normalize_internet_archive_track_links import PART_NOTE  # noqa: E402

CANONICAL = ROOT / "data" / "canonical"


def _rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / f"{name}.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _split(url: str) -> tuple[str, str]:
    identifier, _, file_name = url.split("/download/", 1)[1].partition("/")
    return identifier, urllib.parse.unquote(file_name)


@pytest.fixture(scope="module")
def tape_links() -> list[dict[str, str]]:
    return [
        row
        for row in _rows("performance_links")
        if row["platform"] == "archive" and row["link_type"] == "recording-track"
    ]


@pytest.fixture(scope="module")
def item_payloads(tape_links) -> dict[str, dict]:
    wanted = {_split(row["url"])[0] for row in tape_links}
    payloads: dict[str, dict] = {}
    for path in ia_tracks.item_metadata_paths():
        for record in ia_tracks.read_item_records(path):
            identifier = record.get("source_record_id")
            if identifier in wanted and identifier not in payloads and "files" in record.get("raw_payload", {}):
                payloads[identifier] = record["raw_payload"]
    return payloads


def _played_file(payloads: dict[str, dict], url: str) -> dict | None:
    identifier, file_name = _split(url)
    return next(
        (record for record in payloads.get(identifier, {}).get("files", []) if record.get("name") == file_name),
        None,
    )


def test_every_tape_link_plays_a_file_in_the_preserved_item_metadata(tape_links, item_payloads):
    missing = [row["url"] for row in tape_links if _played_file(item_payloads, row["url"]) is None]
    assert missing == []


def test_a_tape_links_length_is_the_length_of_the_file_it_plays(tape_links, item_payloads):
    wrong = []
    for row in tape_links:
        played = _played_file(item_payloads, row["url"])
        if played is None:
            continue
        # A file that goes on past the song (a medley in one file) states no length for the song.
        expected = "" if ia_tracks.SPANS_MORE_MARK in row["notes"] else ia_tracks.played_length(played)
        if row["duration_seconds"] != expected:
            wrong.append((row["performance_link_id"], row["duration_seconds"], expected))
    assert wrong == []


def test_no_tape_link_plays_a_file_that_stops_before_the_song_does(tape_links, item_payloads):
    cut = [
        row["url"]
        for row in tape_links
        if (played := _played_file(item_payloads, row["url"])) is not None
        and ia_tracks.stream_is_cut_short(item_payloads[_split(row["url"])[0]], played)
    ]
    assert cut == []


def test_no_two_performances_share_a_tape_file(tape_links):
    # No link carries a start offset yet (nothing in the preserved metadata
    # says where a song starts inside a shared file), so a file shared by two
    # songs would play the first song when the second one's button is pressed.
    assert all(not row["start_seconds"] for row in tape_links)
    urls = [row["url"] for row in tape_links]
    assert len(urls) == len(set(urls))


def test_a_song_in_several_files_plays_consecutive_tracks_of_one_tape(tape_links):
    from deadbot.tape import tape_tracks

    by_performance: dict[str, list[dict[str, str]]] = {}
    for row in tape_links:
        by_performance.setdefault(row["performance_id"], []).append(row)
    split = {performance_id: rows for performance_id, rows in by_performance.items() if len(rows) > 1}
    assert split, "the split pass links songs the tape cuts into several files"
    tracks = tape_tracks(tape_links)
    for performance_id, rows in split.items():
        rows.sort(key=lambda row: row["performance_link_id"])
        assert rows[0]["performance_link_id"].endswith("-archive-track")
        assert [_part(row["notes"]) for row in rows] == list(range(1, len(rows) + 1))
        assert len({_split(row["url"])[0] for row in rows}) == 1
        assert tracks[performance_id].duration_seconds == sum(int(row["duration_seconds"]) for row in rows)


@pytest.mark.parametrize(
    ("performance_id", "parts", "seconds"),
    [
        ("gd-1970-02-13-1-dark-star-1-12", 2, 1670 + 123),
        ("gd-1970-02-13-1-turn-on-your-lovelight-1-17", 2, 837 + 398),
        ("gd-1972-05-11-dark-star-2-9", 1, 1764),
        ("gd-1969-02-27-the-other-one-1-5", 1, 512),
    ],
)
def test_named_songs_play_in_full(tape_links, performance_id, parts, seconds):
    from deadbot.tape import tape_tracks

    track = tape_tracks(tape_links)[performance_id]
    assert len(track.parts) == parts
    assert track.duration_seconds == seconds


def _part(notes: str) -> int:
    match = PART_NOTE.search(notes or "")
    return int(match.group(1)) if match else 1


def test_a_mapped_tracks_length_matches_its_link(tape_links, item_payloads):
    recordings = {row["recording_id"]: row["archive_identifier"] for row in _rows("recordings")}
    # A song the tape cuts into several files has one link per part.
    by_part = {(row["performance_id"], _part(row["notes"])): row for row in tape_links}
    wrong = []
    for row in _rows("performance_recordings"):
        link = by_part.get((row["performance_id"], _part(row["notes"])))
        if link is None or _split(link["url"])[0] != recordings.get(row["recording_id"]):
            continue
        played = _played_file(item_payloads, link["url"])
        if played is not None and row["duration_seconds"] != ia_tracks.played_length(played):
            wrong.append((row["performance_id"], row["duration_seconds"], ia_tracks.played_length(played)))
    assert wrong == []


def test_shorten_originals_are_never_the_source_of_a_length():
    payload = {
        "files": [
            {"name": "d1t02.shn", "source": "original", "format": "Shorten", "track": "02", "title": "Sugaree", "length": "370.7"},
            {"name": "d1t02.mp3", "source": "derivative", "format": "VBR MP3", "original": "d1t02.shn", "length": "11:30"},
        ]
    }
    shn, mp3 = payload["files"]
    assert ia_tracks.track_length(payload, shn) == "690"
    assert ia_tracks.played_length(mp3) == "690"
    assert ia_tracks.played_length(shn) == ""
    assert ia_tracks.track_length({"files": [shn]}, shn) == ""


def test_an_mp3_that_stops_early_is_recognized():
    payload = {
        "files": [
            {"name": "03.flac", "source": "original", "format": "24bit Flac", "length": "584.7"},
            {"name": "03.mp3", "source": "derivative", "format": "VBR MP3", "original": "03.flac", "length": "04:20"},
            {"name": "04.flac", "source": "original", "format": "Flac", "length": "679.6"},
            {"name": "04.mp3", "source": "derivative", "format": "VBR MP3", "original": "04.flac", "length": "11:19"},
            {"name": "05.shn", "source": "original", "format": "Shorten", "length": "370.7"},
            {"name": "05.mp3", "source": "derivative", "format": "VBR MP3", "original": "05.shn", "length": "11:30"},
        ]
    }
    by_name = {record["name"]: record for record in payload["files"]}
    assert ia_tracks.stream_is_cut_short(payload, by_name["03.mp3"])
    assert not ia_tracks.stream_is_cut_short(payload, by_name["04.mp3"])
    assert not ia_tracks.stream_is_cut_short(payload, by_name["05.mp3"])
