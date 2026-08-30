import copy

import pytest

from deadbot.lore_source_trails import LoreTrailValidationError, load_lore_trails, source_trails_for_entity, validate_lore_trails


def test_catalog_has_scoped_pilot_trails_and_metadata_only_payload():
    trails = load_lore_trails()
    assert {trail["entity_id"] for trail in trails} == {
        "song-friend-of-the-devil", "song-sugaree", "song-they-love-each-other",
        "song-dancin-in-the-streets", "gd-1972-08-27", "gd-1977-05-08",
    }
    result = source_trails_for_entity("song", "song-friend-of-the-devil")
    assert result["state"] == "ok"
    assert result["coverage"] == "metadata_only"
    assert "content" not in result["records"][0]
    assert result["records"][0]["why_open"]


def test_unknown_entity_is_empty_and_bad_catalog_is_rejected():
    assert source_trails_for_entity("song", "song-unknown")["state"] == "empty"
    document = {"schema_version": 1, "trails": [copy.deepcopy(load_lore_trails()[0])]}
    document["trails"][0]["sources"][0]["url"] = "http://example.com"
    with pytest.raises(LoreTrailValidationError):
        validate_lore_trails(document)
