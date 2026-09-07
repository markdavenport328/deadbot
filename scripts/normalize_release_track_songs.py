#!/usr/bin/env python3
"""Backfill song_id on release tracks that carry a title but no mapped song.

Input: ``data/canonical/official_release_tracks.csv`` as it stands -- both the
live pass's rows (which name a performance) and the studio pass's rows (which
already resolve a song from the title). Output: the same file, in the same
row order, with ``song_id`` recomputed for every row.

A mapped performance already names a song in ``performances.csv``, so that
wins over a title match: a live track's performance is more specific than its
free-text title. Otherwise the track title is folded and matched against
``songs.csv`` the same way the studio pass does, via the shared
``resolve_song_id``. A title that matches neither stays blank and is logged;
this pass never guesses, and it never trusts a song_id written by an earlier
run of itself or by the studio pass -- the column is recomputed from scratch
every time so a stale or wrong value cannot survive a rerun.

This pass changes only the ``song_id`` column. It does not add, remove, or
reorder rows, and it does not touch any other column, so it cannot disturb
the ownership boundary between the live and studio normalizer passes or the
hand-curated Veneta release.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
TRACKS_CSV = CANONICAL / "official_release_tracks.csv"
REVIEW_PATH = ROOT / "data" / "raw" / "releases" / "release-track-song-review.jsonl"

TRACK_FIELDS = ["release_id", "track_number", "performance_id", "song_id", "track_title", "duration_seconds", "spotify_track_url", "notes"]


def _load_studio_module():
    spec = importlib.util.spec_from_file_location(
        "_normalize_musicbrainz_studio_releases", ROOT / "scripts" / "normalize_musicbrainz_studio_releases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_STUDIO = _load_studio_module()
resolve_song_id = _STUDIO.resolve_song_id


def backfill_song_ids(
    tracks: list[dict],
    songs: dict[str, str],
    performances: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """Give every resolvable release track its canonical song.

    A mapped performance already names the song, so it wins.  Otherwise the
    track title is folded and matched.  An unresolved title stays empty and is
    reported; this pass never guesses.  Every run recomputes the column from
    scratch rather than trusting a prior run.
    """

    rows: list[dict] = []
    held: list[dict] = []
    for track in tracks:
        row = dict(track)
        performance_id = row.get("performance_id", "").strip()
        song_id = performances.get(performance_id) if performance_id else None
        if not song_id:
            song_id = resolve_song_id(row.get("track_title", ""), songs)
        if not song_id and not performance_id:
            held.append({"track_title": row.get("track_title", ""), "reason": "unresolved_title"})
        row["song_id"] = song_id or ""
        rows.append(row)
    return rows, held


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> None:
    songs = _STUDIO.load_songs()
    _, performance_rows = read_csv(CANONICAL / "performances.csv")
    performances = {row["performance_id"]: row["song_id"] for row in performance_rows if row.get("song_id")}

    header, tracks = read_csv(TRACKS_CSV)
    if header != TRACK_FIELDS:
        raise SystemExit("canonical release track CSV header changed; refusing to write")

    rows, held = backfill_song_ids(tracks, songs, performances)
    write_csv(TRACKS_CSV, TRACK_FIELDS, rows)

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for record in held:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    no_performance = [row for row in rows if not row.get("performance_id", "").strip()]
    recovered = [row for row in no_performance if row.get("song_id", "").strip()]
    print(
        json.dumps(
            {
                "tracks": len(rows),
                "with_a_song": sum(1 for row in rows if row.get("song_id", "").strip()),
                "without_a_performance": len(no_performance),
                "recovered_by_title": len(recovered),
                "held": len(held),
                "review_path": str(REVIEW_PATH.relative_to(ROOT)),
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
