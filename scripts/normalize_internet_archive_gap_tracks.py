#!/usr/bin/env python3
"""Find a tape track for songs that still have none.

``normalize_internet_archive_tracks.py`` maps one tape per show and leaves a
song unlinked when its track title does not read as the song.  The songs left
behind are mostly the big jams: Drums under "Drumz", Turn On Your Lovelight as
one track around a drum break, The Other One suite under its album title, a
medley in one file.  This pass looks for them, in this order, and never moves
an existing link:

1. **the show's own tape, under another title.**  Between the tracks already
   linked to a song's setlist neighbours, an unused track whose title names
   the song through a tape shorthand (``TAPE_SHORTHAND``), an initialism
   ("GDTRFB"), or a fragment of the title that fits no other song of the show
   ("Dupree's", "Dark Star Jam");
2. **another tape of the same show.**  Each other ``recordings.csv`` item with
   preserved metadata is aligned to the whole setlist with the same aligners
   the track pass uses, which also establishes that it is this show; its
   settled tracks fill the songs still missing, soundboards first, and step 1
   then runs on that tape too;
3. **a medley in one file**, on any of those tapes: a track whose title opens
   with the song and goes on ("Scarlet > Fire", "That's It For The Other
   One") is linked to the song it opens with.  Pressing play starts on that
   song.  The mapping row carries ``SPANS_MORE_MARK``, so the link states no
   length: the file's length is not the song's.

The rule throughout: pressing play on a song plays that song.  A song that
sits later in a shared file would need a start offset, which no player
honours yet, so it stays unlinked; so does a song the tape cuts into several
files.  A repeated song with one track (Good Lovin' > Drums > Good Lovin')
takes the track for its first pass only when that track directly follows the
linked track of the song before it.

Rows this pass wrote before are regenerated, so a rerun is idempotent.  It
reads item metadata from the preserved files and from
``internet-archive-item-files.jsonl`` (plus any ``--candidates`` file a
collector run left outside git), and rewrites ``internet-archive-item-files.jsonl``
to hold exactly the newly used items, compactly.

Run order: normalize_internet_archive_tracks.py (when the setlists or tapes
changed), collect/fetch_internet_archive_item_files.py --gaps, this script,
then normalize_internet_archive_track_links.py.
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

import normalize_internet_archive_tracks as ia  # noqa: E402

ROOT = SCRIPTS_DIR.parent
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "recordings"
REVIEW_PATH = RAW_DIR / "internet-archive-gap-track-review.jsonl"
MAPPING_FIELDS = ["performance_id", "recording_id", "track_number", "start_seconds", "duration_seconds", "track_title", "notes"]

GAP_NOTE_PREFIX = ia.GAP_NOTE_PREFIX
HOW_NOTES = {
    "same_tape": "the source track names this song under another title and sits between the tracks linked to its setlist neighbours on the show's tape",
    "other_tape": "the show's first tape has no track for this song; this tape's titles align to the same setlist and its track names the song",
    "other_tape_variant": "the show's first tape has no track for this song; this tape's titles align to the same setlist and its track names the song under another title, between its neighbours",
}

# Tape shorthand for a setlist song: normalized track title -> canonical song
# title.  Only names a taper could not mean anything else by.
TAPE_SHORTHAND = {
    "drumz": "Drums",
    "drum solo": "Drums",
    "drum duet": "Drums",
    "rhythm devils": "Drums",
    "never trust a woman": "Good Time Blues",
    "long way to go home": "Way To Go Home",
    "king bee": "I'm A King Bee",
    "aiko aiko": "Iko Iko",
    "aiko": "Iko Iko",
    "women are smarter": "Man Smart, Woman Smarter",
    "woman are smarter": "Man Smart, Woman Smarter",
    "man smart women smarter": "Man Smart, Woman Smarter",
    "saturday night": "One More Saturday Night",
    "sat night": "One More Saturday Night",
    "bobby mcgee": "Me And Bobby McGee",
    "masterpiece": "When I Paint My Masterpiece",
    "big rxr blues": "Big Railroad Blues",
    "big rr blues": "Big Railroad Blues",
    "half step": "Mississippi Half Step",
    "schoolgirl": "Good Morning Little Schoolgirl",
    "lovelight": "Turn On Your Lovelight",
    "love light": "Turn On Your Lovelight",
    "cryptical": "Cryptical Envelopment",
    "other one": "The Other One",
    "wrs prelude": "Weather Report Suite Prelude",
    "wrs part 1": "Weather Report Suite Part 1",
    "wrs part i": "Weather Report Suite Part 1",
    "weather report suite part i": "Weather Report Suite Part 1",
    "playin reprise": "Playing In The Band",
    "playing reprise": "Playing In The Band",
    "stronger than dirt or milkin the turkey": "Stronger Than Dirt",
    "caution do not step on tracks": "Caution",
    "caution do not stop on tracks": "Caution",
}

# A suite's own title: the file opens with the first song and runs on through
# the rest, so it is linked to that song as a medley.
SUITE_OPENERS = {
    "that s it for the other one": "Cryptical Envelopment",
    "thats it for the other one": "Cryptical Envelopment",
    "cryptical envelopment suite": "Cryptical Envelopment",
    "the other one suite": "Cryptical Envelopment",
    "other one suite": "Cryptical Envelopment",
    "weather report suite": "Weather Report Suite Prelude",
    "wrs": "Weather Report Suite Prelude",
}

# Words that are not a song's name on their own.
GENERIC_TOKENS = {
    "jam", "space", "drums", "blues", "tuning", "intro", "encore", "reprise", "instrumental", "song", "band", "baby",
    "the", "and", "for", "you", "your", "with", "that", "this", "all", "its", "one", "man", "new", "set", "break",
    "crowd", "banter", "stage", "tape", "flip", "part", "continued", "cont", "tease", "solo", "fade", "cut",
}
SEGMENT_SEPARATOR = re.compile(r"\s*(?:->|-\s*>|>+|/|→|\+)\s*")
LEADING_NOTES = {"encore", "enc", "intro"}
TRAILING_NOTES = {"jam", "reprise", "baby", "set", "break", "uptown"}


def _is_trailing_note(token: str) -> bool:
    # "Uptown Toodeloo" is the rest of Mississippi Half Step's title, however spelled.
    return token in TRAILING_NOTES or token.isdigit() or token.startswith(("tood", "todel"))


def _plain(value: str) -> str:
    """A track title's words, without file-name prefixes, parentheticals or an encore mark."""

    text = ia.PARENTHETICAL.sub("", value or "")
    text = ia.ENCORE_PREFIX.sub("", text)
    return ia._strip_prefix(ia.normalized_title(text))


def _tokens(value: str) -> list[str]:
    return [token for token in _plain(value).split() if len(token) > 1]


def _contains(longer: list[str], shorter: list[str]) -> bool:
    size = len(shorter)
    return any(longer[index : index + size] == shorter for index in range(len(longer) - size + 1))


class Matcher:
    """Decides whether a tape title names a song, and how."""

    def __init__(self, songs: dict[str, str]) -> None:
        self.catalog_keys: set[str] = set()
        for title in songs.values():
            self.catalog_keys |= ia.title_keys(title, extended=True)
        self._song_keys: dict[str, set[str]] = {}

    def song_keys(self, title: str) -> set[str]:
        if title not in self._song_keys:
            self._song_keys[title] = ia.title_keys(title, extended=True)
        return self._song_keys[title]

    def names(self, part: str, song_title: str) -> str:
        """How one title (no medley marks) names the song: "title", "shorthand", "suite", "initials", "fragment" or ""."""

        keys = ia.title_keys(part, extended=True)
        song_keys = self.song_keys(song_title)
        if keys & song_keys:
            return "title"
        plain = _plain(part)
        if plain in SUITE_OPENERS:
            return "suite" if self.song_keys(SUITE_OPENERS[plain]) & song_keys else ""
        if plain in TAPE_SHORTHAND:
            return "shorthand" if self.song_keys(TAPE_SHORTHAND[plain]) & song_keys else ""
        if keys & self.catalog_keys:
            # The title is another song's exact name.
            return ""
        track_tokens, song_tokens = _tokens(part), _tokens(song_title)
        if len(track_tokens) == 1 and len(song_tokens) >= 3 and track_tokens[0] == "".join(token[0] for token in song_tokens):
            return "initials"
        if not track_tokens or not song_tokens:
            return ""
        if len(track_tokens) < len(song_tokens):
            # Part of the song's title: "Dupree's", "Terrapin", "Baby Blue".
            if _contains(song_tokens, track_tokens) and any(len(t) >= 4 and t not in GENERIC_TOKENS for t in track_tokens):
                return "fragment"
            return ""
        # The song's title with a tape note after it: "Dark Star Jam",
        # "Deal, Set Break".  Words before it, or any other words after it,
        # mean another song or a part of this one ("Jam out of Truckin'",
        # "Not Fade Away tease", "Sugar Magnolia - Comes A Time").
        while track_tokens and track_tokens[0] in LEADING_NOTES:
            track_tokens = track_tokens[1:]
        if len(track_tokens) > len(song_tokens) and track_tokens[: len(song_tokens)] == song_tokens:
            if all(_is_trailing_note(token) for token in track_tokens[len(song_tokens) :]):
                return "fragment"
        return ""

    def relation(self, track_title: str, song_title: str) -> tuple[str, bool]:
        """(how, opens_a_medley) for a track title against a song; ("", False) when it does not name it.

        A title with medley marks names only the song it opens with, and the
        file then holds more than that song.
        """

        parts = [part for part in SEGMENT_SEPARATOR.split(ia.PARENTHETICAL.sub("", track_title or "")) if part.strip()]
        if not parts:
            return "", False
        if len(parts) == 1:
            how = self.names(parts[0], song_title)
            return how, how == "suite"
        how = self.names(parts[0], song_title)
        return (how, True) if how else ("", False)


def settle(
    unlinked: list[int],
    tracks: list[tuple[int, str]],
    relation: dict[tuple[int, int], tuple[str, bool]],
) -> dict[int, int]:
    """Pair performances (by index) with track numbers when every longest in-order pairing agrees."""

    rows, cols = len(unlinked), len(tracks)

    def best_length(forbidden: tuple[int, int] | None = None) -> int:
        suffix = [[0] * (cols + 1) for _ in range(rows + 1)]
        for i in range(rows - 1, -1, -1):
            for j in range(cols - 1, -1, -1):
                value = max(suffix[i + 1][j], suffix[i][j + 1])
                if (unlinked[i], tracks[j][0]) in relation and (i, j) != forbidden:
                    value = max(value, suffix[i + 1][j + 1] + 1)
                suffix[i][j] = value
        return suffix[0][0]

    best = best_length()
    settled: dict[int, int] = {}
    if not best:
        return settled
    for i, performance_index in enumerate(unlinked):
        for j, (track_number, _title) in enumerate(tracks):
            if (performance_index, track_number) in relation and best_length(forbidden=(i, j)) < best:
                settled[performance_index] = track_number
    return settled


def fill_gaps_on_tape(
    show_performances: list[dict],
    songs: dict[str, str],
    anchors: dict[int, int],
    track_titles: dict[int, str],
    wanted: set[int],
    matcher: Matcher,
    medleys: bool = False,
    whole_songs: bool = False,
) -> tuple[list[tuple[int, int, str, bool]], dict[int, set[int]]]:
    """Find tracks on one tape for the wanted performances, between the anchored ones.

    ``anchors`` maps a performance index to the track already known to be it
    on this tape; ``wanted`` are the performance indexes still without a
    track anywhere.  Returns the ``(performance_index, track_number, how,
    spans_more)`` found, and the later passes of a song whose one track was
    given to its first pass: they are inside that file.

    With ``medleys`` false only tracks that hold just the song are returned.
    ``whole_songs`` allows the one-track rule for a song played twice around
    something else (Good Lovin' > Drums > Good Lovin'): the file opens with
    the first pass when it directly follows the linked track of the song
    before it.  It applies only while every pass is still without a track, so
    a pass is never linked twice over (once as the whole song, once as its
    own track on another tape).
    """

    ordered = sorted(anchors.items())
    if any(b[1] <= a[1] for a, b in zip(ordered, ordered[1:])):
        return [], {}  # the tape's order disagrees with the setlist; neighbours mean nothing
    used = set(anchors.values())
    titles = [songs[row["song_id"]] for row in show_performances]
    found: list[tuple[int, int, str, bool]] = []
    covered: dict[int, set[int]] = {}
    boundaries = [(-1, 0)] + ordered + [(len(show_performances), 10**9)]
    for (left_index, left_track), (right_index, right_track) in zip(boundaries, boundaries[1:]):
        # Every song of the gap competes for a track, wanted or not: a song
        # already linked on another tape is still the one this tape's track
        # may hold (the one "Lovelight" track is the first pass, not the
        # reprise that happens to be the only pass still missing).
        open_gap = [index for index in range(left_index + 1, right_index)]
        if not any(index in wanted for index in open_gap):
            continue
        free = [(number, title) for number, title in sorted(track_titles.items()) if left_track < number < right_track and number not in used and title]
        if not free:
            continue
        relation: dict[tuple[int, int], tuple[str, bool]] = {}
        for index in open_gap:
            for number, title in free:
                how, spans = matcher.relation(title, titles[index])
                if how and (medleys or not spans):
                    relation[(index, number)] = (how, spans)
        # A fragment or initialism must point one way only: one song of the
        # show for the track, one track of the gap for the song.
        for (index, number), (how, _spans) in list(relation.items()):
            if how not in ("fragment", "initials"):
                continue
            title = dict(free)[number]
            other_songs = {t for i, t in enumerate(titles) if t != titles[index] and matcher.relation(title, t)[0]}
            other_tracks = [n for (i, n) in relation if i == index and n != number]
            if other_songs or other_tracks:
                del relation[(index, number)]
        settled = settle(open_gap, free, relation)
        for index in open_gap if whole_songs else []:
            if index in settled or index not in wanted:
                continue
            related = [number for (i, number) in relation if i == index]
            if len(related) != 1:
                continue
            number = related[0]
            rivals = [i for (i, n) in relation if n == number and i != index]
            if not rivals or any(i < index or show_performances[i]["song_id"] != show_performances[index]["song_id"] for i in rivals):
                continue
            if number in settled.values() or any(i in settled or i not in wanted for i in rivals):
                continue
            previous = index - 1
            same_set = previous >= 0 and show_performances[previous].get("set_number") == show_performances[index].get("set_number")
            previous_track = anchors.get(previous, settled.get(previous)) if same_set else None
            if previous_track is None or any(previous_track < other < number for other, _title in free):
                continue
            settled[index] = number
            covered[index] = set(rivals)
        for index, number in sorted(settled.items()):
            how, spans = relation[(index, number)]
            if index in wanted:
                found.append((index, number, how, spans))
    return found, covered


def runs_on(index: int, track_number: int, anchors: dict[int, int], track_numbers: list[int], show_performances: list[dict]) -> bool:
    """True when a linked file evidently also holds the songs after it.

    The songs that follow in the set have no track on this tape, and the very
    next track is the one linked to the song after them: a 13-minute "China
    Cat Sunflower>" followed directly by "Samson & Delilah" holds I Know You
    Rider too.  A song played around a break (Lovelight > Drums > Lovelight in
    one "Lovelight" track) is the whole of that song and is not counted.
    """

    set_number = show_performances[index].get("set_number")
    swallowed: list[int] = []
    following = index + 1
    while (
        following < len(show_performances)
        and show_performances[following].get("set_number") == set_number
        and following not in anchors
    ):
        swallowed.append(following)
        following += 1
    if not swallowed or following >= len(show_performances) or show_performances[following].get("set_number") != set_number:
        return False
    next_track = min((number for number in track_numbers if number > track_number), default=None)
    if next_track is None or next_track != anchors.get(following):
        return False
    return show_performances[swallowed[-1]]["song_id"] != show_performances[index]["song_id"]


def read_csv(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_items(extra_paths: list[Path]) -> tuple[dict[str, dict], set[str]]:
    """Item metadata by identifier, and the identifiers the older collectors preserved in full."""

    items: dict[str, dict] = {}
    preserved: set[str] = set()
    for path in ia.item_metadata_paths() + extra_paths:
        for record in ia.read_item_records(path):
            identifier = record.get("source_record_id", "")
            if "files" not in record.get("raw_payload", {}) or identifier in items:
                continue
            items[identifier] = record
            if path not in extra_paths and path != ia.ITEM_FILES_PATH:
                preserved.add(identifier)
    return items, preserved


def is_soundboard(identifier: str) -> bool:
    return "sbd" in identifier.casefold()


def playable(record: dict, source_file: dict) -> bool:
    """True when the track has an MP3 the player can stream to the end."""

    payload = record.get("raw_payload", {})
    streams = ia.stream_files(payload, source_file.get("name", ""))
    return bool(streams) and bool(ia.played_length(streams[0])) and not ia.stream_is_cut_short(payload, streams[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", type=Path, action="append", default=[], help="extra compact item-file JSONL (a collector run kept outside git)")
    parser.add_argument("--dry-run", action="store_true", help="report counts without writing any canonical file")
    parser.add_argument("--review-out", type=Path, help="write the review JSONL here instead (also in a dry run)")
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
    current = read_csv("performance_recordings.csv")
    mapping = [row for row in current if not row["notes"].startswith(GAP_NOTE_PREFIX)]
    # A song this pass mapped before had no other link, so its link is this
    # pass's own and is decided again; every other link stands.
    own = {row["performance_id"] for row in current if row["notes"].startswith(GAP_NOTE_PREFIX)}
    linked = {
        row["performance_id"]
        for row in read_csv("performance_links.csv")
        if row["platform"] == "archive" and row["link_type"] == "recording-track"
    } - own

    items, preserved = load_items(args.candidates)
    matcher = Matcher(songs)
    plain_catalog_keys: set[str] = set()
    for title in songs.values():
        plain_catalog_keys |= ia.title_keys(title)

    rows_by_show: dict[str, list[dict]] = defaultdict(list)
    performance_show = {row["performance_id"]: show_id for show_id, rows in performances.items() for row in rows}
    for row in mapping:
        rows_by_show[performance_show.get(row["performance_id"], "")].append(row)

    additions: list[dict] = []
    review: list[dict] = []
    counts: Counter[str] = Counter()
    used_identifiers: set[str] = set()

    for show_id in sorted(performances):
        show_performances = performances[show_id]
        wanted = {index for index, row in enumerate(show_performances) if row["performance_id"] not in linked}
        if not wanted:
            continue
        index_of = {row["performance_id"]: index for index, row in enumerate(show_performances)}
        show_start = len(additions)
        show_rows = [row for row in rows_by_show.get(show_id, []) if row["performance_id"] in linked]
        by_recording = Counter(row["recording_id"] for row in show_rows)
        tapes: list[tuple[str, dict, dict[int, int], str]] = []  # (recording_id, record, anchors, role)
        for recording_id, _count in sorted(by_recording.items(), key=lambda item: (-item[1], item[0])):
            record = items.get(recording_by_id.get(recording_id, {}).get("archive_identifier", ""))
            if record is None:
                continue
            anchors = {
                index_of[row["performance_id"]]: int(row["track_number"])
                for row in show_rows
                if row["recording_id"] == recording_id and row["track_number"].isdigit()
            }
            tapes.append((recording_id, record, anchors, "same_tape"))
        used_recordings = set(by_recording)
        others = sorted(
            (row for row in recordings_by_show.get(show_id, []) if row["recording_id"] not in used_recordings and row["archive_identifier"] in items),
            key=lambda row: (not is_soundboard(row["archive_identifier"]), ia.representative_rank(row["archive_identifier"])),
        )
        for row in others:
            tapes.append((row["recording_id"], items[row["archive_identifier"]], {}, "other_tape"))

        def add(recording_id: str, record: dict, index: int, track_number: int, source_file: dict, how: str, detail: str, spans: bool) -> None:
            performance = show_performances[index]
            note = GAP_NOTE_PREFIX + HOW_NOTES[how] + f" ({detail}); no audio downloaded."
            if spans:
                note += f" {ia.SPANS_MORE_MARK}."
            additions.append(
                {
                    "performance_id": performance["performance_id"],
                    "recording_id": recording_id,
                    "track_number": str(track_number),
                    "start_seconds": "",
                    "duration_seconds": ia.track_length(record.get("raw_payload", {}), source_file),
                    "track_title": source_file.get("title", ""),
                    "notes": note,
                }
            )
            wanted.discard(index)
            used_identifiers.add(record["source_record_id"])
            counts[f"{how}:{detail}" + (":medley" if spans else "")] += 1
            review.append(
                {
                    "source": "internet-archive",
                    "pass": "gap",
                    "status": "linked",
                    "how": how,
                    "detail": detail,
                    "opens_a_medley": spans,
                    "show_id": show_id,
                    "performance_id": performance["performance_id"],
                    "canonical_song_title": songs[performance["song_id"]],
                    "archive_identifier": record["source_record_id"],
                    "track_number": track_number,
                    "source_title": source_file.get("title", ""),
                }
            )

        # In order: variant titles on the show's own tape and plain titles on
        # its other tapes; variant titles on the other tapes; one track for a
        # song played around a break; a medley in one file.
        aligned: dict[str, tuple[dict[int, int], dict[int, dict]]] = {}
        for phase in ("titles", "variants", "whole_songs", "medleys"):
            for recording_id, record, anchors, role in tapes:
                if not wanted:
                    break
                payload = record.get("raw_payload", {})
                if recording_id not in aligned:
                    source_tracks, error = ia.audio_track_files(payload)
                    if error:
                        aligned[recording_id] = ({}, {})
                        continue
                    track_file = dict(source_tracks)
                    if role == "other_tape":
                        status, matches, _reason, _skipped, _tracks, _aligner = ia.evaluate_item(
                            record, show_performances, songs, plain_catalog_keys
                        )
                        if not status.startswith("accepted"):
                            aligned[recording_id] = ({}, {})
                            counts["other_tape_not_evidently_this_show"] += 1
                            continue
                        anchors = {performance_index: track_number for track_number, performance_index, _file in matches}
                        for track_number, performance_index, source_file in matches:
                            if performance_index in wanted and playable(record, source_file):
                                add(recording_id, record, performance_index, track_number, source_file, "other_tape", "title", False)
                    aligned[recording_id] = (anchors, track_file)
                anchors, track_file = aligned[recording_id]
                if not track_file or (role == "other_tape" and not anchors):
                    continue
                if phase == "titles" and role == "other_tape":
                    continue
                track_titles = {number: source_file.get("title", "") or "" for number, source_file in track_file.items()}
                on_this_tape = [row for row in additions[show_start:] if row["recording_id"] == recording_id]
                taken = {int(row["track_number"]) for row in on_this_tape}
                all_anchors = {**anchors, **{index_of[row["performance_id"]]: int(row["track_number"]) for row in on_this_tape}}
                found, covered = fill_gaps_on_tape(
                    show_performances, songs, all_anchors, track_titles, wanted, matcher,
                    medleys=phase == "medleys", whole_songs=phase in ("whole_songs", "medleys"),
                )
                for index, track_number, how, spans in found:
                    source_file = track_file[track_number]
                    if track_number in taken or index not in wanted or not playable(record, source_file):
                        continue
                    add(recording_id, record, index, track_number, source_file, "same_tape" if role == "same_tape" else "other_tape_variant", how, spans)
                    taken.add(track_number)
                    # The later passes of a song whose one track went to its
                    # first pass are inside that file.
                    for other in covered.get(index, ()):
                        if other in wanted:
                            wanted.discard(other)
                            counts["later_pass_inside_the_first_pass_file"] += 1

        # A new link whose file evidently runs on into the next song states no length.
        for position in range(show_start, len(additions)):
            row, entry = additions[position], review[position]
            anchors, track_file = aligned.get(row["recording_id"], ({}, {}))
            on_this_tape = {
                **anchors,
                **{index_of[other["performance_id"]]: int(other["track_number"]) for other in additions[show_start:] if other["recording_id"] == row["recording_id"]},
            }
            if ia.SPANS_MORE_MARK not in row["notes"] and runs_on(
                index_of[row["performance_id"]], int(row["track_number"]), on_this_tape, sorted(track_file), show_performances
            ):
                row["notes"] += f" {ia.SPANS_MORE_MARK}."
                entry["opens_a_medley"] = True
                entry["runs_on_into_the_next_song"] = True
                counts["runs_on_into_the_next_song"] += 1

    print(f"added {len(additions)} mapped tracks on {len(used_identifiers)} tapes")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    review_path = args.review_out or REVIEW_PATH
    if args.review_out or not args.dry_run:
        with review_path.open("w", encoding="utf-8") as handle:
            for row in review:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    if args.dry_run:
        print("dry run: canonical files not written")
        return 0

    with (CANONICAL / "performance_recordings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAPPING_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(mapping + additions)
    # A song this pass mapped on an earlier run and no longer maps loses the
    # link that run caused; the link normalizer keeps links it does not
    # regenerate, so it would otherwise stay.
    dropped = own - {row["performance_id"] for row in additions}
    if dropped:
        with (CANONICAL / "performance_links.csv").open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            link_fields = list(reader.fieldnames or [])
            all_links = list(reader)
        kept = [
            row
            for row in all_links
            if not (row["platform"] == "archive" and row["link_type"] == "recording-track" and row["performance_id"] in dropped)
        ]
        with (CANONICAL / "performance_links.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=link_fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(kept)
        print(f"withdrew {len(all_links) - len(kept)} links for songs this pass no longer maps")
    compact = [items[identifier] for identifier in sorted(used_identifiers - preserved)]
    ia.ITEM_FILES_PATH.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in compact),
        encoding="utf-8",
    )
    print(f"wrote performance_recordings.csv, {REVIEW_PATH.name} and {ia.ITEM_FILES_PATH.name} ({len(compact)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
