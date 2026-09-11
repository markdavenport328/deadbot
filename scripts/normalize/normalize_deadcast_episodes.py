#!/usr/bin/env python3
"""Catalog the indexed Deadcast episodes as stored resources.

Reads ``data/raw/resources/deadcast-episode-index.jsonl`` (written by
``scripts/collect/collect_deadcast_episode_index.py``) and appends one
``resources.csv`` row per episode (``resource_type podcast-episode``), plus
conservative relationships to canonical shows and songs drawn from the
episode's own title. An episode whose title names neither is still a
resource; it is simply unmapped, not held.

Idempotency: an episode is matched to any existing ``resources.csv`` row by
``source_url`` first. Six Deadcast rows already existed before this pass (two
Veneta transcript pages, an American Beauty/Sugar Magnolia episode page, and
three transcript-page links whose URLs differ from the episode-page URLs this
pass indexes); a URL that already has a row is left completely alone —
neither the resource nor its relationships are touched — and counted as
"already cataloged". This also makes a rerun over an unchanged raw file
byte-identical: every row this pass previously wrote is a "known" URL on the
next run.

Mapping rules
-------------
Show: ``find_dates`` (shared with the research-blog normalizer) reads every
unambiguous calendar date named in the full episode title
(``YYYY-MM-DD``, ``M/D/YY``, ``M/D/YYYY``, ``Month D, YYYY``). Exactly one
date matching exactly one canonical show maps; two dates, a date matching two
shows, or a title with a month/day but no year (Deadcast often gives a bare
"6/27" or "4/78") all leave the episode unmapped rather than guessed at — the
methodology's instruction not to map a date that could name several shows or
no show at all.

Song: the text after the title's *last* colon is the episode's stated
subject (e.g. "Blues For Allah 50: Slipknot!" -> "Slipknot!"; a title with no
colon uses the whole title). That segment, and each of its parts if it
contains "/", is compared to every canonical song's ``match_key`` (shared
with the Dead.net essay normalizer, which already reads apostrophes, "&",
punctuation and stopwords as the same phrase). An exact match maps; a segment
whose key equals more than one canonical song's key is held; a segment that
exactly *prefixes* one or more canonical song keys without matching any of
them whole (e.g. "Weather Report Suite" against "Weather Report Suite Part 1"
*and* "...Prelude" — the same pair the Dead.net essay pass held for the same
reason) is also held, with those candidates; anything else is unmapped.

Usage::

    PYTHONPATH=. python scripts/normalize/normalize_deadcast_episodes.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "normalize"))

from normalize_blog_post_resources import (  # noqa: E402
    RESOURCE_FIELDS,
    RESOURCE_SHOW_FIELDS,
    RESOURCE_SONG_FIELDS,
    append_csv,
    find_dates,
    read_csv,
    read_jsonl,
)
from normalize_song_guide_resources import match_key  # noqa: E402

RAW_PATH = ROOT / "data" / "raw" / "resources" / "deadcast-episode-index.jsonl"
CANONICAL = ROOT / "data" / "canonical"
HELD_PATH = ROOT / "data" / "editorial" / "lore-mapping-held-deadcast.jsonl"
RESOURCE_TYPE = "podcast-episode"
SHOW_RELATIONSHIP = "show-oral-history"
SONG_RELATIONSHIP = "song-history-and-interview"


# --- lookups -----------------------------------------------------------------


def url_key(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip().casefold()).rstrip("/")


class SongLookup:
    """Canonical songs indexed by exact ``match_key`` for episode-segment matching."""

    def __init__(self, songs: list[dict[str, str]]) -> None:
        self.by_key: dict[tuple[str, ...], list[str]] = {}
        self.keys_by_song: dict[str, tuple[str, ...]] = {}
        for song in songs:
            key = match_key(song["title"])
            if not key:
                continue
            self.keys_by_song[song["song_id"]] = key
            self.by_key.setdefault(key, []).append(song["song_id"])

    def exact(self, text: str) -> list[str]:
        return sorted(self.by_key.get(match_key(text), []))

    def prefix_candidates(self, text: str) -> list[str]:
        """Songs whose key strictly starts with this text's key, for a near-miss hold.

        Catches "Weather Report Suite" (a Deadcast segment naming the suite as
        a whole) against the two canonical songs whose titles both start with
        those same three words — the same ambiguity the Dead.net essay pass
        held "Weather Report Suite" for.
        """

        key = match_key(text)
        if not key:
            return []
        found = [song_id for song_id, song_key in self.keys_by_song.items() if len(song_key) > len(key) and song_key[: len(key)] == key]
        return sorted(found)


def song_segment(title: str) -> str:
    """The text naming the episode's subject: after the last colon, or the whole title."""

    return title.rsplit(":", 1)[-1].strip() if ":" in title else title.strip()


def song_matches(title: str, songs: SongLookup) -> tuple[list[str], list[str] | None]:
    """``(song_ids, hold_candidates)`` for one episode title; at most one is non-empty."""

    segment = song_segment(title)
    exact = songs.exact(segment)
    if len(exact) == 1:
        return exact, None
    if len(exact) > 1:
        return [], exact
    if "/" in segment:
        matched: list[str] = []
        ambiguous: list[str] = []
        for part in segment.split("/"):
            part = part.strip(" \t\"'“”‘’-")
            if not part:
                continue
            found = songs.exact(part)
            if len(found) == 1:
                matched.append(found[0])
            elif len(found) > 1:
                ambiguous.extend(found)
        if matched:
            return sorted(set(matched)), None
        if ambiguous:
            return [], sorted(set(ambiguous))
    candidates = songs.prefix_candidates(segment)
    if len(candidates) > 1:
        return [], candidates
    return [], None


# --- records -----------------------------------------------------------------


def resource_id_for(url_slug: str) -> str:
    return f"resource-deadcast-{url_slug}"


def resource_row(payload: dict[str, Any], url: str) -> dict[str, str]:
    season = payload.get("season") or ""
    notes = f"Good Ol' Grateful Deadcast episode{f', Season {season}' if season else ''}. Indexed as metadata only; no transcript, description or audio is stored."
    return {
        "resource_id": resource_id_for(payload["url_slug"]),
        "resource_type": RESOURCE_TYPE,
        "title": payload.get("title") or "",
        "creator": "",
        "source_name": payload["source_name"],
        "source_url": url,
        "published_date": payload.get("published_date") or "",
        "notes": notes,
    }


def _blank_counts() -> dict[str, Any]:
    return {
        "episodes_read": 0,
        "resources_written": 0,
        "already_cataloged": 0,
        "song_rows_written": 0,
        "show_rows_written": 0,
        "songs_mapped": 0,
        "shows_mapped": 0,
        "unmapped": 0,
        "held": 0,
        "held_reasons": {},
    }


def normalize(raw_path: Path, canonical_dir: Path, out_dir: Path, held_path: Path) -> dict[str, Any]:
    songs = SongLookup(read_csv(canonical_dir / "songs.csv"))
    shows_by_date: dict[str, list[str]] = {}
    for show in read_csv(canonical_dir / "shows.csv"):
        shows_by_date.setdefault(show["show_date"], []).append(show["show_id"])

    resources = read_csv(canonical_dir / "resources.csv")
    resource_songs = read_csv(canonical_dir / "resource_songs.csv")
    resource_shows = read_csv(canonical_dir / "resource_shows.csv")
    owner_of_url = {url_key(row["source_url"]): row["resource_id"] for row in resources}
    known_song_links = {(row["resource_id"], row["song_id"], row["relationship_type"]) for row in resource_songs}
    known_show_links = {(row["resource_id"], row["show_id"], row["relationship_type"]) for row in resource_shows}

    counts = _blank_counts()
    new_resources: list[dict[str, str]] = []
    new_song_rows: list[dict[str, str]] = []
    new_show_rows: list[dict[str, str]] = []
    held: list[dict[str, Any]] = []
    mapped_songs: set[str] = set()
    mapped_shows: set[str] = set()

    records = read_jsonl(raw_path) if raw_path.exists() else []
    if not records or records[0]["raw_payload"].get("record_type") != "pass_metadata" or records[0]["raw_payload"].get("status") != "ok":
        print(f"  skipping {raw_path.name}: no complete pass metadata")
        return {"counts": counts, "held_path": None}

    for record in records[1:]:
        payload = record["raw_payload"]
        if payload.get("record_type") != "episode":
            continue
        counts["episodes_read"] += 1
        url = record["source_url"]
        title = payload.get("title") or ""
        resource_id = resource_id_for(payload["url_slug"])
        key_for_url = url_key(url)
        existing_owner = owner_of_url.get(key_for_url)

        if existing_owner is not None and existing_owner != resource_id:
            # A different resource_id already carries this URL (the two Veneta
            # episode pages and the Sugar Magnolia episode page were manually
            # cataloged before this pass, under their own ids). Leave that row
            # and its relationships exactly as they are.
            counts["already_cataloged"] += 1
            continue
        if existing_owner is None:
            new_resources.append(resource_row(payload, url))
            owner_of_url[key_for_url] = resource_id
        else:
            # This pass's own row from an earlier run: no new resource row,
            # but recompute the mapping below so a rerun's held queue and
            # relationship rows stay identical rather than going empty.
            counts["already_cataloged"] += 1

        show_ids, show_hold = show_mapping(title, shows_by_date)
        song_ids, song_hold = song_matches(title, songs)

        # "Mapped" reflects a resolved show/song regardless of whether the
        # relationship row is new or already recorded (a rerun), so the
        # printed counts stay accurate on every run, not just the first.
        wrote_anything = bool(show_ids) or bool(song_ids)
        for show_id in show_ids:
            mapped_shows.add(show_id)
            key = (resource_id, show_id, SHOW_RELATIONSHIP)
            if key in known_show_links:
                continue
            known_show_links.add(key)
            new_show_rows.append(
                {"resource_id": resource_id, "show_id": show_id, "relationship_type": SHOW_RELATIONSHIP, "notes": "The episode title names the show date."}
            )
            counts["show_rows_written"] += 1
        for song_id in song_ids:
            mapped_songs.add(song_id)
            key = (resource_id, song_id, SONG_RELATIONSHIP)
            if key in known_song_links:
                continue
            known_song_links.add(key)
            new_song_rows.append(
                {"resource_id": resource_id, "song_id": song_id, "relationship_type": SONG_RELATIONSHIP, "notes": "The episode title names the song."}
            )
            counts["song_rows_written"] += 1
            wrote_anything = True

        if show_hold or song_hold:
            reason, candidates = (
                (show_hold["reason"], show_hold["candidates"]) if show_hold else ("The episode title's subject matches more than one canonical song.", song_hold)
            )
            held.append({"resource_id": resource_id, "url": url, "title": title, "reason": reason, "candidates": candidates})
            counts["held"] += 1
            counts["held_reasons"][reason] = counts["held_reasons"].get(reason, 0) + 1
        elif not wrote_anything:
            counts["unmapped"] += 1

    counts["resources_written"] = len(new_resources)
    counts["songs_mapped"] = len(mapped_songs)
    counts["shows_mapped"] = len(mapped_shows)

    new_resources.sort(key=lambda row: row["resource_id"])
    new_song_rows.sort(key=lambda row: (row["resource_id"], row["song_id"]))
    new_show_rows.sort(key=lambda row: (row["resource_id"], row["show_id"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (
        ("resources.csv", new_resources, RESOURCE_FIELDS),
        ("resource_songs.csv", new_song_rows, RESOURCE_SONG_FIELDS),
        ("resource_shows.csv", new_show_rows, RESOURCE_SHOW_FIELDS),
    ):
        source = canonical_dir / name
        target = out_dir / name
        if target.resolve() != source.resolve():
            target.write_bytes(source.read_bytes())
        append_csv(target, rows, fields)

    held.sort(key=lambda entry: entry["resource_id"])
    held_path.parent.mkdir(parents=True, exist_ok=True)
    with held_path.open("w", encoding="utf-8") as handle:
        for entry in held:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")

    return {"counts": counts, "held_path": str(held_path)}


def show_mapping(title: str, shows_by_date: dict[str, list[str]]) -> tuple[list[str], dict[str, Any] | None]:
    dates = find_dates(title)
    if not dates:
        return [], None
    matched = {date: shows_by_date.get(date, []) for date in dates}
    if not any(matched.values()):
        return [], None
    if len(dates) > 1:
        candidates = [f"{date} ({', '.join(show_ids) if show_ids else 'no canonical show'})" for date, show_ids in matched.items()]
        return [], {"reason": "The episode title names more than one date.", "candidates": candidates}
    date = dates[0]
    show_ids = matched[date]
    if len(show_ids) > 1:
        return [], {"reason": f"{date} matches more than one canonical show.", "candidates": sorted(show_ids)}
    return [show_ids[0]], None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_PATH, help="the collector's raw JSONL file")
    parser.add_argument("--canonical-dir", type=Path, default=CANONICAL, help="canonical CSV directory (read only)")
    parser.add_argument("--out-dir", type=Path, default=CANONICAL, help="directory the updated CSVs are written to")
    parser.add_argument("--held-path", type=Path, default=HELD_PATH, help="path for the held-mapping queue")
    args = parser.parse_args()

    result = normalize(args.raw, args.canonical_dir, args.out_dir, args.held_path)
    counts = result["counts"]
    print(f"{counts['episodes_read']} episode(s) read")
    print(f"  resources: {counts['resources_written']} written, {counts['already_cataloged']} already cataloged (URL already in resources.csv)")
    print(f"  relationships: {counts['song_rows_written']} song row(s) ({counts['songs_mapped']} distinct songs), {counts['show_rows_written']} show row(s) ({counts['shows_mapped']} distinct shows)")
    print(f"  unmapped: {counts['unmapped']}; held: {counts['held']} -> {result['held_path']}")
    for reason, count in sorted(counts["held_reasons"].items(), key=lambda item: (-item[1], item[0])):
        print(f"    {count} x {reason}")


if __name__ == "__main__":
    main()
