#!/usr/bin/env python3
"""Link songs that are not one tape file, where the whole song can still be played.

The track and gap passes link a song to one file. Three kinds of song are left
short or unlinked by that, and this pass settles the ones the tapes allow:

1. **a song the tape cuts into several files.**  Between the tracks linked to
   a song's setlist neighbours, the tape's only music is a run of two or more
   consecutive tracks that each name the song ("Dark Star", "Dark Star ->";
   tuning or audience tracks may sit before or after the run).  Each file is
   a mapping row, part 1, part 2, ..., on the same tape; the player plays them
   back to back as one track and the song's length is their sum.  A linked
   song whose following tracks, up to the next linked song, are all more of it
   gains them as further parts the same way.
2. **a song linked to a fragment.**  A linked song whose file is under 60% of
   its fullest official release, and over five minutes shorter, moves to
   another tape of the show whose titles align to the setlist and which has
   the song as one file within 10% (or two minutes) of the release's length
   (5/11/72's second Dark Star: 1:50 on one tape, 29:24 on another, 30:33 on
   the release).  The release is the reference only for choosing; the stated
   length stays the played file's.
3. **The Other One under the suite's title.**  A track titled "That's It For
   The Other One" is the whole suite when it opens with Cryptical Envelopment;
   when Cryptical Envelopment and Drums have their own tracks directly before
   it and the next track is the Cryptical reprise, it is The Other One alone.

A song that starts partway into a shared file needs to know where it starts.
The preserved metadata gives whole-file lengths only, so those songs stay
unlinked: pressing play must play the song from its start to its end.

Rows this pass wrote before carry ``SPLIT_NOTE_PREFIX`` and are rebuilt on
every run; a row it replaced (kind 2) is kept in the review file and restored
before the run, so a rerun is idempotent.  Run after the gap pass and before
``normalize_internet_archive_track_links.py``, which turns part rows into
``…-archive-track-part-02`` links.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import normalize_internet_archive_gap_tracks as gap  # noqa: E402
import normalize_internet_archive_tracks as ia  # noqa: E402

ROOT = SCRIPTS_DIR.parent
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "recordings"
REVIEW_PATH = RAW_DIR / "internet-archive-split-track-review.jsonl"
MAPPING_FIELDS = gap.MAPPING_FIELDS

SPLIT_NOTE_PREFIX = ia.SPLIT_NOTE_PREFIX
PART_NOTE = re.compile(r"part (\d+) of (\d+) of the song on this tape", re.IGNORECASE)

# Tracks that are not music: what may sit in a gap beside a song's parts.
NOT_MUSIC = {
    "tuning", "audience", "crowd", "banter", "stage", "applause", "intro", "introduction", "announcement",
    "announcements", "encore", "break", "set", "noise", "dead", "air", "silence", "tape", "flip", "end",
    "of", "the", "and", "band", "chatter", "ending", "outro", "pa", "bill", "graham", "cheering",
}

FRAGMENT_SHARE = 0.6
FRAGMENT_SHORTFALL = 300
WHOLE_TOLERANCE_SHARE = 0.10
WHOLE_TOLERANCE_SECONDS = 120


def read_csv(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def is_music(title: str) -> bool:
    words = [word for word in re.split(r"[^a-z]+", (title or "").casefold()) if word]
    return bool(words) and not all(word in NOT_MUSIC for word in words)


def names_song(matcher: gap.Matcher, title: str, song_title: str) -> bool:
    """The title names this song and nothing after it (a trailing ``->`` is a segue mark, not another song)."""

    how, spans = matcher.relation(title, song_title)
    return bool(how) and not spans


def parts_run(free: list[tuple[int, str]], song_title: str, matcher: gap.Matcher, at_start: bool) -> list[int] | None:
    """The track numbers of a run of tracks that are all this song, when they are the gap's only music.

    ``at_start`` requires the run to begin at the gap's first track (more of
    a song that is already linked just before the gap).
    """

    music = [(number, title) for number, title in free if is_music(title)]
    if not music or not all(names_song(matcher, title, song_title) for _number, title in music):
        return None
    if any(ia.ENCORE_PREFIX.match(title.strip()) for _number, title in music):
        # An encore mark puts the track in the encore, not in this song's set.
        return None
    numbers = [number for number, _title in music]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        return None
    if at_start and numbers[0] != free[0][0]:
        return None
    return numbers


def part_note(index: int, total: int, identifier: str, how: str) -> str:
    return f"{SPLIT_NOTE_PREFIX}part {index} of {total} of the song on this tape ({how}); item {identifier}; no audio downloaded."


def tape_anchors(
    record: dict,
    show: list[dict],
    titles: list[str],
    songs: dict[str, str],
    catalog_keys: set[str],
    matcher: gap.Matcher,
    mapped: dict[int, int],
) -> dict[int, int]:
    """Which track of this tape is which song of the show, as far as the tape settles it.

    The tracks already mapped to this tape, the setlist aligner's matches
    (when it accepts the tape as this show), and a lone free track between two
    of those that names the one song between them ("Darkstar >" between Drums
    and Sugar Magnolia). Empty when the tape's order disagrees with the setlist.
    """

    status, matches, _reason, _skipped, tracks, _aligner = ia.evaluate_item(record, show, songs, catalog_keys)
    anchors = {index: number for number, index, _file in matches} if status.startswith("accepted") else {}
    taken = {number: index for index, number in mapped.items()}
    anchors = {index: number for index, number in anchors.items() if number not in taken or taken[number] == index}
    anchors.update(mapped)
    ordered = sorted(anchors.items())
    if any(b[1] <= a[1] for a, b in zip(ordered, ordered[1:])):
        ordered = sorted(mapped.items())
        if any(b[1] <= a[1] for a, b in zip(ordered, ordered[1:])):
            return {}
        anchors = dict(mapped)
    track_titles = {number: source_file.get("title", "") or "" for number, source_file in tracks}
    used = set(anchors.values())
    bounds = [(-1, 0)] + sorted(anchors.items()) + [(len(show), 10**9)]
    for (left_index, left_track), (right_index, right_track) in zip(bounds, bounds[1:]):
        if right_index - left_index != 2:
            continue
        index = left_index + 1
        music = [n for n, title in sorted(track_titles.items()) if left_track < n < right_track and n not in used and is_music(title)]
        if len(music) == 1 and names_song(matcher, track_titles[music[0]], titles[index]):
            anchors[index] = music[0]
    return anchors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report counts without writing any file")
    args = parser.parse_args()

    songs = {row["song_id"]: row["title"] for row in read_csv("songs.csv")}
    recordings = read_csv("recordings.csv")
    recording_by_id = {row["recording_id"]: row for row in recordings}
    recordings_by_show: dict[str, list[dict]] = defaultdict(list)
    for row in recordings:
        if row["archive_identifier"]:
            recordings_by_show[row["show_id"]].append(row)
    performances: dict[str, list[dict]] = defaultdict(list)
    for row in read_csv("performances.csv"):
        performances[row["show_id"]].append(row)
    for rows in performances.values():
        rows.sort(key=lambda row: (int(row["set_number"] or 0), int(row["position_in_set"] or 0)))
    release_seconds: dict[str, int] = {}
    for row in read_csv("official_release_tracks.csv"):
        seconds = row.get("duration_seconds", "")
        if row.get("performance_id") and seconds.isdigit():
            release_seconds[row["performance_id"]] = max(release_seconds.get(row["performance_id"], 0), int(seconds))

    # Rebuild from the rows the other passes wrote: this pass's own rows go,
    # and a row it replaced comes back from the last review.
    current = read_csv("performance_recordings.csv")
    mapping = [row for row in current if not row["notes"].startswith(SPLIT_NOTE_PREFIX)]
    if REVIEW_PATH.exists():
        for line in REVIEW_PATH.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("replaced_row") and not any(
                row["performance_id"] == entry["replaced_row"]["performance_id"] for row in mapping
            ):
                mapping.append(entry["replaced_row"])
    linked = {row["performance_id"] for row in mapping}
    performance_show = {row["performance_id"]: show_id for show_id, rows in performances.items() for row in rows}
    rows_by_show: dict[str, list[dict]] = defaultdict(list)
    for row in mapping:
        rows_by_show[performance_show.get(row["performance_id"], "")].append(row)

    items, _preserved = gap.load_items([])
    matcher = gap.Matcher(songs)
    plain_catalog_keys: set[str] = set()
    for title in songs.values():
        plain_catalog_keys |= ia.title_keys(title)

    added: list[dict] = []
    replaced: dict[str, dict] = {}
    review: list[dict] = []
    counts: Counter[str] = Counter()

    def file_of(record: dict, number: int) -> dict | None:
        tracks, error = ia.audio_track_files(record.get("raw_payload", {}))
        return None if error else dict(tracks).get(number)

    def mapping_row(performance_id: str, recording_id: str, number: int, source_file: dict, record: dict, note: str) -> dict:
        return {
            "performance_id": performance_id,
            "recording_id": recording_id,
            "track_number": str(number),
            "start_seconds": "",
            "duration_seconds": ia.track_length(record.get("raw_payload", {}), source_file),
            "track_title": source_file.get("title", "") or "",
            "notes": note,
        }

    for show_id in sorted(performances):
        show = performances[show_id]
        index_of = {row["performance_id"]: index for index, row in enumerate(show)}
        titles = [songs.get(row["song_id"], "") for row in show]
        by_recording: dict[str, dict[int, int]] = defaultdict(dict)
        for row in rows_by_show.get(show_id, []):
            if row["track_number"].isdigit() and row["performance_id"] in index_of:
                by_recording[row["recording_id"]][index_of[row["performance_id"]]] = int(row["track_number"])

        # Every tape of the show, anchored to its setlist. Tapes the show
        # does not use yet matter only when a song of the show is unlinked.
        unlinked = any(row["performance_id"] not in linked for row in show)
        candidates = sorted(
            (row for row in recordings_by_show.get(show_id, []) if row["archive_identifier"] in items and (unlinked or row["recording_id"] in by_recording)),
            key=lambda row: (row["recording_id"] not in by_recording, not gap.is_soundboard(row["archive_identifier"]), ia.representative_rank(row["archive_identifier"])),
        )
        aligned: dict[str, dict[int, int]] = {}
        for tape in candidates:
            record = items[tape["archive_identifier"]]
            if ia.audio_track_files(record.get("raw_payload", {}))[1]:
                continue
            aligned[tape["recording_id"]] = tape_anchors(record, show, titles, songs, plain_catalog_keys, matcher, by_recording.get(tape["recording_id"], {}))

        # 1 and 3: parts and the suite's title.
        for tape in candidates:
            recording_id = tape["recording_id"]
            anchors = aligned.get(recording_id) or {}
            if not anchors:
                continue
            record = items[tape["archive_identifier"]]
            track_file = dict(ia.audio_track_files(record.get("raw_payload", {}))[0])
            mapped_here = by_recording.get(recording_id, {})
            used = set(anchors.values())
            identifier = record["source_record_id"]
            boundaries = sorted(anchors.items()) + [(len(show), 10**9)]
            for (left_index, left_track), (right_index, right_track) in zip(boundaries, boundaries[1:]):
                between = list(range(left_index + 1, right_index))
                free = [
                    (number, track_file[number].get("title", "") or "")
                    for number in sorted(track_file)
                    if left_track < number < right_track and number not in used
                ]
                if not free:
                    continue
                if not between:
                    if left_index not in mapped_here or show[left_index]["performance_id"] in replaced:
                        continue
                    target, at_start, how = left_index, True, "more of the song linked just before"
                elif len(between) == 1 and show[between[0]]["performance_id"] not in linked:
                    target, at_start, how = between[0], False, "the tape cuts the song into consecutive files"
                else:
                    continue
                run = parts_run(free, titles[target], matcher, at_start)
                if run is None and not at_start and titles[target] == "The Other One":
                    # 3: the suite's title on a track between Drums and the Cryptical reprise.
                    music = [(number, title) for number, title in free if is_music(title)]
                    suite_alone = (
                        len(music) == 1
                        and gap._plain(music[0][1]) in gap.SUITE_OPENERS
                        and titles[left_index] == "Drums"
                        and target == left_index + 1
                        and music[0][0] == left_track + 1
                        and left_index >= 1
                        and titles[left_index - 1] == "Cryptical Envelopment"
                        and anchors.get(left_index - 1) == left_track - 1
                        and right_index < len(show)
                        and titles[right_index] == "Cryptical Envelopment"
                    )
                    if suite_alone:
                        number = music[0][0]
                        source_file = track_file[number]
                        if gap.playable(record, source_file):
                            note = f"{SPLIT_NOTE_PREFIX}the track carries the suite's title, but Cryptical Envelopment and Drums have their own tracks before it and the reprise follows it; item {identifier}; no audio downloaded."
                            added.append(mapping_row(show[target]["performance_id"], recording_id, number, source_file, record, note))
                            linked.add(show[target]["performance_id"])
                            counts["the_other_one_under_the_suite_title"] += 1
                            review.append({"kind": "suite_title", "show_id": show_id, "performance_id": show[target]["performance_id"], "archive_identifier": identifier, "tracks": [number]})
                    continue
                if run is None:
                    continue
                performance_id = show[target]["performance_id"]
                if at_start:
                    numbers = [anchors[target]] + run
                    if not all(gap.playable(record, track_file[number]) for number in numbers):
                        continue
                    # The linked row becomes part 1 (rewritten in place below).
                    total = len(numbers)
                    for row in mapping:
                        if row["performance_id"] == performance_id and row["recording_id"] == recording_id:
                            replaced[performance_id] = dict(row)
                    added.append({**replaced[performance_id], "notes": part_note(1, total, identifier, how) + " " + replaced[performance_id]["notes"]})
                    for position, number in enumerate(run, start=2):
                        added.append(mapping_row(performance_id, recording_id, number, track_file[number], record, part_note(position, total, identifier, how)))
                    counts["extended_with_more_files"] += 1
                else:
                    if len(run) < 2 or not all(gap.playable(record, track_file[number]) for number in run):
                        continue
                    for position, number in enumerate(run, start=1):
                        added.append(mapping_row(performance_id, recording_id, number, track_file[number], record, part_note(position, len(run), identifier, how)))
                    linked.add(performance_id)
                    counts["cut_across_files"] += 1
                used.update(run)
                review.append(
                    {
                        "kind": "parts",
                        "how": how,
                        "show_id": show_id,
                        "performance_id": performance_id,
                        "canonical_song_title": titles[target],
                        "archive_identifier": identifier,
                        "tracks": ([anchors[target]] if at_start else []) + run,
                        "titles": [track_file[number].get("title", "") for number in (([anchors[target]] if at_start else []) + run)],
                        **({"replaced_row": replaced[performance_id]} if at_start else {}),
                    }
                )

        # 2: a song linked to a fragment moves to a tape that has it whole.
        others = sorted(
            (row for row in recordings_by_show.get(show_id, []) if row["archive_identifier"] in items),
            key=lambda row: (not gap.is_soundboard(row["archive_identifier"]), ia.representative_rank(row["archive_identifier"])),
        )
        for row in rows_by_show.get(show_id, []):
            performance_id = row["performance_id"]
            reference = release_seconds.get(performance_id)
            seconds = row["duration_seconds"]
            if performance_id in replaced or not reference or not seconds.isdigit() or ia.SPANS_MORE_MARK in row["notes"]:
                continue
            if not (int(seconds) < FRAGMENT_SHARE * reference and reference - int(seconds) > FRAGMENT_SHORTFALL):
                continue
            index = index_of.get(performance_id)
            if index is None:
                continue
            best: tuple[int, str, int, dict, dict] | None = None
            for other in others:
                if other["recording_id"] == row["recording_id"]:
                    continue
                record = items[other["archive_identifier"]]
                if other["recording_id"] not in aligned:
                    if ia.audio_track_files(record.get("raw_payload", {}))[1]:
                        continue
                    aligned[other["recording_id"]] = tape_anchors(record, show, titles, songs, plain_catalog_keys, matcher, by_recording.get(other["recording_id"], {}))
                anchors_there = aligned[other["recording_id"]]
                number = anchors_there.get(index)
                if number is None:
                    continue
                source_file = dict(ia.audio_track_files(record.get("raw_payload", {}))[0])[number]
                length = ia.track_length(record.get("raw_payload", {}), source_file)
                title_parts = [part for part in gap.SEGMENT_SEPARATOR.split(source_file.get("title", "") or "") if part.strip()]
                if not length.isdigit() or len(title_parts) != 1 or not gap.playable(record, source_file):
                    continue
                if abs(int(length) - reference) > max(WHOLE_TOLERANCE_SHARE * reference, WHOLE_TOLERANCE_SECONDS):
                    continue
                if gap.runs_on(index, number, anchors_there, sorted(dict(ia.audio_track_files(record.get("raw_payload", {}))[0])), show):
                    continue
                candidate = (abs(int(length) - reference), other["recording_id"], number, source_file, record)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
            if best is None:
                counts["fragment_without_a_whole_file"] += 1
                continue
            _gap_seconds, recording_id, number, source_file, record = best
            replaced[performance_id] = dict(row)
            note = (
                f"{SPLIT_NOTE_PREFIX}the first tape's track for this song is a fragment ({seconds} s against {reference} s on its "
                f"fullest release); this tape's titles align to the same setlist and it has the song as one file; "
                f"item {record['source_record_id']}; no audio downloaded."
            )
            added.append(mapping_row(performance_id, recording_id, number, source_file, record, note))
            counts["relinked_from_a_fragment"] += 1
            review.append(
                {
                    "kind": "whole_file",
                    "show_id": show_id,
                    "performance_id": performance_id,
                    "canonical_song_title": titles[index],
                    "archive_identifier": record["source_record_id"],
                    "tracks": [number],
                    "release_seconds": reference,
                    "replaced_row": replaced[performance_id],
                }
            )

    print(f"added {len(added)} mapping rows")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    if args.dry_run:
        for entry in review:
            print(json.dumps({k: v for k, v in entry.items() if k != "replaced_row"}, ensure_ascii=False))
        return 0

    kept = [
        row
        for row in mapping
        if not (row["performance_id"] in replaced and row["recording_id"] == replaced[row["performance_id"]]["recording_id"] and row["track_number"] == replaced[row["performance_id"]]["track_number"])
    ]
    with (CANONICAL / "performance_recordings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAPPING_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept + added)
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for entry in review:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote performance_recordings.csv and {REVIEW_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
