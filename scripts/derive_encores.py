#!/usr/bin/env python3
"""Mark encores in data/canonical/performances.csv.

gdshowsdb has no set labels, so an encore arrives as one more numbered set and
every card printed "Set 3" for Cornell's One More Saturday Night. This script
finds the shows whose last set is an encore and, for those sets only, writes
`encore = true` and `set_label = "Encore"`. `performance_id` and `set_number`
never change, so every reference to a performance still resolves and the encore
keeps its place in the show's order.

Two rules, applied to the last set of a show:

1. Structure. The show has three or more sets, the last set has one or two
   songs, and the set before it has five or more. A set that short after a
   full set is an encore; three-set shows with a real third set are longer than
   that and are not touched. (Of the 567 shows with archive.org tape evidence
   for this pattern, 563 name the whole last set as the encore; in the other
   four the tape names a song from the end of the previous set as the encore,
   so the last set is still part of the encore or follows it.)
2. Tape evidence. The show has two or more sets, the last set has up to four
   songs, and one archive.org tape of the show names every one of those songs
   as the encore, and names nothing outside the set: track titles written "E: Song"
   or "Song (encore)", an "Encore Break" track that the last set's songs follow
   in order, or an "Encore:" line in the taper's description.

Shows with two sets or fewer and no tape evidence are left alone (an early show
whose second "set" is one or two songs may only be all that is known), as are
last sets of three or more songs without evidence (a long final set can be a
real set, or the end of the second set).

Idempotent. Every change is logged to data/raw/corrections/encores-derived.jsonl
so it can be reviewed or reverted.

    python scripts/derive_encores.py
"""

from __future__ import annotations

import csv
import glob
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_RECORDINGS = ROOT / "data" / "raw" / "recordings"
LOG = ROOT / "data" / "raw" / "corrections" / "encores-derived.jsonl"

PERFORMANCE_FIELDS = [
    "performance_id", "show_id", "song_id", "set_number", "set_label", "position_in_set",
    "encore", "segue_into_next", "performance_notes", "source_key", "source_record_id",
]
MAIN_SET_MINIMUM = 5
SHORT_ENCORE_MAXIMUM = 2
TAPE_ENCORE_MAXIMUM = 4

ENCORE_PREFIX = re.compile(r"^\s*(?:e\d?|encore)\s*[:;.\-)]\s*", re.IGNORECASE)
ENCORE_SUFFIX = re.compile(r"\(\s*encore\s*\)|\[\s*encore\s*\]", re.IGNORECASE)
ENCORE_MARKER = re.compile(r"encore\s*break|break\s*before\s*encore|^\W*encore\W*$|^\W*e\W*$", re.IGNORECASE)
DESCRIPTION_ENCORE = re.compile(r"encore\s*\d?\s*[:\-](.{0,400})", re.IGNORECASE | re.DOTALL)
TAPE_FORMATS = {"Flac", "VBR MP3", "24bit Flac", "Ogg Vorbis", "Shorten", "MP3"}


def title_key(value: str) -> str:
    value = html.unescape(value).casefold().replace("&", "and").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", "", value)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tape_items() -> list[dict]:
    """Every archive.org item with its date, ordered track titles and description."""
    items = []
    for path in sorted(glob.glob(str(RAW_RECORDINGS / "internet-archive-*-representatives.jsonl"))):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            payload = record["raw_payload"]
            metadata = payload.get("metadata", {})
            tracks = set()
            for file in payload.get("files", []):
                if file.get("source") == "original" and file.get("title") and file.get("format") in TAPE_FORMATS:
                    number = re.sub(r"\D.*", "", str(file.get("track", "0"))) or "0"
                    tracks.add((int(number), file["title"]))
            description = metadata.get("description", "")
            if isinstance(description, list):
                description = " ".join(description)
            items.append({
                "id": record["source_record_id"],
                "date": metadata.get("date", ""),
                "tracks": sorted(tracks),
                "description": description,
            })
    return items


def match_songs(tokens: list[str], songs: list[tuple[str, str]]) -> set[str]:
    """performance_ids whose song title is the token (or the token with a short suffix)."""
    matched = set()
    for token in tokens:
        token_key = title_key(token)
        for performance_id, song_key in songs:
            if song_key and (token_key == song_key or (len(song_key) >= 6 and song_key in token_key and len(token_key) <= len(song_key) + 14)):
                matched.add(performance_id)
    return matched


def item_encores(item: dict, songs: list[tuple[str, str]]) -> tuple[set[str], str]:
    """(performance_ids this tape names as encore, how)."""
    named: set[str] = set()
    how: list[str] = []
    after_marker = False
    for _, title in item["tracks"]:
        if ENCORE_MARKER.search(title):
            after_marker = True
            continue
        if ENCORE_PREFIX.match(title):
            found = match_songs([ENCORE_PREFIX.sub("", title)], songs)
            named |= found
            after_marker = True
            if found:
                how.append("track title 'E:'")
        elif ENCORE_SUFFIX.search(title):
            found = match_songs([ENCORE_SUFFIX.sub("", title)], songs)
            named |= found
            if found:
                how.append("track title '(encore)'")
        elif after_marker:
            found = match_songs([title], songs)
            named |= found
            if found:
                how.append("track after 'Encore Break'")
    description = item["description"]
    match = DESCRIPTION_ENCORE.search(description)
    if match:
        segment = re.split(r"</span>|</div>|set\s*\d|<div", match.group(1), flags=re.IGNORECASE)[0]
        tokens = [re.sub(r"<[^>]+>", "", t).strip(" *>-") for t in re.split(r"<br\s*/?>|>|\n|,|->|;", segment)]
        found = match_songs([t for t in tokens if t], songs)
        named |= found
        if found:
            how.append("description 'Encore:'")
    return named, ", ".join(sorted(set(how)))


def main() -> None:
    performances = read_csv(CANONICAL / "performances.csv")
    titles = {row["song_id"]: row["title"] for row in read_csv(CANONICAL / "songs.csv")}

    shows: dict[str, dict[int, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in performances:
        shows[row["show_id"]][int(row["set_number"])].append(row)
    for sets in shows.values():
        for rows in sets.values():
            rows.sort(key=lambda r: int(r["position_in_set"]))

    items_by_show: dict[str, list[dict]] = defaultdict(list)
    for item in tape_items():
        if item["date"]:
            items_by_show["gd-" + item["date"]].append(item)

    chosen: dict[tuple[str, int], tuple[str, str]] = {}
    left_short: list[str] = []
    left_long: list[str] = []
    for show_id, sets in sorted(shows.items()):
        last_number = max(sets)
        last = sets[last_number]
        if any(row["encore"] == "true" for row in last) and len(last) > TAPE_ENCORE_MAXIMUM:
            continue  # hand-marked encores inside a longer final set (Veneta) stay as they are
        sizes = [len(sets[n]) for n in sorted(sets)]
        if len(sets) >= 3 and sizes[-1] <= SHORT_ENCORE_MAXIMUM and sizes[-2] >= MAIN_SET_MINIMUM:
            chosen[(show_id, last_number)] = ("structure", "")
            continue
        if len(sets) >= 2 and len(last) <= TAPE_ENCORE_MAXIMUM:
            songs = [(row["performance_id"], title_key(titles[row["song_id"]])) for rows in sets.values() for row in rows]
            last_ids = {row["performance_id"] for row in last}
            for item in items_by_show.get(show_id, []):
                named, how = item_encores(item, songs)
                if named and last_ids <= named and named <= last_ids:
                    chosen[(show_id, last_number)] = ("tape", f"{item['id']}: {how}")
                    break
        if (show_id, last_number) not in chosen:
            if sizes[-1] <= SHORT_ENCORE_MAXIMUM and len(sets) >= 2:
                left_short.append(show_id)
            elif len(sets) >= 3 and sizes[-1] <= TAPE_ENCORE_MAXIMUM:
                left_long.append(show_id)

    log = []
    changed_rows = 0
    for row in performances:
        key = (row["show_id"], int(row["set_number"]))
        if key not in chosen:
            continue
        rule, evidence = chosen[key]
        if row["encore"] != "true" or row["set_label"] != "Encore":
            changed_rows += 1
        row["encore"] = "true"
        row["set_label"] = "Encore"
    for (show_id, number), (rule, evidence) in sorted(chosen.items()):
        log.append({
            "show_id": show_id,
            "set_number": number,
            "rule": rule,
            "evidence": evidence,
            "performance_ids": [row["performance_id"] for row in shows[show_id][number]],
        })

    write_csv(CANONICAL / "performances.csv", performances, PERFORMANCE_FIELDS)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("".join(json.dumps(entry) + "\n" for entry in log), encoding="utf-8")

    per_rule = Counter(rule for rule, _ in chosen.values())
    print(f"Shows with an encore set marked: {len(chosen)} ({dict(per_rule)}); rows changed this run: {changed_rows}")
    print(f"Left alone, short final set without evidence: {len(left_short)}")
    print(f"Left alone, three- or four-song final set without evidence: {len(left_long)}")
    (LOG.parent / "encores-left-alone.txt").write_text(
        "short final set, no tape evidence:\n" + "\n".join(left_short) + "\n\n3-4 song final set, no tape evidence:\n" + "\n".join(left_long) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
