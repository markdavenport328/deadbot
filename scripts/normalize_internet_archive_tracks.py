#!/usr/bin/env python3
"""Map high-confidence Internet Archive source tracks to canonical performances.

This is deliberately conservative.  A representative item can be linked to a
show because its Archive identifier carries a show date, but a track is linked
to a performance only when its source title has a unique monotonic alignment
with the canonical setlist.  Non-song tracks such as tuning or banter are
retained in the review evidence and are not put into the performance graph.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "recordings"
REVIEW_PATH = RAW_DIR / "internet-archive-track-mapping-review.jsonl"

AUDIO_FORMAT_PRIORITY = (
    "flac",
    "shorten",
    "wave",
    "wav",
    "mpeg audio",
    "ogg vorbis",
)


def normalized_title(value: str) -> str:
    """Normalize source and canonical titles without guessing song identity."""

    value = unicodedata.normalize("NFKD", value or "").casefold()
    value = value.replace("&", " and ").replace("->", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = " ".join(value.split())
    aliases = {
        "dancing in the street": "dancin in the streets",
        "dancing in the streets": "dancin in the streets",
        "dancin in the street": "dancin in the streets",
        "greatest story": "greatest story ever told",
        "playin": "playing in the band",
        "u s blues": "us blues",
    }
    return aliases.get(value, value)


def parse_duration(value: object) -> str:
    """Return an integer number of seconds when the source gives a duration."""

    if value in (None, ""):
        return ""
    text = str(value).strip()
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                return str(round(int(parts[0]) * 60 + float(parts[1])))
            if len(parts) == 3:
                return str(round(int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])))
        return str(round(float(text)))
    except (TypeError, ValueError):
        return ""


def audio_track_files(raw_payload: dict) -> tuple[list[tuple[int, dict]], str]:
    """Choose one original audio file per source track number."""

    grouped: dict[int, list[dict]] = defaultdict(list)
    for file_record in raw_payload.get("files", []):
        if file_record.get("source") != "original" or not file_record.get("track"):
            continue
        format_name = (file_record.get("format") or "").casefold()
        if not any(part in format_name for part in AUDIO_FORMAT_PRIORITY):
            continue
        try:
            track_number = int(str(file_record["track"]).split()[0])
        except (TypeError, ValueError):
            continue
        grouped[track_number].append(file_record)

    if not grouped:
        return [], "no_original_audio_tracks"

    chosen: list[tuple[int, dict]] = []
    for track_number, candidates in sorted(grouped.items()):
        titles = {
            normalized_title(candidate.get("title", ""))
            for candidate in candidates
            if candidate.get("title")
        }
        if len(titles) > 1:
            return [], f"conflicting_titles_for_track_{track_number}"
        candidates.sort(
            key=lambda candidate: next(
                (
                    index
                    for index, format_name in enumerate(AUDIO_FORMAT_PRIORITY)
                    if format_name in (candidate.get("format") or "").casefold()
                ),
                len(AUDIO_FORMAT_PRIORITY),
            )
        )
        chosen.append((track_number, candidates[0]))

    if len({track_number for track_number, _ in chosen}) != len(chosen):
        return [], "duplicate_track_numbers"
    return chosen, ""


def align_tracks(source_tracks: list[tuple[int, dict]], performances: list[dict], songs: dict[str, str]) -> tuple[str, list[tuple[int, int, dict]], str]:
    """Return a unique monotonic alignment or a review status and reason."""

    if not performances:
        return "held", [], "show_has_no_canonical_performances"

    # Each state is the tuple of canonical performance indexes already used.
    # Keeping all states lets us distinguish a real alignment from one that is
    # ambiguous because a repeated song could occupy more than one position.
    states: dict[tuple[int, ...], list[tuple[int, int, dict]]] = {(): []}
    canonical_titles = [normalized_title(songs[row["song_id"]]) for row in performances]

    for track_number, source_file in source_tracks:
        source_title = source_file.get("title", "")
        normalized_source = normalized_title(source_title)
        if not normalized_source:
            return "held", [], f"missing_title_for_track_{track_number}"

        next_states: dict[tuple[int, ...], list[tuple[int, int, dict]]] = {}
        for used_indexes, matches in states.items():
            last_index = used_indexes[-1] if used_indexes else -1
            candidate_indexes = [
                index
                for index in range(last_index + 1, len(performances))
                if canonical_titles[index] == normalized_source
            ]
            if not candidate_indexes:
                # A title that is not in the remaining canonical sequence is
                # treated as banter/tuning/source-only material.  A title that
                # exists in the setlist but occurs before the current alignment
                # is a contradictory order and is held for review.
                if normalized_source in canonical_titles:
                    return "held", [], f"source_order_conflict_at_track_{track_number}"
                next_states[used_indexes] = matches
                continue
            for index in candidate_indexes:
                new_indexes = used_indexes + (index,)
                next_states[new_indexes] = matches + [(track_number, index, source_file)]
        states = next_states
        if not states:
            return "held", [], f"no_monotonic_alignment_at_track_{track_number}"

    aligned = [(indexes, matches) for indexes, matches in states.items() if matches]
    if not aligned:
        return "held", [], "no_source_titles_match_canonical_setlist"
    if len(aligned) > 1:
        return "held", [], f"ambiguous_alignment_{len(aligned)}_ways"
    _, matches = aligned[0]
    status = "accepted_full" if len(matches) == len(performances) else "accepted_partial"
    return status, matches, ""


def load_rows() -> tuple[dict[str, str], dict[str, dict], dict[str, list[dict]], list[dict]]:
    with (CANONICAL / "songs.csv").open(newline="", encoding="utf-8") as handle:
        songs = {row["song_id"]: row["title"] for row in csv.DictReader(handle)}
    with (CANONICAL / "recordings.csv").open(newline="", encoding="utf-8") as handle:
        recordings = {row["archive_identifier"]: row for row in csv.DictReader(handle)}
    performances: dict[str, list[dict]] = defaultdict(list)
    with (CANONICAL / "performances.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            performances[row["show_id"]].append(row)
    for rows in performances.values():
        rows.sort(key=lambda row: (int(row["set_number"] or 0), int(row["position_in_set"] or 0)))
    with (CANONICAL / "performance_recordings.csv").open(newline="", encoding="utf-8") as handle:
        existing = list(csv.DictReader(handle))
    return songs, recordings, performances, existing


def main() -> None:
    songs, recordings, performances, existing = load_rows()
    fields = [
        "performance_id",
        "recording_id",
        "track_number",
        "start_seconds",
        "duration_seconds",
        "track_title",
        "notes",
    ]
    existing_keys = {
        (row["performance_id"], row["recording_id"], row["track_number"])
        for row in existing
    }
    additions: list[dict] = []
    review: list[dict] = []
    status_counts: dict[str, int] = defaultdict(int)

    for raw_path in sorted(RAW_DIR.glob("internet-archive-*-representatives.jsonl")):
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            source_record_id = record["source_record_id"]
            recording = recordings.get(source_record_id)
            if not recording:
                continue
            source_tracks, track_error = audio_track_files(record["raw_payload"])
            if track_error:
                status, matches, reason = "held", [], track_error
            else:
                status, matches, reason = align_tracks(
                    source_tracks,
                    performances.get(recording["show_id"], []),
                    songs,
                )
            status_counts[status] += 1
            matched_track_numbers = {track_number for track_number, _, _ in matches}
            review.append(
                {
                    "source": "internet-archive",
                    "source_record_id": source_record_id,
                    "show_id": recording["show_id"],
                    "status": status,
                    "reason": reason,
                    "matched_track_count": len(matches),
                    "source_track_count": len(source_tracks),
                    "source_tracks": [
                        {
                            "track_number": track_number,
                            "title": source_file.get("title", ""),
                            "duration": source_file.get("length", ""),
                        }
                        for track_number, source_file in source_tracks
                    ],
                    "representative_source_url": record.get("source_url", ""),
                    "retrieved_at": record.get("retrieved_at", ""),
                }
            )
            if not status.startswith("accepted"):
                continue
            for track_number, performance_index, source_file in matches:
                performance = performances[recording["show_id"]][performance_index]
                key = (performance["performance_id"], recording["recording_id"], str(track_number))
                if key in existing_keys:
                    continue
                additions.append(
                    {
                        "performance_id": performance["performance_id"],
                        "recording_id": recording["recording_id"],
                        "track_number": track_number,
                        "start_seconds": "",
                        "duration_seconds": parse_duration(source_file.get("length")),
                        "track_title": source_file.get("title", ""),
                        "notes": (
                            "Source track title/order uniquely aligned to the canonical setlist; "
                            "duration comes from Internet Archive item metadata; no audio downloaded."
                        ),
                    }
                )
                existing_keys.add(key)

    all_rows = existing + additions
    with (CANONICAL / "performance_recordings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for row in review:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(
        f"Added {len(additions)} track links from {len(review)} representatives; "
        f"statuses: {dict(sorted(status_counts.items()))}. "
        f"Review evidence: {REVIEW_PATH.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
