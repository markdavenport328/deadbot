"""Offline loading and validation for the model-facing editorial discovery guide."""

import json
from pathlib import Path
from typing import Any

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
