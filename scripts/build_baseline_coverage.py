#!/usr/bin/env python3
"""Materialize canonical-spine coverage without hiding missing relationships."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
OUTPUT = ROOT / "data" / "coverage" / "canonical-spine-baseline.json"


def rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def ids(rows_: list[dict[str, str]], key: str) -> set[str]:
    return {row[key] for row in rows_}


def by_year(
    shows: list[dict[str, str]], performances: list[dict[str, str]],
    assignments: list[dict[str, str]],
) -> list[dict[str, int]]:
    performance_show_ids = {row["show_id"] for row in performances}
    assignment_show_ids = {row["show_id"] for row in assignments}
    performance_counts: dict[str, int] = defaultdict(int)
    assignment_counts: dict[str, int] = defaultdict(int)
    for row in performances:
        performance_counts[row["show_id"]] += 1
    for row in assignments:
        assignment_counts[row["show_id"]] += 1
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for show in shows:
        grouped[int(show["show_date"][:4])].append(show)
    result = []
    for year, year_shows in sorted(grouped.items()):
        show_ids = {show["show_id"] for show in year_shows}
        result.append({
            "year": year,
            "show_count": len(show_ids),
            "performance_count": sum(performance_counts[show_id] for show_id in show_ids),
            "shows_with_performances": len(show_ids & performance_show_ids),
            "shows_without_performances": len(show_ids - performance_show_ids),
            "performer_assignment_count": sum(assignment_counts[show_id] for show_id in show_ids),
            "shows_with_performer_assignments": len(show_ids & assignment_show_ids),
            "shows_without_performer_assignments": len(show_ids - assignment_show_ids),
        })
    return result


def document() -> dict[str, object]:
    shows = rows("shows.csv")
    songs = rows("songs.csv")
    performances = rows("performances.csv")
    people = rows("people.csv")
    assignments = rows("show_performers.csv")
    show_ids = ids(shows, "show_id")
    song_ids = ids(songs, "song_id")
    person_ids = ids(people, "person_id")
    performance_show_ids = {row["show_id"] for row in performances}
    performance_song_ids = {row["song_id"] for row in performances}
    assigned_show_ids = {row["show_id"] for row in assignments}
    assigned_person_ids = {row["person_id"] for row in assignments}

    missing_setlists = sorted(show_ids - performance_show_ids)
    missing_performers = sorted(show_ids - assigned_show_ids)
    return {
        "schema_version": 1,
        "kind": "canonical_spine_baseline",
        "status": "partial_relationship_coverage",
        "purpose": (
            "A generated coverage baseline for the canonical entity spine. It "
            "distinguishes valid, connected records from missing relationship "
            "coverage; it does not infer an absent setlist or performer credit."
        ),
        "scope": {
            "show_year_start": min(int(row["show_date"][:4]) for row in shows),
            "show_year_end": max(int(row["show_date"][:4]) for row in shows),
        },
        "entity_counts": {
            "shows": len(shows),
            "songs": len(songs),
            "performances": len(performances),
            "people": len(people),
            "people_with_show_assignments": len(assigned_person_ids),
            "show_performer_assignments": len(assignments),
        },
        "relationship_integrity": {
            "performances_with_missing_show": len({row["show_id"] for row in performances} - show_ids),
            "performances_with_missing_song": len({row["song_id"] for row in performances} - song_ids),
            "show_performer_assignments_with_missing_show": len({row["show_id"] for row in assignments} - show_ids),
            "show_performer_assignments_with_missing_person": len({row["person_id"] for row in assignments} - person_ids),
        },
        "coverage": {
            "shows_with_performances": len(performance_show_ids),
            "shows_without_performances": len(missing_setlists),
            "songs_with_performances": len(performance_song_ids),
            "songs_without_performances": len(song_ids - performance_song_ids),
            "shows_with_performer_assignments": len(assigned_show_ids),
            "shows_without_performer_assignments": len(missing_performers),
            "people_with_show_assignments": len(assigned_person_ids),
            "people_without_show_assignments": len(person_ids - assigned_person_ids),
        },
        "gaps": {
            "shows_without_performances": missing_setlists,
            "shows_without_performer_assignments": missing_performers,
            "note": (
                "People without show assignments are not automatically data gaps: "
                "the people table also holds songwriters and other relationship "
                "subjects. Treat only a supported show-person relationship as a performer credit."
            ),
        },
        "coverage_by_year": by_year(shows, performances, assignments),
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote canonical spine baseline to {OUTPUT}")


if __name__ == "__main__":
    main()
