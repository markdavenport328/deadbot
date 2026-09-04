"""Read-only access to the reviewable canonical CSV graph.

CSV is the portable source-of-truth representation. The PostgreSQL adapter
implements this same interface for operational use without changing agent
tools or the model-provider layer.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
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

    def filtered_rows(self, table: str, **criteria: str) -> list[dict[str, str]]:
        """Return rows matching exact field values.

        PostgreSQL implements this as a bounded query; the CSV store preserves
        the same contract with a small in-memory scan.
        """

        return [
            row
            for row in self.rows(table)
            if all(row.get(column, "") == value for column, value in criteria.items())
        ]

    def row_count(self, table: str) -> int:
        """Return a table count without requiring callers to fetch its rows."""

        return len(self.rows(table))

    def coverage_summary(self) -> dict[str, Any]:
        """Return compact catalog-wide counts without exposing full tables."""

        dated_shows = [show for show in self.rows("shows") if show.get("show_date", "")]
        years = sorted({show["show_date"][:4] for show in dated_shows})
        performance_song_ids = {
            performance.get("song_id")
            for performance in self.rows("performances")
            if performance.get("song_id")
        }
        return {
            "dated_show_count": len(dated_shows),
            "performance_count": len(self.rows("performances")),
            "performance_song_count": len(performance_song_ids),
            "first_year": years[0] if years else "",
            "last_year": years[-1] if years else "",
        }

    def search_shows(self, phrases: list[str], limit: int = 20) -> list[dict[str, str]]:
        """Find shows through event and venue text with compact venue labels."""

        needles = [phrase.casefold() for phrase in phrases if phrase.strip()]
        if not needles or limit <= 0:
            return []
        venues = self.by_id.get("venues", {})
        matches = []
        for show in self.rows("shows"):
            venue = venues.get(show.get("venue_id", ""), {})
            searchable = " ".join(
                [
                    show.get("show_id", ""),
                    show.get("show_date", ""),
                    show.get("event_name", ""),
                    show.get("tour_name", ""),
                    venue.get("name", ""),
                    venue.get("city", ""),
                    venue.get("state_region", ""),
                ]
            ).casefold()
            if any(needle in searchable for needle in needles):
                matches.append(
                    {
                        **show,
                        "venue_name": venue.get("name", ""),
                        "venue_city": venue.get("city", ""),
                        "venue_state_region": venue.get("state_region", ""),
                    }
                )
                if len(matches) >= limit:
                    break
        return matches

    def one(self, table: str, entity_id: str) -> dict[str, str] | None:
        return self.by_id.get(table, {}).get(entity_id)

    def rows_in(self, table: str, column: str, values) -> list[dict[str, str]]:
        """Rows whose ``column`` is one of ``values``.

        PostgreSQL implements this as one ``IN`` query; the CSV store scans in
        memory. Block builders use it instead of one ``one()`` call per row.
        """

        wanted = set(values)
        if not wanted:
            return []
        return [row for row in self.rows(table) if row.get(column, "") in wanted]

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

    def show_candidates(self, identifier: str) -> list[dict[str, str]]:
        """Return every show matching an ID, date, or phrase, for disambiguation."""

        direct = self.one("shows", identifier)
        if direct:
            return [direct]
        return self.matching_rows("shows", identifier, ("show_date", "event_name", "tour_name"))

    def resolve_show(self, identifier: str) -> dict[str, str] | None:
        matches = self.show_candidates(identifier)
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
        performance_ids = {row["performance_id"] for row in performances}
        listen_by_performance = self._listen_paths(performance_ids)
        performance_summaries = []
        for row in performances:
            summary = self._performance_summary(row, include_show_id=True)
            listen = listen_by_performance.get(row["performance_id"])
            if listen:
                summary["listen"] = listen
            performance_summaries.append(summary)
        return {
            "song": song,
            "writers": writers,
            "performances": performance_summaries,
            "resources": self.resources_for("resource_songs", "song_id", song_id),
            "arrangements": arrangements,
        }

    def _listen_paths(self, performance_ids: set[str]) -> dict[str, dict[str, str]]:
        """Build a compact per-performance listening path: URLs only.

        An archive track link comes from ``performance_links`` rows tagged as
        an Internet Archive recording track; a release track link comes from
        an ``official_release_tracks`` row for that performance with a
        resolvable streaming URL. When a performance has more than one
        candidate row, the selection is sorted deterministically (by the
        link's own identifying columns, never by source row order) so the
        CSV and PostgreSQL stores agree regardless of how their underlying
        rows happen to be ordered. A performance with neither link is
        omitted entirely rather than carrying empty listening keys.
        """

        archive_candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in self.rows("performance_links"):
            performance_id = row.get("performance_id", "")
            if performance_id not in performance_ids:
                continue
            if row.get("platform") != "archive" or row.get("link_type") != "recording-track":
                continue
            url = row.get("url", "")
            if url:
                archive_candidates[performance_id].append((row.get("performance_link_id", ""), url))

        release_candidates: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for row in self.rows("official_release_tracks"):
            performance_id = row.get("performance_id", "")
            if performance_id not in performance_ids:
                continue
            url = row.get("spotify_track_url", "")
            if url:
                release_candidates[performance_id].append(
                    (row.get("release_id", ""), row.get("track_number", ""), url)
                )

        listen: dict[str, dict[str, str]] = {}
        for performance_id in performance_ids:
            paths: dict[str, str] = {}
            archive_options = archive_candidates.get(performance_id)
            if archive_options:
                paths["archive_track_url"] = min(archive_options)[1]
            release_options = release_candidates.get(performance_id)
            if release_options:
                paths["release_track_url"] = min(release_options)[2]
            if paths:
                listen[performance_id] = paths
        return listen

    def song_performance_profile(self, song: dict[str, str]) -> dict[str, Any]:
        """Derive bounded performance observations for one song.

        Adjacencies are counted only inside a documented show/set, using the
        stored set and position fields.  This is deliberately a library
        observation, not a claim about the band's complete performance history.
        """
        song_id = song["song_id"]
        performances = [row for row in self.rows("performances") if row.get("song_id") == song_id]
        shows = self.by_id.get("shows", {})
        songs = self.by_id.get("songs", {})

        def order_key(row: dict[str, str]) -> tuple[str, int, int, str]:
            def number(value: str, missing: int = 10**9) -> int:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return missing
            show = shows.get(row.get("show_id", ""), {})
            return (
                show.get("show_date", "9999-99-99") or "9999-99-99",
                number(row.get("set_number", "")),
                number(row.get("position_in_set", "")),
                row.get("performance_id", ""),
            )

        dated = sorted(performances, key=order_key)

        def endpoint(row: dict[str, str] | None) -> dict[str, str] | None:
            if not row:
                return None
            show = shows.get(row.get("show_id", ""), {})
            return {
                "performance_id": row.get("performance_id", ""),
                "show_id": row.get("show_id", ""),
                "show_date": show.get("show_date", ""),
                "set_number": row.get("set_number", ""),
                "position_in_set": row.get("position_in_set", ""),
            }

        predecessor_counts: Counter[str] = Counter()
        successor_counts: Counter[str] = Counter()
        predecessor_denominator = successor_denominator = 0
        by_show: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.rows("performances"):
            by_show[row.get("show_id", "")].append(row)
        for rows in by_show.values():
            # A transition never crosses a set boundary. Missing positions are
            # retained deterministically but are not treated as adjacent.
            rows.sort(key=lambda row: (
                int(row["set_number"]) if row.get("set_number", "").isdigit() else 10**9,
                int(row["position_in_set"]) if row.get("position_in_set", "").isdigit() else 10**9,
                row.get("performance_id", ""),
            ))
            for index, row in enumerate(rows):
                if row.get("song_id") != song_id:
                    continue
                set_number = row.get("set_number", "")
                if index > 0 and rows[index - 1].get("set_number", "") == set_number:
                    predecessor_denominator += 1
                    predecessor_counts[rows[index - 1].get("song_id", "")] += 1
                if index + 1 < len(rows) and rows[index + 1].get("set_number", "") == set_number:
                    successor_denominator += 1
                    successor_counts[rows[index + 1].get("song_id", "")] += 1

        def neighbors(counts: Counter[str]) -> list[dict[str, Any]]:
            if not counts:
                return []
            highest = max(counts.values())
            return [
                {"song_id": neighbor_id, "title": songs.get(neighbor_id, {}).get("title", ""), "count": count}
                for neighbor_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                if count == highest
            ]

        coverage = self.coverage_summary()
        return {
            "song": song,
            "known_performance_count": len(performances),
            "first_known_performance": endpoint(dated[0] if dated else None),
            "last_known_performance": endpoint(dated[-1] if dated else None),
            "immediate_predecessors": neighbors(predecessor_counts),
            "immediate_successors": neighbors(successor_counts),
            "predecessor_denominator": predecessor_denominator,
            "successor_denominator": successor_denominator,
            "coverage": {
                "scope": "current canonical library",
                "documented_performance_count": coverage["performance_count"],
                "documented_show_count": coverage["dated_show_count"],
                "first_documented_year": coverage["first_year"],
                "last_documented_year": coverage["last_year"],
                "limitations": (
                    "Counts, endpoints, and neighboring songs describe only performances and set order "
                    "documented in this library; they are not band-history-complete and do not identify a best version."
                ),
            },
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

    def _performance_summary(self, row: dict[str, str], include_show_id: bool = False) -> dict[str, str]:
        """Project a performance row to the fields a model answer needs.

        Row provenance (source_key, source_record_id, notes) stays in the
        canonical CSV; sending it with every row would crowd the local-model
        context window without grounding any visitor-facing claim.
        """

        summary = {
            "performance_id": row["performance_id"],
            "song_id": row["song_id"],
            "set_number": row.get("set_number", ""),
            "set_label": row.get("set_label", ""),
            "position_in_set": row.get("position_in_set", ""),
            "encore": row.get("encore", ""),
            "segue_into_next": row.get("segue_into_next", ""),
        }
        if include_show_id:
            summary["show_id"] = row.get("show_id", "")
        return summary

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
        show_summary = {
            key: show.get(key, "")
            for key in ("show_id", "show_date", "venue_id", "tour_name", "event_name")
        }
        # An empty setlist can mean two different things. When the source record
        # itself had no setlist, say so, so a gap answer can attribute the limit
        # to source coverage rather than to this library's collection state.
        if "no setlist entries" in show.get("notes", ""):
            show_summary["setlist_note"] = "The source record for this show contains no setlist entries."
        return {
            "show": show_summary,
            "venue": venue,
            "performances": [self._performance_summary(row) for row in performances],
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
