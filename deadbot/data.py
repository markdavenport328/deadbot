"""Read-only access to the canonical CSV graph.

The harness intentionally reads from the reviewable canonical files during the
pilot. Replacing this with PostgreSQL later changes only this store interface,
not the agent's tools or model-provider layer.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass
class CanonicalStore:
    """A small in-memory projection of the canonical CSV relationships."""

    canonical_dir: Path = field(default_factory=lambda: repository_root() / "data" / "canonical")

    @cached_property
    def tables(self) -> dict[str, list[dict[str, str]]]:
        tables: dict[str, list[dict[str, str]]] = {}
        for path in self.canonical_dir.glob("*.csv"):
            with path.open(newline="", encoding="utf-8") as source:
                tables[path.stem] = list(csv.DictReader(source))
        return tables

    @cached_property
    def by_id(self) -> dict[str, dict[str, dict[str, str]]]:
        result: dict[str, dict[str, dict[str, str]]] = {}
        for table, rows in self.tables.items():
            singular = {"people": "person"}.get(table, table[:-1] if table.endswith("s") else table)
            id_column = f"{singular}_id"
            if rows and id_column in rows[0]:
                result[table] = {row[id_column]: row for row in rows}
        return result

    def rows(self, table: str) -> list[dict[str, str]]:
        return self.tables.get(table, [])

    def one(self, table: str, entity_id: str) -> dict[str, str] | None:
        return self.by_id.get(table, {}).get(entity_id)

    def matching_rows(self, table: str, query: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
        needle = query.casefold().strip()
        if not needle:
            return []
        exact = [
            row for row in self.rows(table)
            if any(row.get(field, "").casefold() == needle for field in fields)
        ]
        if exact:
            return exact
        return [
            row for row in self.rows(table)
            if any(needle in row.get(field, "").casefold() for field in fields)
        ]

    def resolve_song(self, identifier: str) -> dict[str, str] | None:
        direct = self.one("songs", identifier)
        if direct:
            return direct
        matches = self.matching_rows("songs", identifier, ("title", "slug"))
        return matches[0] if len(matches) == 1 else None

    def resolve_show(self, identifier: str) -> dict[str, str] | None:
        direct = self.one("shows", identifier)
        if direct:
            return direct
        matches = self.matching_rows("shows", identifier, ("show_date", "event_name", "tour_name"))
        return matches[0] if len(matches) == 1 else None

    def resolve_equipment(self, identifier: str) -> dict[str, str] | None:
        direct = self.one("equipment", identifier)
        if direct:
            return direct
        matches = self.matching_rows("equipment", identifier, ("name", "manufacturer", "model"))
        return matches[0] if len(matches) == 1 else None

    def resources_for(self, relation_table: str, target_key: str, target_id: str) -> list[dict[str, str]]:
        resource_ids = list(dict.fromkeys(
            row["resource_id"] for row in self.rows(relation_table) if row[target_key] == target_id
        ))
        resources = self.by_id.get("resources", {})
        relationships = [row for row in self.rows(relation_table) if row[target_key] == target_id]
        relationship_by_resource = defaultdict(list)
        for relationship in relationships:
            relationship_by_resource[relationship["resource_id"]].append(relationship)
        result = []
        for resource_id in resource_ids:
            resource = resources.get(resource_id)
            if resource:
                result.append({**resource, "relationships": relationship_by_resource[resource_id]})
        return result

    def official_release_summaries(self, release_ids: set[str]) -> list[dict[str, str]]:
        """Return the small display subset needed by retrieval and the UI."""

        return [
            {
                "release_id": row["release_id"],
                "title": row["title"],
                "spotify_album_url": row.get("spotify_album_url", ""),
            }
            for row in self.rows("official_releases")
            if row["release_id"] in release_ids
        ]

    def song_context(self, song: dict[str, str]) -> dict[str, Any]:
        song_id = song["song_id"]
        writers = [row for row in self.rows("song_writers") if row["song_id"] == song_id]
        performances = [row for row in self.rows("performances") if row["song_id"] == song_id]
        arrangements = [row for row in self.rows("song_arrangements") if row["song_id"] == song_id]
        return {
            "song": song,
            "writers": writers,
            "performances": performances,
            "resources": self.resources_for("resource_songs", "song_id", song_id),
            "arrangements": arrangements,
        }

    def arrangement_search(self, key_signature: str) -> dict[str, Any]:
        """Find only source-documented arrangements in the requested key."""

        normalized_key = key_signature.strip()
        arrangements = [
            row
            for row in self.rows("song_arrangements")
            if row.get("key_signature", "").casefold() == normalized_key.casefold()
        ]
        return {
            "arrangement_search": {
                "key_signature": normalized_key,
                "match_count": len(arrangements),
                "coverage_note": (
                    "Results include only arrangements documented in the current library. "
                    "They do not establish a universal key for a song or cover undocumented transpositions."
                ),
            },
            "arrangements": arrangements,
        }

    def equipment_history(self, equipment: dict[str, str]) -> dict[str, Any]:
        """Return source-dated show assignments for one named instrument."""

        equipment_id = equipment["equipment_id"]
        venues = self.by_id.get("venues", {})
        shows = self.by_id.get("shows", {})
        assignments = []
        for row in self.rows("show_equipment"):
            if row.get("equipment_id") != equipment_id:
                continue
            show = shows.get(row.get("show_id", ""))
            if not show:
                continue
            venue = venues.get(show.get("venue_id", ""), {})
            assignments.append({**row, "show": show, "venue": venue})
        assignments.sort(key=lambda item: item["show"].get("show_date", "9999-99-99"))

        def show_summary(assignment: dict[str, Any] | None) -> dict[str, str] | None:
            if not assignment:
                return None
            show = assignment["show"]
            venue = assignment["venue"]
            return {
                "show_id": show["show_id"],
                "show_date": show.get("show_date", ""),
                "venue_name": venue.get("name", ""),
                "city": venue.get("city", ""),
                "state_region": venue.get("state_region", ""),
                "usage_context": assignment.get("usage_context", ""),
                "claim_type": assignment.get("claim_type", ""),
                "source_id": assignment.get("source_id", ""),
                "source_url": assignment.get("source_url", ""),
                "source_note": assignment.get("source_note", ""),
            }

        return {
            "equipment": equipment,
            "first_documented_show": show_summary(assignments[0] if assignments else None),
            "last_documented_show": show_summary(assignments[-1] if assignments else None),
            "documented_show_count": len(assignments),
            "coverage_note": (
                "These are source-dated equipment assignments in the current library, "
                "not a complete instrument log for every show."
            ),
        }

    def show_context(self, show: dict[str, str]) -> dict[str, Any]:
        show_id = show["show_id"]
        performances = [row for row in self.rows("performances") if row["show_id"] == show_id]
        performance_ids = {row["performance_id"] for row in performances}
        release_ids = {
            row["release_id"]
            for row in self.rows("official_release_tracks")
            if row.get("performance_id") in performance_ids
        }
        venue = self.one("venues", show["venue_id"])
        people = {row["person_id"]: row for row in self.rows("people")}
        performers = []
        for assignment in self.rows("show_performers"):
            if assignment["show_id"] != show_id:
                continue
            person = people.get(assignment["person_id"])
            # Keep the retrieval packet compact: source provenance lives in the
            # canonical CSV notes and raw snapshot, while the model needs the
            # grounded person, role, and instrument values for show questions.
            performers.append(
                {
                    "person_id": assignment["person_id"],
                    "role": assignment["role"],
                    "instrument": assignment["instrument"],
                    "person": person,
                }
            )
        equipment_by_id = {row["equipment_id"]: row for row in self.rows("equipment")}
        equipment = []
        for assignment in self.rows("show_equipment"):
            if assignment.get("show_id") != show_id:
                continue
            item = equipment_by_id.get(assignment.get("equipment_id", ""))
            if not item:
                continue
            equipment.append(
                {
                    "equipment_id": item["equipment_id"],
                    "name": item["name"],
                    "usage_context": assignment.get("usage_context", ""),
                    "claim_type": assignment.get("claim_type", ""),
                    "source_id": assignment.get("source_id", ""),
                    "source_url": assignment.get("source_url", ""),
                }
            )
        recording_summaries = []
        for recording in self.rows("recordings"):
            if recording["show_id"] != show_id:
                continue
            summary = {
                key: recording[key]
                for key in ("recording_id", "source_type")
                if recording.get(key, "")
            }
            if "search-index" not in recording.get("notes", ""):
                summary["archive_identifier"] = recording["archive_identifier"]
            recording_summaries.append(summary)
        return {
            "show": show,
            "venue": venue,
            "performances": performances,
            "performers": performers,
            "equipment": equipment,
            "resources": self.resources_for("resource_shows", "show_id", show_id),
            "show_links": [row for row in self.rows("show_links") if row["show_id"] == show_id],
            "recordings": recording_summaries,
            "official_releases": self.official_release_summaries(release_ids),
        }

    def performance_context(self, performance_id: str) -> dict[str, Any] | None:
        performance = self.one("performances", performance_id)
        if not performance:
            return None
        release_ids = {
            row["release_id"]
            for row in self.rows("official_release_tracks")
            if row.get("performance_id") == performance_id
        }
        return {
            "performance": performance,
            "song": self.one("songs", performance["song_id"]),
            "show": self.one("shows", performance["show_id"]),
            "resources": self.resources_for("resource_performances", "performance_id", performance_id),
            "links": [row for row in self.rows("performance_links") if row["performance_id"] == performance_id],
            "recordings": [row for row in self.rows("performance_recordings") if row["performance_id"] == performance_id],
            "official_releases": self.official_release_summaries(release_ids),
        }
