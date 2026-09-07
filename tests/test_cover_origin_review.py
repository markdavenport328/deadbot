import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_cover_origin_review", ROOT / "scripts" / "build_cover_origin_review.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

FAMILY = {"person-jerry-garcia", "person-robert-hunter"}


def test_a_song_written_outside_the_family_is_a_cover_candidate():
    songs = [{"song_id": "song-morning-dew", "title": "Morning Dew"}]
    writers = [{"song_id": "song-morning-dew", "person_id": "person-bonnie-dobson"}]
    candidates = module.candidate_covers(songs, writers, FAMILY)
    assert candidates == [
        {
            "song_id": "song-morning-dew",
            "title": "Morning Dew",
            "writers": ["person-bonnie-dobson"],
            "signal": "non_family_writer",
        }
    ]


def test_a_family_written_song_is_not_a_candidate():
    songs = [{"song_id": "song-ripple", "title": "Ripple"}]
    writers = [
        {"song_id": "song-ripple", "person_id": "person-jerry-garcia"},
        {"song_id": "song-ripple", "person_id": "person-robert-hunter"},
    ]
    assert module.candidate_covers(songs, writers, FAMILY) == []


def test_a_song_with_no_writer_data_is_flagged_for_review_not_assumed():
    songs = [{"song_id": "song-unknown", "title": "Unknown"}]
    candidates = module.candidate_covers(songs, [], FAMILY)
    assert candidates[0]["signal"] == "no_writer_data"
