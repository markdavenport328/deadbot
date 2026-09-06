import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "normalize_release_track_songs",
    ROOT / "scripts" / "normalize_release_track_songs.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

SONGS = {"sugaree": "song-sugaree", "deal": "song-deal"}
PERFORMANCES = {"gd-1979-11-06-deal-1-11": "song-deal"}


def test_a_mapped_performance_supplies_the_song_directly():
    rows, held = module.backfill_song_ids(
        [{"performance_id": "gd-1979-11-06-deal-1-11", "song_id": "", "track_title": "Deal"}],
        SONGS,
        PERFORMANCES,
    )
    assert rows[0]["song_id"] == "song-deal"
    assert held == []


def test_an_unmapped_track_resolves_by_title():
    rows, held = module.backfill_song_ids(
        [{"performance_id": "", "song_id": "", "track_title": "Sugaree"}], SONGS, PERFORMANCES
    )
    assert rows[0]["song_id"] == "song-sugaree"


def test_an_unresolvable_title_stays_empty_and_is_reported():
    rows, held = module.backfill_song_ids(
        [{"performance_id": "", "song_id": "", "track_title": "Tuning"}], SONGS, PERFORMANCES
    )
    assert rows[0]["song_id"] == ""
    assert held == [{"track_title": "Tuning", "reason": "unresolved_title"}]


def test_an_existing_song_id_is_recomputed_not_trusted():
    rows, _ = module.backfill_song_ids(
        [{"performance_id": "", "song_id": "song-wrong", "track_title": "Sugaree"}], SONGS, PERFORMANCES
    )
    assert rows[0]["song_id"] == "song-sugaree"
