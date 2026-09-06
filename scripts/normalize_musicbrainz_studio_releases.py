#!/usr/bin/env python3
"""Promote MusicBrainz studio release groups into the canonical release tables.

Input: the compact raw records written by
``scripts/collect/fetch_musicbrainz_studio_releases.py``
(``data/raw/releases/musicbrainz-studio-release-groups.jsonl`` and
``musicbrainz-studio-releases.jsonl``), plus the optional
``musicbrainz-studio-release-credits.jsonl`` written by the collector's
``--artist-relations`` pass, which is the only source of per-person instrument
credits.

Output: ``studio`` rows in ``data/canonical/official_releases.csv``, their track
rows in ``data/canonical/official_release_tracks.csv`` carrying ``song_id``,
album credits in ``data/canonical/release_personnel.csv``, and a decision log at
``data/raw/releases/musicbrainz-studio-release-review.jsonl``.

Rules:

* **Scope.**  The catalog is the Grateful Dead studio albums plus the solo and
  side-project records that first carried songs the band played.  The collector
  is deliberately fail-closed and keeps every ``Album`` release group that
  MusicBrainz did not tag ``Live``, so some concert and bootleg material arrives
  in the raw file with no ``Live`` secondary type to reject it.  Filtering that
  material is this script's job, not the collector's.
* **Holding suspected live material.**  A release group is held, never promoted,
  when its title carries a calendar date, names a venue in ``venues.csv``, uses
  an explicit live phrase (``live``, ``alive``, ``in concert``, ``final show``
  …), or reads as a hits compilation; when a third or more of the chosen
  release's tracks carry a MusicBrainz ``live`` recording disambiguation; or
  when it appears in ``MANUAL_HOLDS`` below.  Erring toward holding is
  deliberate: a studio album held by mistake is visible in the review log and
  cheap to promote by hand, while a bootleg shipped as a studio album attaches a
  wrong record to real songs.
* **One release per release group.**  The chosen release is the official release
  that best represents the original album: single-disc first (anniversary boxes
  add live bonus discs), then closest to the group's modal track count, then
  CD/digital before vinyl, then the earliest date, then the lowest MBID.
* **Songs are resolved, never guessed.**  A track title is matched against
  ``songs.csv`` titles and slugs plus the alias table already reviewed for the
  live pass.  A title that does not match leaves ``song_id`` blank with the
  reason in ``notes``; nothing is inferred from track order or position.
* **Personnel are resolved, never guessed.**  A ``release_personnel`` row needs a
  person resolvable in ``people.csv`` *and* an instrument, because ``instrument``
  is part of the table's primary key.  Anything else goes to the review log.
* **Row ownership.**  Rows written here carry ``MusicBrainz release <mbid>`` for
  provenance *and* the phrase ``studio release-group pass`` so that reruns
  replace only this script's own rows.  The MBID marker alone is not enough: the
  294 rows from ``normalize_musicbrainz_live_releases.py`` and the hand-curated
  Veneta rows carry MBIDs too, and both must survive untouched.  Reruns reuse the
  ``release_id`` previously assigned to the same release or release-group MBID,
  so IDs never renumber.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW_DIR = ROOT / "data" / "raw" / "releases"
RELEASE_GROUPS_PATH = RAW_DIR / "musicbrainz-studio-release-groups.jsonl"
RELEASES_PATH = RAW_DIR / "musicbrainz-studio-releases.jsonl"
CREDITS_PATH = RAW_DIR / "musicbrainz-studio-release-credits.jsonl"
REVIEW_PATH = RAW_DIR / "musicbrainz-studio-release-review.jsonl"
RELEASES_CSV = CANONICAL / "official_releases.csv"
TRACKS_CSV = CANONICAL / "official_release_tracks.csv"
PERSONNEL_CSV = CANONICAL / "release_personnel.csv"

RELEASE_FIELDS = ["release_id", "title", "artist_name", "release_date", "release_type", "spotify_album_url", "source_url", "notes"]
TRACK_FIELDS = ["release_id", "track_number", "performance_id", "song_id", "track_title", "duration_seconds", "spotify_track_url", "notes"]
PERSONNEL_FIELDS = ["release_id", "person_id", "role", "instrument", "notes"]
RELEASE_TYPES = {"studio", "live", "compilation", "single"}
RELEASE_TYPE = "studio"
STUDIO_MARKER = "studio release-group pass"


def owns_row(row: dict) -> bool:
    """True when this pass wrote the row and a rerun may replace it.

    The narrow marker is the whole point.  ``MusicBrainz release <mbid>`` also
    appears in every live-pass row, so a filter built on it would make this pass
    delete the live catalog; ``normalize_musicbrainz_live_releases.owns_row`` is
    the mirror of this function and excludes ``STUDIO_MARKER`` for the same
    reason.  Together they let the two passes run in either order, repeatedly.
    """

    return STUDIO_MARKER in row.get("notes", "")

_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_APOSTROPHE = re.compile(r"['‘’ʼ]")

# Titles that announce a concert recording rather than a studio album.  Kept
# deliberately short and literal; anything subtler belongs in MANUAL_HOLDS with
# a written reason.
LIVE_PHRASE = re.compile(
    r"\b(live|alive|in concert|unplugged|on ?stage|bootleg|final show|last show|farewell show|"
    r"recorded live|soundboard)\b"
)
# Hits packages and retrospectives: real records, but not studio albums.
COMPILATION_PHRASE = re.compile(r"\b(very best|best of|greatest hits|anthology|essential|retrospective|collection)\b")
# A venue name must be this long before a substring match counts, so that short
# names ("The Ark") cannot fire on ordinary album titles.
MIN_VENUE_NAME = 12
# Share of a chosen release's tracks that must carry MusicBrainz live evidence
# before the whole release group is held.
LIVE_TRACK_SHARE = 1 / 3

# MusicBrainz artist-relation types that describe someone playing on the record.
# Everything else (producer, engineer, art direction) is a real credit with no
# instrument, and release_personnel cannot store one: instrument is part of the
# primary key.  Those are held, not invented.
PERFORMER_RELATION_TYPES = frozenset({"instrument", "vocal", "performer", "performing orchestra"})

# Release groups the automatic signals cannot see, held by hand with a reason.
# Each entry is a MusicBrainz release-group MBID.  Add to this list rather than
# loosening the regexes above, which would start holding real studio albums.
MANUAL_HOLDS = {
    "5287ce24-bbd4-46a7-b16e-9ceece084deb": (
        "Move Me Brightly is the filmed Jerry Garcia birthday tribute concert, not a Bob Weir "
        "studio album; its 14 tracks are Grateful Dead standards performed by a guest band"
    ),
    "3e9aef44-948c-402c-aa34-139b8ecf7911": (
        "Kingfish Double Dose is a concert set of covers; none of its titles first appeared here, "
        "so it is outside the 'records that first carried songs the band played' scope"
    ),
    "900cfb8d-cb66-34f0-8919-c8fdde86dccf": (
        "duplicate release group for Kingfish Double Dose (same track list, no date, no external "
        "identifiers) and held for the same reason as 3e9aef44"
    ),
    "1d0e909f-c764-3696-9002-946f5b0f14da": (
        "The Pizza Tapes (2000) is an informally taped Garcia/Grisman/Rice jam session issued "
        "archivally, not a studio album that first carried a song: it first carried nothing, five "
        "of its tracks are fragments titled 'Appetizer', and promoting it attached song-so-what "
        "and song-knockin-on-heaven-s-door to a jam tape"
    ),
    "1670f945-b182-385e-9766-52aef31bb304": (
        "So What (1998) is a posthumous Garcia/Grisman compilation of alternate takes from earlier "
        "sessions, not a record that first carried a song; its three tracks all titled 'So What' "
        "all resolve to song-so-what, the only duplicate (release_id, song_id) pair in the set"
    ),
    "56568b68-084d-36fa-99b9-acc80d02d43a": (
        "Blue Incantation is a Sanjay Mishra album that Jerry Garcia guests on; a guest appearance "
        "is neither a solo record nor a side-project record, so it is outside the catalog's scope"
    ),
}


# --- shared vocabulary from the live pass -------------------------------------
# Imported rather than copied so the two passes cannot drift apart.  The live
# module defines constants and functions only; importing it runs nothing.

def _load_live_module():
    spec = importlib.util.spec_from_file_location(
        "_normalize_musicbrainz_live_releases", ROOT / "scripts" / "normalize_musicbrainz_live_releases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LIVE = _load_live_module()
extract_dates = _LIVE.extract_dates
slugify = _LIVE.slugify

# Two additions to the live pass's reviewed alias table, in the same spirit
# (documented alternate and article variants whose target is an existing
# songs.csv title): MusicBrainz spells the debut album's opener with a leading
# article, and the 1978 studio take of Minglewood Blues with a third variant.
EXTRA_ALIASES = {
    "the golden road to unlimited devotion": "golden road to unlimited devotion",
    "all new minglewood blues": "minglewood blues",
}


def _fold(title: str) -> str:
    """Fold a title to its comparison form.

    Apostrophes vanish so ``Truckin'`` and ``Truckin`` agree, ``&`` becomes
    ``and`` so ``Cold Rain & Snow`` reaches ``Cold Rain And Snow``, and every
    other run of punctuation becomes a single space.
    """

    value = _APOSTROPHE.sub("", title or "").casefold().replace("&", " and ")
    return _PUNCTUATION.sub(" ", value).strip()


def _fold_variants(title: str) -> set[str]:
    """Both readings of an apostrophe, so the lookup table answers either.

    ``Truckin'`` wants the apostrophe to vanish; the live pass's alias table was
    written with the apostrophe read as a separator (``i can t get no
    satisfaction``).  Indexing both spellings costs nothing and keeps
    ``resolve_song_id`` a single dictionary lookup.
    """

    separated = _PUNCTUATION.sub(" ", (title or "").casefold().replace("&", " and ")).strip()
    return {value for value in (_fold(title), separated) if value}


def resolve_song_id(title: str, songs: dict[str, str]) -> str | None:
    """Resolve a track title to a canonical song, or hold it.

    Fail-closed: a title that does not match a known song returns None and is
    recorded in the review log.  A guessed match would put a wrong song on a
    record permanently.
    """

    return songs.get(_fold(title))


def release_id_for(title: str) -> str:
    """Canonical lowercase kebab-case release id for an album title.

    The album title alone identifies the release; collisions between two groups
    that share a title are disambiguated by the caller, which can see both.
    """

    return "release-" + _PUNCTUATION.sub("-", _APOSTROPHE.sub("", title or "").casefold()).strip("-")


# --- loading ------------------------------------------------------------------

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


def load_songs() -> dict[str, str]:
    """Map every folded canonical title, slug, and reviewed alias to a song_id."""

    _, rows = read_csv(CANONICAL / "songs.csv")
    songs: dict[str, str] = {}
    for row in rows:
        for key in _fold_variants(row["title"]) | _fold_variants(row["slug"]):
            songs.setdefault(key, row["song_id"])
    for source, target in {**_LIVE.TITLE_ALIASES, **EXTRA_ALIASES}.items():
        song_id = next((songs[key] for key in _fold_variants(target) if key in songs), None)
        if song_id is None:
            # An alias whose target left songs.csv would silently stop working.
            continue
        for key in _fold_variants(source):
            songs.setdefault(key, song_id)
    return songs


def load_people() -> dict[str, str]:
    _, rows = read_csv(CANONICAL / "people.csv")
    return {_fold(row["name"]): row["person_id"] for row in rows}


def load_venue_names() -> list[str]:
    _, rows = read_csv(CANONICAL / "venues.csv")
    names = {_fold(row["name"]) for row in rows}
    return sorted(name for name in names if len(name) >= MIN_VENUE_NAME)


# --- choosing the release that represents the album ---------------------------

def track_count(release: dict) -> int:
    return sum(len(medium["tracks"]) for medium in release["media"])


def format_rank(release: dict) -> int:
    """Prefer CD/digital editions: vinyl sides split and reorder long tracks."""

    formats = {(medium.get("format") or "").casefold() for medium in release["media"]}
    if any("vinyl" in name for name in formats):
        return 2
    if any(name and "cd" not in name and "digital" not in name for name in formats):
        return 1
    return 0


def modal_track_count(releases: list[dict]) -> int:
    """The track count most editions of this album agree on.

    Single-disc editions vote first; anniversary boxes and deluxe reissues pad
    the album with outtakes and live discs and must not decide the shape of the
    record.
    """

    single = [release for release in releases if len(release["media"]) == 1] or releases
    counts = Counter(track_count(release) for release in single)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def choose_release(releases: list[dict]) -> dict:
    modal = modal_track_count(releases)
    return sorted(
        releases,
        key=lambda release: (
            len(release["media"]) > 1,
            abs(track_count(release) - modal),
            format_rank(release),
            _LIVE.date_sort_key(release.get("date", "")),
            release["id"],
        ),
    )[0]


def flatten_tracks(release: dict) -> list[dict]:
    entries = []
    for medium in sorted(release["media"], key=lambda medium: medium.get("position") or 0):
        for track in sorted(medium["tracks"], key=lambda track: track.get("position") or 0):
            entries.append({"medium": medium, "track": track})
    return entries


def live_track_count(entries: list[dict]) -> int:
    """Tracks MusicBrainz itself marks as concert recordings."""

    total = 0
    for entry in entries:
        disambiguation = ((entry["track"].get("recording") or {}).get("disambiguation") or "").casefold()
        title = (entry["track"].get("title") or "").casefold()
        if re.search(r"\blive\b", disambiguation) or "(live" in title or "[live" in title:
            total += 1
    return total


# --- the live/bootleg filter --------------------------------------------------

def live_title_signals(title: str, venue_names: list[str]) -> list[str]:
    """Reasons the title of a release group says 'concert', not 'studio album'."""

    folded = _fold(title)
    signals = []
    dates = sorted(extract_dates(title))
    if dates:
        signals.append(f"date in title ({', '.join(dates)})")
    matched_venues = [name for name in venue_names if name in folded]
    if matched_venues:
        signals.append(f"venue in title ({', '.join(matched_venues)})")
    phrases = sorted(set(LIVE_PHRASE.findall(folded)))
    if phrases:
        signals.append(f"live phrase in title ({', '.join(phrases)})")
    return signals


# --- personnel ----------------------------------------------------------------

def load_release_credits() -> dict[str, dict]:
    """Releases re-fetched with ``artist-rels``, keyed by release MBID.

    Written by ``fetch_musicbrainz_studio_releases.py --artist-relations``.  The
    file is optional: without it this pass simply writes no personnel and says
    so in the review log, because the browse used for the main raw file carries
    ``artist-credits`` (the billed album artist) and no per-person relations.
    """

    if not CREDITS_PATH.exists():
        return {}
    return {record["source_record_id"]: record["raw_payload"]["release"] for record in read_jsonl(CREDITS_PATH)}


def _credit(relation: dict, source: str) -> dict:
    """One MusicBrainz artist relation as a candidate personnel credit.

    ``role`` follows ``show_performers``' vocabulary so the two tables read
    alike: an instrument or vocal relation is a ``performer``, and anything else
    (producer, engineer, art direction) keeps MusicBrainz's own relation type.

    Only a performing relation yields an instrument.  Attributes on the other
    relation types are qualifiers, not instruments -- MusicBrainz gives
    ``producer`` the attributes ``executive``, ``additional`` and ``assistant``,
    and reading those as instruments would put "Bob Weir, producer, executive"
    in a column that means what he played.  Those credits are real and are held
    with reason ``no_instrument``, which is what the primary key forces.
    """

    performing = (relation.get("type", "") or "") in PERFORMER_RELATION_TYPES
    return {
        "name": relation.get("artist_name", "") or "",
        "relation_type": relation.get("type", "") or "",
        "role": "performer" if performing else (relation.get("type", "") or ""),
        "instruments": [value for value in (relation.get("attributes") or []) if value] if performing else [],
        "source": source,
    }


def personnel_credits(release: dict) -> list[dict]:
    """Flatten a release's artist relations, release-level and recording-level.

    MusicBrainz keeps most instrument credits on the recording rather than the
    release, so both levels are read; ``release_personnel`` has no track column,
    and a person credited on many tracks of one album is one row per instrument.
    """

    credits = [_credit(relation, f"release {release['id']}") for relation in release.get("artist_relations") or []]
    for medium in release.get("media") or []:
        for track in medium.get("tracks") or []:
            recording = track.get("recording") or {}
            credits.extend(
                _credit(relation, f"recording {recording.get('id', '')}")
                for relation in recording.get("artist_relations") or []
            )
    return credits


def resolve_personnel(release_id: str, release: dict, people: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Return (rows, held) for one release's credits.

    A row needs a person resolvable in people.csv *and* an instrument, because
    ``instrument`` is part of the ``release_personnel`` primary key and a credit
    without one cannot be stored.  Rows and holds are both aggregated by their
    key: a guitarist credited on twelve recordings is one row that says twelve,
    not twelve rows the primary key would reject.
    """

    rows: dict[tuple[str, str, str], dict] = {}
    held: dict[tuple[str, str, str], dict] = {}

    def hold(key: tuple[str, str, str], credit: dict, reason: str) -> None:
        record = held.setdefault(
            key,
            {
                "release_id": release_id,
                "name": credit["name"],
                "relation_type": credit["relation_type"],
                "role": credit["role"],
                "reason": reason,
                "credits": 0,
                "sources": [],
            },
        )
        record["credits"] += 1
        if len(record["sources"]) < 3 and credit["source"] not in record["sources"]:
            record["sources"].append(credit["source"])

    for credit in personnel_credits(release):
        person_id = people.get(_fold(credit["name"]))
        if not person_id:
            hold((credit["name"], credit["relation_type"], "person_not_in_people_csv"), credit, "person_not_in_people_csv")
            continue
        if not credit["instruments"]:
            hold((credit["name"], credit["relation_type"], "no_instrument"), credit, "no_instrument")
            continue
        for instrument in credit["instruments"]:
            key = (person_id, credit["role"], instrument)
            row = rows.setdefault(
                key,
                {
                    "release_id": release_id,
                    "person_id": person_id,
                    "role": credit["role"],
                    "instrument": instrument,
                    "relation_types": set(),
                    "credits": 0,
                },
            )
            row["relation_types"].add(credit["relation_type"])
            row["credits"] += 1

    ordered_rows = []
    for key in sorted(rows):
        row = rows[key]
        credits = row.pop("credits")
        types = ", ".join(sorted(row.pop("relation_types")))
        row["notes"] = (
            f"MusicBrainz artist relation ({types}) on {credits} "
            f"{'credit' if credits == 1 else 'credits'} for release {release['id']}; {STUDIO_MARKER}."
        )
        ordered_rows.append(row)
    return ordered_rows, [held[key] for key in sorted(held)]


# --- per release-group processing ---------------------------------------------

def process_group(
    group: dict,
    artist_name: str,
    releases: list[dict],
    songs: dict[str, str],
    people: dict[str, str],
    venue_names: list[str],
) -> dict:
    """Return a decision record, with canonical rows when the group is promoted."""

    decision = {
        "release_group_id": group["id"],
        "release_group_title": group["title"],
        "artist_name": artist_name,
        "first_release_date": group.get("first_release_date", ""),
        "secondary_types": group.get("secondary_types", []),
        "official_release_count": len(releases),
        "status": "held",
        "reason": "",
    }

    signals = live_title_signals(group["title"], venue_names)
    if signals:
        decision["reason"] = "suspected_live_material_in_title"
        decision["signals"] = signals
        return decision
    compilation = sorted(set(COMPILATION_PHRASE.findall(_fold(group["title"]))))
    if compilation:
        decision["reason"] = "suspected_compilation_in_title"
        decision["signals"] = [f"compilation phrase in title ({', '.join(compilation)})"]
        return decision
    if group["id"] in MANUAL_HOLDS:
        decision["reason"] = "manually_held_not_a_studio_album"
        decision["signals"] = [MANUAL_HOLDS[group["id"]]]
        return decision
    if not releases:
        # The collector browses official releases by artist; a group with none is
        # bootleg-only or the artist is credited on tracks rather than the album.
        decision["reason"] = "no_official_release_fetched"
        return decision

    primary = choose_release(releases)
    entries = flatten_tracks(primary)
    decision.update({"release_mbid": primary["id"], "release_title": primary["title"], "track_count": len(entries)})
    if not entries:
        decision["reason"] = "release_has_no_tracks"
        return decision

    live_tracks = live_track_count(entries)
    if live_tracks >= max(1, round(len(entries) * LIVE_TRACK_SHARE)):
        decision["reason"] = "live_recordings_on_chosen_release"
        decision["signals"] = [f"{live_tracks}/{len(entries)} tracks carry a MusicBrainz live recording disambiguation"]
        return decision

    album_url, album_url_release = "", ""
    for candidate in [primary] + sorted(
        (release for release in releases if release["id"] != primary["id"]), key=lambda release: release["id"]
    ):
        album_url = _LIVE.spotify_album_url(candidate.get("url_relations", []))
        if album_url:
            album_url_release = candidate["id"]
            break

    # A studio album's release date is the release group's first release date.
    # When MusicBrainz gives only a year or a month, an edition's own full date
    # is used only if it corroborates that partial value; otherwise the field is
    # left blank with the partial value in notes.  Without that guard a 2005
    # remaster would be published as the release date of a 1972 album.
    partial = group.get("first_release_date", "") or ""
    release_date = _LIVE.full_date(partial)
    date_note = ""
    if not release_date:
        dated = sorted(
            value
            for value in (_LIVE.full_date(release.get("date", "")) for release in releases)
            if value and partial and value.startswith(partial)
        )
        if dated:
            release_date = dated[0]
            date_note = f"release date from the earliest edition dated within '{partial}'"
        else:
            date_note = (
                f"release date left blank: MusicBrainz gives only '{partial}' for the release group and no "
                "edition carries a full date inside it"
            )

    track_rows: list[dict] = []
    unresolved_titles: list[str] = []
    for index, entry in enumerate(entries):
        track = entry["track"]
        recording = track.get("recording") or {}
        title = track.get("title", "")
        song_id = resolve_song_id(title, songs)
        location = f"disc {entry['medium'].get('position')} track {track.get('number') or track.get('position')}"
        note = f"{location}; MusicBrainz recording {recording.get('id', '')}"
        if song_id:
            note += f"; track title resolved to canonical song {song_id}."
        else:
            note += "; no canonical song matched: title is not a songs.csv title, slug, or reviewed alias."
            unresolved_titles.append(title)
        length = track.get("length_ms") or recording.get("length_ms")
        track_rows.append(
            {
                "track_number": index + 1,
                "performance_id": "",
                "song_id": song_id or "",
                "track_title": title,
                "duration_seconds": str(round(length / 1000)) if isinstance(length, (int, float)) else "",
                "spotify_track_url": _LIVE.spotify_track_url(recording.get("url_relations", [])),
                "notes": note,
            }
        )

    resolved = sum(1 for row in track_rows if row["song_id"])
    notes = [
        f"MusicBrainz release {primary['id']}",
        f"release group {group['id']}",
        STUDIO_MARKER,
        f"{resolved}/{len(track_rows)} tracks resolved to a canonical song",
    ]
    if primary["title"] != group["title"]:
        notes.append(f"chosen edition is titled '{primary['title']}'")
    if album_url and album_url_release != primary["id"]:
        notes.append(f"Spotify album URL from MusicBrainz release {album_url_release} in the same group")
    if date_note:
        notes.append(date_note)

    decision.update(
        {
            "status": "promoted",
            "reason": "",
            "tracks_resolved": resolved,
            "tracks_unresolved": len(track_rows) - resolved,
            "unresolved_titles": unresolved_titles,
            "spotify_album_url": album_url,
            "release_row": {
                "title": group["title"],
                "artist_name": artist_name,
                "release_date": release_date,
                "release_type": RELEASE_TYPE,
                "spotify_album_url": album_url,
                "source_url": f"https://musicbrainz.org/release/{primary['id']}",
                "notes": "; ".join(notes) + ".",
            },
            "track_rows": track_rows,
            "_primary": primary,
        }
    )
    return decision


# --- release_id assignment ----------------------------------------------------

def assign_release_ids(promoted: list[dict], reserved: set[str], id_by_mbid: dict[str, str]) -> dict[str, str]:
    """Give every promoted group a stable release_id.

    An id already assigned to this release or release-group MBID by an earlier
    run wins, so IDs never renumber.  Two groups that share a title are
    disambiguated by artist when the artists differ and by release-group year
    when they do not; an eight-character MBID suffix is the last resort.
    """

    assigned: dict[str, str] = {}
    remaining: list[dict] = []
    for decision in promoted:
        previous = id_by_mbid.get(decision["release_mbid"]) or id_by_mbid.get(decision["release_group_id"])
        if previous and previous not in reserved:
            assigned[decision["release_group_id"]] = previous
            reserved.add(previous)
        else:
            remaining.append(decision)

    by_base: dict[str, list[dict]] = defaultdict(list)
    for decision in remaining:
        by_base[release_id_for(decision["release_group_title"])].append(decision)
    for base, group in sorted(by_base.items()):
        artists = {decision["artist_name"] for decision in group}
        for decision in sorted(group, key=lambda decision: decision["release_group_id"]):
            candidates = [base] if len(group) == 1 else []
            if len(artists) == len(group) > 1:
                candidates.append(f"{base}-{slugify(decision['artist_name'])}")
            candidates.append(f"{base}-{(decision.get('first_release_date') or '')[:4]}".rstrip("-"))
            candidates.append(f"{base}-{decision['release_group_id'][:8]}")
            release_id = next(value for value in candidates if value and value not in reserved)
            assigned[decision["release_group_id"]] = release_id
            reserved.add(release_id)
    return assigned


def previous_studio_ids(rows: list[dict]) -> dict[str, str]:
    """Release and release-group MBIDs this script already assigned an id to."""

    mapping: dict[str, str] = {}
    for row in rows:
        if not owns_row(row):
            continue
        for mbid in re.findall(r"(?:MusicBrainz release|release group) ([0-9a-f-]{36})", row.get("notes", "")):
            mapping.setdefault(mbid, row["release_id"])
    return mapping


# --- validation ---------------------------------------------------------------

def validate(
    release_rows: list[dict],
    track_rows: list[dict],
    personnel_rows: list[dict],
    songs_by_id: set[str],
    performance_ids: set[str],
    people_ids: set[str],
) -> None:
    ids = [row["release_id"] for row in release_rows]
    duplicates = [key for key, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise SystemExit(f"duplicate release_id values: {duplicates}")
    known = set(ids)
    for row in release_rows:
        if not row["title"] or not row["source_url"]:
            raise SystemExit(f"release {row['release_id']} is missing title or source_url")
        if row["release_type"] not in RELEASE_TYPES:
            raise SystemExit(f"release {row['release_id']} has release_type {row['release_type']!r}")
        if row["release_date"]:
            date.fromisoformat(row["release_date"])
    seen: set[tuple[str, int]] = set()
    for row in track_rows:
        key = (row["release_id"], int(row["track_number"]))
        if key in seen or key[1] <= 0:
            raise SystemExit(f"invalid or duplicate track key {key}")
        seen.add(key)
        if row["release_id"] not in known:
            raise SystemExit(f"track references unknown release {row['release_id']}")
        if not row["track_title"]:
            raise SystemExit(f"blank track_title for {key}")
        if row["duration_seconds"] and int(row["duration_seconds"]) < 0:
            raise SystemExit(f"negative duration for {key}")
        if row["song_id"] and row["song_id"] not in songs_by_id:
            raise SystemExit(f"unknown song {row['song_id']} for {key}")
        if row["performance_id"] and row["performance_id"] not in performance_ids:
            raise SystemExit(f"unknown performance {row['performance_id']} for {key}")
    personnel_seen: set[tuple[str, str, str, str]] = set()
    for row in personnel_rows:
        key = (row["release_id"], row["person_id"], row["role"], row["instrument"])
        if key in personnel_seen:
            raise SystemExit(f"duplicate release_personnel key {key}")
        personnel_seen.add(key)
        if row["release_id"] not in known:
            raise SystemExit(f"personnel row references unknown release {row['release_id']}")
        if row["person_id"] not in people_ids:
            raise SystemExit(f"personnel row references unknown person {row['person_id']}")
        if not row["instrument"]:
            raise SystemExit(f"personnel row {key} has no instrument")


def main() -> None:
    songs = load_songs()
    _, song_rows = read_csv(CANONICAL / "songs.csv")
    songs_by_id = {row["song_id"] for row in song_rows}
    _, performance_rows = read_csv(CANONICAL / "performances.csv")
    performance_ids = {row["performance_id"] for row in performance_rows}
    people = load_people()
    people_ids = set(people.values())
    venue_names = load_venue_names()
    credits_by_mbid = load_release_credits()

    groups: dict[str, dict] = {}
    artist_of_group: dict[str, str] = {}
    for record in read_jsonl(RELEASE_GROUPS_PATH):
        payload = record["raw_payload"]
        groups[record["source_record_id"]] = payload["release_group"]
        artist_of_group[record["source_record_id"]] = payload.get("artist_name", "")
    releases_by_group: dict[str, list[dict]] = defaultdict(list)
    seen_release_mbids: set[str] = set()
    for record in read_jsonl(RELEASES_PATH):
        release = record["raw_payload"]["release"]
        if release.get("status", "").casefold() != "official" or release["id"] in seen_release_mbids:
            continue
        seen_release_mbids.add(release["id"])
        releases_by_group[release["release_group"]["id"]].append(release)
    for rows in releases_by_group.values():
        rows.sort(key=lambda release: release["id"])

    release_header, existing_releases = read_csv(RELEASES_CSV)
    track_header, existing_tracks = read_csv(TRACKS_CSV)
    personnel_header, existing_personnel = read_csv(PERSONNEL_CSV)
    if release_header != RELEASE_FIELDS or track_header != TRACK_FIELDS or personnel_header != PERSONNEL_FIELDS:
        raise SystemExit("canonical release CSV headers changed; refusing to write")

    # Everything this script did not write stays exactly as it is: the 294 rows
    # from the live pass and the hand-curated Veneta release and its tracks.
    kept_releases = [row for row in existing_releases if not owns_row(row)]
    kept_ids = {row["release_id"] for row in kept_releases}
    kept_tracks = [row for row in existing_tracks if row["release_id"] in kept_ids]
    kept_personnel = [row for row in existing_personnel if row["release_id"] in kept_ids]
    id_by_mbid = previous_studio_ids(existing_releases)

    decisions = [
        process_group(groups[group_id], artist_of_group[group_id], releases_by_group.get(group_id, []), songs, people, venue_names)
        for group_id in sorted(groups)
    ]
    promoted = [decision for decision in decisions if decision["status"] == "promoted"]
    release_ids = assign_release_ids(promoted, set(kept_ids), id_by_mbid)

    new_releases: list[dict] = []
    new_tracks: list[dict] = []
    new_personnel: list[dict] = []
    held_credits: list[dict] = []
    for decision in promoted:
        release_id = release_ids[decision["release_group_id"]]
        decision["release_id"] = release_id
        new_releases.append({"release_id": release_id, **decision.pop("release_row")})
        for track in decision.pop("track_rows"):
            new_tracks.append({"release_id": release_id, **track})
        primary = decision.pop("_primary")
        # The credits file carries the same release re-fetched with artist-rels;
        # the browse payload has no relations at all, so prefer it when present.
        rows, held = resolve_personnel(release_id, credits_by_mbid.get(primary["id"], primary), people)
        new_personnel.extend(rows)
        held_credits.extend(held)
        decision["personnel_rows"] = len(rows)
        decision["personnel_held"] = len(held)

    new_releases.sort(key=lambda row: row["release_id"])
    order = {row["release_id"]: index for index, row in enumerate(new_releases)}
    new_tracks.sort(key=lambda row: (order[row["release_id"]], int(row["track_number"])))
    new_personnel.sort(key=lambda row: (order[row["release_id"]], row["person_id"], row["role"], row["instrument"]))

    all_releases = kept_releases + new_releases
    all_tracks = kept_tracks + new_tracks
    all_personnel = kept_personnel + new_personnel
    validate(all_releases, all_tracks, all_personnel, songs_by_id, performance_ids, people_ids)
    write_csv(RELEASES_CSV, RELEASE_FIELDS, all_releases)
    write_csv(TRACKS_CSV, TRACK_FIELDS, all_tracks)
    write_csv(PERSONNEL_CSV, PERSONNEL_FIELDS, all_personnel)

    log: list[dict] = [{key: value for key, value in decision.items() if not key.startswith("_")} for decision in decisions]
    log.extend({"record": "held_credit", **credit} for credit in held_credits)
    if not credits_by_mbid:
        log.append(
            {
                "record": "personnel_source_unavailable",
                "reason": "no_artist_relations_fetched",
                "detail": (
                    f"{CREDITS_PATH.relative_to(ROOT)} does not exist, and the browse that produced "
                    f"{RELEASES_PATH.relative_to(ROOT)} carries artist-credits (the billed album artist) but no "
                    "per-person instrument relations; run scripts/collect/fetch_musicbrainz_studio_releases.py "
                    "--artist-relations to populate release_personnel.csv"
                ),
            }
        )
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for record in log:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    held_reasons = Counter(decision["reason"] for decision in decisions if decision["status"] != "promoted")
    resolved = sum(1 for row in new_tracks if row["song_id"])
    print(
        json.dumps(
            {
                "release_groups": len(groups),
                "release_groups_with_official_releases": len(releases_by_group),
                "official_releases_fetched": sum(len(rows) for rows in releases_by_group.values()),
                "promoted": len(promoted),
                "held": len(decisions) - len(promoted),
                "held_reasons": dict(sorted(held_reasons.items())),
                "tracks_written": len(new_tracks),
                "tracks_resolved_to_a_song": resolved,
                "tracks_unresolved": len(new_tracks) - resolved,
                "distinct_songs_linked": len({row["song_id"] for row in new_tracks if row["song_id"]}),
                "personnel_rows": len(new_personnel),
                "personnel_credits_held": len(held_credits),
                "releases_with_spotify_album_url": sum(1 for row in new_releases if row["spotify_album_url"]),
                "kept_rows_untouched": {"releases": len(kept_releases), "tracks": len(kept_tracks), "personnel": len(kept_personnel)},
                "review_path": str(REVIEW_PATH.relative_to(ROOT)),
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
