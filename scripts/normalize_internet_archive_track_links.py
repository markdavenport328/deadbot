#!/usr/bin/env python3
"""Derive per-track Internet Archive playback links for mapped performances.

`normalize_internet_archive_tracks.py` decides which source track is which
canonical performance.  This script only turns each of those accepted
decisions into a resolvable URL of the form

    https://archive.org/details/{identifier}/{file_name}

which opens the archive.org web player positioned on that track.  It works
entirely from the preserved representative item metadata in
``data/raw/recordings/internet-archive-*-representatives.jsonl``; it does not
re-fetch item metadata and never retrieves audio.

The file for a track is chosen conservatively:

1. the file's track number must equal the mapped ``track_number``;
2. the file's title (or, for a derivative that carries no title, the title of
   the lossless original it was derived from) must normalize to the canonical
   song title with the same alias rules used for the track mapping;
3. a single ``VBR MP3`` file is preferred because the web player streams MP3;
   otherwise the lossless original selected by the track-mapping rules is
   used.

Anything else is held in ``internet-archive-track-link-review.jsonl`` with a
reason.  Nothing is guessed.

Optionally ``--verify-samples N`` requests up to N sample URLs (one per
second, GET, headers only) before writing; if any sample does not return
HTTP 200 the canonical file is left untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from normalize_internet_archive_tracks import audio_track_files, normalized_title  # noqa: E402

ROOT = SCRIPTS_DIR.parent
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "recordings"
LINKS_PATH = CANONICAL / "performance_links.csv"
REVIEW_PATH = RAW_DIR / "internet-archive-track-link-review.jsonl"

PLATFORM = "archive"
LINK_TYPE = "recording-track"
STREAM_FORMAT = "VBR MP3"
USER_AGENT = "Deadbot/0.1 (historical-show-context)"
REQUEST_INTERVAL_SECONDS = 1.0

LINK_FIELDS = [
    "performance_link_id",
    "performance_id",
    "platform",
    "link_type",
    "url",
    "title",
    "start_seconds",
    "duration_seconds",
    "is_official",
    "notes",
]


def parse_track_number(value: object) -> int | None:
    try:
        return int(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def effective_title_and_track(file_record: dict, files_by_name: dict[str, dict]) -> tuple[str, int | None]:
    """Use a derivative's own title/track, else those of its lossless original."""

    title = file_record.get("title") or ""
    track = parse_track_number(file_record.get("track")) if file_record.get("track") else None
    if title and track is not None:
        return title, track
    original = files_by_name.get(file_record.get("original") or "")
    if original:
        title = title or (original.get("title") or "")
        if track is None and original.get("track"):
            track = parse_track_number(original.get("track"))
    return title, track


def track_url(identifier: str, file_name: str) -> str:
    return f"https://archive.org/details/{identifier}/{urllib.parse.quote(file_name, safe='/')}"


def select_track_file(
    payload: dict,
    track_number: int,
    canonical_title: str,
) -> tuple[dict | None, str, str, list[str]]:
    """Return (file, selection_kind, hold_reason, titles_seen) for one track."""

    files = payload.get("files", [])
    files_by_name = {record.get("name", ""): record for record in files}
    titles_seen: list[str] = []

    mp3_matches: list[dict] = []
    for record in files:
        if record.get("format") != STREAM_FORMAT:
            continue
        title, track = effective_title_and_track(record, files_by_name)
        if track != track_number:
            continue
        if title:
            titles_seen.append(title)
        if title and normalized_title(title) == canonical_title:
            mp3_matches.append(record)
    if len(mp3_matches) == 1:
        return mp3_matches[0], "mp3", "", titles_seen
    if len(mp3_matches) > 1:
        # Several MP3 encodes of one lossless original (for example
        # "d1t03.mp3" and "d1t03_vbr.mp3") name the same track; only the
        # encode differs.  Choose the shortest name deterministically.  Any
        # other multiplicity is a real ambiguity and is held.
        originals = {record.get("original") or "" for record in mp3_matches}
        if len(originals) == 1 and originals != {""}:
            chosen = sorted(mp3_matches, key=lambda record: (len(record["name"]), record["name"]))[0]
            return chosen, "mp3_same_original_tiebreak", "", titles_seen
        return None, "", "multiple_mp3_files_for_track", titles_seen

    lossless_tracks, error = audio_track_files(payload)
    if error:
        return None, "", f"lossless_selection_{error}", titles_seen
    lossless = dict(lossless_tracks).get(track_number)
    if lossless is None:
        return None, "", "no_file_for_track_number", titles_seen
    title = lossless.get("title") or ""
    if title:
        titles_seen.append(title)
    if title and normalized_title(title) == canonical_title:
        return lossless, "lossless", "", titles_seen
    return None, "", "file_title_does_not_match_canonical_song", titles_seen


def load_inputs() -> tuple[dict[str, str], dict[str, str], dict[str, dict], list[dict], list[dict]]:
    with (CANONICAL / "songs.csv").open(newline="", encoding="utf-8") as handle:
        songs = {row["song_id"]: row["title"] for row in csv.DictReader(handle)}
    with (CANONICAL / "performances.csv").open(newline="", encoding="utf-8") as handle:
        performance_song = {row["performance_id"]: row["song_id"] for row in csv.DictReader(handle)}
    with (CANONICAL / "recordings.csv").open(newline="", encoding="utf-8") as handle:
        recordings = {row["recording_id"]: row for row in csv.DictReader(handle)}
    with (CANONICAL / "performance_recordings.csv").open(newline="", encoding="utf-8") as handle:
        performance_recordings = list(csv.DictReader(handle))
    with LINKS_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or ()) != LINK_FIELDS:
            raise SystemExit(f"unexpected performance_links.csv header: {reader.fieldnames!r}")
        existing_links = list(reader)
    return songs, performance_song, recordings, performance_recordings, existing_links


def load_representatives(identifiers: set[str]) -> dict[str, dict]:
    representatives: dict[str, dict] = {}
    for raw_path in sorted(RAW_DIR.glob("internet-archive-*-representatives.jsonl")):
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            identifier = record.get("source_record_id")
            if identifier in identifiers and identifier not in representatives:
                representatives[identifier] = record
    return representatives


def build_links(
    songs: dict[str, str],
    performance_song: dict[str, str],
    recordings: dict[str, dict],
    performance_recordings: list[dict],
    representatives: dict[str, dict],
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Derive candidate link rows and review records for every mapped track."""

    candidates: list[dict] = []
    review: list[dict] = []
    counts: dict[str, int] = defaultdict(int)

    ordered = sorted(
        performance_recordings,
        key=lambda row: (row["performance_id"], row["recording_id"], int(row["track_number"])),
    )
    for row in ordered:
        performance_id = row["performance_id"]
        recording = recordings.get(row["recording_id"])
        identifier = (recording or {}).get("archive_identifier", "")
        track_number = parse_track_number(row["track_number"])
        song_id = performance_song.get(performance_id, "")
        canonical_title = normalized_title(songs.get(song_id, ""))

        def hold(reason: str, titles_seen: list[str] | None = None) -> None:
            counts[f"held:{reason}"] += 1
            review.append(
                {
                    "source": "internet-archive",
                    "status": "held",
                    "reason": reason,
                    "performance_id": performance_id,
                    "recording_id": row["recording_id"],
                    "archive_identifier": identifier,
                    "track_number": row["track_number"],
                    "mapped_track_title": row.get("track_title", ""),
                    "canonical_song_title": songs.get(song_id, ""),
                    "file_titles_seen": sorted(set(titles_seen or [])),
                }
            )

        if recording is None or not identifier:
            hold("recording_has_no_archive_identifier")
            continue
        if track_number is None or not canonical_title:
            hold("unparseable_track_or_missing_canonical_song")
            continue
        record = representatives.get(identifier)
        if record is None:
            hold("no_representative_record")
            continue

        chosen, kind, reason, titles_seen = select_track_file(
            record.get("raw_payload", {}), track_number, canonical_title
        )
        if chosen is None:
            hold(reason, titles_seen)
            continue

        file_name = chosen["name"]
        counts[f"matched:{kind}"] += 1
        candidates.append(
            {
                "performance_link_id": f"performance-link-{performance_id}-archive-track",
                "performance_id": performance_id,
                "platform": PLATFORM,
                "link_type": LINK_TYPE,
                "url": track_url(identifier, file_name),
                "title": row.get("track_title") or chosen.get("title") or "",
                "start_seconds": "",
                "duration_seconds": row.get("duration_seconds", ""),
                "is_official": "false",
                "notes": (
                    f"Track {track_number} of Internet Archive item {identifier} "
                    f"({row['recording_id']}); file {file_name}. Derived from preserved "
                    "representative item metadata; no audio retrieved."
                ),
            }
        )
    return candidates, review, counts


def merge_links(existing: list[dict], candidates: list[dict], review: list[dict], counts: dict[str, int]) -> list[dict]:
    """Keep every existing row; add candidates whose url and id are both new."""

    by_url = {row["url"]: row for row in existing}
    by_id = {row["performance_link_id"]: row for row in existing}
    merged = list(existing)
    for candidate in candidates:
        if candidate["url"] in by_url:
            counts["existing_url_unchanged"] += 1
            continue
        if candidate["performance_link_id"] in by_id:
            counts["held:existing_link_id_with_different_url"] += 1
            review.append(
                {
                    "source": "internet-archive",
                    "status": "held",
                    "reason": "existing_link_id_with_different_url",
                    "performance_id": candidate["performance_id"],
                    "performance_link_id": candidate["performance_link_id"],
                    "existing_url": by_id[candidate["performance_link_id"]]["url"],
                    "candidate_url": candidate["url"],
                }
            )
            continue
        merged.append(candidate)
        by_url[candidate["url"]] = candidate
        by_id[candidate["performance_link_id"]] = candidate
        counts["written"] += 1
    merged.sort(key=lambda row: row["performance_link_id"])
    return merged


def choose_samples(candidates: list[dict], limit: int) -> list[dict]:
    """Pick a deterministic spread of candidates, including encoded-name and lossless cases."""

    if limit <= 0 or not candidates:
        return []
    step = max(1, len(candidates) // limit)
    samples = candidates[::step][:limit]
    chosen_urls = {row["url"] for row in samples}
    specials = [
        next((row for row in candidates if "%" in row["url"]), None),
        next((row for row in candidates if "file " in row["notes"] and not row["url"].casefold().endswith(".mp3")), None),
    ]
    for special in specials:
        if special is None or special["url"] in chosen_urls:
            continue
        if len(samples) >= limit:
            samples.pop()
        samples.append(special)
        chosen_urls.add(special["url"])
    return samples


def verify_samples(samples: list[dict]) -> list[dict]:
    results: list[dict] = []
    for index, row in enumerate(samples):
        if index:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        request = urllib.request.Request(row["url"], method="GET", headers={"User-Agent": USER_AGENT})
        status: int | str
        final_url = row["url"]
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            status = exc.code
        except urllib.error.URLError as exc:
            status = f"error: {exc.reason}"
        results.append({"url": row["url"], "status": status, "final_url": final_url})
        print(f"{status}\t{row['url']}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify-samples", type=int, default=0, metavar="N", help="GET up to N sample URLs (max 10) before writing")
    parser.add_argument("--dry-run", action="store_true", help="report counts without writing any file")
    args = parser.parse_args()

    songs, performance_song, recordings, performance_recordings, existing_links = load_inputs()
    identifiers = {
        recordings[row["recording_id"]]["archive_identifier"]
        for row in performance_recordings
        if row["recording_id"] in recordings
    }
    representatives = load_representatives(identifiers)
    candidates, review, counts = build_links(songs, performance_song, recordings, performance_recordings, representatives)
    merged = merge_links(existing_links, candidates, review, counts)

    print(f"performance_recordings rows: {len(performance_recordings)}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    print(f"performance_links rows after merge: {len(merged)} (existing {len(existing_links)})")

    if args.verify_samples:
        samples = choose_samples(candidates, min(args.verify_samples, 10))
        print(f"verifying {len(samples)} sample URLs, one per second")
        results = verify_samples(samples)
        if any(result["status"] != 200 for result in results):
            print("sample verification failed; canonical file not written", file=sys.stderr)
            return 1

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    with LINKS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LINK_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for entry in review:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {LINKS_PATH.relative_to(ROOT)} and {REVIEW_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
