"""What a ranked row, chart bar or roster name opens to.

A ranking's rows carry record IDs: a song, a person, a venue, a release, or a
year. Opening one shows that record's key facts, one play button and one
question for the chat. Every fact comes from the store, and the recording the
row plays is chosen here, the same way every time, from stored selection
signals and tapes; the model is not involved. A row whose ID the library does
not hold does not open.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Any

from deadbot import song_life
from deadbot.canonical_import import _selector_name
from deadbot.data import CanonicalStore
from deadbot.experience import PlayableTrack, RowDetail, RowFact, RowKind, RowPlay
from deadbot.listening import _long_date, playable_show_tracks
from deadbot.record_refs import release_shows
from deadbot.selection_signals import SelectionSignalError, load_selection_signals

logger = logging.getLogger(__name__)

# The band's years; a year outside them names no shows.
FIRST_YEAR = 1965
LAST_YEAR = 1995
# How many of the best-ranked shows are tried for a tape before giving up.
TAPE_TRIES = 12
# How many instruments and songs a person's facts name.
NAMED_INSTRUMENTS = 3
NAMED_SONGS = 3

# Each record kind's ID prefix, table and ID column.
_KINDS: dict[str, tuple[RowKind, str, str]] = {
    "song-": ("song", "songs", "song_id"),
    "person-": ("person", "people", "person_id"),
    "venue-": ("venue", "venues", "venue_id"),
    "release-": ("release", "official_releases", "release_id"),
}
_YEAR = re.compile(r"\d{4}")


def row_kind(row_id: str | None) -> RowKind | None:
    """The kind of record a row ID names, read from its form alone."""

    if not isinstance(row_id, str):
        return None
    if _YEAR.fullmatch(row_id):
        return "year" if FIRST_YEAR <= int(row_id) <= LAST_YEAR else None
    for prefix, (kind, _table, _column) in _KINDS.items():
        if row_id.startswith(prefix):
            return kind
    return None


def openable_ids(store: CanonicalStore, ids: list[str]) -> list[str]:
    """The IDs, in order, that name a record the library holds: one query per kind."""

    wanted: dict[str, set[str]] = defaultdict(set)
    years: set[str] = set()
    for row_id in ids:
        kind = row_kind(row_id)
        if kind == "year":
            years.add(row_id)
        elif kind:
            prefix = next(prefix for prefix in _KINDS if row_id.startswith(prefix))
            wanted[prefix].add(row_id)
    found = set(years)
    for prefix, values in wanted.items():
        _kind, table, column = _KINDS[prefix]
        try:
            found |= {row.get(column, "") for row in store.rows_in(table, column, values)}
        except Exception:
            logger.warning("Could not check %d %s row IDs against the library", len(values), table, exc_info=True)
    return [row_id for row_id in dict.fromkeys(ids) if row_id in found]


def _dimension_ids(payload: dict[str, Any]) -> tuple[list[str], bool]:
    """The row IDs of one aggregate_data payload (a year row's ID is its year), and whether it is a year series."""

    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    ids: list[str] = []
    is_years = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if isinstance(row.get("id"), str):
            ids.append(row["id"])
        elif isinstance(row.get("year"), int) and not isinstance(row.get("year"), bool):
            ids.append(str(row["year"]))
            is_years = True
    return ids, is_years


def open_scope(store: CanonicalStore, payload: dict[str, Any]) -> str | None:
    """The song a year series counts, when it counts one the library holds."""

    query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
    filters = query.get("filters") if isinstance(query.get("filters"), dict) else {}
    song_id = filters.get("song_id")
    if query.get("group_by") != "year" or not isinstance(song_id, str) or not song_id:
        return None
    try:
        return song_id if store.one("songs", song_id) else None
    except Exception:
        logger.debug("Could not look up chart scope %r", song_id, exc_info=True)
        return None


def chart_openings(store: CanonicalStore, payload: dict[str, Any]) -> tuple[list[str], str | None]:
    """Which of a chart's rows open, and the song its years belong to."""

    ids, is_years = _dimension_ids(payload)
    return openable_ids(store, ids), (open_scope(store, payload) if is_years else None)


# --- Shared pieces -----------------------------------------------------------


def _span(years: list[int]) -> str | None:
    if not years:
        return None
    first, last = min(years), max(years)
    return str(first) if first == last else f"{first}–{last}"


def _times(count: int, one: str = "time", many: str | None = None) -> str:
    return f"{count:,} {one if count == 1 else (many or one + 's')}"


def _picked_by(voices: list[str]) -> str | None:
    if not voices:
        return None
    if len(voices) <= 2:
        return "Picked by " + " and ".join(voices)
    return f"Picked by {', '.join(voices[:2])} and {len(voices) - 2} more"


class Picks:
    """The selection signals, read once: who picked each performance and each show, and how many picks each show drew."""

    def __init__(self, store: CanonicalStore) -> None:
        self.by_performance: dict[str, list[str]] = defaultdict(list)
        self.by_show: dict[str, list[str]] = defaultdict(list)
        # Every pick naming the show or one of its performances; a show whose
        # songs were picked again and again is a show listeners return to.
        self.show_picks: Counter[str] = Counter()
        try:
            inventory = load_selection_signals(store)["selection_signals"]
        except SelectionSignalError:
            logger.info("Selection signals are not available from this store; rows open without picks")
            return
        for signal in inventory:
            if str(signal.get("resolution_state", "")).startswith("held_") or signal.get("source") in song_life.RELEASE_CONFIRMATION_SOURCES:
                continue
            voice = _selector_name(signal) or signal.get("selection_label") or song_life.SOURCE_VOICES.get(signal["source"], signal["source"])
            named: set[str] = set()
            for performance in signal.get("candidate_performances") or []:
                performance_id, show_id = performance.get("performance_id"), performance.get("show_id")
                if performance_id and voice not in self.by_performance[performance_id]:
                    self.by_performance[performance_id].append(voice)
                if show_id:
                    named.add(show_id)
            for show in signal.get("candidate_shows") or []:
                if show.get("show_id"):
                    named.add(show["show_id"])
            for show_id in named:
                self.show_picks[show_id] += 1
                if voice not in self.by_show[show_id]:
                    self.by_show[show_id].append(voice)


def _notable_show(
    store: CanonicalStore,
    shows: list[dict[str, str]],
    picks: Picks,
    *,
    show_voices: dict[str, list[str]] | None = None,
    weight: dict[str, int] | None = None,
    keep: dict[str, set[str]] | None = None,
) -> RowPlay | None:
    """The best-picked show with a tape: most voices, then most picks, then the higher ``weight``, then the earliest.

    ``keep`` narrows a show's tape to some of its performances (a guest's
    songs that night); when none of them is on the tape, the whole tape plays.
    """

    weight = weight or {}
    show_voices = show_voices if show_voices is not None else picks.by_show
    dated = [show for show in shows if show.get("show_id") and len(show.get("show_date") or "") >= 10]
    ranked = sorted(
        dated,
        key=lambda show: (
            -len(show_voices.get(show["show_id"], [])),
            -picks.show_picks.get(show["show_id"], 0),
            -weight.get(show["show_id"], 0),
            show["show_date"],
            show["show_id"],
        ),
    )
    venues = {
        row["venue_id"]: row
        for row in store.rows_in("venues", "venue_id", {show.get("venue_id", "") for show in ranked[:TAPE_TRIES]} - {""})
    }
    for show in ranked[:TAPE_TRIES]:
        tracks, _identifier = playable_show_tracks(show["show_id"], store)
        wanted = (keep or {}).get(show["show_id"])
        if wanted:
            tracks = [track for track in tracks if track.performance_id in wanted] or tracks
        if not tracks:
            continue
        return RowPlay(
            show_id=show["show_id"],
            show_date=show["show_date"],
            venue_name=(venues.get(show.get("venue_id", "")) or {}).get("name") or None,
            why=_picked_by(show_voices.get(show["show_id"], [])),
            tracks=tracks,
        )
    return None


def _performance_play(performances: list[song_life.LifePerformance], title: str) -> RowPlay | None:
    """A song's version to play: the most-picked with a tape, else the longest with a tape."""

    taped = [p for p in performances if p.audio_url]
    if not taped:
        return None

    def voices(p: song_life.LifePerformance) -> list[str]:
        return [signal.voice for signal in p.signals if signal.scope == "performance"]

    picked = [p for p in taped if voices(p)]
    pool = picked or taped
    chosen = min(pool, key=lambda p: (-len(voices(p)), -(p.seconds or 0), p.show_date, p.performance_id))
    track = chosen.track_json(title)
    if track is None:
        return None
    return RowPlay(
        show_id=chosen.show_id,
        show_date=chosen.show_date,
        venue_name=chosen.venue_name,
        why=_picked_by(voices(chosen)),
        tracks=[PlayableTrack.model_validate(track)],
    )


# --- One kind each -------------------------------------------------------------


def _song(store: CanonicalStore, song_id: str, song: dict[str, str]) -> RowDetail:
    title = song.get("title") or song_id
    performances = song_life.life_performances(store, song_id)
    facts = [RowFact(label="Played", value=_times(len(performances)))]
    span = _span([p.year for p in performances])
    if span:
        facts.append(RowFact(label="Years", value=span))
    by_year = Counter(p.year for p in performances)
    if len(by_year) > 1:
        year, count = min(by_year.items(), key=lambda item: (-item[1], item[0]))
        facts.append(RowFact(label="Most in", value=f"{year}, {_times(count)}"))
    return RowDetail(
        id=song_id,
        kind="song",
        title=title,
        facts=facts,
        play=_performance_play(performances, title),
        ask=f"The story of {title} on stage",
    )


def _song_year(store: CanonicalStore, song_id: str, song: dict[str, str], year: int) -> RowDetail | None:
    title = song.get("title") or song_id
    performances = [p for p in song_life.life_performances(store, song_id) if p.year == year]
    facts = [RowFact(label="Played", value=f"{_times(len(performances))} in {year}")]
    timed = [p for p in performances if p.seconds is not None]
    if timed:
        longest = max(timed, key=lambda p: (p.seconds, p.show_date))
        facts.append(RowFact(label="Longest", value=f"{song_life.clock(longest.seconds)}, {_long_date(longest.show_date)}"))
    return RowDetail(
        id=str(year),
        kind="year",
        title=f"{title} in {year}",
        facts=facts,
        play=_performance_play(performances, title),
        ask=f"{title} in {year}",
    )


def _year(store: CanonicalStore, year: int) -> RowDetail | None:
    dates = [f"{year}-{month:02d}-{day:02d}" for month in range(1, 13) for day in range(1, 32)]
    shows = store.rows_in("shows", "show_date", dates)
    if not shows:
        return None
    performances = store.rows_in("performances", "show_id", {show["show_id"] for show in shows})
    songs = Counter(row.get("song_id") for row in performances if row.get("song_id"))
    sizes = Counter(row.get("show_id") for row in performances)
    facts = [RowFact(label="Shows", value=f"{len(shows):,}")]
    if songs:
        facts.append(RowFact(label="Songs", value=f"{len(songs):,} different"))
        song_id, count = min(songs.items(), key=lambda item: (-item[1], item[0]))
        title = (store.one("songs", song_id) or {}).get("title") or song_id
        facts.append(RowFact(label="Most played", value=f"{title}, {_times(count)}"))
    return RowDetail(
        id=str(year),
        kind="year",
        title=str(year),
        facts=facts,
        play=_notable_show(store, shows, Picks(store), weight=dict(sizes)),
        ask=f"The Grateful Dead in {year}",
    )


def _venue(store: CanonicalStore, venue_id: str, venue: dict[str, str]) -> RowDetail:
    name = venue.get("name") or venue_id
    shows = store.filtered_rows("shows", venue_id=venue_id)
    facts = [RowFact(label="Shows", value=f"{len(shows):,}")]
    span = _span([int(show["show_date"][:4]) for show in shows if (show.get("show_date") or "")[:4].isdigit()])
    if span:
        facts.append(RowFact(label="Years", value=span))
    country = venue.get("country") or ""
    place = ", ".join(part for part in (venue.get("city"), venue.get("state_region"), country if country not in {"", "US", "USA"} else None) if part)
    if place:
        facts.append(RowFact(label="Place", value=place))
    return RowDetail(
        id=venue_id,
        kind="venue",
        title=name,
        facts=facts,
        play=_notable_show(store, shows, Picks(store)),
        ask=f"The Grateful Dead at {name}",
    )


def _release(store: CanonicalStore, release_id: str, release: dict[str, str]) -> RowDetail:
    title = release.get("title") or release_id
    shows = release_shows(release_id, store)
    facts: list[RowFact] = []
    if release.get("release_date"):
        facts.append(RowFact(label="Released", value=_long_date(release["release_date"])))
    if len(shows) == 1:
        venue = (shows[0].get("venue") or {}).get("name")
        facts.append(RowFact(label="Show", value=", ".join(part for part in (_long_date(shows[0].get("show_date") or ""), venue) if part)))
    elif shows:
        span = _span([int(show["show_date"][:4]) for show in shows if (show.get("show_date") or "")[:4].isdigit()])
        facts.append(RowFact(label="Shows", value=f"{len(shows)}" + (f", {span}" if span else "")))
    return RowDetail(
        id=release_id,
        kind="release",
        title=title,
        facts=facts,
        play=_notable_show(store, shows, Picks(store)),
        ask=f"Tell me about {title}",
    )


def _person(store: CanonicalStore, person_id: str, person: dict[str, str]) -> RowDetail:
    name = person.get("name") or person_id
    assignments = store.filtered_rows("show_performers", person_id=person_id)
    guest_rows = [row for row in store.filtered_rows("performance_performers", person_id=person_id) if row.get("role") == "guest"]
    member = any(row.get("role") == "performer" for row in assignments)
    shows = store.rows_in("shows", "show_id", {row.get("show_id", "") for row in assignments} - {""})
    facts = [RowFact(label="Shows", value=f"{len(shows):,}")]
    span = _span([int(show["show_date"][:4]) for show in shows if (show.get("show_date") or "")[:4].isdigit()])
    if span:
        facts.append(RowFact(label="Years", value=span))
    instruments = Counter(row.get("instrument") for row in assignments if row.get("instrument"))
    if instruments:
        named = [instrument for instrument, _count in sorted(instruments.items(), key=lambda item: (-item[1], item[0]))[:NAMED_INSTRUMENTS]]
        facts.append(RowFact(label="Played", value=", ".join(named)))
    guest_performances = store.rows_in("performances", "performance_id", {row.get("performance_id", "") for row in guest_rows} - {""})
    if guest_performances:
        counts = Counter(row.get("song_id") for row in guest_performances if row.get("song_id"))
        titles = {row["song_id"]: row.get("title") or row["song_id"] for row in store.rows_in("songs", "song_id", set(counts))}
        top = sorted(counts.items(), key=lambda item: (-item[1], titles.get(item[0], item[0])))[:NAMED_SONGS]
        facts.append(RowFact(label="Most often on", value=", ".join(f"{titles.get(song_id, song_id)} ({count})" for song_id, count in top)))

    picks = Picks(store)
    keep: dict[str, set[str]] = defaultdict(set)
    for row in guest_performances:
        keep[row["show_id"]].add(row["performance_id"])
    # A sit-in's own songs that night count for its show as picks of the show do.
    weight = {show_id: len(ids) for show_id, ids in keep.items()}
    voices = {
        show["show_id"]: list(dict.fromkeys(picks.by_show.get(show["show_id"], []) + [voice for pid in keep.get(show["show_id"], ()) for voice in picks.by_performance.get(pid, [])]))
        for show in shows
    }
    sat_in = {row.get("show_id") for row in assignments if row.get("role") == "guest"}
    candidates = [show for show in shows if show["show_id"] in sat_in] or shows
    return RowDetail(
        id=person_id,
        kind="person",
        title=name,
        facts=facts,
        play=_notable_show(store, candidates, picks, show_voices=voices, weight=weight, keep=keep),
        ask=f"Tell me about {name} in the Grateful Dead" if member else f"Tell me about {name} with the Dead",
    )


def row_detail(store: CanonicalStore, row_id: str, scope: str | None = None) -> RowDetail | None:
    """What one row opens to, or None when the library holds no such record.

    ``scope`` is the song a year chart counts; a year opened within it is that
    song's year.
    """

    kind = row_kind(row_id)
    if kind is None:
        return None
    if kind == "year":
        song = store.one("songs", scope) if scope and scope.startswith("song-") else None
        if song:
            return _song_year(store, scope, song, int(row_id))
        return _year(store, int(row_id))
    _kind, table, _column = next(_KINDS[prefix] for prefix in _KINDS if row_id.startswith(prefix))
    record = store.one(table, row_id)
    if not record:
        return None
    if kind == "song":
        return _song(store, row_id, record)
    if kind == "venue":
        return _venue(store, row_id, record)
    if kind == "release":
        return _release(store, row_id, record)
    return _person(store, row_id, record)
