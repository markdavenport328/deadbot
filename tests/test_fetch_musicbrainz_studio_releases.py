import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_musicbrainz_studio_releases",
    ROOT / "scripts" / "collect" / "fetch_musicbrainz_studio_releases.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_studio_artists_cover_the_dead_family_catalog():
    names = {name.casefold() for name in module.STUDIO_ARTISTS}
    assert "grateful dead" in names
    assert "jerry garcia" in names
    assert "bob weir" in names
    assert "new riders of the purple sage" in names
    assert "old & in the way" in names
    assert "kingfish" in names
    assert "jerry garcia band" in names


def test_a_live_secondary_type_disqualifies_a_release_group():
    live = {"primary-type": "Album", "secondary-types": ["Live"]}
    assert module.is_studio_release_group(live) is False


def test_a_plain_album_qualifies():
    album = {"primary-type": "Album", "secondary-types": []}
    assert module.is_studio_release_group(album) is True


def test_a_compilation_or_single_is_out_of_scope():
    assert module.is_studio_release_group({"primary-type": "Single", "secondary-types": []}) is False
    assert module.is_studio_release_group({"primary-type": "Album", "secondary-types": ["Compilation"]}) is False
