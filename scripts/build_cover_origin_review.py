#!/usr/bin/env python3
"""Build a human-review queue of candidate cover-song origins.

This does not name an original artist. It sorts every canonical song into a
review candidate (or not) based on writer-credit evidence already collected
in `data/canonical/song_writers.csv`, and writes an editable CSV for a human
to fill in `original_artist`, `evidence_url`, and `decision`.

A writer credit naming nobody in the Grateful Dead's songwriting family is
evidence a song came from outside the band, but it is not proof of who
performed or recorded it first — that stays a review decision backed by
evidence already in this repository (the song's own `notes`, or a cataloged
resource in `resources.csv`), never by recollection of music history.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
OUTPUT = ROOT / "data" / "editorial" / "cover-origin-review.csv"

# The Grateful Dead's songwriting family: performing band members across the
# band's lifetime, plus the two non-performing lyricists who wrote as part of
# the band's own songwriting process (Robert Hunter, John Perry Barlow). A
# writer credit naming any of these is an in-house composition, not a cover.
DEAD_FAMILY_PERSON_IDS = {
    "person-jerry-garcia",
    "person-bob-weir",
    "person-phil-lesh",
    "person-bill-kreutzmann",
    "person-mickey-hart",
    "person-ron-pigpen-mckernan",
    "person-keith-godchaux",
    "person-donna-jean-godchaux",
    "person-brent-mydland",
    "person-vince-welnick",
    "person-tom-constanten",
    "person-bruce-hornsby",
    "person-robert-hunter",
    "person-john-perry-barlow",
}


def read_rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def candidate_covers(
    songs: list[dict],
    writers: list[dict],
    dead_family_person_ids: set[str],
) -> list[dict]:
    """Sort songs into cover candidates for human review.

    A writer credit naming nobody in the Dead family is evidence a song came
    from outside, but it does not name the original artist — that stays a
    review decision.  A song with no writer data is flagged rather than
    assumed either way.
    """

    by_song: dict[str, list[str]] = {}
    for row in writers:
        by_song.setdefault(row["song_id"], []).append(row["person_id"])

    candidates = []
    for song in songs:
        credited = by_song.get(song["song_id"], [])
        if not credited:
            signal = "no_writer_data"
        elif set(credited) & dead_family_person_ids:
            continue
        else:
            signal = "non_family_writer"
        candidates.append(
            {
                "song_id": song["song_id"],
                "title": song["title"],
                "writers": sorted(credited),
                "signal": signal,
            }
        )
    return candidates


def main() -> None:
    songs = read_rows("songs.csv")
    writers = read_rows("song_writers.csv")

    candidates = candidate_covers(songs, writers, DEAD_FAMILY_PERSON_IDS)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "song_id",
                "title",
                "writers",
                "signal",
                "original_artist",
                "evidence_url",
                "decision",
            ]
        )
        for row in sorted(candidates, key=lambda r: r["song_id"]):
            writer.writerow(
                [
                    row["song_id"],
                    row["title"],
                    ";".join(row["writers"]),
                    row["signal"],
                    "",
                    "",
                    "",
                ]
            )

    non_family = sum(1 for c in candidates if c["signal"] == "non_family_writer")
    no_writer = sum(1 for c in candidates if c["signal"] == "no_writer_data")
    print(
        f"Wrote {len(candidates)} candidates to {OUTPUT.relative_to(ROOT)} "
        f"({non_family} non_family_writer, {no_writer} no_writer_data)."
    )


if __name__ == "__main__":
    main()
