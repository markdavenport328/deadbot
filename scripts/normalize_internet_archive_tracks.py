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
# Full item metadata for further recordings of shows whose representative item
# could not be aligned (collect/fetch_internet_archive_alternates.py).
ALTERNATES_PATH = RAW_DIR / "internet-archive-alternate-items.jsonl"
FALLBACK_NOTE = (
    "Source track titles aligned to the canonical setlist track by track after removing file-name "
    "prefixes, segue marks and annotations; out-of-order, ambiguous, untitled and combined tracks were "
    "left unlinked; duration comes from Internet Archive item metadata; no audio downloaded."
)


def representative_rank(identifier: str) -> tuple[bool, bool, str]:
    """The representative-item preference: soundboard, then audience, then identifier."""

    folded = identifier.casefold()
    return (".sbd." not in folded, ".aud." not in folded, identifier)


def read_item_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


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
    # Some Archive sources prefix every title with its source-track number
    # ("14 Franklin's Tower"). The number describes the file, not the song.
    value = re.sub(r"^\d+\s+", "", value)
    value = " ".join(value.split())
    aliases = {
        "dancing in the street": "dancin in the streets",
        "dancing in the streets": "dancin in the streets",
        "dancin in the street": "dancin in the streets",
        "greatest story": "greatest story ever told",
        "franklins tower": "franklin s tower",
        "new minglewood blues": "minglewood blues",
        "playin": "playing in the band",
        "u s blues": "us blues",
    }
    return aliases.get(value, value)


def parse_duration(value: object) -> str:
    """Return an integer number of seconds when the source gives a duration.

    A zero or blank length means the source did not measure the file, so it
    is returned as unknown rather than as a zero-second track.
    """

    if value in (None, ""):
        return ""
    text = str(value).strip()
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                seconds = round(int(parts[0]) * 60 + float(parts[1]))
            elif len(parts) == 3:
                seconds = round(int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
            else:
                return ""
        else:
            seconds = round(float(text))
    except (TypeError, ValueError):
        return ""
    return str(seconds) if seconds > 0 else ""


# ---------------------------------------------------------------------------
# Tolerant fallback alignment
#
# The strict aligner above holds a whole item as soon as one title is
# missing, one track is out of setlist order, or a repeated song could sit in
# two places.  For items it holds, the fallback below keeps the same
# principle -- a track is linked only when its title names the canonical
# song -- but decides track by track:
#
# * source titles are compared after removing file-name prefixes
#   ("gd66-07-03 t01 ...", "d1t03 ..."), segue markers and parenthetical
#   annotations, and after folding documented alternate titles;
# * untitled, non-setlist (tuning, banter, crowd) and combined tracks
#   ("Dark Star > St. Stephen") are skipped, never split;
# * the accepted links are those present in *every* longest in-order
#   alignment between the titled tracks and the setlist.  A track that is out
#   of order, or a repeated song whose position is not settled by its
#   neighbours, is left unlinked with a logged reason;
# * an item whose song-titled tracks mostly do not align is held as not
#   evidently this show.
# ---------------------------------------------------------------------------

PARENTHETICAL = re.compile(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]")
COMBINED_SEPARATOR = re.compile(r"\s*(?:->|-\s*>|>|/|→|\+)\s*")
PREFIX_TOKEN = re.compile(r"^(?:gd\d{2,4}|\d{1,4}|[ds]\d{1,2}|t\d{1,3}|[ds]\d{1,2}t\d{1,3}|cd\d{1,2}|disc|disk|set|track)$")
MIN_ALIGNED_SHARE = 0.5


def _extra_aliases() -> dict[str, str]:
    # The official-release normalizer keeps the broader table of documented
    # alternate titles ("St. Stephen", "Turn On Your Love Light", ...).
    from normalize_musicbrainz_live_releases import TITLE_ALIASES

    return dict(TITLE_ALIASES)


_ALIASES: dict[str, str] | None = None


def _fold(value: str) -> str:
    """Fold a normalized title so spelling-only variants compare equal."""

    global _ALIASES
    if _ALIASES is None:
        _ALIASES = _extra_aliases()
    value = _ALIASES.get(value, value)
    value = re.sub(r"^the ", "", value)
    value = re.sub(r"ing\b", "in", value)
    return value.replace(" ", "")


def _strip_prefix(value: str) -> str:
    tokens = value.split()
    while len(tokens) > 1 and PREFIX_TOKEN.match(tokens[0]):
        tokens.pop(0)
    return " ".join(tokens)


def title_keys(value: str) -> set[str]:
    """Comparable keys for one title: as written and without parentheticals."""

    keys: set[str] = set()
    for variant in {value or "", PARENTHETICAL.sub("", value or "")}:
        base = normalized_title(variant)
        if not base:
            continue
        for candidate in {base, _strip_prefix(base)}:
            folded = _fold(normalized_title(candidate))
            if folded:
                keys.add(folded)
    return keys


def is_combined_track(title: str, song_keys: set[str]) -> bool:
    """True when a title names two or more songs, as in "Dark Star > St. Stephen"."""

    parts = [part for part in COMBINED_SEPARATOR.split(PARENTHETICAL.sub("", title or "")) if part.strip()]
    return len(parts) >= 2 and sum(bool(title_keys(part) & song_keys) for part in parts) >= 2


def _lcs_table(left: list[set[str]], right: list[set[str]], forbidden: tuple[int, int] | None = None) -> list[list[int]]:
    """suffix[i][j] = longest in-order match of left[i:] against right[j:]."""

    rows, cols = len(left), len(right)
    suffix = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            best = max(suffix[i + 1][j], suffix[i][j + 1])
            if left[i] & right[j] and (i, j) != forbidden:
                best = max(best, suffix[i + 1][j + 1] + 1)
            suffix[i][j] = best
    return suffix


def align_tracks_tolerant(
    source_tracks: list[tuple[int, dict]],
    performances: list[dict],
    songs: dict[str, str],
    catalog_keys: set[str] | None = None,
) -> tuple[str, list[tuple[int, int, dict]], str, list[dict]]:
    """Return (status, matches, reason, skipped_tracks) for one item."""

    if not performances:
        return "held", [], "show_has_no_canonical_performances", []
    canonical = [title_keys(songs[row["song_id"]]) for row in performances]
    setlist_keys = set().union(*canonical)
    catalog_keys = catalog_keys if catalog_keys is not None else setlist_keys

    skipped: list[dict] = []
    titled: list[tuple[int, dict, set[str]]] = []
    song_titled = 0
    for track_number, source_file in source_tracks:
        title = source_file.get("title", "") or ""
        keys = title_keys(title)

        def skip(reason: str) -> None:
            skipped.append({"track_number": track_number, "title": title, "reason": reason})

        if not keys:
            skip("untitled_track")
        elif is_combined_track(title, catalog_keys | setlist_keys):
            song_titled += 1
            skip("combined_track_spans_several_songs")
        elif keys & setlist_keys:
            song_titled += 1
            titled.append((track_number, source_file, keys & setlist_keys))
        else:
            if keys & catalog_keys:
                song_titled += 1
                skip("song_not_in_canonical_setlist")
            else:
                skip("not_a_setlist_song")

    left = [keys for _, _, keys in titled]
    suffix = _lcs_table(left, canonical)
    best = suffix[0][0] if titled else 0
    if not best:
        return "held", [], "no_source_titles_match_canonical_setlist", skipped

    # prefix[i][j] = longest in-order match of left[:i] against canonical[:j].
    rows, cols = len(left), len(canonical)
    prefix = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            value = max(prefix[i - 1][j], prefix[i][j - 1])
            if left[i - 1] & canonical[j - 1]:
                value = max(value, prefix[i - 1][j - 1] + 1)
            prefix[i][j] = value

    matches: list[tuple[int, int, dict]] = []
    placed: set[int] = set()
    for i in range(rows):
        for j in range(cols):
            if not left[i] & canonical[j]:
                continue
            if prefix[i][j] + 1 + suffix[i + 1][j + 1] != best:
                continue
            # On some longest alignment; keep it only if every longest
            # alignment uses it.
            if _lcs_table(left, canonical, forbidden=(i, j))[0][0] < best:
                matches.append((titled[i][0], j, titled[i][1]))
                placed.add(i)
    for i, (track_number, source_file, _) in enumerate(titled):
        if i in placed:
            continue
        on_some = any(
            left[i] & canonical[j] and prefix[i][j] + 1 + suffix[i + 1][j + 1] == best for j in range(cols)
        )
        skipped.append(
            {
                "track_number": track_number,
                "title": source_file.get("title", ""),
                "reason": "repeated_song_position_ambiguous" if on_some else "out_of_setlist_order",
            }
        )

    if not matches:
        return "held", [], "ambiguous_alignment_no_settled_tracks", skipped
    if len(matches) < MIN_ALIGNED_SHARE * song_titled:
        return "held", [], f"item_does_not_evidently_match_show_{len(matches)}_of_{song_titled}_song_tracks", skipped
    matches.sort(key=lambda match: match[1])
    status = "accepted_full" if len(matches) == len(performances) else "accepted_partial"
    return status, matches, "", sorted(skipped, key=lambda row: row["track_number"])


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
                # exists in the setlist but occurs before this candidate
                # alignment invalidates only this candidate. Another live
                # candidate may have assigned an earlier occurrence of a
                # repeated song and still align unambiguously.
                if normalized_source in canonical_titles:
                    continue
                next_states[used_indexes] = matches
                continue
            for index in candidate_indexes:
                new_indexes = used_indexes + (index,)
                next_states[new_indexes] = matches + [(track_number, index, source_file)]
        states = next_states
        if not states:
            reason = (
                f"source_order_conflict_at_track_{track_number}"
                if normalized_source in canonical_titles
                else f"no_monotonic_alignment_at_track_{track_number}"
            )
            return "held", [], reason

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


def evaluate_item(
    record: dict,
    show_performances: list[dict],
    songs: dict[str, str],
    catalog_keys: set[str],
) -> tuple[str, list[tuple[int, int, dict]], str, list[dict], list[tuple[int, dict]], str]:
    """Align one item strictly, then tolerantly; return the result and which aligner decided."""

    payload = record.get("raw_payload", {})
    if "files" not in payload:
        return "held", [], "item_metadata_unavailable", [], [], ""
    source_tracks, track_error = audio_track_files(payload)
    if track_error:
        return "held", [], track_error, [], [], ""
    status, matches, reason = align_tracks(source_tracks, show_performances, songs)
    if status.startswith("accepted"):
        return status, matches, reason, [], source_tracks, "strict"
    status, matches, reason, skipped = align_tracks_tolerant(source_tracks, show_performances, songs, catalog_keys)
    return status, matches, reason, skipped, source_tracks, "tolerant"


def fallback_pass(
    songs: dict[str, str],
    recordings_by_identifier: dict[str, dict],
    performances: dict[str, list[dict]],
    current_rows: list[dict],
    strict_accepted_shows: set[str],
) -> tuple[list[dict], list[dict], dict[str, int], set[str]]:
    """Map shows the strict representative pass left without any track.

    Candidates are the show's representative item followed by any preserved
    alternate items, in representative order.  The first item that aligns
    every canonical performance wins; otherwise the item with the most
    settled tracks does (ties keep representative order).  Only one item is
    ever used for a show, so a show never mixes recordings.

    Rows this pass wrote before are regenerated rather than appended to: the
    returned recording ids name the rows the caller must replace.  A show
    that the strict pass accepted, or that has rows from a recording outside
    these candidates (for example a hand-reviewed source), is left alone.
    """

    performance_show = {
        row["performance_id"]: show_id for show_id, rows in performances.items() for row in rows
    }
    rows_by_show: dict[str, set[str]] = defaultdict(set)
    for row in current_rows:
        rows_by_show[performance_show.get(row["performance_id"], "")].add(row["recording_id"])
    catalog_keys: set[str] = set()
    for title in songs.values():
        catalog_keys |= title_keys(title)

    candidates: dict[str, list[tuple[bool, dict]]] = defaultdict(list)
    seen: set[str] = set()
    sources = [(False, path) for path in sorted(RAW_DIR.glob("internet-archive-*-representatives.jsonl"))]
    sources.append((True, ALTERNATES_PATH))
    for is_alternate, path in sources:
        for record in read_item_records(path):
            identifier = record.get("source_record_id", "")
            recording = recordings_by_identifier.get(identifier)
            if not recording or identifier in seen:
                continue
            show_id = recording["show_id"]
            if show_id in strict_accepted_shows or not performances.get(show_id):
                continue
            seen.add(identifier)
            candidates[show_id].append((is_alternate, record))

    additions: list[dict] = []
    review: list[dict] = []
    counts: dict[str, int] = defaultdict(int)
    managed_recordings: set[str] = set()
    for show_id in sorted(candidates):
        candidate_recordings = {
            recordings_by_identifier[record["source_record_id"]]["recording_id"] for _, record in candidates[show_id]
        }
        if rows_by_show.get(show_id, set()) - candidate_recordings:
            counts["skipped_show_has_other_recording_rows"] += 1
            continue
        managed_recordings |= candidate_recordings
        ordered = sorted(
            candidates[show_id],
            key=lambda item: (item[0], representative_rank(item[1]["source_record_id"])),
        )
        show_performances = performances[show_id]
        evaluated = []
        for is_alternate, record in ordered:
            status, matches, reason, skipped, source_tracks, aligner = evaluate_item(
                record, show_performances, songs, catalog_keys
            )
            evaluated.append((is_alternate, record, status, matches, reason, skipped, source_tracks, aligner))
        accepted = [item for item in evaluated if item[2].startswith("accepted")]
        chosen = None
        if accepted:
            full = [item for item in accepted if item[2] == "accepted_full"]
            chosen = full[0] if full else max(accepted, key=lambda item: len(item[3]))
        counts[chosen[2] if chosen else "held"] += 1

        for item in evaluated:
            is_alternate, record, status, matches, reason, skipped, source_tracks, aligner = item
            review.append(
                {
                    "source": "internet-archive",
                    "pass": "fallback",
                    "source_record_id": record["source_record_id"],
                    "item_role": "alternate" if is_alternate else "representative",
                    "show_id": show_id,
                    "status": status,
                    "reason": reason,
                    "aligner": aligner,
                    "chosen_for_show": item is chosen,
                    "matched_track_count": len(matches),
                    "canonical_performance_count": len(show_performances),
                    "source_track_count": len(source_tracks),
                    "matched_tracks": [
                        {
                            "track_number": track_number,
                            "title": source_file.get("title", ""),
                            "performance_id": show_performances[index]["performance_id"],
                        }
                        for track_number, index, source_file in matches
                    ],
                    "skipped_tracks": skipped,
                    "representative_source_url": record.get("source_url", ""),
                    "retrieved_at": record.get("retrieved_at", ""),
                }
            )
        if chosen is None:
            continue
        _, record, _, matches, _, _, _, aligner = chosen
        recording = recordings_by_identifier[record["source_record_id"]]
        for track_number, performance_index, source_file in matches:
            performance = show_performances[performance_index]
            additions.append(
                {
                    "performance_id": performance["performance_id"],
                    "recording_id": recording["recording_id"],
                    "track_number": track_number,
                    "start_seconds": "",
                    "duration_seconds": parse_duration(source_file.get("length")),
                    "track_title": source_file.get("title", ""),
                    "notes": FALLBACK_NOTE
                    if aligner == "tolerant"
                    else (
                        "Source track title/order uniquely aligned to the canonical setlist; "
                        "duration comes from Internet Archive item metadata; no audio downloaded."
                    ),
                }
            )
        counts["rows"] += len(matches)
    return additions, review, counts, managed_recordings


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

    strict_accepted_shows = {row["show_id"] for row in review if row["status"].startswith("accepted")}
    fallback_additions, fallback_review, fallback_counts, managed_recordings = fallback_pass(
        songs, recordings, performances, existing + additions, strict_accepted_shows
    )
    # Rows an earlier fallback run wrote are regenerated, not appended to.
    existing = [row for row in existing if row["recording_id"] not in managed_recordings]
    additions = [row for row in additions if row["recording_id"] not in managed_recordings]
    additions.extend(fallback_additions)
    review.extend(fallback_review)

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
        f"Fallback pass: {dict(sorted(fallback_counts.items()))}. "
        f"Review evidence: {REVIEW_PATH.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
