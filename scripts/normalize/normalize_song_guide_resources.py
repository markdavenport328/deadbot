#!/usr/bin/env python3
"""Catalog the Dead.net song essays and Deadhead High guides as resources.

Reads the two raw files written by the collectors of this pass —
``data/raw/resources/deadnet-greatest-stories.jsonl`` and
``data/raw/resources/deadheadhigh-index.jsonl`` — and writes one
``resources.csv`` row per page plus conservative ``about`` relationships to
canonical songs and shows. A page whose subject cannot be resolved is still a
resource; its mapping goes to
``data/editorial/lore-mapping-held-{source}.jsonl`` with the reason and the
candidates, never guessed at.

Mapping rules
-------------
Song: the URL slug (Dead.net's ``greatest-stories-ever-told-<slug>`` tail, or
Deadhead High's ``/songs/<slug>``) matches exactly one canonical song under
``match_key`` — a comparison that reads apostrophes, ampersands, punctuation
and the stopwords Dead.net's path builder drops ("Attics Of My Life" ->
``attics-my-life``, "He's Gone" -> ``hes-gone``) as the same phrase. A slug
matching two songs, or none, is held with its candidates. A Dead.net
``/song/<slug>`` page carries the target's own song id, so it maps directly.

Show: a Deadhead High page whose slug is a full date maps to the show on that
date when exactly one canonical show sits there; two shows is a hold. This is
the same date rule the pass applies to archive items, and it is what lets the
featured-show pages map at all — Deadhead High names those pages by date.

Neither: the page is still stored as a resource with no relationship rows and
counted as "unmapped"; it never enters the held queue.

Canonical safety
----------------
``--canonical-dir`` is read and never written. Output goes to ``--out-dir``:
the canonical files are copied there byte for byte and this pass's rows are
appended, so an existing reviewed row is never rewritten, reordered or
reformatted. Pointing ``--out-dir`` at ``--canonical-dir`` appends in place.
A rerun over unchanged raw input reproduces byte-identical files.

Usage::

    PYTHONPATH=. python scripts/normalize/normalize_song_guide_resources.py \
        --out-dir /tmp/taskA-out
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "normalize"))

from normalize_blog_post_resources import (  # noqa: E402
    RESOURCE_FIELDS,
    RESOURCE_SHOW_FIELDS,
    RESOURCE_SONG_FIELDS,
    append_csv,
    read_csv,
    read_jsonl,
    slugify,
)

RAW_DIR = ROOT / "data" / "raw" / "resources"
CANONICAL = ROOT / "data" / "canonical"
HELD_DIR = ROOT / "data" / "editorial"
TARGETS_PATH = ROOT / "data" / "editorial" / "lore-targets-2026-09-08.json"

RELATIONSHIP = "about"
MAX_CANDIDATES = 5
MAX_NOTES_DESCRIPTION = 200

# One raw file per source, and the held queue each one writes.
RAW_FILES = {
    "deadnet": "deadnet-greatest-stories.jsonl",
    "deadheadhigh": "deadheadhigh-index.jsonl",
}

# Boilerplate a site sends on every page. It says nothing about the page, so it
# is not copied into the canonical notes.
GENERIC_DESCRIPTIONS = frozenset({"official site of the grateful dead", ""})

# Drupal's pathauto stopword list, which is what turns "Friend Of The Devil"
# into ``friend-devil`` and "Blues For Allah" into ``blues-allah`` on Dead.net,
# plus "like" ("Looks Like Rain" -> ``looks-rain``). Both sides of a comparison
# lose these words, so dropping them cannot introduce a match between two
# different songs; it only lets one song's two spellings meet.
STOPWORDS = frozenset(
    """a an and are as at be but by for if in into is it like no not of on or s such that the their
    then there these they this to was will with""".split()
)
# What is left of a contraction once the apostrophe goes: "it-s-all-over" is
# the slug spelling of "It's All Over", so a lone remnant rejoins the word
# before it.
CONTRACTION_REMNANTS = frozenset({"s", "t", "d", "m", "ll", "re", "ve"})

_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
# Drupal appends a counter when a path is already taken, so Dodd's "Box Of
# Rain" essay lives at ``greatest-stories-ever-told-box-rain-0``. The counter
# is part of the URL, not of the song's name.
_PATH_COUNTER = re.compile(r"-\d+$")
_QUOTED = re.compile(r"[\"“”'‘’](.+?)[\"“”'‘’]")


# --- matching ----------------------------------------------------------------


def match_key(value: str) -> tuple[str, ...]:
    """One comparable form for a song title or a URL slug.

    Apostrophes vanish rather than splitting a word, ``&`` reads as "and",
    punctuation is a separator, the path builder's stopwords are dropped, and a
    trailing "-ing" is read as "-in'" so "Feelin'" and "Feeling" agree.
    """

    text = value.replace("’", "'").replace("‘", "'").replace("ʼ", "'").replace("'", "")
    text = text.replace("&", " and ").casefold()
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", text):
        if token in CONTRACTION_REMNANTS and tokens:
            tokens[-1] += token
        else:
            tokens.append(token)
    kept = [token for token in tokens if token not in STOPWORDS] or tokens
    return tuple(token[:-1] if token.endswith("ing") and len(token) >= 5 else token for token in kept)


class SongIndex:
    """Canonical songs indexed by every match key they answer to."""

    def __init__(self, songs: list[dict[str, str]]) -> None:
        self.by_key: dict[tuple[str, ...], list[str]] = {}
        self.by_token: dict[str, set[str]] = {}
        for song in songs:
            song_id = song["song_id"]
            for value in (song["title"], song.get("slug", "")):
                key = match_key(value)
                if not key:
                    continue
                holders = self.by_key.setdefault(key, [])
                if song_id not in holders:
                    holders.append(song_id)
                for token in key:
                    self.by_token.setdefault(token, set()).add(song_id)

    def match(self, *values: str) -> tuple[list[str], tuple[str, ...]]:
        """Song ids for the first value that matches, with the key that matched."""

        for value in values:
            key = match_key(value)
            if key and key in self.by_key:
                return sorted(self.by_key[key]), key
        return [], match_key(values[0]) if values else ()

    def candidates(self, key: tuple[str, ...]) -> list[str]:
        """Songs sharing the most words with an unmatched key, for review."""

        scored: dict[str, int] = {}
        for token in key:
            for song_id in self.by_token.get(token, ()):
                scored[song_id] = scored.get(song_id, 0) + 1
        return [song_id for song_id, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:MAX_CANDIDATES]]


def slug_aliases(slug: str) -> list[str]:
    """A URL slug and the same slug without Drupal's duplicate-path counter."""

    aliases = [slug]
    trimmed = _PATH_COUNTER.sub("", slug)
    if trimmed and trimmed != slug:
        aliases.append(trimmed)
    return aliases


def quoted_titles(title: str) -> list[str]:
    """The song names a page title quotes, including the pairs in one essay.

    Dodd covers two songs at once often enough to matter: ``"Help on the
    Way"/"Slipknot"``, ``"Sugar Magnolia/Sunshine Daydream"``, ``"Lost Sailor"
    & "Saint Of Circumstance"``. Each name in such a title is a candidate, so
    a paired essay maps to both songs rather than to neither.
    """

    found: list[str] = []
    for group in _QUOTED.findall(title or ""):
        for part in re.split(r"[/>]|\s&\s", group):
            part = part.strip(" \t\"'“”‘’,-")
            if part and part not in found:
                found.append(part)
    return found


def url_key(url: str) -> str:
    """A resource URL without the parts that do not change which page it is."""

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/').casefold()}"


# --- output ------------------------------------------------------------------


def emit(canonical_dir: Path, out_dir: Path, name: str, rows: list[dict[str, str]], fields: list[str]) -> None:
    """Copy a canonical file to the output directory and append this pass's rows."""

    out_dir.mkdir(parents=True, exist_ok=True)
    source = canonical_dir / name
    target = out_dir / name
    if target.resolve() != source.resolve():
        target.write_bytes(source.read_bytes())
    append_csv(target, rows, fields)


def write_held(held_dir: Path, source: str, entries: list[dict[str, Any]]) -> Path:
    held_dir.mkdir(parents=True, exist_ok=True)
    path = held_dir / f"lore-mapping-held-{source}.jsonl"
    entries = sorted(entries, key=lambda entry: (entry["resource_id"], entry["reason"]))
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


# --- records -----------------------------------------------------------------


def resource_id_for(payload: dict[str, Any]) -> str:
    kind = payload["record_type"]
    if kind == "essay":
        return f"resource-deadnet-gset-{slugify(payload['url_slug'])}"
    if kind == "song_page":
        return f"resource-deadnet-song-{slugify(payload['url_slug'])}"
    return f"resource-deadheadhigh-{slugify(payload['url_path'])}"


def notes_for(payload: dict[str, Any]) -> str:
    kind = payload["record_type"]
    parts: list[str] = []
    if kind == "essay":
        parts.append("David Dodd's song-history and lyric-analysis essay in the Greatest Stories Ever Told series.")
    elif kind == "song_page":
        parts.append("Official song page: displayed title and credits.")
    elif payload.get("section") == "songs":
        parts.append("Per-song listening guide: performance counts, first and last dates and listening links.")
    else:
        parts.append("Listener guide page.")
    description = re.sub(r"\s+", " ", payload.get("description") or "").strip()
    if description.casefold() not in GENERIC_DESCRIPTIONS:
        parts.append(f"Source page description: {description[:MAX_NOTES_DESCRIPTION]}")
    parts.append("Indexed as metadata only; no page text is stored.")
    return " ".join(parts)


def resource_row(payload: dict[str, Any], url: str, resource_id: str) -> dict[str, str]:
    return {
        "resource_id": resource_id,
        "resource_type": payload["resource_type"],
        "title": re.sub(r"\s+", " ", payload.get("title") or "").strip(),
        "creator": payload.get("byline") or "",
        "source_name": payload["source_name"],
        "source_url": url,
        "published_date": (payload.get("published_date") or "")[:10],
        "notes": notes_for(payload),
    }


# --- normalization -----------------------------------------------------------


def _blank_counts() -> dict[str, Any]:
    return {
        "records_read": 0,
        "resources_written": 0,
        "resources_already_present": 0,
        "urls_already_cataloged": 0,
        "song_rows_written": 0,
        "show_rows_written": 0,
        "songs_mapped": 0,
        "shows_mapped": 0,
        "unmapped": 0,
        "held": 0,
        "held_reasons": {},
        "by_kind": {},
    }


def normalize(raw_dir: Path, canonical_dir: Path, out_dir: Path, held_dir: Path, targets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Catalog both raw files; write canonical rows to ``out_dir``; hold the rest."""

    songs = SongIndex(read_csv(canonical_dir / "songs.csv"))
    shows_by_date: dict[str, list[str]] = {}
    for show in read_csv(canonical_dir / "shows.csv"):
        shows_by_date.setdefault(show["show_date"], []).append(show["show_id"])

    resources = read_csv(canonical_dir / "resources.csv")
    resource_songs = read_csv(canonical_dir / "resource_songs.csv")
    resource_shows = read_csv(canonical_dir / "resource_shows.csv")
    known_ids = {row["resource_id"] for row in resources}
    known_urls = {url_key(row["source_url"]): row["resource_id"] for row in resources}
    known_song_links = {(row["resource_id"], row["song_id"], row["relationship_type"]) for row in resource_songs}
    known_show_links = {(row["resource_id"], row["show_id"], row["relationship_type"]) for row in resource_shows}

    new_resources: list[dict[str, str]] = []
    new_song_rows: list[dict[str, str]] = []
    new_show_rows: list[dict[str, str]] = []
    summary: dict[str, Any] = {"by_source": {}, "held_paths": {}, "targets": {}}
    mapped_by_kind: dict[str, set[str]] = {}
    held_by_kind: dict[str, set[str]] = {}
    cataloged_by_kind: dict[str, set[str]] = {}

    for source, filename in RAW_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            continue
        records = read_jsonl(path)
        if not records:
            continue
        head = records[0]["raw_payload"]
        if head.get("record_type") != "pass_metadata" or head.get("status") != "ok":
            print(f"  skipping {path.name}: no complete pass metadata")
            continue
        counts = summary["by_source"].setdefault(source, _blank_counts())
        held: list[dict[str, Any]] = []
        source_song_ids: set[str] = set()
        source_show_ids: set[str] = set()

        for record in records[1:]:
            payload = record["raw_payload"]
            kind = payload.get("record_type")
            if kind not in {"essay", "song_page", "page"}:
                continue
            counts["records_read"] += 1
            url = record["source_url"]
            resource_id = resource_id_for(payload)
            kind_key = f"{source}-{'song' if kind == 'page' and payload.get('section') == 'songs' else kind}"
            counts["by_kind"][kind_key] = counts["by_kind"].get(kind_key, 0) + 1

            if kind == "song_page" and url_key(url) in known_urls:
                # The plan's rule: catalog a Dead.net song page only when no
                # reviewed row already carries that URL. Ninety-three of them
                # are already stored as ``lyrics-and-credits`` rows under this
                # same id scheme, and those rows keep their own type and
                # relationships.
                counts["urls_already_cataloged"] += 1
                already, _, _, _ = resolve(payload, songs, shows_by_date)
                cataloged_by_kind.setdefault(kind_key, set()).update(already)
                continue
            if resource_id in known_ids:
                counts["resources_already_present"] += 1
            elif url_key(url) in known_urls:
                # Already cataloged under another id; leave that row alone and
                # attach nothing of this pass to it.
                counts["urls_already_cataloged"] += 1
                already, _, _, _ = resolve(payload, songs, shows_by_date)
                cataloged_by_kind.setdefault(kind_key, set()).update(already)
                continue
            else:
                new_resources.append(resource_row(payload, url, resource_id))
                known_ids.add(resource_id)
                known_urls[url_key(url)] = resource_id
                counts["resources_written"] += 1

            song_ids, show_ids, basis, hold = resolve(payload, songs, shows_by_date)
            if hold:
                held.append({"resource_id": resource_id, "source": source, "url": url, "title": payload.get("title", ""), **hold})
                counts["held"] += 1
                counts["held_reasons"][hold["reason"]] = counts["held_reasons"].get(hold["reason"], 0) + 1
                held_by_kind.setdefault(kind_key, set()).update(hold["candidates"])
                continue
            if not song_ids and not show_ids:
                counts["unmapped"] += 1
                continue
            for song_id in song_ids:
                source_song_ids.add(song_id)
                mapped_by_kind.setdefault(kind_key, set()).add(song_id)
                key = (resource_id, song_id, RELATIONSHIP)
                if key in known_song_links:
                    continue
                known_song_links.add(key)
                new_song_rows.append({"resource_id": resource_id, "song_id": song_id, "relationship_type": RELATIONSHIP, "notes": basis})
                counts["song_rows_written"] += 1
            for show_id in show_ids:
                source_show_ids.add(show_id)
                mapped_by_kind.setdefault(kind_key, set()).add(show_id)
                key = (resource_id, show_id, RELATIONSHIP)
                if key in known_show_links:
                    continue
                known_show_links.add(key)
                new_show_rows.append({"resource_id": resource_id, "show_id": show_id, "relationship_type": RELATIONSHIP, "notes": basis})
                counts["show_rows_written"] += 1

        counts["songs_mapped"] = len(source_song_ids)
        counts["shows_mapped"] = len(source_show_ids)
        summary["held_paths"][source] = str(write_held(held_dir, source, held))

    new_resources.sort(key=lambda row: row["resource_id"])
    new_song_rows.sort(key=lambda row: (row["resource_id"], row["song_id"]))
    new_show_rows.sort(key=lambda row: (row["resource_id"], row["show_id"]))
    emit(canonical_dir, out_dir, "resources.csv", new_resources, RESOURCE_FIELDS)
    emit(canonical_dir, out_dir, "resource_songs.csv", new_song_rows, RESOURCE_SONG_FIELDS)
    emit(canonical_dir, out_dir, "resource_shows.csv", new_show_rows, RESOURCE_SHOW_FIELDS)

    if targets:
        summary["targets"] = target_outcomes(targets, mapped_by_kind, held_by_kind, cataloged_by_kind)
    return summary


def resolve(
    payload: dict[str, Any], songs: SongIndex, shows_by_date: dict[str, list[str]]
) -> tuple[list[str], list[str], str, dict[str, Any] | None]:
    """Resolve one page's subject: song rows, show rows, the basis, or a hold."""

    kind = payload["record_type"]
    if kind == "song_page":
        return [payload["song_id"]], [], "Dead.net song page for this song.", None
    if kind == "essay" or payload.get("section") == "songs":
        song_ids, key = songs.match(*slug_aliases(payload["url_slug"]))
        if len(song_ids) == 1:
            return song_ids, [], "The page slug names the song.", None
        if len(song_ids) > 1:
            return [], [], "", {"reason": "The page slug matches more than one canonical song.", "candidates": song_ids}
        # No slug match: read the song names the page title quotes.
        matched: list[str] = []
        ambiguous: list[str] = []
        for candidate in quoted_titles(payload.get("title") or ""):
            found, _ = songs.match(candidate)
            if len(found) == 1:
                matched.extend(found)
            elif len(found) > 1:
                ambiguous.extend(found)
        if matched:
            return sorted(set(matched)), [], "The page title names the song.", None
        if ambiguous:
            return [], [], "", {"reason": "The page title matches more than one canonical song.", "candidates": sorted(set(ambiguous))}
        return [], [], "", {"reason": "No canonical song matches the page slug or title.", "candidates": songs.candidates(key)}
    dates = sorted({f"{y}-{m}-{d}" for y, m, d in _ISO_DATE.findall(payload.get("url_slug") or "")})
    if len(dates) == 1:
        show_ids = sorted(shows_by_date.get(dates[0], []))
        if len(show_ids) == 1:
            return [], show_ids, "The page slug names the show date.", None
        if len(show_ids) > 1:
            return [], [], "", {"reason": f"{dates[0]} matches more than one canonical show.", "candidates": show_ids}
        return [], [], "", {"reason": f"{dates[0]} matches no canonical show.", "candidates": []}
    if len(dates) > 1:
        return [], [], "", {"reason": "The page slug names more than one date.", "candidates": dates}
    return [], [], "", None


def target_outcomes(
    targets: dict[str, Any],
    mapped: dict[str, set[str]],
    held: dict[str, set[str]],
    cataloged: dict[str, set[str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Per-target outcome by source kind.

    ``found`` is a row this pass wrote or confirmed; ``already cataloged`` is a
    page the source has and Deadbot already stored before this pass, which this
    pass leaves exactly as it is; ``held`` is a page found whose subject needs
    review; ``not found at source`` is a reviewed absence.
    """

    cataloged = cataloged or {}
    kinds = ("deadnet-essay", "deadnet-song_page", "deadheadhigh-song")
    outcomes: dict[str, dict[str, str]] = {}
    for target in targets.get("songs", []):
        song_id = target["song_id"]
        outcomes[song_id] = {}
        for kind in kinds:
            if song_id in mapped.get(kind, ()):
                outcome = "found"
            elif song_id in cataloged.get(kind, ()):
                outcome = "already cataloged"
            elif song_id in held.get(kind, ()):
                outcome = "held"
            else:
                outcome = "not found at source"
            outcomes[song_id][kind] = outcome
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_DIR, help="directory holding the two raw JSONL files")
    parser.add_argument("--canonical-dir", type=Path, default=CANONICAL, help="canonical CSV directory (read only)")
    parser.add_argument("--out-dir", type=Path, default=CANONICAL, help="directory the updated CSVs are written to")
    parser.add_argument("--held-dir", type=Path, default=HELD_DIR, help="directory for the held-mapping queues")
    parser.add_argument("--targets", type=Path, default=TARGETS_PATH, help="the pass's target list, for the per-target outcome report")
    args = parser.parse_args()

    targets = json.loads(args.targets.read_text(encoding="utf-8")) if args.targets and args.targets.exists() else None
    summary = normalize(args.raw, args.canonical_dir, args.out_dir, args.held_dir, targets)
    for source, counts in summary["by_source"].items():
        print(f"{source}: {counts['records_read']} record(s) read")
        print(f"  resources: {counts['resources_written']} written, {counts['resources_already_present']} already present, {counts['urls_already_cataloged']} url(s) already cataloged elsewhere")
        print(f"  relationships: {counts['song_rows_written']} song row(s), {counts['show_rows_written']} show row(s)")
        print(f"  distinct entities: {counts['songs_mapped']} song(s), {counts['shows_mapped']} show(s)")
        print(f"  unmapped: {counts['unmapped']}; held: {counts['held']} -> {summary['held_paths'].get(source)}")
        for reason, count in sorted(counts["held_reasons"].items(), key=lambda item: (-item[1], item[0])):
            print(f"    {count} x {reason}")
        print(f"  by page kind: {counts['by_kind']}")
    if summary["targets"]:
        print("target songs (essay / song page / Deadhead High):")
        for song_id, outcome in summary["targets"].items():
            print(f"  {song_id}: {outcome['deadnet-essay']} / {outcome['deadnet-song_page']} / {outcome['deadheadhigh-song']}")


if __name__ == "__main__":
    main()
