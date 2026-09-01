#!/usr/bin/env python3
"""Promote MusicBrainz official live releases into the canonical release tables.

Input: the compact raw records written by
``scripts/collect/fetch_musicbrainz_live_releases.py``.

Output: ``data/canonical/official_releases.csv`` and
``data/canonical/official_release_tracks.csv`` plus a review log at
``data/raw/releases/musicbrainz-release-review.jsonl``.

Rules (also written up in ``docs/collection-status-official-releases.md``):

* One release is chosen per MusicBrainz release group: the official release with
  the most tracks, then the earliest release date, then the lowest MBID.  The
  Spotify album URL may come from any release in the group.
* Show dates come from release-group and release titles/disambiguations and
  from recording disambiguations (``live, YYYY-MM-DD: venue``) or medium
  titles.  When the union of those dates is exactly one date that matches
  exactly one canonical show, the release is a single-show release.  When more
  than one date is present, each track is attributed only by its own
  track-level date; the release is promoted when at least one track resolves
  to exactly one canonical show and is marked as spanning more than one show.
* A track receives a ``performance_id`` only when its title aligns uniquely and
  monotonically with the attributed show's canonical setlist using the
  ``normalized_title`` alias approach from
  ``scripts/normalize_internet_archive_tracks.py``.  Everything else is left
  blank with the reason in ``notes``.  Nothing is guessed.
* Rows produced by this script carry ``MusicBrainz release <mbid>`` in notes;
  reruns replace only those rows and reuse the release_id previously assigned
  to the same release or release-group MBID.  Hand-curated rows are preserved.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "releases"
RELEASE_GROUPS_PATH = RAW_DIR / "musicbrainz-release-groups.jsonl"
RELEASES_PATH = RAW_DIR / "musicbrainz-releases.jsonl"
REVIEW_PATH = RAW_DIR / "musicbrainz-release-review.jsonl"
RELEASES_CSV = CANONICAL / "official_releases.csv"
TRACKS_CSV = CANONICAL / "official_release_tracks.csv"

RELEASE_FIELDS = ["release_id", "title", "artist_name", "release_date", "release_type", "spotify_album_url", "source_url", "notes"]
TRACK_FIELDS = ["release_id", "track_number", "performance_id", "track_title", "duration_seconds", "spotify_track_url", "notes"]
ARTIST_NAME = "Grateful Dead"
MANAGED_MARKER = "MusicBrainz release "

MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
ISO_DATE = re.compile(r"(?<!\d)(19\d\d)-(\d{1,2})-(\d{1,2})(?!\d)")
US_DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])")
US_DAY_RANGE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*[-&,]\s*(\d{1,2})/(\d{4}|\d{2})(?![\d/])")
US_DAY_LIST = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*[&,]\s*(?:and\s*)?(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])")
NUMERIC_DASH_DATE = re.compile(r"(?<![\d/.\-])(\d{1,2})([.\-])(\d{1,2})\2(\d{2})(?![\d/.\-])")
TEXT_DATE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(19\d\d)\b", re.IGNORECASE)
TEXT_DAY_LIST = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})\s*(?:&|and|,|-)\s*(\d{{1,2}}),?\s+(19\d\d)\b", re.IGNORECASE)
LIVE_SUFFIX = re.compile(r"\s*[\(\[]\s*live(?:\s+[^\)\]]*)?[\)\]]\s*$", re.IGNORECASE)
PARENTHETICAL = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]")


# --- title normalization (mirrors normalize_internet_archive_tracks.normalized_title) ---

def normalized_title(value: str) -> str:
    """Normalize source and canonical titles without guessing song identity."""

    value = LIVE_SUFFIX.sub("", value or "")
    # Release track titles sometimes carry the performance date and venue in a
    # parenthetical ("Dark Star (1969-06-05: Fillmore West)"); that is
    # provenance, not part of the song title.
    value = PARENTHETICAL.sub(lambda match: "" if extract_dates(match.group(1)) else match.group(0), value)
    value = unicodedata.normalize("NFKD", value).casefold()
    value = value.replace("&", " and ").replace("->", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = " ".join(value.split())
    return TITLE_ALIASES.get(value, value)


# Punctuation, contraction, abbreviation, and documented alternate-title
# variants that appear on official release track lists.  Every target is the
# normalized form of an existing songs.csv title.  Segment names that are not
# title variants (for example "Rhythm Devils" for the drums segment) are
# deliberately absent; suites and medleys are left to the segment bridge.
TITLE_ALIASES = {
    # inherited from normalize_internet_archive_tracks.py
    "dancing in the street": "dancin in the streets",
    "dancing in the streets": "dancin in the streets",
    "dancin in the street": "dancin in the streets",
    "greatest story": "greatest story ever told",
    "playin": "playing in the band",
    "u s blues": "us blues",
    # contractions and spelling
    "goin down the road feeling bad": "goin down the road feelin bad",
    "going down the road feeling bad": "goin down the road feelin bad",
    "going down the road feelin bad": "goin down the road feelin bad",
    "sittin on top of the world": "sitting on top of the world",
    "smokestack lightnin": "smokestack lightning",
    "lazy lightnin": "lazy lightning",
    "brown eyed woman": "brown eyed women",
    "turn on your love light": "turn on your lovelight",
    "lovelight": "turn on your lovelight",
    "good morning little school girl": "good morning little schoolgirl",
    "cc rider": "c c rider",
    "west la fadeaway": "west l a fadeaway",
    "hey pocky a way": "hey pocky way",
    # abbreviations and article variants
    "st stephen": "saint stephen",
    "the promised land": "promised land",
    "days between": "the days between",
    "it hurts me too": "hurts me too",
    "in the midnight hour": "midnight hour",
    # full or alternate titles of the same composition
    "new minglewood blues": "minglewood blues",
    "new new minglewood blues": "minglewood blues",
    "mississippi half step uptown toodeloo": "mississippi half step",
    "mississippi half step uptown toodleoo": "mississippi half step",
    "mississippi half step uptown toodleloo": "mississippi half step",
    "rockin pneumonia and the boogie woogie flu": "rockin pneumonia",
    "caution do not stop on tracks": "caution",
    "the stranger two souls in communion": "two souls in communion",
    "the stranger": "two souls in communion",
    "keep your day job": "day job",
    "i can t get no satisfaction": "satisfaction",
    "walk me out in the morning dew": "morning dew",
    "quinn the eskimo the mighty quinn": "quinn the eskimo",
    "the mighty quinn": "quinn the eskimo",
    "women are smarter": "man smart woman smarter",
}


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    value = re.sub(r"['’]", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


# --- date extraction ---

def _year(text: str) -> int:
    year = int(text)
    if year < 100:
        return 1900 + year if year >= 65 else 2000 + year
    return year


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def extract_dates(text: str) -> set[str]:
    """Return every full calendar date expressed in a title or disambiguation."""

    text = (text or "").translate(DASHES)
    found: set[str] = set()
    for year, month, day in ISO_DATE.findall(text):
        if value := _safe_date(int(year), int(month), int(day)):
            found.add(value)
    for month, day_a, day_b, year in US_DAY_RANGE.findall(text):
        lo, hi = sorted((int(day_a), int(day_b)))
        for day in range(lo, hi + 1):
            if value := _safe_date(_year(year), int(month), day):
                found.add(value)
    for month_a, day_a, month_b, day_b, year in US_DAY_LIST.findall(text):
        for month, day in ((month_a, day_a), (month_b, day_b)):
            if value := _safe_date(_year(year), int(month), int(day)):
                found.add(value)
    for month, day, year in US_DATE.findall(text):
        if value := _safe_date(_year(year), int(month), int(day)):
            found.add(value)
    for month, _, day, year in NUMERIC_DASH_DATE.findall(text):
        if value := _safe_date(_year(year), int(month), int(day)):
            found.add(value)
    for month, day, year in TEXT_DATE.findall(text):
        month_number = MONTHS.split("|").index(month.casefold()) + 1
        if value := _safe_date(int(year), month_number, int(day)):
            found.add(value)
    for month, day_a, day_b, year in TEXT_DAY_LIST.findall(text):
        month_number = MONTHS.split("|").index(month.casefold()) + 1
        for day in (day_a, day_b):
            if value := _safe_date(int(year), month_number, int(day)):
                found.add(value)
    return found


def full_date(value: str) -> str:
    return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or "") else ""


def date_sort_key(value: str) -> str:
    return (value or "9999").ljust(10, "0")


def spotify_album_url(urls: list[dict]) -> str:
    for relation in urls:
        parsed = urlparse(relation.get("url", ""))
        if parsed.netloc.endswith("open.spotify.com") and parsed.path.startswith("/album/"):
            return f"https://open.spotify.com{parsed.path}"
    return ""


def spotify_track_url(urls: list[dict]) -> str:
    for relation in urls:
        parsed = urlparse(relation.get("url", ""))
        if parsed.netloc.endswith("open.spotify.com") and parsed.path.startswith("/track/"):
            return f"https://open.spotify.com{parsed.path}"
    return ""


# --- setlist alignment (adapted from normalize_internet_archive_tracks.align_tracks) ---

def align_tracks(
    source_tracks: list[tuple[int, str]], performances: list[dict], songs: dict[str, str]
) -> tuple[str, dict[int, int], set[int], str]:
    """Align release tracks with a show's canonical setlist.

    Returns ``(status, matches, ambiguous, reason)`` where ``matches`` maps a
    track index to the performance index that every monotonic alignment agrees
    on and ``ambiguous`` lists tracks whose position differs between otherwise
    valid alignments.  A release order that contradicts the setlist holds the
    whole show group, because an undated bonus track from another show can
    otherwise be absorbed into a setlist gap.
    """

    if not performances:
        return "held", {}, set(), "show_has_no_canonical_performances"
    canonical_titles = [normalized_title(songs[row["song_id"]]) for row in performances]
    states: dict[tuple[int, ...], dict[int, int]] = {(): {}}
    for track_index, title in source_tracks:
        normalized_source = normalized_title(title)
        if not normalized_source:
            return "held", {}, set(), f"missing_title_for_track_{track_index}"
        next_states: dict[tuple[int, ...], dict[int, int]] = {}
        for used_indexes, matches in states.items():
            last_index = used_indexes[-1] if used_indexes else -1
            candidates = [
                index for index in range(last_index + 1, len(performances)) if canonical_titles[index] == normalized_source
            ]
            if not candidates:
                # A title absent from the whole setlist is intro/tuning/banter
                # or source-only material and leaves the state untouched.  A
                # title that exists only earlier in the setlist contradicts
                # this state's order, so the state is dropped; if every state
                # dies the release order conflicts with the canonical setlist.
                if normalized_source not in canonical_titles:
                    next_states[used_indexes] = matches
                continue
            for index in candidates:
                next_states[used_indexes + (index,)] = {**matches, track_index: index}
        states = next_states
        if not states:
            return "held", {}, set(), f"source_order_conflict_at_track_{track_index}:{title}"
    aligned = [matches for matches in states.values() if matches]
    if not aligned:
        return "held", {}, set(), "no_source_titles_match_canonical_setlist"
    track_indexes = {index for matches in aligned for index in matches}
    agreed = {
        index: aligned[0][index]
        for index in track_indexes
        if all(index in matches and matches[index] == aligned[0][index] for matches in aligned)
    }
    ambiguous = track_indexes - set(agreed)
    if not agreed:
        return "held", {}, set(), f"ambiguous_alignment_{len(aligned)}_ways"
    if ambiguous:
        return "accepted_partial", agreed, ambiguous, f"ambiguous_alignment_{len(aligned)}_ways_for_{len(ambiguous)}_tracks"
    status = "accepted_full" if len(agreed) == len(performances) else "accepted_partial"
    return status, agreed, set(), ""


def looks_like_medley(title: str, canonical_titles: set[str]) -> bool:
    parts = [normalized_title(part) for part in re.split(r"\s*(?:/|>|→|→)\s*", (title or "").replace("->", ">")) if part.strip()]
    return len(parts) >= 2 and all(part in canonical_titles for part in parts)


# --- loading ---

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing raw file {path.relative_to(ROOT)}; run the collector first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def load_canonical() -> tuple[dict[str, list[str]], dict[str, list[dict]], dict[str, str]]:
    _, shows = read_csv(CANONICAL / "shows.csv")
    shows_by_date: dict[str, list[str]] = defaultdict(list)
    for row in shows:
        shows_by_date[row["show_date"]].append(row["show_id"])
    for ids in shows_by_date.values():
        ids.sort()
    _, performances = read_csv(CANONICAL / "performances.csv")
    by_show: dict[str, list[dict]] = defaultdict(list)
    for row in performances:
        by_show[row["show_id"]].append(row)
    for rows in by_show.values():
        rows.sort(key=lambda row: (int(row["set_number"] or 0), int(row["position_in_set"] or 0)))
    _, songs = read_csv(CANONICAL / "songs.csv")
    return shows_by_date, by_show, {row["song_id"]: row["title"] for row in songs}


# --- per release-group processing ---

def flatten_tracks(release: dict) -> list[dict]:
    tracks = []
    for medium in sorted(release["media"], key=lambda medium: medium.get("position") or 0):
        for track in sorted(medium["tracks"], key=lambda track: track.get("position") or 0):
            tracks.append({"medium": medium, "track": track})
    return tracks


def track_dates(entry: dict) -> tuple[set[str], str]:
    recording = entry["track"].get("recording", {})
    for basis, text in (
        ("recording disambiguation", recording.get("disambiguation", "")),
        ("medium title", entry["medium"].get("title", "")),
        ("track title", entry["track"].get("title", "")),
    ):
        dates = extract_dates(text)
        if dates:
            return dates, basis
    return set(), ""


def format_rank(release: dict) -> int:
    """Prefer CD/digital editions: vinyl sides split and reorder long tracks."""

    formats = {(medium.get("format") or "").casefold() for medium in release["media"]}
    if any("vinyl" in name for name in formats):
        return 2
    if any(name and "cd" not in name and "digital" not in name for name in formats):
        return 1
    return 0


def choose_release(releases: list[dict]) -> dict:
    return sorted(
        releases,
        key=lambda release: (
            format_rank(release),
            -sum(len(medium["tracks"]) for medium in release["media"]),
            date_sort_key(release.get("date", "")),
            release["id"],
        ),
    )[0]


def resolve_show(date_value: str, shows_by_date: dict[str, list[str]]) -> tuple[str, str]:
    show_ids = shows_by_date.get(date_value, [])
    if len(show_ids) == 1:
        return show_ids[0], ""
    if not show_ids:
        return "", "date_not_in_canonical_shows"
    return "", "date_matches_multiple_canonical_shows"


def process_group(
    group: dict,
    releases: list[dict],
    shows_by_date: dict[str, list[str]],
    performances_by_show: dict[str, list[dict]],
    songs: dict[str, str],
) -> dict:
    """Return a decision record with optional canonical rows."""

    decision = {
        "release_group_id": group["id"],
        "release_group_title": group["title"],
        "first_release_date": group.get("first_release_date", ""),
        "secondary_types": group.get("secondary_types", []),
        "official_release_count": len(releases),
        "status": "held",
        "reason": "",
    }
    if not releases:
        decision["reason"] = "no_official_release_fetched"
        return decision

    primary = choose_release(releases)
    tracks = flatten_tracks(primary)
    decision.update({"release_id_mbid": primary["id"], "release_title": primary["title"], "track_count": len(tracks)})

    title_sources = [
        ("release-group title", group["title"]),
        ("release-group disambiguation", group.get("disambiguation", "")),
        ("release title", primary["title"]),
        ("release disambiguation", primary.get("disambiguation", "")),
    ]
    title_dates: set[str] = set()
    title_basis: list[str] = []
    for basis, text in title_sources:
        found = extract_dates(text)
        if found:
            title_dates |= found
            title_basis.append(basis)

    per_track_dates = [track_dates(entry) for entry in tracks]
    track_date_union = set().union(*(dates for dates, _ in per_track_dates)) if per_track_dates else set()
    all_dates = title_dates | track_date_union
    decision["title_dates"] = sorted(title_dates)
    decision["track_dates"] = sorted(track_date_union)

    if not all_dates:
        decision["reason"] = "no_show_date_in_metadata"
        return decision

    # Attribute each track to a show.
    attribution: list[tuple[str, str]] = []  # (show_id, unattributed reason)
    if len(all_dates) == 1:
        (only_date,) = all_dates
        show_id, error = resolve_show(only_date, shows_by_date)
        if not show_id:
            decision["reason"] = error
            decision["dates"] = [only_date]
            return decision
        basis_bits = title_basis + ([f"{sum(1 for dates, _ in per_track_dates if dates)}/{len(tracks)} track-level dates"] if track_date_union else [])
        resolution = f"single date {only_date} from {', '.join(basis_bits)}"
        attribution = [(show_id, "")] * len(tracks)
        spans_multiple = False
    else:
        spans_multiple = True
        for dates, basis in per_track_dates:
            if not dates:
                attribution.append(("", "no per-track show date in MusicBrainz metadata (multi-show release)"))
            elif len(dates) > 1:
                attribution.append(("", f"more than one date in track metadata ({', '.join(sorted(dates))})"))
            else:
                (track_date,) = dates
                show_id, error = resolve_show(track_date, shows_by_date)
                if show_id:
                    attribution.append((show_id, ""))
                else:
                    attribution.append(("", f"track date {track_date} {error.replace('_', ' ')}"))
        attributed_shows = sorted({show_id for show_id, _ in attribution if show_id})
        if not attributed_shows:
            decision["reason"] = "multi_show_without_track_attribution"
            decision["unattributed_reasons"] = dict(Counter(reason for _, reason in attribution))
            return decision
        resolution = (
            f"multiple dates ({len(all_dates)}) in metadata; {sum(1 for show_id, _ in attribution if show_id)}/{len(tracks)} "
            f"tracks attributed by track-level dates to {len(attributed_shows)} canonical show(s): {', '.join(attributed_shows)}"
        )

    # Align attributed tracks with each show's canonical setlist.
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for index, (show_id, _) in enumerate(attribution):
        if show_id:
            grouped[show_id].append((index, tracks[index]["track"].get("title", "")))
    alignment: dict[int, dict] = {}
    alignment_notes: dict[str, str] = {}
    for show_id, source_tracks in grouped.items():
        status, matches, ambiguous, reason = align_tracks(source_tracks, performances_by_show.get(show_id, []), songs)
        alignment_notes[show_id] = status if not reason else f"{status}: {reason}"
        for track_index, performance_index in matches.items():
            alignment[track_index] = performances_by_show[show_id][performance_index]
        for track_index in ambiguous:
            alignment[track_index] = {"held": "title matches more than one setlist position (ambiguous alignment)"}
        if status == "held":
            for track_index, _ in source_tracks:
                alignment.setdefault(track_index, {"held": reason})

    shows_covered = sorted(grouped)
    earliest_date = min(
        date_value
        for date_value, show_ids in shows_by_date.items()
        if len(show_ids) == 1 and show_ids[0] in shows_covered
    )

    # Spotify album URL from any release in the group (primary release preferred).
    album_url, album_url_release = "", ""
    for candidate in [primary] + sorted((release for release in releases if release["id"] != primary["id"]), key=lambda release: release["id"]):
        album_url = spotify_album_url(candidate.get("url_relations", []))
        if album_url:
            album_url_release = candidate["id"]
            break

    release_date = full_date(group.get("first_release_date", ""))
    date_note = ""
    if not release_date:
        candidates = sorted(full_date(release.get("date", "")) for release in releases if full_date(release.get("date", "")))
        if candidates:
            release_date = candidates[0]
            date_note = f"release date from earliest fully dated release in the group (release-group first release date is '{group.get('first_release_date', '')}')"
        else:
            date_note = f"release date left blank: MusicBrainz gives only '{group.get('first_release_date', '')}'"

    mapped = sum(1 for index in range(len(tracks)) if index in alignment and "held" not in alignment[index])
    notes = [
        f"MusicBrainz release {primary['id']}",
        f"release group {group['id']}",
        f"show resolution: {resolution}",
        "spans more than one show" if spans_multiple else f"covers one canonical show {shows_covered[0]}",
        f"{mapped}/{len(tracks)} tracks mapped to canonical performances",
    ]
    if album_url and album_url_release != primary["id"]:
        notes.append(f"Spotify album URL from MusicBrainz release {album_url_release} in the same group")
    if date_note:
        notes.append(date_note)

    release_row = {
        "title": group["title"] if group["title"] == primary["title"] else primary["title"],
        "artist_name": ARTIST_NAME,
        "release_date": release_date,
        "release_type": "live",
        "spotify_album_url": album_url,
        "source_url": f"https://musicbrainz.org/release/{primary['id']}",
        "notes": "; ".join(notes) + ".",
    }

    track_rows = []
    unmapped_reasons: Counter = Counter()
    for index, entry in enumerate(tracks):
        track = entry["track"]
        medium = entry["medium"]
        recording = track.get("recording", {})
        show_id, unattributed = attribution[index]
        location = f"disc {medium.get('position')} track {track.get('number') or track.get('position')}"
        length = track.get("length_ms") or recording.get("length_ms")
        performance_id, note = "", ""
        if show_id and index in alignment and "held" not in alignment[index]:
            performance_id = alignment[index]["performance_id"]
            note = f"{location}; MusicBrainz recording {recording.get('id', '')}; title aligned uniquely and monotonically with the {show_id} setlist."
        elif show_id and index in alignment:
            reason = alignment[index]["held"]
            note = f"{location}; MusicBrainz recording {recording.get('id', '')}; no canonical performance mapped: setlist alignment for {show_id} held ({reason})."
            unmapped_reasons[f"alignment held: {re.sub(r'_at_track_\d+:.*$|_\d+_ways$|_for_track_\d+$', '', reason)}"] += 1
        elif show_id:
            canonical_titles = {normalized_title(songs[row["song_id"]]) for row in performances_by_show.get(show_id, [])}
            if looks_like_medley(track.get("title", ""), canonical_titles):
                why = "track combines more than one canonical performance (medley); needs the segment bridge table"
            else:
                why = "title is not in the show's canonical setlist (intro, tuning, banter, or source-only segment)"
            note = f"{location}; MusicBrainz recording {recording.get('id', '')}; no canonical performance mapped: {why}."
            unmapped_reasons[why.split(" (")[0]] += 1
        else:
            note = f"{location}; MusicBrainz recording {recording.get('id', '')}; no canonical performance mapped: {unattributed}."
            unmapped_reasons[unattributed.split(" (")[0]] += 1
        track_rows.append(
            {
                "track_number": index + 1,
                "performance_id": performance_id,
                "track_title": track.get("title", ""),
                "duration_seconds": str(round(length / 1000)) if isinstance(length, (int, float)) else "",
                "spotify_track_url": spotify_track_url(recording.get("url_relations", [])),
                "notes": note,
                "_show_id": show_id,
            }
        )

    decision.update(
        {
            "status": "promoted",
            "spans_multiple_shows": spans_multiple,
            "shows": shows_covered,
            "resolution": resolution,
            "alignment": alignment_notes,
            "tracks_mapped": mapped,
            "tracks_unmapped": len(tracks) - mapped,
            "unmapped_reasons": dict(unmapped_reasons),
            "spotify_album_url": album_url,
            "earliest_show_date": earliest_date,
            "release_row": release_row,
            "track_rows": track_rows,
        }
    )
    return decision


# --- release_id assignment ---

def base_release_id(group: dict, decision: dict) -> str:
    """Slug from the release-group title plus the show date it names.

    A release whose title names exactly one show date (or that covers exactly
    one show) becomes ``release-<title before the first colon>-<show date>``,
    for example ``release-dicks-picks-volume-8-1970-05-02``.  A compilation
    spanning several shows without a single title date keeps its full title and
    the release year instead, for example ``release-europe-72-1972``.
    """

    title = group["title"].translate(DASHES)
    for pattern in (US_DAY_LIST, US_DAY_RANGE, US_DATE, ISO_DATE, NUMERIC_DASH_DATE, TEXT_DAY_LIST, TEXT_DATE):
        title = pattern.sub(" ", title)
    title_dates = decision.get("title_dates", [])
    if not decision["spans_multiple_shows"] or len(title_dates) == 1:
        show_date = title_dates[0] if len(title_dates) == 1 else decision["earliest_show_date"]
        head = title.split(":", 1)[0]
        slug = slugify(head) or slugify(title) or slugify(group["title"])
        return f"release-{slug}-{show_date}"
    slug = slugify(title) or slugify(group["title"])
    year = (group.get("first_release_date") or "")[:4]
    if year and not slug.endswith(year):
        return f"release-{slug}-{year}"
    if year:
        return f"release-{slug}"
    return f"release-{slug}-{decision['earliest_show_date']}"


def previous_ids(rows: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        for mbid in re.findall(r"(?:MusicBrainz release|release group) ([0-9a-f-]{36})", row.get("notes", "")):
            mapping.setdefault(mbid, row["release_id"])
    return mapping


# --- validation ---

def validate(release_rows: list[dict], track_rows: list[dict], performances_by_show: dict[str, list[dict]], show_of_track: dict[tuple[str, int], str]) -> None:
    ids = [row["release_id"] for row in release_rows]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"duplicate release_id values: {[key for key, count in Counter(ids).items() if count > 1]}")
    for row in release_rows:
        if not row["title"] or not row["source_url"]:
            raise SystemExit(f"release {row['release_id']} is missing title or source_url")
        if row["release_date"]:
            date.fromisoformat(row["release_date"])
    performance_show = {row["performance_id"]: show_id for show_id, rows in performances_by_show.items() for row in rows}
    seen: set[tuple[str, int]] = set()
    for row in track_rows:
        key = (row["release_id"], int(row["track_number"]))
        if key in seen or key[1] <= 0:
            raise SystemExit(f"invalid or duplicate track key {key}")
        seen.add(key)
        if row["release_id"] not in set(ids):
            raise SystemExit(f"track references unknown release {row['release_id']}")
        if row["duration_seconds"] and int(row["duration_seconds"]) < 0:
            raise SystemExit(f"negative duration for {key}")
        if not row["track_title"]:
            raise SystemExit(f"blank track_title for {key}")
        if row["performance_id"]:
            if row["performance_id"] not in performance_show:
                raise SystemExit(f"unknown performance {row['performance_id']} for {key}")
            expected = show_of_track.get(key)
            if expected and performance_show[row["performance_id"]] != expected:
                raise SystemExit(f"performance {row['performance_id']} is not in show {expected} for {key}")


def main() -> None:
    shows_by_date, performances_by_show, songs = load_canonical()
    groups = {record["source_record_id"]: record["raw_payload"]["release_group"] for record in read_jsonl(RELEASE_GROUPS_PATH)}
    releases_by_group: dict[str, list[dict]] = defaultdict(list)
    for record in read_jsonl(RELEASES_PATH):
        release = record["raw_payload"]["release"]
        if release.get("status", "").casefold() != "official":
            continue
        releases_by_group[release["release_group"]["id"]].append(release)

    release_header, existing_releases = read_csv(RELEASES_CSV)
    track_header, existing_tracks = read_csv(TRACKS_CSV)
    if release_header != RELEASE_FIELDS or track_header != TRACK_FIELDS:
        raise SystemExit("canonical release CSV headers changed; refusing to write")
    kept_releases = [row for row in existing_releases if MANAGED_MARKER not in row.get("notes", "")]
    kept_ids = {row["release_id"] for row in kept_releases}
    kept_tracks = [row for row in existing_tracks if row["release_id"] in kept_ids]
    curated_urls = {row[column] for row in kept_releases for column in ("spotify_album_url", "source_url") if row.get(column)}
    # A hand-curated release covers the show(s) its mapped tracks belong to.  A
    # MusicBrainz single-show release for the same show issued in the same year
    # is almost certainly the same product under a different title, so it is
    # held for review instead of being written as a second row.
    performance_show = {row["performance_id"]: show_id for show_id, rows in performances_by_show.items() for row in rows}
    curated_show_years: dict[tuple[str, str], str] = {}
    for row in kept_releases:
        shows = {performance_show[track["performance_id"]] for track in kept_tracks if track["release_id"] == row["release_id"] and track["performance_id"] in performance_show}
        if len(shows) == 1:
            curated_show_years[(shows.pop(), (row.get("release_date") or "")[:4])] = row["release_id"]
    id_by_mbid = previous_ids(existing_releases)

    decisions: list[dict] = []
    new_releases: list[dict] = []
    new_tracks: list[dict] = []
    show_of_track: dict[tuple[str, int], str] = {}
    used_ids = set(kept_ids)
    status_counts: Counter = Counter()
    reason_counts: Counter = Counter()

    for group_id in sorted(groups):
        group = groups[group_id]
        decision = process_group(group, releases_by_group.get(group_id, []), shows_by_date, performances_by_show, songs)
        if decision["status"] == "promoted":
            url = decision["release_row"]["spotify_album_url"]
            if url and url in curated_urls:
                decision["status"] = "skipped"
                decision["reason"] = f"already_curated_release:{next(row['release_id'] for row in kept_releases if url in (row.get('spotify_album_url'), row.get('source_url')))}"
            elif not decision["spans_multiple_shows"] and (decision["shows"][0], (group.get("first_release_date") or "")[:4]) in curated_show_years:
                decision["status"] = "skipped"
                decision["reason"] = f"possible_duplicate_of_curated_release:{curated_show_years[(decision['shows'][0], (group.get('first_release_date') or '')[:4])]}"
        if decision["status"] == "promoted":
            release_id = id_by_mbid.get(decision["release_id_mbid"]) or id_by_mbid.get(group_id)
            if not release_id or release_id in used_ids:
                release_id = base_release_id(group, decision)
                if release_id in used_ids:
                    release_id = f"{release_id}-{decision['release_id_mbid'][:8]}"
            used_ids.add(release_id)
            decision["release_id"] = release_id
            new_releases.append({"release_id": release_id, **decision.pop("release_row")})
            for track in decision.pop("track_rows"):
                show_id = track.pop("_show_id")
                new_tracks.append({"release_id": release_id, **track})
                if show_id:
                    show_of_track[(release_id, int(track["track_number"]))] = show_id
        status_counts[decision["status"]] += 1
        if decision["status"] != "promoted":
            reason_counts[decision["reason"].split(":")[0]] += 1
        decisions.append(decision)

    new_releases.sort(key=lambda row: row["release_id"])
    order = {row["release_id"]: index for index, row in enumerate(new_releases)}
    new_tracks.sort(key=lambda row: (order[row["release_id"]], int(row["track_number"])))
    all_releases = kept_releases + new_releases
    all_tracks = kept_tracks + new_tracks
    validate(all_releases, all_tracks, performances_by_show, show_of_track)
    write_csv(RELEASES_CSV, RELEASE_FIELDS, all_releases)
    write_csv(TRACKS_CSV, TRACK_FIELDS, all_tracks)
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")

    mapped = sum(1 for row in new_tracks if row["performance_id"])
    unmapped_reasons: Counter = Counter()
    for decision in decisions:
        if decision["status"] == "promoted":
            unmapped_reasons.update(decision.get("unmapped_reasons", {}))
    print(
        json.dumps(
            {
                "release_groups": len(groups),
                "release_groups_with_official_releases": len(releases_by_group),
                "official_releases_fetched": sum(len(rows) for rows in releases_by_group.values()),
                "statuses": dict(status_counts),
                "held_reasons": dict(reason_counts),
                "promoted_single_show": sum(1 for d in decisions if d["status"] == "promoted" and not d["spans_multiple_shows"]),
                "promoted_multi_show": sum(1 for d in decisions if d["status"] == "promoted" and d["spans_multiple_shows"]),
                "promoted_with_spotify_album_url": sum(1 for row in new_releases if row["spotify_album_url"]),
                "tracks_written": len(new_tracks),
                "tracks_mapped": mapped,
                "tracks_unmapped": len(new_tracks) - mapped,
                "unmapped_reasons": dict(unmapped_reasons.most_common()),
                "kept_curated_releases": len(kept_releases),
                "review_path": str(REVIEW_PATH.relative_to(ROOT)),
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
