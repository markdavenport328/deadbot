import copy
import json
from pathlib import Path

import pytest

from deadbot.source_registry import RegistryValidationError, load_registry, validate_registry


def test_reviewed_seed_loads_with_every_metadata_adapter():
    sources = load_registry()
    assert {source["source_id"] for source in sources} == {
        "deadnet-editorial",
        "deadcast-metadata",
        "musicbrainz-api",
        "wikipedia-api",
        "lostlivedead-feed",
        "hooterollin-feed",
        "deadessays-feed",
        "deadsources-feed",
        "gratefulseconds-feed",
        "deadheadhigh-guides",
        "gdao-archive",
        "whitegum-lyric-finder",
    }
    for source in sources:
        assert source["review_state"] == "approved"
        assert source["retention_policy"]["mode"] == "metadata_only"
        assert source["retention_policy"]["store_content"] is False
        assert set(source["allowed_operations"]) == set(source["operation_policies"])


def test_registry_rejects_unsafe_path_or_mismatched_policy():
    source = copy.deepcopy(load_registry()[0])
    document = {"schema_version": 3, "sources": [source]}
    source["operation_policies"]["read"]["paths"].append("/../private")
    with pytest.raises(RegistryValidationError):
        validate_registry(document)

    source["operation_policies"]["read"]["paths"].pop()
    source["allowed_operations"].append("write")
    with pytest.raises(RegistryValidationError):
        validate_registry(document)
