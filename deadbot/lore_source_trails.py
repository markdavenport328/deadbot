"""Offline, reviewed source trails for model-led Deadhead lore exploration.

This catalog stores links and editorial invitations. Callers pair source
content with the local performance graph when making factual assertions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "lore-source-trails.json"
SCHEMA_VERSION = 1
_KINDS = {"official", "editorial", "community"}
_ENTITY_TYPES = {"song", "show"}


class LoreTrailValidationError(ValueError):
    """Raised when the reviewed lore trail catalog is malformed."""


def load_lore_trails(path: Path = DEFAULT_PATH) -> tuple[dict[str, Any], ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoreTrailValidationError(f"cannot read lore trail catalog {path}: {exc}") from exc
    return validate_lore_trails(document)


def validate_lore_trails(document: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise LoreTrailValidationError("lore trail schema_version must be 1")
    trails = document.get("trails")
    if not isinstance(trails, list) or not trails:
        raise LoreTrailValidationError("trails must be a non-empty list")
    ids: set[str] = set()
    for trail in trails:
        if not isinstance(trail, dict):
            raise LoreTrailValidationError("each trail must be an object")
        required = {"trail_id", "entity_type", "entity_id", "entity_label", "question_themes", "sources"}
        if not required.issubset(trail):
            raise LoreTrailValidationError("trail is missing required fields")
        trail_id = trail["trail_id"]
        if not isinstance(trail_id, str) or not trail_id or trail_id in ids:
            raise LoreTrailValidationError("trail IDs must be unique and non-empty")
        ids.add(trail_id)
        if trail["entity_type"] not in _ENTITY_TYPES or not isinstance(trail["entity_id"], str) or not trail["entity_id"]:
            raise LoreTrailValidationError(f"invalid entity scope in {trail_id}")
        if not isinstance(trail["question_themes"], list) or not trail["question_themes"]:
            raise LoreTrailValidationError(f"{trail_id} needs question themes")
        sources = trail["sources"]
        if not isinstance(sources, list) or not sources:
            raise LoreTrailValidationError(f"{trail_id} needs sources")
        for source in sources:
            if not isinstance(source, dict) or not {"title", "url", "source_kind", "why_open"}.issubset(source):
                raise LoreTrailValidationError(f"invalid source in {trail_id}")
            parsed = urlparse(source["url"])
            if parsed.scheme != "https" or not parsed.netloc or not source["title"] or not source["why_open"]:
                raise LoreTrailValidationError(f"source in {trail_id} needs https URL, title, and why_open")
            if source["source_kind"] not in _KINDS:
                raise LoreTrailValidationError(f"invalid source_kind in {trail_id}")
    return tuple(trails)


def source_trails_for_entity(entity_type: str, entity_id: str, *, path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """Return link metadata for one canonical song/show, without source text."""

    if entity_type not in _ENTITY_TYPES or not entity_id.strip():
        return {"state": "invalid", "coverage": "metadata_only", "records": [], "message": "A canonical song or show ID is required."}
    trails = [trail for trail in load_lore_trails(path) if trail["entity_type"] == entity_type and trail["entity_id"] == entity_id]
    records = []
    for trail in trails:
        for source in trail["sources"]:
            records.append({
                "resource_id": f"lore:{trail['trail_id']}:{source['title']}",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "title": source["title"],
                "url": source["url"],
                "resource_type": "lore_source_trail",
                "source": source["source_kind"],
                "source_kind": source["source_kind"],
                "why_open": source["why_open"],
                "question_themes": trail["question_themes"],
                "trail_id": trail["trail_id"],
            })
    return {"state": "ok" if records else "empty", "coverage": "metadata_only", "records": records, "trail_ids": [trail["trail_id"] for trail in trails], "message": "Reviewed link metadata only; source content must be researched separately."}
