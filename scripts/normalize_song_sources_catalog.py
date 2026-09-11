#!/usr/bin/env python3
"""Normalize compact song-credit and lyric-source metadata catalog-wide.

Companion to `scripts/normalize_song_sources_1972.py`, which merges the
year-scoped 1970-1972 raw records. This script merges the catalog-wide raw
records collected by `scripts/collect/fetch_deadnet_song_credits.py` and
`scripts/collect/fetch_musicbrainz_song_works.py` (their default,
non-`--year` runs, written to `*-catalog.jsonl`) for every other song in
`data/canonical/songs.csv`.

Follows the same staged title-resolution and conservative credit rules as
docs/collection-methodology.md:

- A MusicBrainz work is promoted only when there is exactly one exact
  title-key match, or every exact match agrees on the same credit set.
  Exact matches that disagree on credits (a shared title across unrelated
  works, e.g. "A Day In the Life") are held for review, never promoted.
- Dead.net's displayed Lyrics By / Music By credit is used as a fallback
  only when MusicBrainz produced no promotable credit.
- `lyricist`/"Lyrics By" -> `lyrics`, `composer`/"Music By" -> `music`,
  `writer` -> `writer`. Traditional and band-level credits ("Traditional",
  "Grateful Dead") are held as source evidence, not turned into people rows.
- `original_artist` is left untouched: neither source in this collection
  pass states an explicit "originally recorded by" fact distinct from a
  writer/composer credit, so nothing is promoted into that field here (see
  docs/collection-status-song-credits-catalog.md).

Idempotent and rerunnable: existing song_writers.csv/people.csv rows are
preserved and only new (song_id, person_id, writer_role) combinations are
added; both outputs are written sorted by their ID columns so a concurrent
agent's appends merge cleanly.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "songs"
DEADNET_RAW = RAW / "deadnet-song-credits-catalog.jsonl"
MUSICBRAINZ_RAW = RAW / "musicbrainz-song-works-catalog.jsonl"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
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


NAME_REPLACEMENTS = {
    "John Barlow": "John Perry Barlow",
    "Goin'": "Going",
    "Chester Burnett (Howlin' Wolf)": "Howlin' Wolf",
}

NON_PERSON_CREDITS = {"traditional", "[traditional]", "grateful dead", "unknown", ""}


def normalize_credit_name(name: str) -> str | None:
    name = name.strip()
    if not name or name.casefold() in NON_PERSON_CREDITS:
        return None
    return NAME_REPLACEMENTS.get(name, name)


def credit_set(work: dict) -> frozenset[tuple[str, str]]:
    """A work's credits as a comparable (role, normalized-name) set."""
    result = set()
    for credit in work.get("credits", []):
        name = normalize_credit_name(credit.get("name", ""))
        if name:
            result.add((credit.get("role", ""), name))
    return frozenset(result)


def selected_musicbrainz(mb_record: dict | None) -> tuple[list[dict], str]:
    """Return (credits, status) for a song's MusicBrainz record.

    status is one of: "ok" (0 or 1 usable exact match), "ambiguous" (more
    than one exact match and they disagree on credits), or "none".
    """
    if mb_record is None:
        return [], "none"
    matches = mb_record["raw_payload"].get("exact_title_matches", [])
    if not matches:
        return [], "none"
    if len(matches) == 1:
        return matches[0].get("credits", []), "ok"
    sets = {credit_set(work) for work in matches}
    sets.discard(frozenset())
    if len(sets) <= 1:
        # Either every match agrees, or only one match has any named credits.
        for work in matches:
            if work.get("credits"):
                return work["credits"], "ok"
        return [], "none"
    return [], "ambiguous"


def deadnet_fallback_credits(dead_payload: dict) -> list[tuple[str, str]]:
    """(name, role) pairs from Dead.net's own Lyrics By / Music By fields."""
    pairs: list[tuple[str, str]] = []
    for name in dead_payload.get("lyrics_by", []):
        pairs.append((name, "lyrics"))
    for name in dead_payload.get("music_by", []):
        pairs.append((name, "music"))
    return pairs


def main() -> None:
    songs = read_csv(CANONICAL / "songs.csv")
    people = read_csv(CANONICAL / "people.csv")
    existing_writers = read_csv(CANONICAL / "song_writers.csv")
    resources = read_csv(CANONICAL / "resources.csv")
    resource_songs = read_csv(CANONICAL / "resource_songs.csv")

    deadnet_by_song = {
        record["raw_payload"]["song_id"]: record for record in read_jsonl(DEADNET_RAW)
    }
    musicbrainz_by_song = {
        record["raw_payload"]["song_id"]: record for record in read_jsonl(MUSICBRAINZ_RAW)
    }

    catalog_song_ids = set(deadnet_by_song) | set(musicbrainz_by_song)

    people_by_name = {key(row["name"]): row["person_id"] for row in people}
    used_person_ids = {row["person_id"] for row in people}
    writer_rows = {
        (row["song_id"], row["person_id"], row["writer_role"]): row for row in existing_writers
    }
    resource_by_url = {row["source_url"]: row["resource_id"] for row in resources}
    used_resource_ids = {row["resource_id"] for row in resources}
    relation_keys = {
        (row["resource_id"], row["song_id"], row["relationship_type"]): row for row in resource_songs
    }

    requested = 0
    dn_successful = 0
    mb_successful = 0
    dn_error = 0
    mb_error = 0
    mb_exact = 0
    promoted_titles: set[str] = set()
    held_reasons: dict[str, int] = {}

    def hold(reason: str) -> None:
        held_reasons[reason] = held_reasons.get(reason, 0) + 1

    for song in songs:
        song_id = song["song_id"]
        if song_id not in catalog_song_ids:
            continue
        requested += 1
        title = song["title"]

        for generated in (
            "Dead.net lyric/credit page unresolved in this collection pass",
            "External Dead.net lyric page linked; full lyrics not stored",
            "Song credits normalized from MusicBrainz and/or Dead.net source metadata",
            "Credit evidence retained in raw source records but not canonicalized pending title/source review",
        ):
            song["notes"] = remove_note(song["notes"], generated)

        dead_record = deadnet_by_song.get(song_id)
        mb_record = musicbrainz_by_song.get(song_id)
        dead = dead_record["raw_payload"] if dead_record else {"attempts": [{"status": 0}]}

        dn_status = dead["attempts"][-1]["status"] if dead.get("attempts") else 0
        if dn_status == 200:
            dn_successful += 1
        elif dead_record is not None:
            dn_error += 1

        mb_status = mb_record["raw_payload"].get("http_status", 0) if mb_record else 0
        if mb_status == 200:
            mb_successful += 1
        elif mb_record is not None:
            mb_error += 1
        if mb_record and mb_record["raw_payload"].get("exact_title_matches"):
            mb_exact += 1

        mb_credits, mb_state = selected_musicbrainz(mb_record)
        mb_matches_exist = bool(mb_record and mb_record["raw_payload"].get("exact_title_matches"))

        credits: list[tuple[str, str, str]] = []
        for credit in mb_credits:
            role = {"composer": "music", "lyricist": "lyrics", "writer": "writer"}.get(credit["role"])
            name = normalize_credit_name(credit["name"])
            if role and name:
                credits.append((name, role, "MusicBrainz exact-title work match."))
        mb_only_traditional_or_unmapped = bool(mb_credits) and not credits

        dn_fallback_attempted = not credits and dn_status == 200 and bool(dead.get("has_credits"))
        dn_only_traditional = False
        if dn_fallback_attempted:
            dn_pairs = deadnet_fallback_credits(dead)
            dn_named: list[tuple[str, str, str]] = []
            for name, role in dn_pairs:
                normalized = normalize_credit_name(name)
                if normalized:
                    dn_named.append((normalized, role, "Dead.net song-page credit."))
            credits.extend(dn_named)
            dn_only_traditional = bool(dn_pairs) and not dn_named

        if credits:
            promoted_titles.add(title)
            for name, role, note in credits:
                person_key = key(name)
                person_id = people_by_name.get(person_key)
                if person_id is None:
                    person_id = f"person-{slug(name)}"
                    while person_id in used_person_ids:
                        person_id += "-2"
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
                    used_person_ids.add(person_id)
                writer_rows[(song_id, person_id, role)] = {
                    "song_id": song_id,
                    "person_id": person_id,
                    "writer_role": role,
                    "notes": note,
                }
        elif mb_state == "ambiguous":
            hold("ambiguous_musicbrainz_matches")
        elif mb_only_traditional_or_unmapped or dn_only_traditional:
            hold("traditional_or_band_credit_only")
        elif dn_status != 200 and not mb_matches_exist:
            hold("no_deadnet_page_and_no_musicbrainz_exact_match")
        elif dn_status != 200:
            hold("no_deadnet_page")
        else:
            hold("no_named_credit_in_either_source")

        # Dead.net resource/relationship bookkeeping, matching the 1970-1972
        # normalizer's convention.
        resolved = dn_status == 200
        has_lyrics = bool(dead.get("has_lyrics"))
        if resolved:
            url = f"https://www.dead.net/song/{dead['resolved_slug']}"
            resource_id = resource_by_url.get(url)
            if resource_id is None:
                resource_id = f"resource-deadnet-song-{song['slug']}"
                if resource_id in used_resource_ids:
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
                used_resource_ids.add(resource_id)
            relationship = "lyrics-source" if has_lyrics else "song-credit-source"
            relation_keys.setdefault(
                (resource_id, song_id, relationship),
                {
                    "resource_id": resource_id,
                    "song_id": song_id,
                    "relationship_type": relationship,
                    "notes": "External lyric/credit page; text not stored." if has_lyrics else "External catalog page; text not stored.",
                },
            )

        mb_url = mb_record["source_url"] if mb_record else ""
        if mb_url:
            resource_id = resource_by_url.get(mb_url)
            if resource_id is None:
                resource_id = f"resource-musicbrainz-work-search-{song['slug']}"
                if resource_id in used_resource_ids:
                    resource_id += "-query"
                resources.append(
                    {
                        "resource_id": resource_id,
                        "resource_type": "catalog-work-search",
                        "title": f"{title} — MusicBrainz work search",
                        "creator": "",
                        "source_name": "MusicBrainz",
                        "source_url": mb_url,
                        "published_date": "",
                        "notes": "Work-search evidence retained for composition-credit review; exact-title candidates may be ambiguous and are not automatically canonical.",
                    }
                )
                resource_by_url[mb_url] = resource_id
                used_resource_ids.add(resource_id)
            relation_keys.setdefault(
                (resource_id, song_id, "composition-credit-source"),
                {
                    "resource_id": resource_id,
                    "song_id": song_id,
                    "relationship_type": "composition-credit-source",
                    "notes": (
                        "Accepted credit evidence; see canonical role rows."
                        if credits and any(n[2].startswith("MusicBrainz") for n in credits)
                        else "Candidate work search retained for review; no canonical credit promoted."
                    ),
                },
            )

        if has_lyrics:
            song["notes"] = append_note(song["notes"], "External Dead.net lyric page linked; full lyrics not stored")
        elif not resolved:
            song["notes"] = append_note(song["notes"], "Dead.net lyric/credit page unresolved in this collection pass")
        if title in promoted_titles:
            song["notes"] = append_note(song["notes"], "Song credits normalized from MusicBrainz and/or Dead.net source metadata")
        elif mb_state == "ambiguous":
            song["notes"] = append_note(song["notes"], "Credit evidence retained in raw source records but not canonicalized pending title/source review")

    people.sort(key=lambda row: row["person_id"])
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

    print(f"Requested {requested} catalog songs (Dead.net + MusicBrainz raw records found).")
    print(f"Dead.net: {dn_successful} successful, {dn_error} error.")
    print(f"MusicBrainz: {mb_successful} successful, {mb_error} error, {mb_exact} with an exact title match.")
    print(f"Promoted credits for {len(promoted_titles)} songs.")
    print(f"Held: {held_reasons}")


if __name__ == "__main__":
    main()
