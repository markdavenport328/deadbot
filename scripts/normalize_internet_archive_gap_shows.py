#!/usr/bin/env python3
"""Attach gap-pass Internet Archive tapes to the shows whose setlist they match.

``collect/fetch_internet_archive_gap_shows.py`` preserves, for every date that
has a canonical show with a setlist but no track audio, the Archive items found
for that date and their metadata.  The earlier index pass could not use those
items: it skips any date shared by two canonical shows (an early/late pair),
because a date does not say which show a tape holds.

This script decides by tracks instead.  An item is evaluated against every
canonical show on its date with the same aligners the track pass uses
(``normalize_internet_archive_tracks.evaluate_item``) and is attached to a show
only when

* its track titles align to exactly one show's setlist,
* on a date shared by several shows, the alignment is complete or settles at
  least ``MIN_MATCHES_ON_SHARED_DATE`` tracks (one or two shared titles do not
  say which show a tape holds),
* on a shared date, the venue the item names (its ``venue`` or title) does
  not belong to another show of that date and not to this one, and
* the item's own early/late label (a ``early`` or ``late`` word in its
  identifier) does not name the other end of the date's show order, and
* that show has no track audio from another tape yet.

An item that aligns to several shows (an early-and-late tape, or setlists that
share songs), to none, or only to a show that is already covered, is held in
``data/raw/recordings/internet-archive-gap-review.jsonl`` with the reason; it
is never guessed onto a show.  For each show it attaches the one item the
track pass would choose (the first that aligns every performance in the
pipeline's representative order, else the one with the most settled tracks) as
a new ``recordings.csv`` row, with the same metadata fields the representative
enrichment fills.

Run order: the collector, this script, ``normalize_internet_archive_tracks.py``
(whose fallback pass maps the new rows to performances), then
``normalize_internet_archive_track_links.py``.  Rerunning is idempotent.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "collect"))

import normalize_internet_archive_tracks as ia_tracks  # noqa: E402
from normalize_internet_archive_1972_index import slugify  # noqa: E402
from normalize_internet_archive_1972_metadata import source_type  # noqa: E402

ROOT = SCRIPTS_DIR.parent
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw" / "recordings"
SEARCH_PATH = RAW / "internet-archive-gap-search.jsonl"
REVIEW_PATH = RAW / "internet-archive-gap-review.jsonl"
MIN_MATCHES_ON_SHARED_DATE = 3
NOTE = (
    "Found by the Internet Archive date search for a show without track audio; full item metadata "
    "preserved in data/raw/recordings/internet-archive-alternate-items.jsonl; the source track "
    "titles align to this show's setlist; track descriptions remain source-attributed."
)


def read_rows(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def item_records() -> dict[str, dict]:
    records: dict[str, dict] = {}
    for path in sorted(RAW.glob("internet-archive-*-representatives.jsonl")) + [ia_tracks.ALTERNATES_PATH]:
        for record in ia_tracks.read_item_records(path):
            if "files" in record.get("raw_payload", {}):
                records.setdefault(record["source_record_id"], record)
    return records


VENUE_STOPWORDS = {"the", "of", "at", "and", "a", "live", "grateful", "dead"}


def venue_tokens(value: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    return {token for token in re.findall(r"[a-z0-9]+", folded) if token not in VENUE_STOPWORDS}


def venue_matches(venue_name: str, item_text: str) -> bool:
    """True when the item's venue text names this venue (most of its words appear)."""

    wanted = venue_tokens(venue_name)
    return bool(wanted) and len(wanted & venue_tokens(item_text)) / len(wanted) >= 0.6


def label_position(identifier: str) -> str:
    """"first" for an early-only tape, "last" for a late-only tape, else empty."""

    words = re.split(r"[^a-z0-9]+", identifier.casefold())
    early = any(word.startswith("early") for word in words)
    late = any(word.startswith("late") for word in words)
    return "first" if early and not late else "last" if late and not early else ""


def recording_row(identifier: str, show_id: str, record: dict) -> dict[str, str]:
    metadata = record["raw_payload"].get("metadata", {})
    row = {
        "recording_id": f"recording-archive-{slugify(identifier)}",
        "show_id": show_id,
        "source_type": "",
        "taper": "",
        "transferer": "",
        "shnid": "",
        "archive_identifier": identifier,
        "source_description": metadata.get("source", "") or metadata.get("title", ""),
        "lineage": "",
        "source_url": f"https://archive.org/details/{identifier}",
        "notes": NOTE,
    }
    inferred = source_type(metadata.get("source", ""))
    if inferred:
        row["source_type"] = inferred
    elif ".sbd." in identifier.casefold():
        row["source_type"] = "SBD"
    elif ".aud." in identifier.casefold():
        row["source_type"] = "AUD"
    for field in ("taper", "transferer", "shnid", "lineage"):
        if metadata.get(field):
            row[field] = str(metadata[field])
    return row


def main() -> int:
    songs, recordings_by_identifier, performances, _ = ia_tracks.load_rows()
    fields, recordings = read_rows("recordings.csv")
    _, shows = read_rows("shows.csv")
    _, performance_recordings = read_rows("performance_recordings.csv")
    show_date = {row["show_id"]: row["show_date"] for row in shows}
    shows_on_date: dict[str, list[str]] = defaultdict(list)
    canonical_on_date: dict[str, int] = defaultdict(int)
    all_shows_on_date: dict[str, list[str]] = defaultdict(list)
    _, venues = read_rows("venues.csv")
    venue_names = {row["venue_id"]: row["name"] for row in venues}
    venue_name = {row["show_id"]: venue_names.get(row["venue_id"], "") for row in shows}
    for show_id, date in show_date.items():
        canonical_on_date[date] += 1
        all_shows_on_date[date].append(show_id)
        if performances.get(show_id):
            shows_on_date[date].append(show_id)

    performance_show = {row["performance_id"]: show_id for show_id, rows in performances.items() for row in rows}
    # Rows an earlier run of this script added are regenerated, not kept.
    gap_recordings = {row["recording_id"] for row in recordings if row["notes"] == NOTE}
    recordings = [row for row in recordings if row["notes"] != NOTE]
    recordings_by_identifier = {
        identifier: row for identifier, row in recordings_by_identifier.items() if row["notes"] != NOTE
    }
    # A show is open to a gap tape when no tape other than a gap tape maps to it.
    covered_by_other: set[str] = set()
    for row in performance_recordings:
        show_id = performance_show.get(row["performance_id"], "")
        if show_id and row["recording_id"] not in gap_recordings:
            covered_by_other.add(show_id)

    catalog_keys: set[str] = set()
    for title in songs.values():
        catalog_keys |= ia_tracks.title_keys(title)
    items = item_records()
    searches = [json.loads(line) for line in SEARCH_PATH.read_text(encoding="utf-8").splitlines() if line]

    review: list[dict] = []
    additions: dict[str, dict] = {}
    counts: dict[str, int] = defaultdict(int)
    for search in searches:
        response = search["raw_payload"].get("response")
        if response is None:
            continue
        date = search["raw_payload"]["date"]
        date_shows = sorted(shows_on_date.get(date, []))
        found = {doc["identifier"] for doc in response.get("docs", [])}
        found |= {identifier for identifier, row in recordings_by_identifier.items() if row["show_id"] in date_shows}
        accepted_by_show: dict[str, list[tuple[bool, str, int, str, list]]] = defaultdict(list)
        for identifier in sorted(found):
            record = items.get(identifier)
            base = {"date": date, "archive_identifier": identifier, "date_show_ids": date_shows}
            if record is None:
                review.append({**base, "status": "held", "reason": "item_metadata_not_preserved"})
                counts["held:item_metadata_not_preserved"] += 1
                continue
            outcomes = {}
            for show_id in date_shows:
                status, matches, reason, _, source_tracks, aligner = ia_tracks.evaluate_item(
                    record, performances[show_id], songs, catalog_keys
                )
                outcomes[show_id] = (status, matches, reason, aligner, len(source_tracks))
            accepted = [show_id for show_id, outcome in outcomes.items() if outcome[0].startswith("accepted")]
            summary = {
                show_id: {"status": outcome[0], "matched_tracks": len(outcome[1]), "reason": outcome[2]}
                for show_id, outcome in outcomes.items()
            }
            existing = recordings_by_identifier.get(identifier)
            if existing is not None:
                review.append({**base, "status": "skipped", "reason": "item_already_attached_to_a_show", "attached_show_id": existing["show_id"], "per_show": summary})
                counts["skipped:item_already_attached"] += 1
                continue
            if not date_shows:
                review.append({**base, "status": "held", "reason": "date_has_no_canonical_show_with_a_setlist"})
                counts["held:no_show_with_setlist"] += 1
                continue
            if not accepted:
                reason = sorted({outcome[2] for outcome in outcomes.values()})
                review.append({**base, "status": "held", "reason": "no_show_setlist_aligns:" + ",".join(reason), "per_show": summary})
                counts["held:no_show_setlist_aligns"] += 1
                continue
            if len(accepted) > 1:
                review.append({**base, "status": "held", "reason": "aligns_to_more_than_one_show_on_date", "per_show": summary})
                counts["held:aligns_to_several_shows"] += 1
                continue
            show_id = accepted[0]
            if canonical_on_date[date] > 1:
                metadata = record["raw_payload"].get("metadata", {})
                item_text = " ".join(str(metadata.get(field) or "") for field in ("venue", "title"))
                named = {sid for sid in all_shows_on_date[date] if venue_matches(venue_name[sid], item_text)}
                if named and show_id not in named:
                    review.append({**base, "status": "held", "reason": "item_names_the_venue_of_another_show_on_date", "show_id": show_id, "item_venue": metadata.get("venue", ""), "per_show": summary})
                    counts["held:item_names_other_venue"] += 1
                    continue
            if canonical_on_date[date] > 1:
                ordered_shows = sorted(all_shows_on_date[date])
                expected = {"first": ordered_shows[0], "last": ordered_shows[-1]}.get(label_position(identifier))
                if expected and expected != show_id:
                    review.append({**base, "status": "held", "reason": "early_late_label_disagrees_with_the_show_order", "show_id": show_id, "per_show": summary})
                    counts["held:label_disagrees_with_order"] += 1
                    continue
            if canonical_on_date[date] > 1 and outcomes[show_id][0] != "accepted_full" and len(outcomes[show_id][1]) < MIN_MATCHES_ON_SHARED_DATE:
                review.append({**base, "status": "held", "reason": "too_few_matching_tracks_to_place_a_tape_on_a_shared_date", "show_id": show_id, "per_show": summary})
                counts["held:too_few_matches_on_shared_date"] += 1
                continue
            if show_id in covered_by_other:
                review.append({**base, "status": "held", "reason": "show_already_has_track_audio_from_another_tape", "show_id": show_id, "per_show": summary})
                counts["held:show_already_covered"] += 1
                continue
            status, matches, _, aligner, _ = outcomes[show_id]
            accepted_by_show[show_id].append((status == "accepted_full", identifier, len(matches), aligner, summary))

        for show_id, candidates in sorted(accepted_by_show.items()):
            # The track pass's own choice: the first item that aligns every
            # performance in representative order, else the most settled tracks.
            ordered = sorted(candidates, key=lambda item: ia_tracks.representative_rank(item[1]))
            full = [item for item in ordered if item[0]]
            chosen = full[0] if full else max(ordered, key=lambda item: item[2])
            for item in ordered:
                is_chosen = item is chosen
                review.append(
                    {
                        "date": date,
                        "archive_identifier": item[1],
                        "date_show_ids": date_shows,
                        "status": "attached" if is_chosen else "not_chosen",
                        "reason": "" if is_chosen else "another_aligned_tape_chosen_for_the_show",
                        "show_id": show_id,
                        "matched_tracks": item[2],
                        "canonical_performances": len(performances[show_id]),
                        "aligner": item[3],
                        "per_show": item[4],
                    }
                )
                counts["attached" if is_chosen else "not_chosen"] += 1
            additions[chosen[1]] = recording_row(chosen[1], show_id, items[chosen[1]])

    by_archive = {row["archive_identifier"]: row for row in recordings}
    for identifier, row in additions.items():
        by_archive.setdefault(identifier, row)
    rows = sorted(by_archive.values(), key=lambda row: (row["show_id"], row["archive_identifier"]))
    seen: set[str] = set()
    for row in rows:
        if row["recording_id"] in seen:
            row["recording_id"] += "-" + hashlib.sha1(row["archive_identifier"].encode("utf-8")).hexdigest()[:8]
        seen.add(row["recording_id"])
    with (CANONICAL / "recordings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    review.sort(key=lambda row: (row["date"], row["archive_identifier"]))
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for row in review:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"{len(searches)} dates searched; {dict(sorted(counts.items()))}")
    print(f"recordings.csv now has {len(rows)} rows; review: {REVIEW_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
