import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "normalize_musicbrainz_studio_releases",
    ROOT / "scripts" / "normalize_musicbrainz_studio_releases.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

SONGS = {
    "sugaree": "song-sugaree",
    "truckin": "song-truckin",
    "china cat sunflower": "song-china-cat-sunflower",
}


def test_an_exact_title_resolves_to_its_song():
    assert module.resolve_song_id("Sugaree", SONGS) == "song-sugaree"


def test_punctuation_and_case_do_not_block_a_match():
    assert module.resolve_song_id("Truckin'", SONGS) == "song-truckin"
    assert module.resolve_song_id("CHINA CAT SUNFLOWER", SONGS) == "song-china-cat-sunflower"


def test_an_unresolved_title_is_held_rather_than_guessed():
    assert module.resolve_song_id("Untitled Studio Jam", SONGS) is None


def test_release_ids_are_stable_kebab_case():
    assert module.release_id_for("American Beauty") == "release-american-beauty"
    assert module.release_id_for("Ace") == "release-ace"
