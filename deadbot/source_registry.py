"""Validation and loading for the reviewed, source-controlled registry.

This module intentionally only reads a local JSON seed.  It does not grant
network access and is not consulted by a runtime adapter; callers can use it
to validate a registry before promoting rows to schema-v3 ``source_registry``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT / "data" / "source_registry.json"
SCHEMA_VERSION = 3
_ENUMS = {
    "authority_level": {"primary", "official", "curated", "community", "discovery", "unknown"},
    "access_state": {"allowed", "restricted", "prohibited", "unknown"},
    "rights_state": {"cleared", "restricted", "prohibited", "unknown"},
    "review_state": {"unreviewed", "approved", "rejected", "deprecated"},
}


class RegistryValidationError(ValueError):
    """Raised when a source registry seed violates the v3 contract."""


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> tuple[dict[str, Any], ...]:
    """Load and validate a source-controlled registry seed."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryValidationError(f"cannot read registry {path}: {exc}") from exc
    return validate_registry(document)


def validate_registry(document: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise RegistryValidationError("registry schema_version must be 3")
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RegistryValidationError("registry sources must be a non-empty list")
    seen: set[str] = set()
    validated = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise RegistryValidationError(f"source {index} must be an object")
        _validate_source(source, seen, index)
        validated.append(source)
    return tuple(validated)


def _validate_source(source: Mapping[str, Any], seen: set[str], index: int) -> None:
    required = {"source_id", "name", "host_allowlist", "authority_level", "access_state", "rights_state", "review_state", "allowed_operations", "operation_policies", "retention_policy", "rate_policy", "adapter_version"}
    missing = required - source.keys()
    if missing:
        raise RegistryValidationError(f"source {index} missing: {', '.join(sorted(missing))}")
    source_id = source["source_id"]
    if not isinstance(source_id, str) or not source_id.strip() or source_id in seen:
        raise RegistryValidationError(f"source {index} has an empty or duplicate source_id")
    seen.add(source_id)
    if not isinstance(source["name"], str) or not source["name"].strip():
        raise RegistryValidationError(f"source {source_id} has an empty name")
    for field, choices in _ENUMS.items():
        if source[field] not in choices:
            raise RegistryValidationError(f"source {source_id} has invalid {field}")
    hosts = source["host_allowlist"]
    if not isinstance(hosts, list) or not hosts or any(not isinstance(host, str) or not host or urlparse("https://" + host).hostname != host for host in hosts):
        raise RegistryValidationError(f"source {source_id} has invalid host_allowlist")
    operations = source["allowed_operations"]
    policies = source["operation_policies"]
    if not isinstance(operations, list) or not operations or not isinstance(policies, dict) or set(operations) != set(policies):
        raise RegistryValidationError(f"source {source_id} operation policies must exactly match allowed_operations")
    for operation, policy in policies.items():
        if not isinstance(operation, str) or not isinstance(policy, dict) or not isinstance(policy.get("methods"), list) or not policy["methods"] or not isinstance(policy.get("paths"), list) or not policy["paths"]:
            raise RegistryValidationError(f"source {source_id} has invalid policy for {operation}")
        if any(not isinstance(method, str) or method != "GET" for method in policy["methods"]):
            raise RegistryValidationError(f"source {source_id} permits a non-GET method")
        if any(not isinstance(path, str) or not path.startswith("/") or ".." in path.split("/") for path in policy["paths"]):
            raise RegistryValidationError(f"source {source_id} has an unsafe path policy")
    for field in ("retention_policy", "rate_policy"):
        if not isinstance(source[field], dict) or not source[field]:
            raise RegistryValidationError(f"source {source_id} has an empty {field}")
    rate = source["rate_policy"]
    if not isinstance(rate.get("requests_per_minute"), int) or rate["requests_per_minute"] < 1 or not isinstance(rate.get("min_interval_seconds"), (int, float)) or rate["min_interval_seconds"] <= 0:
        raise RegistryValidationError(f"source {source_id} has invalid rate_policy")
    if not isinstance(source["adapter_version"], str) or not source["adapter_version"].strip():
        raise RegistryValidationError(f"source {source_id} has empty adapter_version")

