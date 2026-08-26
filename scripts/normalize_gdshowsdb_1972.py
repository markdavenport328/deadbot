#!/usr/bin/env python3
"""Normalize a pinned gdshowsdb year raw record into canonical CSV files.

This pass is intentionally limited to the facts supplied by gdshowsdb:
shows, venues, songs, ordered performances, and segue flags. Existing rows
are retained where they contain richer Veneta-specific review or provenance
notes.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"


def slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def parse_source_date(source_date: str) -> tuple[str, str]:
    """Return an ISO date and optional same-day source sequence."""
    parts = source_date.split("/")
    if len(parts) not in {3, 4} or not all(part.isdigit() for part in parts):
        raise ValueError(f"unsupported gdshowsdb show key: {source_date!r}")
    date = "-".join(parts[:3])
    sequence = parts[3] if len(parts) == 4 else ""
    return date, sequence


def append_note(value: str, addition: str) -> str:
    if addition in value:
        return value
    return f"{value}; {addition}" if value else addition


def read_csv(name: str) -> tuple[list[str], list[dict[str, str]]]:
    path = CANONICAL / name
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(name: str, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path = CANONICAL / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_source(path: Path) -> tuple[dict, dict]:
    record = json.loads(path.read_text(encoding="utf-8"))
    payload = record["raw_payload"]
    source = yaml.safe_load(base64.b64decode(payload["content"]).decode("utf-8"))
    return record, source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "year",
        type=int,
        nargs="?",
        default=1972,
        help="four-digit year represented by the raw snapshot (default: 1972)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="raw JSONL snapshot (defaults to data/raw/shows/gdshowsdb-<year>.jsonl)",
    )
    args = parser.parse_args()
    if args.year < 1965 or args.year > 1995:
        parser.error("year must be between 1965 and 1995")
    input_path = args.input or ROOT / "data" / "raw" / "shows" / f"gdshowsdb-{args.year}.jsonl"

    source_record, source_shows = load_source(input_path)
    source_id = source_record["source_record_id"]

    venue_fields, existing_venues = read_csv("venues.csv")
    song_fields, existing_songs = read_csv("songs.csv")
    show_fields, existing_shows = read_csv("shows.csv")
    performance_fields, existing_performances = read_csv("performances.csv")

    existing_venue_by_key = {
        (row["name"].casefold(), row["city"].casefold()): row for row in existing_venues
    }
    existing_song_by_key = {row["title"].casefold(): row for row in existing_songs}
    existing_show_by_id = {row["show_id"]: row for row in existing_shows}
    existing_performance_by_id = {
        row["performance_id"]: row for row in existing_performances
    }

    venues: dict[str, dict[str, str]] = {
        row["venue_id"]: row for row in existing_venues
    }
    songs: dict[str, dict[str, str]] = {row["song_id"]: row for row in existing_songs}
    shows: dict[str, dict[str, str]] = {row["show_id"]: row for row in existing_shows}
    performances: dict[str, dict[str, str]] = dict(existing_performance_by_id)

    for source_date, show in source_shows.items():
        date, sequence = parse_source_date(source_date)
        city = show.get(":city") or ""
        state = show.get(":state") or ""
        country = show.get(":country") or ""
        venue_name = show.get(":venue") or ""
        venue_key = (venue_name.casefold(), city.casefold())
        existing_venue = existing_venue_by_key.get(venue_key)
        venue_id = existing_venue["venue_id"] if existing_venue else f"venue-{slugify(venue_name)}-{slugify(city)}"
        venues.setdefault(
            venue_id,
            {
                "venue_id": venue_id,
                "name": venue_name,
                "city": city,
                "state_region": state,
                "country": country,
                "latitude": "",
                "longitude": "",
                "notes": f"Normalized from gdshowsdb {args.year} bulk baseline.",
            },
        )

        show_id = f"gd-{date}{f'-{sequence}' if sequence else ''}"
        existing_show = existing_show_by_id.get(show_id)
        if existing_show:
            existing_show["show_date"] = date
            existing_show["venue_id"] = venue_id
            shows[show_id] = existing_show
        else:
            shows[show_id] = {
                "show_id": show_id,
                "show_date": date,
                "venue_id": venue_id,
                "tour_name": "",
                "event_name": "",
                "notes": f"Normalized from gdshowsdb show UUID {show[':uuid']} in {source_id}.",
            }

        if not show.get(":sets") or not any(source_set.get(":songs") for source_set in show.get(":sets", [])):
            shows[show_id]["notes"] = append_note(
                shows[show_id]["notes"],
                "Source record contains no setlist entries.",
            )

        for set_number, source_set in enumerate(show.get(":sets", []), start=1):
            for position, source_song in enumerate(source_set.get(":songs", []), start=1):
                title = source_song[":name"]
                existing_song = existing_song_by_key.get(title.casefold())
                song_id = existing_song["song_id"] if existing_song else f"song-{slugify(title)}"
                songs.setdefault(
                    song_id,
                    {
                        "song_id": song_id,
                        "title": title,
                        "slug": slugify(title),
                        "original_artist": "",
                        "first_known_dead_performance": "",
                        "last_known_dead_performance": "",
                        "notes": f"Source label normalized from gdshowsdb {args.year} bulk baseline.",
                    },
                )
                performance_slug = existing_song["slug"] if existing_song else slugify(title)
                performance_id = f"{show_id}-{performance_slug}-{set_number}-{position}"
                if show_id == "gd-1972-08-27":
                    performance_id = f"{show_id}-{performance_slug}"
                existing_performance = existing_performance_by_id.get(performance_id)
                performances[performance_id] = existing_performance or {
                    "performance_id": performance_id,
                    "show_id": show_id,
                    "song_id": song_id,
                    "set_number": str(set_number),
                    "set_label": f"Set {set_number}",
                    "position_in_set": str(position),
                    "encore": "false",
                    "segue_into_next": str(bool(source_song.get(":segued"))).lower(),
                    "performance_notes": (
                        f"Source song UUID {source_song[':uuid']}; source label {title!r}."
                    ),
                }

    write_csv("venues.csv", venue_fields, sorted(venues.values(), key=lambda row: row["venue_id"]))
    write_csv("songs.csv", song_fields, sorted(songs.values(), key=lambda row: row["song_id"]))
    write_csv("shows.csv", show_fields, sorted(shows.values(), key=lambda row: row["show_date"]))
    write_csv(
        "performances.csv",
        performance_fields,
        sorted(
            performances.values(),
            key=lambda row: (
                row["show_id"],
                int(row["set_number"]),
                int(row["position_in_set"]),
            ),
        ),
    )

    print(
        f"Normalized {len(shows)} shows, {len(venues)} venues, {len(songs)} songs, "
        f"and {len(performances)} performances from {source_id}."
    )


if __name__ == "__main__":
    main()
