#!/usr/bin/env python3
"""Catalog the indexed research-blog posts as stored resources.

Reads every ``data/raw/resources/blog-post-index-*.jsonl`` file written by
``scripts/collect/collect_blog_post_index.py`` and appends one
``data/canonical/resources.csv`` row per post, plus conservative ``about``
relationships to canonical songs and shows. A post that names neither is still
a resource; it is simply unmapped. A post whose reference is ambiguous is
written to ``data/editorial/blog-post-mapping-held.jsonl`` with the reason and
the candidates, never guessed at.

Mapping rules
-------------
Show: the title, or failing that a post label, names exactly one date the
collector can parse (``YYYY-MM-DD``, ``M/D/YY``, ``M/D/YYYY``, ``Month D,
YYYY``) and exactly one canonical show sits on that date. Two dates, or a date
carrying two shows, is a hold.

Song: the title contains a canonical song title as a whole phrase, matched
case-insensitively with straight and curly apostrophes treated alike and
``&`` read as ``and``. A one-word or very short title (``Deal``, ``Ripple``,
``Truckin'``, ``Bertha``, ``Cassidy``), and a title these blogs also write for
another reason (a city in a venue line, a phrase in ordinary prose; see
``AMBIGUOUS_SONG_TITLES``), maps only when a post label is exactly the song
title, or when the post is on Deadessays and its title begins with it. A song
named after a city (``PLACE_NAME_SONG_TITLES``) has only the second path, since
these blogs label a post with its venue's city. More than three song matches in
one title is a hold.

Idempotency: existing rows are never modified or reordered, this pass's rows
are appended sorted by id, and a rerun over unchanged raw files reproduces
byte-identical files.

Usage::

    PYTHONPATH=. python scripts/normalize/normalize_blog_post_resources.py
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "resources"
CANONICAL = ROOT / "data" / "canonical"
HELD_PATH = ROOT / "data" / "editorial" / "blog-post-mapping-held.jsonl"
RAW_GLOB = "blog-post-index-*.jsonl"
RELATIONSHIP = "about"
MAX_SONG_MATCHES = 3
MAX_LABELS_IN_NOTES = 12
DEADESSAYS_HOST = "deadessays.blogspot.com"

# Song titles that these blogs also write for another reason. Four are cities
# the band played, and these sites title posts "date: venue, city", so "The
# Warehouse, New Orleans" and "Terrace Ballroom, Salt Lake City, UT" matched
# the songs of those names in the first pass. The other three turned up in
# ordinary prose: "The Seven And Only Seven Terrapin Encores", "The Eleven
# Longest Jerry Bands Songs", "The Eleven, Plus One", "Maybe You Know Brent Got
# Wasted", and a "South Bay Landmark Guide (So Many Roads I)" series — a
# numbered jam's name reads as a count. These need the support a one-word title
# needs: a post label naming the song, or a Deadessays title that begins with
# it. The cost is real (two genuine "Dark Star > The Eleven" posts go unmapped)
# and accepted: a wrong "about" row would have Deadbot say a post covers a song
# it never mentions.
AMBIGUOUS_SONG_TITLES = frozenset({"the seven", "the eleven", "the main ten", "maybe you know", "so many roads"})

# Songs named after a city the band played. These sites title posts "date:
# venue, city" and label them by place, so a label reading "Kansas City" is the
# venue's city as often as the song. A label cannot support these; only a
# Deadessays title that begins with the song title can.
PLACE_NAME_SONG_TITLES = frozenset({"new orleans", "kansas city", "salt lake city", "el paso"})

RESOURCE_FIELDS = ["resource_id", "resource_type", "title", "creator", "source_name", "source_url", "published_date", "notes"]
RESOURCE_SONG_FIELDS = ["resource_id", "song_id", "relationship_type", "notes"]
RESOURCE_SHOW_FIELDS = ["resource_id", "show_id", "relationship_type", "notes"]

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_SLASH_DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})(?![\d/])")
_MONTH_DAY_YEAR = re.compile(rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b", re.IGNORECASE)
# "September 26-27, 1969" and "September 26 & 27, 1969" name two shows.
_MONTH_DAY_RANGE = re.compile(
    rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|&|and)\s*(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b",
    re.IGNORECASE,
)
# "Fillmore West February 27-March 2, 1969" and "January 31 - February 1,
# 1970" cover a run of shows, so both ends are read and the post is held.
_MONTH_DAY_TO_MONTH_DAY = re.compile(
    rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|to|and|&)\s*({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z0-9]")


# --- small file helpers ------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    """Add rows to an existing canonical file, leaving its bytes untouched.

    Appending rather than rewriting matters: a couple of existing rows were
    written with quoting this writer would not choose, and a canonical row
    already reviewed should not change because a later pass ran.
    """

    if not rows:
        return
    existing = path.read_bytes() if path.exists() else b""
    with path.open("a", newline="", encoding="utf-8") as handle:
        if existing and not existing.endswith(b"\n"):
            handle.write("\n")
        csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n").writerows(rows)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- text normalization ------------------------------------------------------


def match_text(value: str) -> str:
    """One comparable spelling: casefolded, straight apostrophes, ``&`` as and."""

    value = value.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    value = value.replace("&", " and ")
    return re.sub(r"\s+", " ", value.casefold()).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def host_slug(host: str) -> str:
    host = host.strip().casefold()
    if host.startswith("www."):
        host = host[4:]
    return slugify(host.split(".")[0])


def post_slug(url: str) -> str:
    """A stable slug for one post: its whole feed path, minus the extension."""

    path = urlparse(url).path
    if path.endswith(".html"):
        path = path[: -len(".html")]
    return slugify(path)


def resource_id_for(url: str) -> str:
    host = urlparse(url).hostname or ""
    return f"resource-{host_slug(host)}-{post_slug(url)}"


def canonical_url(url: str, feed_host: str) -> str:
    """The stored link: the post's own URL, over https.

    Grateful Seconds publishes on gratefulseconds.com, whose feed advertises
    ``http://`` links and which answers nothing on port 443. Blogger still
    serves the same post path on the blog's own https address and redirects
    from there, so an http post URL is stored as
    ``https://{feed host}{path}``. The raw record keeps the feed's own URL.
    """

    parsed = urlparse(url)
    if parsed.scheme == "https":
        return url
    return f"https://{feed_host}{parsed.path}"


# --- dates -------------------------------------------------------------------


def _iso(year: int, month: int, day: int) -> str | None:
    if not 1 <= month <= 12:
        return None
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _four_digit_year(value: str) -> int | None:
    """``72`` is 1972; a two-digit year outside the band's era is not a date."""

    year = int(value)
    if len(value) == 4:
        return year
    return 1900 + year if 65 <= year <= 99 else None


def find_dates(text: str) -> list[str]:
    """Every unambiguous calendar date the text names, sorted and deduplicated."""

    found: set[str] = set()
    for match in _ISO_DATE.finditer(text):
        date = _iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if date:
            found.add(date)
    for match in _SLASH_DATE.finditer(text):
        year = _four_digit_year(match.group(3))
        if year is None:
            continue
        date = _iso(year, int(match.group(1)), int(match.group(2)))
        if date:
            found.add(date)
    for match in _MONTH_DAY_TO_MONTH_DAY.finditer(text):
        first_month = _MONTHS[match.group(1).casefold()]
        second_month = _MONTHS[match.group(3).casefold()]
        year = int(match.group(5))
        # A run over New Year starts in the previous year.
        first = _iso(year - 1 if first_month > second_month else year, first_month, int(match.group(2)))
        second = _iso(year, second_month, int(match.group(4)))
        found.update(date for date in (first, second) if date)
    for match in _MONTH_DAY_RANGE.finditer(text):
        month = _MONTHS[match.group(1).casefold()]
        year = int(match.group(4))
        for day in (int(match.group(2)), int(match.group(3))):
            date = _iso(year, month, day)
            if date:
                found.add(date)
    for match in _MONTH_DAY_YEAR.finditer(text):
        date = _iso(int(match.group(3)), _MONTHS[match.group(1).casefold()], int(match.group(2)))
        if date:
            found.add(date)
    return sorted(found)


# --- songs -------------------------------------------------------------------


class SongIndex:
    """Canonical song titles compiled into whole-phrase title matchers."""

    def __init__(self, songs: list[dict[str, str]]) -> None:
        self.entries: list[tuple[str, str, re.Pattern[str], bool, bool]] = []
        for song in songs:
            title = match_text(song["title"])
            if not title:
                continue
            pattern = re.compile(r"(?<![a-z0-9])" + _phrase_body(title) + r"(?![a-z0-9])")
            place_name = title in PLACE_NAME_SONG_TITLES
            needs_support = place_name or is_short_title(title) or title in AMBIGUOUS_SONG_TITLES
            self.entries.append((song["song_id"], title, pattern, needs_support, place_name))
        self.entries.sort(key=lambda entry: entry[0])

    def matches(self, title: str, labels: list[str], host: str) -> list[tuple[str, str]]:
        """Return ``(song_id, match basis)`` pairs for one post title."""

        text = match_text(title)
        label_texts = [match_text(label) for label in labels]
        spans: list[tuple[int, int, str, str]] = []
        for song_id, song_title, pattern, needs_support, place_name in self.entries:
            found = pattern.search(text)
            if not found:
                continue
            if not needs_support:
                basis = "Title names the song."
            elif not place_name and song_title in label_texts:
                basis = "Title names the song and a post label names it too."
            elif host == DEADESSAYS_HOST and found.start() == 0:
                basis = "Title begins with the song title."
            else:
                continue
            spans.append((found.start(), found.end(), song_id, basis))
        return [
            (song_id, basis)
            for start, end, song_id, basis in spans
            # A shorter title inside a longer one ("Playing In The Band" inside
            # its "Reprise") is the same reference, not a second song.
            if not any(other_start <= start and end <= other_end and (other_start, other_end) != (start, end) for other_start, other_end, _, _ in spans)
        ]


def _phrase_body(phrase: str) -> str:
    """A phrase matcher that tolerates the punctuation a writer adds inside it.

    A post titled ``"It's All Over Now, Baby Blue" encore`` names the song
    whose canonical title carries no comma, so a comma, colon or dash between
    words is read as the space it stands in for.
    """

    return re.escape(phrase).replace(r"\ ", r"[,:;]?[\s\-–—]+")


def is_short_title(title: str) -> bool:
    """True for a title too slight to identify a song on its own.

    The plan's gate is "at least two words or at least six letters", and its
    own examples of titles that need help — ``Deal``, ``Ripple``, ``Truckin'``,
    ``Bertha``, ``Cassidy`` — are all one word, four of them six letters or
    more. So a one-word title is always treated as short, and a two-word title
    of fewer than six letters is too.
    """

    words = [word for word in title.split() if _WORD.search(word)]
    letters = sum(1 for character in title if character.isalpha())
    return len(words) < 2 or letters < 6


# --- normalization -----------------------------------------------------------


def show_mapping(title: str, labels: list[str], shows_by_date: dict[str, list[str]]) -> tuple[list[tuple[str, str]], dict[str, Any] | None, bool]:
    """Resolve one post's show reference.

    Returns the ``(show_id, note)`` rows to write, a hold record when the
    reference is ambiguous, and whether a parsed date named no canonical show.
    """

    dates = find_dates(title)
    basis = "Title names the show date."
    if not dates:
        dates = sorted({date for label in labels for date in find_dates(label)})
        basis = "A post label names the show date."
    if not dates:
        return [], None, False
    matched = {date: shows_by_date.get(date, []) for date in dates}
    if not any(matched.values()):
        return [], None, True
    if len(dates) > 1:
        candidates = [f"{date} ({', '.join(show_ids) if show_ids else 'no canonical show'})" for date, show_ids in matched.items()]
        return [], {"reason": "The title names more than one date." if basis.startswith("Title") else "The post labels name more than one date.", "candidates": candidates}, False
    date = dates[0]
    show_ids = matched[date]
    if len(show_ids) > 1:
        return [], {"reason": f"{date} matches more than one canonical show.", "candidates": sorted(show_ids)}, False
    return [(show_ids[0], basis)], None, False


def normalize(raw_dir: Path, canonical_dir: Path, held_path: Path) -> dict[str, Any]:
    """Catalog every indexed post; append canonical rows; write the held queue."""

    songs = SongIndex(read_csv(canonical_dir / "songs.csv"))
    shows_by_date: dict[str, list[str]] = {}
    for show in read_csv(canonical_dir / "shows.csv"):
        shows_by_date.setdefault(show["show_date"], []).append(show["show_id"])

    resources = read_csv(canonical_dir / "resources.csv")
    resource_songs = read_csv(canonical_dir / "resource_songs.csv")
    resource_shows = read_csv(canonical_dir / "resource_shows.csv")
    known_ids = {row["resource_id"] for row in resources}
    known_urls = {row["source_url"] for row in resources}
    known_song_links = {(row["resource_id"], row["song_id"], row["relationship_type"]) for row in resource_songs}
    known_show_links = {(row["resource_id"], row["show_id"], row["relationship_type"]) for row in resource_shows}

    pass_resource_ids: set[str] = set()
    new_resources: list[dict[str, str]] = []
    new_song_rows: list[dict[str, str]] = []
    new_show_rows: list[dict[str, str]] = []
    held: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "hosts": 0,
        "posts_read": 0,
        "resources_written": 0,
        "resources_already_present": 0,
        "urls_already_cataloged": 0,
        "song_rows_written": 0,
        "show_rows_written": 0,
        "songs_mapped": 0,
        "shows_mapped": 0,
        "unmapped": 0,
        "held": 0,
        "dates_without_a_canonical_show": 0,
        "held_reasons": {},
        "by_host": {},
    }

    for path in sorted(raw_dir.glob(RAW_GLOB)):
        records = read_jsonl(path)
        if not records:
            continue
        head = records[0]["raw_payload"]
        if head.get("record_type") != "pass_metadata" or head.get("status") != "ok":
            print(f"  skipping {path.name}: no complete pass metadata")
            continue
        host = head["host"]
        summary["hosts"] += 1
        host_summary = summary["by_host"].setdefault(
            host,
            {"site_name": head["site_name"], "posts": 0, "resources_written": 0, "song_rows": 0, "show_rows": 0, "unmapped": 0, "held": 0},
        )
        for record in records[1:]:
            payload = record["raw_payload"]
            if payload.get("record_type") != "post":
                continue
            summary["posts_read"] += 1
            host_summary["posts"] += 1
            url = canonical_url(record["source_url"], host)
            resource_id = resource_id_for(url)
            pass_resource_ids.add(resource_id)
            title = payload["title"]
            labels = list(payload.get("labels") or [])

            if resource_id in known_ids:
                summary["resources_already_present"] += 1
            elif url in known_urls:
                # The post is already cataloged under a hand-written id; leave
                # that row alone and do not attach this pass's relationships.
                summary["urls_already_cataloged"] += 1
                continue
            else:
                new_resources.append(
                    {
                        "resource_id": resource_id,
                        "resource_type": payload["resource_type"],
                        "title": title,
                        "creator": payload.get("author", ""),
                        "source_name": payload["site_name"],
                        "source_url": url,
                        "published_date": (payload.get("published") or "")[:10],
                        "notes": resource_notes(labels, record["source_url"] if url != record["source_url"] else ""),
                    }
                )
                known_ids.add(resource_id)
                known_urls.add(url)
                summary["resources_written"] += 1
                host_summary["resources_written"] += 1

            song_matches = songs.matches(title, labels, host)
            show_rows, show_hold, unmatched_date = show_mapping(title, labels, shows_by_date)
            if unmatched_date:
                summary["dates_without_a_canonical_show"] += 1
            reasons: list[dict[str, Any]] = []
            if len(song_matches) > MAX_SONG_MATCHES:
                reasons.append({"reason": "The title names more than three songs.", "candidates": sorted(song_id for song_id, _ in song_matches)})
                song_matches = []
            if show_hold:
                reasons.append(show_hold)

            wrote = False
            for song_id, basis in sorted(song_matches):
                key = (resource_id, song_id, RELATIONSHIP)
                if key in known_song_links:
                    continue
                known_song_links.add(key)
                new_song_rows.append({"resource_id": resource_id, "song_id": song_id, "relationship_type": RELATIONSHIP, "notes": basis})
                summary["song_rows_written"] += 1
                host_summary["song_rows"] += 1
            for show_id, basis in show_rows:
                key = (resource_id, show_id, RELATIONSHIP)
                if key in known_show_links:
                    continue
                known_show_links.add(key)
                new_show_rows.append({"resource_id": resource_id, "show_id": show_id, "relationship_type": RELATIONSHIP, "notes": basis})
                summary["show_rows_written"] += 1
                host_summary["show_rows"] += 1
            wrote = bool(song_matches or show_rows)

            for reason in reasons:
                held.append(
                    {
                        "resource_id": resource_id,
                        "host": host,
                        "url": url,
                        "title": title,
                        "reason": reason["reason"],
                        "candidates": reason["candidates"],
                    }
                )
                summary["held_reasons"][reason["reason"]] = summary["held_reasons"].get(reason["reason"], 0) + 1
            if reasons:
                summary["held"] += 1
                host_summary["held"] += 1
            elif not wrote:
                summary["unmapped"] += 1
                host_summary["unmapped"] += 1

    new_resources.sort(key=lambda row: row["resource_id"])
    new_song_rows.sort(key=lambda row: (row["resource_id"], row["song_id"]))
    new_show_rows.sort(key=lambda row: (row["resource_id"], row["show_id"]))
    append_csv(canonical_dir / "resources.csv", new_resources, RESOURCE_FIELDS)
    append_csv(canonical_dir / "resource_songs.csv", new_song_rows, RESOURCE_SONG_FIELDS)
    append_csv(canonical_dir / "resource_shows.csv", new_show_rows, RESOURCE_SHOW_FIELDS)

    held.sort(key=lambda row: (row["resource_id"], row["reason"]))
    held_path.parent.mkdir(parents=True, exist_ok=True)
    with held_path.open("w", encoding="utf-8") as handle:
        for row in held:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    # Distinct entities reachable from this pass's posts, however many runs it
    # took to write their rows.
    summary["songs_mapped"] = len({row["song_id"] for row in resource_songs + new_song_rows if row["resource_id"] in pass_resource_ids and row["relationship_type"] == RELATIONSHIP})
    summary["shows_mapped"] = len({row["show_id"] for row in resource_shows + new_show_rows if row["resource_id"] in pass_resource_ids and row["relationship_type"] == RELATIONSHIP})
    return summary


def resource_notes(labels: list[str], feed_url: str = "") -> str:
    parts = []
    kept = [label for label in labels if label][:MAX_LABELS_IN_NOTES]
    if kept:
        parts.append(f"Post labels: {', '.join(kept)}.")
    parts.append("Indexed from the site's public post feed; metadata only, no post text is stored.")
    if feed_url:
        parts.append(f"The blog's feed gives this post as {feed_url}, an http-only custom domain; the https address above serves the same post.")
    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_DIR, help="directory holding blog-post-index-*.jsonl")
    parser.add_argument("--canonical", type=Path, default=CANONICAL, help="canonical CSV directory")
    parser.add_argument("--held", type=Path, default=HELD_PATH, help="path for the held-mapping queue")
    args = parser.parse_args()

    summary = normalize(args.raw, args.canonical, args.held)
    print(f"{summary['posts_read']} posts read from {summary['hosts']} host(s)")
    print(f"  resources: {summary['resources_written']} written, {summary['resources_already_present']} already present, {summary['urls_already_cataloged']} url(s) already cataloged elsewhere")
    print(f"  relationships: {summary['song_rows_written']} song row(s), {summary['show_rows_written']} show row(s)")
    print(f"  distinct entities with a blog resource: {summary['songs_mapped']} song(s), {summary['shows_mapped']} show(s)")
    print(f"  unmapped: {summary['unmapped']}; held: {summary['held']}; parsed dates with no canonical show: {summary['dates_without_a_canonical_show']}")
    for reason, count in sorted(summary["held_reasons"].items(), key=lambda item: (-item[1], item[0])):
        print(f"    {count} x {reason}")
    for host, counts in sorted(summary["by_host"].items()):
        print(f"  {counts['site_name']} ({host}): {counts['posts']} posts, {counts['resources_written']} new resources, {counts['song_rows']} song rows, {counts['show_rows']} show rows, {counts['unmapped']} unmapped, {counts['held']} held")


if __name__ == "__main__":
    main()
