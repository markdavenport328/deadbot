import json
from pathlib import Path

import pytest

from deadbot.data import CanonicalStore
from deadbot.editorial_discovery import (
    GUIDE_PATH,
    DiscoveryGuideError,
    load_discovery_guide,
    model_capability_map,
    model_discovery_brief,
    validate_discovery_guide,
)


def store_with_selection_evidence() -> CanonicalStore:
    document = json.loads(
        (Path(__file__).parents[1] / "data" / "editorial" / "selection-evidence-review.json").read_text(encoding="utf-8")
    )
    entries = [
        {**entry, "review_packet": {"source_constraints": document["source_constraints"]}}
        for entry in document["entries"]
    ]

    class StoreWithSelectionEvidence(CanonicalStore):
        def selection_signal_rows(self):
            return entries

    return StoreWithSelectionEvidence()


def test_seed_loads_offline_and_covers_requested_paths():
    guide = load_discovery_guide()
    assert 20 <= len(guide["leads"]) <= 30
    categories = {lead["category"] for lead in guide["leads"]}
    assert {"song_evolution", "improvisation", "transition_suite", "lyrics_history", "show_context", "late_era_sound"} <= categories
    text = json.dumps(guide)
    for expected in ("Friend of the Devil", "They Love Each Other", "Dancin' in the Streets", "Sugaree", "Dark Star", "MIDI"):
        assert expected in text


def test_validation_rejects_duplicate_ids_and_missing_verification():
    guide = load_discovery_guide()
    guide["leads"][1]["id"] = guide["leads"][0]["id"]
    with pytest.raises(DiscoveryGuideError):
        validate_discovery_guide(guide)

    guide = load_discovery_guide()
    guide["leads"][0]["verification_instruction"] = "Have fun exploring."
    with pytest.raises(DiscoveryGuideError):
        validate_discovery_guide(guide)


def test_default_path_is_source_controlled():
    assert GUIDE_PATH.is_file()


def test_model_brief_is_a_full_discretionary_inventory_not_a_router():
    brief = json.loads(model_discovery_brief())
    assert "optional invitations" in brief["instruction"]
    assert len(brief["leads"]) == 20
    assert all(set(lead) == {"id", "category", "entities", "question_themes", "editorial_prompt", "source_trail_preference"} for lead in brief["leads"])


def test_capability_map_exposes_data_relationship_and_source_coverage():
    capability_map = json.loads(model_capability_map(store_with_selection_evidence()))
    assert capability_map["canonical_library"]["entity_types"]["people"] > 0
    assert capability_map["canonical_library"]["relationships"]["people_with_guest_credits"] > 0
    assert capability_map["reviewed_selection_signals"]["entry_count"] > 0
    assert {source["source_id"] for source in capability_map["approved_external_research"]} >= {"deadnet-editorial", "deadcast-metadata"}
    assert capability_map["stored_context_links"]["trail_count"] >= 1
