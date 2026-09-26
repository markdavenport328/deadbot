"""Song pairings: one song followed by another in the same set.

A pairing is song A at position p followed by song B at position p + 1 in the
same set of the same show. When A's ``segue_into_next`` is true the two run
together without a stop (China Cat Sunflower > I Know You Rider); otherwise B
simply came next. The stores find the adjacent pairs (SQL for SQLite and
PostgreSQL, an in-memory scan for the CSV store); everything here is shared
shaping over those rows, so every store returns the same versions, lengths and
listening paths.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any, Callable, Iterable

from deadbot.data import CanonicalStore
from deadbot.experience import fit

TRANSITIONS = ("segue", "any")

# A pairing with more versions than this returns summaries plus a way to ask
# for the full list, so the default result stays compact.
VERSION_LIST_THRESHOLD = 24

LENGTHS_NOTE = (
    "Seconds are each night's Internet Archive tape tracks for the two songs. Where a tape splits the "
    "transition, the split decides which half the jam counts toward."
)


def pairing_id(first_song_id: str, second_song_id: str) -> str:
    return f"pairing:{first_song_id}>{second_song_id}"


def parse_pairing_id(value: str) -> tuple[str, str] | None:
    if not value.startswith("pairing:") or ">" not in value:
        return None
    first, _, second = value[len("pairing:") :].partition(">")
    return (first, second) if first and second else None


def pair_id(show_id: str, set_number: str, position_in_set: str) -> str:
    """One night's pairing: the show, the set, and the first song's position."""

    return f"{show_id}:{set_number}:{position_in_set}"


@dataclass(frozen=True)
class Track:
    url: str
    duration_seconds: int | None


@dataclass(frozen=True)
class Version:
    pair_id: str
    show_id: str
    show_date: str
    venue_name: str
    city: str
    state_region: str
    set_label: str
    segue: bool
    first_performance_id: str
    second_performance_id: str
    first_track: Track | None
    second_track: Track | None

    @property
    def year(self) -> int | None:
        text = self.show_date[:4]
        return int(text) if text.isdigit() else None

    @property
    def first_seconds(self) -> int | None:
        return self.first_track.duration_seconds if self.first_track else None

    @property
    def second_seconds(self) -> int | None:
        return self.second_track.duration_seconds if self.second_track else None

    @property
    def location(self) -> str:
        return ", ".join(value for value in (self.city, self.state_region) if value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "show_id": self.show_id,
            "show_date": self.show_date,
            "venue_name": self.venue_name,
            "location": self.location,
            "set_label": self.set_label,
            "segue": self.segue,
            "first_performance_id": self.first_performance_id,
            "second_performance_id": self.second_performance_id,
            "first_seconds": self.first_seconds,
            "second_seconds": self.second_seconds,
            "first_track_url": self.first_track.url if self.first_track else None,
            "second_track_url": self.second_track.url if self.second_track else None,
        }


def _number(value: Any, missing: int = 10**9) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return missing


def csv_sequence_pairs(store: CanonicalStore, first_song_id: str, second_song_id: str) -> list[dict[str, str]]:
    """The CSV store's adjacent pairs, in the row shape the SQL stores return."""

    performances = store.rows("performances")
    by_slot = {
        (row.get("show_id", ""), row.get("set_number", ""), _number(row.get("position_in_set"))): row
        for row in performances
        if row.get("set_number", "")
    }
    shows = store.by_id.get("shows", {})
    venues = store.by_id.get("venues", {})
    rows: list[dict[str, str]] = []
    for first in performances:
        if first.get("song_id") != first_song_id or not first.get("set_number", ""):
            continue
        position = _number(first.get("position_in_set"))
        second = by_slot.get((first.get("show_id", ""), first.get("set_number", ""), position + 1))
        if not second or second.get("song_id") != second_song_id:
            continue
        show = shows.get(first.get("show_id", ""))
        if not show:
            continue
        venue = venues.get(show.get("venue_id", ""), {})
        rows.append(
            {
                "first_performance_id": first.get("performance_id", ""),
                "second_performance_id": second.get("performance_id", ""),
                "show_id": show.get("show_id", ""),
                "show_date": show.get("show_date", ""),
                "set_number": first.get("set_number", ""),
                "set_label": first.get("set_label", ""),
                "position_in_set": first.get("position_in_set", ""),
                "segue": first.get("segue_into_next", ""),
                "venue_name": venue.get("name", ""),
                "city": venue.get("city", ""),
                "state_region": venue.get("state_region", ""),
            }
        )
    return sort_pair_rows(rows)


def sort_pair_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("show_date", ""),
            row.get("show_id", ""),
            _number(row.get("set_number")),
            _number(row.get("position_in_set")),
        ),
    )


def _archive_tracks(store: CanonicalStore, performance_ids: Iterable[str]) -> dict[str, Track]:
    """Each performance's archive tape track, chosen by link id as the listen paths choose it."""

    candidates: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in store.rows_in("performance_links", "performance_id", performance_ids):
        if row.get("platform") != "archive" or row.get("link_type") != "recording-track" or not row.get("url"):
            continue
        candidates[row["performance_id"]].append((row.get("performance_link_id", ""), row["url"], row.get("duration_seconds", "")))
    tracks: dict[str, Track] = {}
    for performance_id, options in candidates.items():
        _link_id, url, duration = min(options)
        text = str(duration).strip()
        # A zero-length track is a cataloging gap, not a length.
        seconds = int(text) if text.isdigit() and int(text) > 0 else None
        tracks[performance_id] = Track(url=url, duration_seconds=seconds)
    return tracks


def versions(store: CanonicalStore, first_song_id: str, second_song_id: str) -> list[Version]:
    """Every night song A was followed by song B in one set, with both tape tracks."""

    rows = store.sequence_pairs(first_song_id, second_song_id)
    ids = [row["first_performance_id"] for row in rows] + [row["second_performance_id"] for row in rows]
    tracks = _archive_tracks(store, ids)
    return [
        Version(
            pair_id=pair_id(row["show_id"], row["set_number"], row["position_in_set"]),
            show_id=row["show_id"],
            show_date=row["show_date"],
            venue_name=row.get("venue_name", ""),
            city=row.get("city", ""),
            state_region=row.get("state_region", ""),
            set_label=row.get("set_label", ""),
            segue=row.get("segue") == "true",
            first_performance_id=row["first_performance_id"],
            second_performance_id=row["second_performance_id"],
            first_track=tracks.get(row["first_performance_id"]),
            second_track=tracks.get(row["second_performance_id"]),
        )
        for row in rows
    ]


def _median(values: list[int]) -> int | None:
    return int(round(median(values))) if values else None


def _extremes(versions: list[Version], seconds: Callable[[Version], int | None]) -> dict[str, Any] | None:
    timed = [version for version in versions if seconds(version) is not None]
    if not timed:
        return None
    longest = max(timed, key=lambda version: (seconds(version), version.show_date))
    shortest = min(timed, key=lambda version: (seconds(version), version.show_date))
    return {
        "median_seconds": _median([seconds(version) for version in timed]),
        "timed_versions": len(timed),
        "longest": longest.to_payload(),
        "shortest": shortest.to_payload(),
    }


def _total_seconds(version: Version) -> int | None:
    if version.first_seconds is None or version.second_seconds is None:
        return None
    return version.first_seconds + version.second_seconds


def _period_row(label_key: str, label: Any, members: list[Version]) -> dict[str, Any]:
    firsts = [version.first_seconds for version in members if version.first_seconds is not None]
    seconds = [version.second_seconds for version in members if version.second_seconds is not None]
    row: dict[str, Any] = {label_key: label, "count": len(members)}
    if firsts:
        row["median_first_seconds"] = _median(firsts)
    if seconds:
        row["median_second_seconds"] = _median(seconds)
    return row


def year_counts(versions: list[Version]) -> list[dict[str, int]]:
    """Versions per year across the pairing's span, with the empty years kept as zero."""

    counts: dict[int, int] = defaultdict(int)
    for version in versions:
        if version.year is not None:
            counts[version.year] += 1
    if not counts:
        return []
    return [{"year": year, "count": counts.get(year, 0)} for year in range(min(counts), max(counts) + 1)]


def pairing_payload(
    first_song: dict[str, str],
    second_song: dict[str, str],
    all_versions: list[Version],
    *,
    transition: str,
    include_versions: bool,
    year_from: int | None,
    year_to: int | None,
    era_of: Callable[[str], str],
) -> dict[str, Any]:
    """The get_segue_pairing result: counts, the span, lengths and the versions."""

    segued = [version for version in all_versions if version.segue]
    chosen = segued if transition == "segue" else all_versions
    in_range = [
        version
        for version in chosen
        if (year_from is None or (version.year is not None and version.year >= year_from))
        and (year_to is None or (version.year is not None and version.year <= year_to))
    ]
    payload: dict[str, Any] = {
        "pairing_id": pairing_id(first_song["song_id"], second_song["song_id"]),
        "first_song": {"song_id": first_song["song_id"], "title": first_song.get("title", "")},
        "second_song": {"song_id": second_song["song_id"], "title": second_song.get("title", "")},
        "transition": transition,
        "count": len(chosen),
        "counts": {"segue": len(segued), "followed_without_segue": len(all_versions) - len(segued)},
    }
    if year_from is not None or year_to is not None:
        payload["year_range"] = {"from": year_from, "to": year_to, "count": len(in_range)}
    if not chosen:
        return payload
    payload["span"] = {"first_date": chosen[0].show_date, "last_date": chosen[-1].show_date}
    by_year: dict[int, list[Version]] = defaultdict(list)
    for version in chosen:
        if version.year is not None:
            by_year[version.year].append(version)
    payload["by_year"] = [
        _period_row("year", year, by_year.get(year, []))
        for year in (range(min(by_year), max(by_year) + 1) if by_year else [])
    ]
    by_era: dict[str, list[Version]] = defaultdict(list)
    for version in chosen:
        by_era[era_of(version.show_date)].append(version)
    payload["by_era"] = [_period_row("era", era, members) for era, members in by_era.items()]
    payload["with_archive_tracks"] = sum(1 for version in chosen if version.first_track and version.second_track)
    payload["lengths"] = {
        "first_song": _extremes(in_range, lambda version: version.first_seconds),
        "second_song": _extremes(in_range, lambda version: version.second_seconds),
        "together": _extremes(in_range, _total_seconds),
    }
    payload["lengths_note"] = LENGTHS_NOTE
    if include_versions or len(in_range) <= VERSION_LIST_THRESHOLD:
        payload["versions"] = [version.to_payload() for version in in_range]
    else:
        payload["available"] = {
            "versions": {
                "count": len(in_range),
                "ask": 'include=["versions"] for every version; narrow with year_from and year_to',
            }
        }
    return payload


def version_strip_block(
    store: CanonicalStore,
    grounded_ids: frozenset[str],
    *,
    pairing: str,
    pair_ids: list[str],
    title: str | None,
    note: str | None,
    show_year_counts: bool,
) -> Any:
    """Hydrate a model-planned version_strip, or None when nothing in it was retrieved.

    The pairing and each pair_id must have appeared in this turn's tool output;
    the rows keep the model's order, and their venue, date, lengths and tracks
    come from the store rather than from anything the model wrote.
    """

    from deadbot.experience import PlayableTrack, VersionStripBlock, VersionStripRow, VersionStripSong, VersionStripYear

    songs = parse_pairing_id(pairing)
    if pairing not in grounded_ids or songs is None:
        return None
    first_song, second_song = (store.one("songs", song_id) for song_id in songs)
    if not first_song or not second_song:
        return None
    found = versions(store, songs[0], songs[1])
    by_pair = {version.pair_id: version for version in found}
    chosen: list[Version] = []
    for wanted in dict.fromkeys(pair_ids):
        version = by_pair.get(wanted)
        if version is not None and wanted in grounded_ids:
            chosen.append(version)
    if not chosen:
        return None
    first_title = first_song.get("title", "") or songs[0]
    second_title = second_song.get("title", "") or songs[1]

    def playable(performance_id: str, song_title: str, track: Track | None, set_label: str) -> PlayableTrack | None:
        if track is None:
            return None
        return PlayableTrack(
            performance_id=performance_id,
            title=song_title,
            audio_url=track.url,
            duration_seconds=track.duration_seconds,
            set_label=set_label or None,
        )

    rows = [
        VersionStripRow(
            pair_id=version.pair_id,
            show_id=version.show_id,
            show_date=version.show_date,
            venue_name=version.venue_name or version.show_id,
            location=version.location or None,
            segue=version.segue,
            first_performance_id=version.first_performance_id,
            second_performance_id=version.second_performance_id,
            first_seconds=version.first_seconds,
            second_seconds=version.second_seconds,
            first_track=playable(version.first_performance_id, first_title, version.first_track, version.set_label),
            second_track=playable(version.second_performance_id, second_title, version.second_track, version.set_label),
        )
        for version in fit(chosen, "version strip nights")
    ]
    # The count and year strip describe the same relationship the rows show:
    # segued nights when every chosen night is a segue, otherwise every night
    # the second song followed the first.
    counted = [version for version in found if version.segue] if all(version.segue for version in chosen) else found
    return VersionStripBlock(
        type="version_strip",
        pairing_id=pairing,
        title=(title or "").strip() or None,
        note=(note or "").strip() or None,
        first_song=VersionStripSong(song_id=songs[0], title=first_title),
        second_song=VersionStripSong(song_id=songs[1], title=second_title),
        total_count=len(counted),
        rows=rows,
        year_counts=[VersionStripYear(**entry) for entry in year_counts(counted)] if show_year_counts else [],
    )
