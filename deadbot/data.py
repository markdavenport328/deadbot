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
            singular = table[:-1] if table.endswith("s") else table
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

    def resources_for(self, relation_table: str, target_key: str, target_id: str) -> list[dict[str, str]]:
        resource_ids = [row["resource_id"] for row in self.rows(relation_table) if row[target_key] == target_id]
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
            performers.append({**assignment, "person": person})
        return {
            "show": show,
            "venue": venue,
            "performances": performances,
            "performers": performers,
            "resources": self.resources_for("resource_shows", "show_id", show_id),
            "show_links": [row for row in self.rows("show_links") if row["show_id"] == show_id],
            "recordings": [row for row in self.rows("recordings") if row["show_id"] == show_id],
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
