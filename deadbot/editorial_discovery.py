"""Offline loading and validation for the model-facing editorial discovery guide."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from deadbot.data import CanonicalStore
from deadbot.lore_source_trails import LoreTrailValidationError, load_lore_trails
from deadbot.selection_signals import SelectionSignalError, selection_signal_summary
from deadbot.source_registry import RegistryValidationError, load_registry

GUIDE_PATH = Path(__file__).parents[1] / "data" / "editorial" / "discovery-guide.json"
REQUIRED_LEAD_FIELDS = {
    "id", "category", "entities", "question_themes", "editorial_prompt",
    "source_trail_preference", "verification_instruction",
}
ALLOWED_CATEGORIES = {
    "song_evolution", "improvisation", "transition_suite", "lyrics_history",
    "show_context", "late_era_sound",
}


class DiscoveryGuideError(ValueError):
    """Raised when a discovery guide is malformed or unsafe to load."""


def validate_discovery_guide(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("kind") != "editorial_discovery_guide":
        raise DiscoveryGuideError("guide must be an editorial_discovery_guide object")
    if document.get("schema_version") != 1:
        raise DiscoveryGuideError("unsupported or missing schema_version")
    if not isinstance(document.get("model_instruction"), str) or "verify" not in document["model_instruction"].lower():
        raise DiscoveryGuideError("model_instruction must require verification")
    leads = document.get("leads")
    if not isinstance(leads, list) or not leads:
        raise DiscoveryGuideError("leads must be a non-empty list")
    ids: set[str] = set()
    for index, lead in enumerate(leads):
        if not isinstance(lead, dict) or set(lead) != REQUIRED_LEAD_FIELDS:
            raise DiscoveryGuideError(f"lead {index} has an invalid field set")
        lead_id = lead["id"]
        if not isinstance(lead_id, str) or not lead_id or lead_id in ids:
            raise DiscoveryGuideError(f"lead {index} has a missing or duplicate id")
        ids.add(lead_id)
        if lead["category"] not in ALLOWED_CATEGORIES:
            raise DiscoveryGuideError(f"lead {lead_id} has an unknown category")
        for field in ("entities", "question_themes", "source_trail_preference"):
            if not isinstance(lead[field], list) or not lead[field] or not all(isinstance(v, str) and v for v in lead[field]):
                raise DiscoveryGuideError(f"lead {lead_id} field {field} must be non-empty strings")
        for field in ("editorial_prompt", "verification_instruction"):
            if not isinstance(lead[field], str) or not lead[field].strip():
                raise DiscoveryGuideError(f"lead {lead_id} field {field} must be non-empty")
        if "verify" not in lead["verification_instruction"].lower() and "research" not in lead["verification_instruction"].lower():
            raise DiscoveryGuideError(f"lead {lead_id} must require research or verification")
    return document


def load_discovery_guide(path: str | Path = GUIDE_PATH) -> dict[str, Any]:
    """Load and validate the guide without network access or side effects."""
    guide_path = Path(path)
    try:
        document = json.loads(guide_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscoveryGuideError(f"could not read guide {guide_path}: {exc}") from exc
    return validate_discovery_guide(document)


def model_discovery_brief(path: str | Path = GUIDE_PATH) -> str:
    """Return the compact, non-factual guide packet for the answering model.

    The model receives a compact inventory and decides relevance itself. Code
    supplies the whole guide for the model's contextual judgment.
    """

    guide = load_discovery_guide(path)
    packet = {
        "instruction": guide["model_instruction"],
        "leads": [
            {
                "id": lead["id"],
                "category": lead["category"],
                "entities": lead["entities"],
                "question_themes": lead["question_themes"],
                "editorial_prompt": lead["editorial_prompt"],
                "source_trail_preference": lead["source_trail_preference"],
            }
            for lead in guide["leads"]
        ],
    }
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))


def model_capability_map(store: CanonicalStore) -> str:
    """Return a grounded inventory of the model's data and research surface.

    This is deliberately a map, not a router: the model decides whether and
    how a question calls for any part of it. Tool descriptions provide the
    precise argument contracts and output limits.
    """

    guest_person_ids = {
        assignment.get("person_id")
        for assignment in store.rows("show_performers")
        if assignment.get("role") == "guest" and assignment.get("person_id")
    }
    resource_types = Counter(resource.get("resource_type", "unknown") for resource in store.rows("resources"))
    resource_sources = sorted({resource.get("source_name", "") for resource in store.rows("resources") if resource.get("source_name")})
    packet: dict[str, Any] = {
        "decision_principle": (
            "This is the complete currently available map, not a prescribed retrieval plan. "
            "Choose the relevant tools and sources from the visitor's actual question, then favor "
            "the facts and exploration paths that make the answer worth opening."
        ),
        "canonical_library": {
            "coverage": store.coverage_summary(),
            "entity_types": {
                "songs": store.row_count("songs"),
                "shows": store.row_count("shows"),
                "performances": store.row_count("performances"),
                "people": store.row_count("people"),
                "venues": store.row_count("venues"),
                "recordings": store.row_count("recordings"),
                "cataloged_external_resources": store.row_count("resources"),
            },
            "relationships": {
                "show_performer_credits": store.row_count("show_performers"),
                "people_with_guest_credits": len(guest_person_ids),
                "guest_credit_meaning": "Guest credits record documented show relationships.",
                "other_relationships": ["ordered show setlists", "show recordings and media links", "song-performance history", "equipment assignments", "song resources and arrangements"],
            },
            "stored_resource_catalog": {
                "access": "searchable metadata and provenance notes; external source text is not locally available",
                "resource_types": dict(sorted(resource_types.items())),
                "source_names": resource_sources,
            },
        },
    }
    try:
        packet["reviewed_selection_signals"] = selection_signal_summary(store)
    except SelectionSignalError:
        packet["reviewed_selection_signals"] = {"state": "unavailable"}
    try:
        packet["approved_external_research"] = [
            {
                "source_id": source["source_id"],
                "name": source["name"],
                "authority_level": source["authority_level"],
                "allowed_operations": source["allowed_operations"],
                "retention_mode": source["retention_policy"].get("mode"),
                "notes": source.get("notes"),
            }
            for source in load_registry()
        ]
    except RegistryValidationError:
        packet["approved_external_research"] = []
    try:
        trails = load_lore_trails()
        packet["stored_context_links"] = {
            "access": "reviewed link metadata only; no article body, transcript, or audio is locally available",
            "trail_count": len(trails),
            "scopes": [
                {
                    "entity_type": trail["entity_type"],
                    "entity_id": trail["entity_id"],
                    "entity_label": trail["entity_label"],
                    "question_themes": trail["question_themes"],
                }
                for trail in trails
            ],
        }
    except LoreTrailValidationError:
        packet["stored_context_links"] = {"state": "unavailable"}
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
