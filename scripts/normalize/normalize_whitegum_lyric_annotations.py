#!/usr/bin/env python3
"""Catalog the indexed whitegum.com song pages as stored resources.

Reads ``data/raw/songs/whitegum-lyric-annotations.jsonl`` (written by
``scripts/collect/collect_whitegum_lyric_annotations.py``) and appends one
``resources.csv`` row per confirmed page (``resource_type
lyric-annotation``), plus a ``resource_songs`` row with relationship_type
``annotates`` for every song the collector resolved to exactly one live page.
A song the collector held (its title matched more than one distinct page) is
written to ``data/editorial/lore-mapping-held-whitegum.jsonl`` with both
candidate pages; each candidate still gets its own resource row, only the
relationship is withheld. A song the collector could not find at source
(``not found at source``) gets no row at all — there is nothing to catalog.

Idempotency: a page is matched to any existing ``resources.csv`` row by
``source_url``; a rerun over an unchanged raw file reproduces byte-identical
CSVs and held queue, and never rewrites a row this pass wrote on an earlier
run.

Usage::

    PYTHONPATH=. python scripts/normalize/normalize_whitegum_lyric_annotations.py
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
    RESOURCE_SONG_FIELDS,
    append_csv,
    read_csv,
    read_jsonl,
)

RAW_PATH = ROOT / "data" / "raw" / "songs" / "whitegum-lyric-annotations.jsonl"
CANONICAL = ROOT / "data" / "canonical"
HELD_PATH = ROOT / "data" / "editorial" / "lore-mapping-held-whitegum.jsonl"
RESOURCE_TYPE = "lyric-annotation"
RELATIONSHIP = "annotates"


def url_key(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip().casefold()).rstrip("/")


def resource_id_for(url: str) -> str:
    """A stable id per *page*, not per song: a held song has two distinct pages.

    Derived from the page's own filename (e.g. ``COMESTIM.HTM`` -> ``comestim``)
    rather than the canonical song id, so the two candidate pages for a held
    song (same song_id, different URLs — "Comes A Time" the Grateful Dead
    original and "Comes A Time" the Phil & Friends cover) never collide on one
    resource_id.
    """

    stem = url.rstrip("/").rsplit("/", 1)[-1]
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", stem)
    return f"resource-whitegum-{re.sub(r'[^a-z0-9]+', '-', stem.casefold()).strip('-')}"


def resource_row(payload: dict[str, Any], url: str, title_fallback: str) -> dict[str, str]:
    title = payload.get("title") or title_fallback
    return {
        "resource_id": resource_id_for(url),
        "resource_type": RESOURCE_TYPE,
        "title": title,
        "creator": payload.get("creator") or "",
        "source_name": payload["source_name"],
        "source_url": url,
        "published_date": "",
        "notes": (
            "Alex Allan's Grateful Dead Lyric and Song Finder page for this song, with lyric-variant "
            "notes and a link to David Dodd's Annotated Grateful Dead Lyrics. Indexed as metadata only; "
            "lyrics and annotation text are not stored."
        ),
    }


def _blank_counts() -> dict[str, Any]:
    return {
        "pages_read": 0,
        "resources_written": 0,
        "already_cataloged": 0,
        "song_rows_written": 0,
        "songs_mapped": 0,
        "held": 0,
    }


def normalize(raw_path: Path, canonical_dir: Path, out_dir: Path, held_path: Path) -> dict[str, Any]:
    songs_by_id = {row["song_id"]: row["title"] for row in read_csv(canonical_dir / "songs.csv")}
    resources = read_csv(canonical_dir / "resources.csv")
    resource_songs = read_csv(canonical_dir / "resource_songs.csv")
    owner_of_url = {url_key(row["source_url"]): row["resource_id"] for row in resources}
    known_song_links = {(row["resource_id"], row["song_id"], row["relationship_type"]) for row in resource_songs}

    counts = _blank_counts()
    new_resources: list[dict[str, str]] = []
    new_song_rows: list[dict[str, str]] = []
    mapped_songs: set[str] = set()

    records = read_jsonl(raw_path) if raw_path.exists() else []
    if not records or records[0]["raw_payload"].get("record_type") != "pass_metadata" or records[0]["raw_payload"].get("status") != "ok":
        print(f"  skipping {raw_path.name}: no complete pass metadata")
        return {"counts": counts, "held_path": None}

    # Group this pass's page records by song, so a held (ambiguous) song's
    # two-or-more candidate pages are recognized even though each is its own
    # resource row.
    pages_by_song: dict[str, list[dict[str, Any]]] = {}
    for record in records[1:]:
        payload = record["raw_payload"]
        if payload.get("record_type") != "page":
            continue
        counts["pages_read"] += 1
        pages_by_song.setdefault(payload["song_id"], []).append(record)

    held: list[dict[str, Any]] = []
    for song_id, page_records in sorted(pages_by_song.items()):
        is_held = len(page_records) > 1
        for record in page_records:
            payload = record["raw_payload"]
            url = record["source_url"]
            resource_id = resource_id_for(url)
            key_for_url = url_key(url)
            existing_owner = owner_of_url.get(key_for_url)
            if existing_owner is not None and existing_owner != resource_id:
                counts["already_cataloged"] += 1
                continue
            if existing_owner is None:
                new_resources.append(resource_row(payload, url, songs_by_id.get(song_id, "")))
                owner_of_url[key_for_url] = resource_id
                counts["resources_written"] += 1
            else:
                counts["already_cataloged"] += 1

            if is_held:
                continue
            mapped_songs.add(song_id)
            link_key = (resource_id, song_id, RELATIONSHIP)
            if link_key in known_song_links:
                continue
            known_song_links.add(link_key)
            new_song_rows.append(
                {"resource_id": resource_id, "song_id": song_id, "relationship_type": RELATIONSHIP, "notes": "The song's title matched exactly one page on the site's own index."}
            )
            counts["song_rows_written"] += 1

        if is_held:
            counts["held"] += 1
            held.append(
                {
                    "song_id": song_id,
                    "reason": "The song's title matched more than one distinct page on the site's own index.",
                    "candidates": [record["source_url"] for record in page_records],
                }
            )

    counts["songs_mapped"] = len(mapped_songs)

    new_resources.sort(key=lambda row: row["resource_id"])
    new_song_rows.sort(key=lambda row: (row["resource_id"], row["song_id"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (
        ("resources.csv", new_resources, RESOURCE_FIELDS),
        ("resource_songs.csv", new_song_rows, RESOURCE_SONG_FIELDS),
    ):
        source = canonical_dir / name
        target = out_dir / name
        if target.resolve() != source.resolve():
            target.write_bytes(source.read_bytes())
        append_csv(target, rows, fields)

    held.sort(key=lambda entry: entry["song_id"])
    held_path.parent.mkdir(parents=True, exist_ok=True)
    with held_path.open("w", encoding="utf-8") as handle:
        for entry in held:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")

    return {"counts": counts, "held_path": str(held_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_PATH, help="the collector's raw JSONL file")
    parser.add_argument("--canonical-dir", type=Path, default=CANONICAL, help="canonical CSV directory (read only)")
    parser.add_argument("--out-dir", type=Path, default=CANONICAL, help="directory the updated CSVs are written to")
    parser.add_argument("--held-path", type=Path, default=HELD_PATH, help="path for the held-mapping queue")
    args = parser.parse_args()

    result = normalize(args.raw, args.canonical_dir, args.out_dir, args.held_path)
    counts = result["counts"]
    print(f"{counts['pages_read']} page(s) read")
    print(f"  resources: {counts['resources_written']} written, {counts['already_cataloged']} already cataloged (URL already in resources.csv)")
    print(f"  relationships: {counts['song_rows_written']} song row(s) ({counts['songs_mapped']} distinct songs)")
    print(f"  held: {counts['held']} -> {result['held_path']}")


if __name__ == "__main__":
    main()
