#!/usr/bin/env python3
"""Normalize compact song-credit and lyric-source metadata for the 1972 set."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "songs"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def key(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = value.replace("feelin'", "feeling").replace("goin'", "going")
    return re.sub(r"[^a-z0-9]+", "", value)


def slug(value: str) -> str:
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def append_note(value: str, addition: str) -> str:
    if addition in value:
        return value
    return f"{value}; {addition}" if value else addition


def remove_note(value: str, unwanted: str) -> str:
    value = value.replace(f"; {unwanted}", "").replace(unwanted, "")
    return value.replace(".;", ";").strip(" ;")


# MusicBrainz exact-title results are useful, but title-only search can surface
# unrelated works. These are the selected result indexes for the few titles
# where the relevant Grateful Dead work is not the first exact match.
MB_RESULT_INDEX = {"Comes A Time": 1}

# Do not canonicalize these title-only matches without a stronger source.
MB_EXCLUDED = {"Caution", "Nobody's Fault But Mine", "Space"}

# The Dead.net page is a good fallback for these titles when MusicBrainz has no
# exact relevant work. Names are kept as source-level facts, not inferred from
# lyric text.
DEADNET_FALLBACKS = {
    "Around And Around": {"lyrics": ["Chuck Berry"], "music": ["Chuck Berry"]},
    "Big Railroad Blues": {"writer": ["Noah Lewis"]},
    "Big River": {"writer": ["Johnny Cash"]},
    "Brokedown Palace": {"lyrics": ["Robert Hunter"], "music": ["Jerry Garcia"]},
    "Brown Eyed Women": {"lyrics": ["Robert Hunter"], "music": ["Jerry Garcia"]},
    "Cryptical Envelopment": {"writer": ["Jerry Garcia"]},
    "El Paso": {"writer": ["Marty Robbins"]},
    "Frozen Logger": {"writer": ["James Stevens"]},
    "He's Gone": {"lyrics": ["Robert Hunter"], "music": ["Jerry Garcia"]},
    "It's All Over Now Baby Blue": {"writer": ["Bob Dylan"]},
    "Jack Straw": {"lyrics": ["Robert Hunter"], "music": ["Bob Weir"]},
    "Morning Dew": {"writer": ["Bonnie Dobson"]},
    "You Win Again": {"writer": ["Hank Williams"]},
    "Weather Report Suite Prelude": {"music": ["Bob Weir"]},
}

# These Dead.net fields are visibly incomplete or conflict with the better
# MusicBrainz match, so they remain source evidence only.
DEADNET_REVIEW = {
    "Big Boss Man",
    "Good Lovin'",
    "Hey Bo Diddley",
    "Mind Left Body Jam",
    "Next Time You See Me",
    "Not Fade Away",
    "Smokestack Lightning",
}


def selected_musicbrainz(song: dict[str, str], record: dict) -> list[dict]:
    title = song["title"]
    if title in MB_EXCLUDED:
        return []
    matches = record["raw_payload"].get("exact_title_matches", [])
    if not matches:
        return []
    index = MB_RESULT_INDEX.get(title, 0)
    if index >= len(matches):
        return []
    selected = matches[index]
    return selected.get("credits", [])


def normalize_credit_name(name: str) -> str | None:
    name = name.strip()
    if not name or name.casefold() in {"traditional", "[traditional]", "grateful dead"}:
        return None
    replacements = {
        "John Barlow": "John Perry Barlow",
        "Goin'": "Going",
        "Chester Burnett (Howlin' Wolf)": "Howlin' Wolf",
    }
    return replacements.get(name, name)


def main() -> None:
    songs = read_csv(CANONICAL / "songs.csv")
    people = read_csv(CANONICAL / "people.csv")
    existing_writers = read_csv(CANONICAL / "song_writers.csv")
    resources = read_csv(CANONICAL / "resources.csv")
    resource_songs = read_csv(CANONICAL / "resource_songs.csv")
    deadnet = {
        row["raw_payload"]["song_id"]: row for row in read_jsonl(RAW / "deadnet-song-credits-1972.jsonl")
    }
    musicbrainz = {
        row["raw_payload"]["song_id"]: row
        for row in read_jsonl(RAW / "musicbrainz-song-works-1972.jsonl")
    }

    people_by_name = {key(row["name"]): row["person_id"] for row in people}
    writer_rows = {
        (row["song_id"], row["person_id"], row["writer_role"]): row for row in existing_writers
    }
    resource_by_url = {row["source_url"]: row["resource_id"] for row in resources}
    relation_keys = {
        (row["resource_id"], row["song_id"], row["relationship_type"]): row for row in resource_songs
    }

    accepted_titles: set[str] = set()
    source_credit_titles: set[str] = set()
    for song in songs:
        title = song["title"]
        # Remove only annotations produced by an earlier run, so a transient
        # failed fetch cannot become permanent canonical evidence.
        for generated in (
            "Dead.net lyric/credit page unresolved in this collection pass",
            "External Dead.net lyric page linked; full lyrics not stored",
            "Song credits normalized from MusicBrainz and/or Dead.net source metadata",
            "Credit evidence retained in raw source records but not canonicalized pending title/source review",
        ):
            song["notes"] = remove_note(song["notes"], generated)
        dead = deadnet[song["song_id"]]["raw_payload"]
        mb_credits = selected_musicbrainz(song, musicbrainz[song["song_id"]])
        credits: list[tuple[str, str, str]] = []
        for credit in mb_credits:
            role = {"composer": "music", "lyricist": "lyrics", "writer": "writer"}.get(credit["role"])
            name = normalize_credit_name(credit["name"])
            if role and name:
                credits.append((name, role, "MusicBrainz exact-title work match."))
        if not credits and title in DEADNET_FALLBACKS:
            for role, names in DEADNET_FALLBACKS[title].items():
                for name in names:
                    credits.append((name, role, "Dead.net song-page credit."))
        if credits:
            accepted_titles.add(title)
            for name, role, note in credits:
                person_key = key(name)
                person_id = people_by_name.get(person_key)
                if person_id is None:
                    person_id = f"person-{slug(name)}"
                    people.append(
                        {
                            "person_id": person_id,
                            "name": name,
                            "birth_date": "",
                            "death_date": "",
                            "notes": "Added from song-credit source; biographical fields not collected in this pass.",
                        }
                    )
                    people_by_name[person_key] = person_id
                writer_rows[(song["song_id"], person_id, role)] = {
                    "song_id": song["song_id"],
                    "person_id": person_id,
                    "writer_role": role,
                    "notes": note,
                }
            source_credit_titles.add(title)

        resolved = dead["attempts"][-1]["status"] == 200
        has_lyrics = bool(dead.get("has_lyrics"))
        if resolved:
            url = f"https://www.dead.net/song/{dead['resolved_slug']}"
            resource_id = resource_by_url.get(url)
            if resource_id is None:
                resource_id = f"resource-deadnet-song-{song['slug']}"
                used_ids = {row["resource_id"] for row in resources}
                if resource_id in used_ids:
                    resource_id += "-page"
                resources.append(
                    {
                        "resource_id": resource_id,
                        "resource_type": "lyrics-and-credits" if has_lyrics else "catalog-song-page",
                        "title": f"{title} — Dead.net song page",
                        "creator": "",
                        "source_name": "Grateful Dead / Dead.net",
                        "source_url": url,
                        "published_date": "",
                        "notes": "Lyrics remain external and are not copied into the repository; page metadata is retained for source linking.",
                    }
                )
                resource_by_url[url] = resource_id
            relationship = "lyrics-source" if has_lyrics else "song-credit-source"
            relation_keys.setdefault(
                (resource_id, song["song_id"], relationship),
                {
                    "resource_id": resource_id,
                    "song_id": song["song_id"],
                    "relationship_type": relationship,
                    "notes": "External lyric/credit page; text not stored." if has_lyrics else "External catalog page; text not stored.",
                },
            )

        if has_lyrics:
            song["notes"] = append_note(song["notes"], "External Dead.net lyric page linked; full lyrics not stored")
        elif not resolved:
            song["notes"] = append_note(song["notes"], "Dead.net lyric/credit page unresolved in this collection pass")
        if title in source_credit_titles:
            song["notes"] = append_note(song["notes"], "Song credits normalized from MusicBrainz and/or Dead.net source metadata")
        elif title in DEADNET_REVIEW or title in {"Caution", "Nobody's Fault But Mine", "Space"}:
            song["notes"] = append_note(song["notes"], "Credit evidence retained in raw source records but not canonicalized pending title/source review")

    write_csv(CANONICAL / "people.csv", people, ["person_id", "name", "birth_date", "death_date", "notes"])
    write_csv(
        CANONICAL / "song_writers.csv",
        sorted(writer_rows.values(), key=lambda row: (row["song_id"], row["writer_role"], row["person_id"])),
        ["song_id", "person_id", "writer_role", "notes"],
    )
    write_csv(
        CANONICAL / "resources.csv",
        resources,
        ["resource_id", "resource_type", "title", "creator", "source_name", "source_url", "published_date", "notes"],
    )
    write_csv(
        CANONICAL / "resource_songs.csv",
        sorted(relation_keys.values(), key=lambda row: (row["song_id"], row["resource_id"], row["relationship_type"])),
        ["resource_id", "song_id", "relationship_type", "notes"],
    )
    write_csv(
        CANONICAL / "songs.csv",
        songs,
        ["song_id", "title", "slug", "original_artist", "first_known_dead_performance", "last_known_dead_performance", "notes"],
    )
    print(
        f"Normalized {len(songs)} songs; {len(source_credit_titles)} have canonical credits, "
        f"{sum(1 for row in deadnet.values() if row['raw_payload']['attempts'][-1]['status'] == 200)} have Dead.net pages, "
        f"and {sum(1 for row in deadnet.values() if row['raw_payload'].get('has_lyrics'))} have linked lyric pages."
    )


if __name__ == "__main__":
    main()
