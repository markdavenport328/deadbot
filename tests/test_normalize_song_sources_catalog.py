"""The catalog song-credit normalizer resolves printed names and reruns byte for byte."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("normalize_song_sources_catalog", ROOT / "scripts" / "normalize_song_sources_catalog.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

OUTPUTS = ["people.csv", "song_writers.csv", "resources.csv", "resource_songs.csv", "songs.csv"]


def test_a_resolved_printed_name_points_at_the_person_and_says_why():
    assert module.normalize_credit_name("Leiber") == "Jerry Leiber"
    assert module.normalize_credit_name("Donna Godchaux") == "Donna Jean Godchaux"
    assert module.credit_note("Bruce Welnick", "Dead.net song-page credit.") == (
        "Dead.net song-page credit (printed 'Bruce Welnick'; resolved by name: Easy Answers MusicBrainz "
        "work 3f42f391 (ISWC T-914.475.299-8) credits Vince Welnick)."
    )
    assert module.credit_note("Robert Hunter", "Dead.net song-page credit.") == "Dead.net song-page credit."


def test_remove_note_keeps_the_punctuation_of_the_notes_around_it():
    value = "Source label normalized from gdshowsdb 1979 bulk baseline.; External Dead.net lyric page linked; full lyrics not stored; Tail"
    assert module.remove_note(value, "External Dead.net lyric page linked; full lyrics not stored") == (
        "Source label normalized from gdshowsdb 1979 bulk baseline.; Tail"
    )


def test_a_rerun_reproduces_the_committed_outputs_byte_for_byte(tmp_path, monkeypatch):
    for name in OUTPUTS:
        shutil.copy(module.CANONICAL / name, tmp_path / name)
    monkeypatch.setattr(module, "CANONICAL", tmp_path)

    module.main()

    for name in OUTPUTS:
        assert (tmp_path / name).read_bytes() == (ROOT / "data" / "canonical" / name).read_bytes(), name
