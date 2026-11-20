import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_selection_evidence_review import document


def test_selection_evidence_review_is_materialized_and_preserves_holds():
    path = Path(__file__).parents[1] / "data" / "editorial" / "selection-evidence-review.json"
    materialized = json.loads(path.read_text(encoding="utf-8"))
    assert materialized == document()
    summary = materialized["summary"]
    assert summary["by_source"] == {
        "charlie-miller-reddit": 17,
        "charlie-miller-user-provided-threads": 20,
        "deadnet-official-release-pass": 5,
        "guitar-world-50-best": 96,
        "headyversion": 16,
        "pitchfork-essential-live-songs": 79,
        "rolling-stone-australia": 20,
    }
    assert summary["by_resolution_state"]["resolved_unique_show"] >= 19
    assert summary["by_resolution_state"]["resolved_unique_performance"] >= 11
    assert summary["by_resolution_state"]["held_ambiguous_show_date"] > 0
    assert summary["by_resolution_state"]["held_multiple_canonical_performances"] > 0


def test_critic_performance_lists_resolve_each_named_song_conservatively():
    entries = [
        entry for entry in document()["entries"]
        if entry["signal_type"] == "critic_editorial_performance_selection"
    ]
    assert len(entries) == 175
    resolved = [entry for entry in entries if entry["resolution_state"] == "resolved_unique_performance"]
    assert len(resolved) > 140
    for entry in resolved:
        assert len(entry["candidate_performance_ids"]) == 1 and len(entry["candidate_show_ids"]) == 1
        assert entry["candidate_performance_ids"][0].startswith(entry["candidate_show_ids"][0])
        assert entry["source_url"].startswith("https://")
    held = {entry["resolution_state"] for entry in entries} - {"resolved_unique_performance"}
    assert held <= {"held_ambiguous_show_date", "held_missing_canonical_performance", "held_multiple_canonical_performances"}
    # A source's own date with no show in the catalog is held, not guessed.
    assert any(entry["show_date"] == "1990-04-22" and entry["resolution_state"] == "held_ambiguous_show_date" for entry in entries)
