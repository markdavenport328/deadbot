"""A song's life on stage: every performance with its facts, year by year.

The song card's timeline and the get_song_life tool read from here. Every fact
comes from the store; nothing here judges which performances matter, it only
says what stands out. Reads use only rows_in, one and filtered_rows, which the
CSV, SQLite and PostgreSQL stores implement alike.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any

from deadbot.canonical_import import _selector_name
from deadbot.data import CanonicalStore
from deadbot.selection_signals import SelectionSignalError, load_selection_signals
from deadbot.sequences import _archive_tracks

logger = logging.getLogger(__name__)

# A shorter "length" is a partial tape track or a segment, not the performance.
MIN_LENGTH_SECONDS = 60
# Standouts the tool lists before cutting; released-only versions go first.
STANDOUT_CEILING = 30
# A placement shared by at most this share of a song's performances stands out.
RARE_PLACEMENT_SHARE = 0.10
# A rare placement shared by more performances than this is a pattern, reported once.
PATTERN_THRESHOLD = 5
# A neighbor song met this many times or fewer stands out.
RARE_NEIGHBOR_MEETINGS = 2
# Voices for selection sources the import's selector names do not cover.
SOURCE_VOICES = {"headyversion": "Headyversion voters"}
# Signals that confirm an official release rather than pick a version; the
# release titles already carry them.
RELEASE_CONFIRMATION_SOURCES = {"deadnet-official-release-pass"}


def clock(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    return f"{seconds // 60}:{seconds % 60:02d}"


def _int(value: Any, default: int = 0) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else default


@dataclass(frozen=True)
class Neighbor:
    song_id: str
    title: str
    segued: bool

    def to_json(self) -> dict[str, Any]:
        return {"song_id": self.song_id, "title": self.title, "segued": self.segued}


@dataclass(frozen=True)
class Signal:
    voice: str
    scope: str  # "performance" or "show"

    def to_json(self) -> dict[str, Any]:
        return {"voice": self.voice, "scope": self.scope}


@dataclass(frozen=True)
class Guest:
    name: str
    instrument: str | None

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "instrument": self.instrument}


@dataclass(frozen=True)
class LifePerformance:
    performance_id: str
    show_id: str
    show_date: str
    venue_name: str | None
    city: str | None
    set_number: int
    set_label: str
    position_in_set: int
    encore: bool
    previous: Neighbor | None
    next: Neighbor | None
    seconds: int | None
    length_source: str | None
    audio_url: str | None
    tape_seconds: int | None
    releases: tuple[str, ...]
    signals: tuple[Signal, ...]
    guests: tuple[Guest, ...]

    @property
    def year(self) -> int:
        return int(self.show_date[:4])

    def track_json(self, title: str) -> dict[str, Any] | None:
        if not self.audio_url:
            return None
        return {
            "performance_id": self.performance_id,
            "title": title,
            "audio_url": self.audio_url,
            "duration_seconds": self.tape_seconds,
            "set_label": self.set_label or None,
        }

    def to_json(self, title: str) -> dict[str, Any]:
        return {
            "performance_id": self.performance_id,
            "show_id": self.show_id,
            "show_date": self.show_date,
            "venue_name": self.venue_name,
            "city": self.city,
            "set_label": self.set_label or None,
            "position_in_set": self.position_in_set,
            "encore": self.encore,
            "previous": self.previous.to_json() if self.previous else None,
            "next": self.next.to_json() if self.next else None,
            "seconds": self.seconds,
            "length_source": self.length_source,
            "track": self.track_json(title),
            "releases": list(self.releases),
            "signals": [signal.to_json() for signal in self.signals],
            "guests": [guest.to_json() for guest in self.guests],
        }


def _release_length(candidates: list[int], tape_seconds: int | None) -> int | None:
    """One release length when several releases carry the performance.

    Releases can disagree (a 30 Days of Dead excerpt against the full
    release), so the one nearest the tape wins; with no tape, the longest.
    """

    usable = [seconds for seconds in candidates if seconds >= MIN_LENGTH_SECONDS]
    if not usable:
        return min(candidates) if candidates else None
    if tape_seconds is not None and tape_seconds >= MIN_LENGTH_SECONDS:
        return min(usable, key=lambda seconds: (abs(seconds - tape_seconds), -seconds))
    return max(usable)


def _length(release_seconds: int | None, tape_seconds: int | None, performance_id: str) -> tuple[int | None, str | None]:
    """Official release seconds first, then the tape track's; a too-short value is unknown."""

    for seconds, source in ((release_seconds, "release"), (tape_seconds, "tape")):
        if seconds is None:
            continue
        if seconds < MIN_LENGTH_SECONDS:
            logger.info("Ignored a %d-second %s length for %s", seconds, source, performance_id)
            continue
        return seconds, source
    return None, None


def _releases(store: CanonicalStore, performance_ids: list[str]) -> tuple[dict[str, list[int]], dict[str, tuple[str, ...]]]:
    """Each performance's release lengths (its tracks on one release summed, one per release) and release titles."""

    tracks = store.rows_in("official_release_tracks", "performance_id", performance_ids)
    releases = {row["release_id"]: row for row in store.rows_in("official_releases", "release_id", {t["release_id"] for t in tracks})}
    per_release: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for track in tracks:
        if track["release_id"] in releases:
            per_release[track["performance_id"]][track["release_id"]] += _int(track.get("duration_seconds"))
    seconds: dict[str, list[int]] = {}
    titles: dict[str, tuple[str, ...]] = {}
    for performance_id, by_release in per_release.items():
        timed = [total for _release_id, total in sorted(by_release.items()) if total > 0]
        if timed:
            seconds[performance_id] = timed
        ordered = sorted(by_release, key=lambda release_id: (releases[release_id].get("release_date") or "9999", releases[release_id].get("title") or ""))
        titles[performance_id] = tuple(dict.fromkeys(releases[release_id].get("title") or release_id for release_id in ordered))
    return seconds, titles


def _guests(store: CanonicalStore, performance_ids: list[str]) -> dict[str, tuple[Guest, ...]]:
    rows = [row for row in store.rows_in("performance_performers", "performance_id", performance_ids) if row.get("role") == "guest"]
    people = {row["person_id"]: row for row in store.rows_in("people", "person_id", {row["person_id"] for row in rows})}
    guests: dict[str, list[Guest]] = defaultdict(list)
    for row in rows:
        name = (people.get(row["person_id"]) or {}).get("name") or row["person_id"]
        guests[row["performance_id"]].append(Guest(name=name, instrument=row.get("instrument") or None))
    return {performance_id: tuple(sorted(set(items), key=lambda guest: guest.name)) for performance_id, items in guests.items()}


def _signals(store: CanonicalStore, performance_ids: set[str], show_ids: set[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The voices that picked each performance, and each show (for signals that name no performance)."""

    try:
        inventory = load_selection_signals(store)["selection_signals"]
    except SelectionSignalError:
        # The CSV store holds no selection inventory; the SQLite and PostgreSQL stores do.
        logger.info("Selection signals are not available from this store; song life carries no picks")
        return {}, {}
    by_performance: dict[str, list[str]] = defaultdict(list)
    by_show: dict[str, list[str]] = defaultdict(list)
    for signal in inventory:
        if str(signal.get("resolution_state", "")).startswith("held_") or signal.get("source") in RELEASE_CONFIRMATION_SOURCES:
            continue
        voice = _selector_name(signal) or signal.get("selection_label") or SOURCE_VOICES.get(signal["source"], signal["source"])
        performances = signal.get("candidate_performances") or []
        if performances:
            for performance in performances:
                if performance.get("performance_id") in performance_ids and voice not in by_performance[performance["performance_id"]]:
                    by_performance[performance["performance_id"]].append(voice)
        else:
            for show in signal.get("candidate_shows") or []:
                if show.get("show_id") in show_ids and voice not in by_show[show["show_id"]]:
                    by_show[show["show_id"]].append(voice)
    return by_performance, by_show


def life_performances(store: CanonicalStore, song_id: str) -> list[LifePerformance]:
    """Every dated performance of the song, in order, with its facts."""

    rows = store.filtered_rows("performances", song_id=song_id)
    if not rows:
        return []
    show_ids = {row["show_id"] for row in rows}
    shows = {row["show_id"]: row for row in store.rows_in("shows", "show_id", show_ids)}
    venues = {row["venue_id"]: row for row in store.rows_in("venues", "venue_id", {show.get("venue_id", "") for show in shows.values()} - {""})}
    sets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for mate in store.rows_in("performances", "show_id", show_ids):
        sets[(mate["show_id"], mate.get("set_number", ""))].append(mate)
    for mates in sets.values():
        mates.sort(key=lambda mate: _int(mate.get("position_in_set"), 10**6))
    performance_ids = [row["performance_id"] for row in rows]
    around: dict[str, tuple[dict[str, str] | None, dict[str, str] | None]] = {}
    neighbor_song_ids: set[str] = set()
    for row in rows:
        mates = sets[(row["show_id"], row.get("set_number", ""))]
        index = next(i for i, mate in enumerate(mates) if mate["performance_id"] == row["performance_id"])
        before = mates[index - 1] if index > 0 else None
        after = mates[index + 1] if index + 1 < len(mates) else None
        around[row["performance_id"]] = (before, after)
        neighbor_song_ids |= {mate["song_id"] for mate in (before, after) if mate}
    titles = {row["song_id"]: row.get("title") or row["song_id"] for row in store.rows_in("songs", "song_id", neighbor_song_ids)}
    release_seconds, release_titles = _releases(store, performance_ids)
    tracks = _archive_tracks(store, performance_ids)
    guests = _guests(store, performance_ids)
    performance_voices, show_voices = _signals(store, set(performance_ids), show_ids)

    result: list[LifePerformance] = []
    undated = 0
    for row in rows:
        performance_id = row["performance_id"]
        show = shows.get(row["show_id"]) or {}
        show_date = show.get("show_date") or ""
        if len(show_date) < 10 or not show_date[:4].isdigit():
            undated += 1
            continue
        venue = venues.get(show.get("venue_id", "")) or {}
        before, after = around[performance_id]
        track = tracks.get(performance_id)
        tape_seconds = track.duration_seconds if track else None
        release = _release_length(release_seconds.get(performance_id, []), tape_seconds)
        seconds, source = _length(release, tape_seconds, performance_id)
        voices = performance_voices.get(performance_id, [])
        signals = [Signal(voice, "performance") for voice in voices]
        signals += [Signal(voice, "show") for voice in show_voices.get(row["show_id"], []) if voice not in voices]
        result.append(
            LifePerformance(
                performance_id=performance_id,
                show_id=row["show_id"],
                show_date=show_date,
                venue_name=venue.get("name") or None,
                city=", ".join(part for part in (venue.get("city"), venue.get("state_region")) if part) or None,
                set_number=_int(row.get("set_number")),
                set_label=row.get("set_label") or "",
                position_in_set=_int(row.get("position_in_set")),
                encore=row.get("encore") == "true",
                previous=Neighbor(before["song_id"], titles.get(before["song_id"], before["song_id"]), before.get("segue_into_next") == "true") if before else None,
                next=Neighbor(after["song_id"], titles.get(after["song_id"], after["song_id"]), row.get("segue_into_next") == "true") if after else None,
                seconds=seconds,
                length_source=source,
                audio_url=track.url if track else None,
                tape_seconds=track.duration_seconds if track else None,
                releases=release_titles.get(performance_id, ()),
                signals=tuple(signals),
                guests=guests.get(performance_id, ()),
            )
        )
    if undated:
        logger.info("Left %d undated performances of %s off its life", undated, song_id)
    result.sort(key=lambda performance: (performance.show_date, performance.set_number, performance.position_in_set))
    return result


def _fallback_pick(members: list[LifePerformance]) -> tuple[LifePerformance, str, str | None] | None:
    """The year's pick when the model names none: a picked version, a picked show, a release, the first."""

    playable = [performance for performance in members if performance.audio_url]
    for scope, basis in (("performance", "picked"), ("show", "show_picked")):
        for performance in playable:
            signal = next((item for item in performance.signals if item.scope == scope), None)
            if signal:
                return performance, basis, signal.voice
    for performance in playable:
        if performance.releases:
            return performance, "released", performance.releases[0]
    if playable:
        return playable[0], "first", None
    return (members[0], "first", None) if members else None


def year_summaries(performances: list[LifePerformance], title: str) -> list[dict[str, Any]]:
    """One row per year from the first to the last, the unplayed years as zero."""

    by_year: dict[int, list[LifePerformance]] = defaultdict(list)
    for performance in performances:
        by_year[performance.year].append(performance)
    if not by_year:
        return []
    rows = []
    for year in range(min(by_year), max(by_year) + 1):
        members = by_year.get(year, [])
        timed = [performance for performance in members if performance.seconds is not None]
        longest = max(timed, key=lambda performance: (performance.seconds, performance.show_date)) if timed else None
        nexts = Counter(performance.next.title for performance in members if performance.next)
        top = nexts.most_common(1)[0] if nexts else None
        pick = _fallback_pick(members)
        rows.append(
            {
                "year": year,
                "count": len(members),
                "median_seconds": int(round(median([performance.seconds for performance in timed]))) if timed else None,
                "longest": {"performance_id": longest.performance_id, "seconds": longest.seconds} if longest else None,
                "top_next": {"title": top[0], "count": top[1]} if top else None,
                "pick": (
                    {
                        "performance_id": pick[0].performance_id,
                        "show_date": pick[0].show_date,
                        "venue_name": pick[0].venue_name,
                        "set_label": pick[0].set_label or None,
                        "seconds": pick[0].seconds,
                        "basis": pick[1],
                        "basis_detail": pick[2],
                        "track": pick[0].track_json(title),
                    }
                    if pick
                    else None
                ),
            }
        )
    return rows


def _song(store: CanonicalStore, song_id: str) -> tuple[str, str] | None:
    song = store.one("songs", song_id)
    return (song_id, song.get("title") or song_id) if song else None


def card_data(store: CanonicalStore, song_id: str) -> dict[str, Any] | None:
    """What a song card's timeline carries: year summaries and one length point per performance."""

    song = _song(store, song_id)
    if not song:
        return None
    performances = life_performances(store, song_id)
    return {
        "song_id": song_id,
        "title": song[1],
        "performance_count": len(performances),
        "year_summaries": year_summaries(performances, song[1]),
        "length_points": [
            {"performance_id": p.performance_id, "show_date": p.show_date, "seconds": p.seconds}
            for p in performances
            if p.seconds is not None
        ],
    }


def year_detail(store: CanonicalStore, song_id: str, year: int) -> dict[str, Any] | None:
    """Every performance of the song in one year, with all its facts, for See all."""

    song = _song(store, song_id)
    if not song:
        return None
    return {
        "song_id": song_id,
        "title": song[1],
        "year": year,
        "performances": [p.to_json(song[1]) for p in life_performances(store, song_id) if p.year == year],
    }


def standouts(performances: list[LifePerformance]) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Performances whose facts stand out, each fact plain; no quality claims.

    Returns the kept standouts in date order, how many were cut, and patterns:
    rare placements shared by more than PATTERN_THRESHOLD performances, said
    once ("opened the show 25 times, 1968–1970") instead of listed. The most
    distinctive facts rank first, then versions with more facts; versions that
    stand out only for a release are cut first.
    """

    if not performances:
        return [], 0, []
    facts: dict[str, list[str]] = defaultdict(list)
    tier: dict[str, int] = {}
    order = {p.performance_id: index for index, p in enumerate(performances)}
    by_id = {p.performance_id: p for p in performances}

    def add(performance: LifePerformance, text: str, level: int) -> None:
        if text not in facts[performance.performance_id]:
            facts[performance.performance_id].append(text)
        tier[performance.performance_id] = min(tier.get(performance.performance_id, 9), level)

    total = len(performances)

    def rare(count: int) -> bool:
        return count / total <= RARE_PLACEMENT_SHARE

    add(performances[0], "first performance", 1)
    add(performances[-1], "last performance", 1)
    timed = [p for p in performances if p.seconds is not None]
    longest = max(timed, key=lambda p: (p.seconds, p.show_date)) if timed else None
    if longest:
        add(longest, f"longest on record ({clock(longest.seconds)})", 1)

    first_set = [p for p in performances if p.set_number == 1]
    later_sets = [p for p in performances if p.set_number != 1]
    opened_show = [p for p in first_set if p.previous is None]
    opened_set = [p for p in later_sets if p.previous is None]
    closed_set = [p for p in performances if p.next is None]
    encores = [p for p in performances if p.encore]
    meetings = Counter(n.song_id for p in performances for n in (p.previous, p.next) if n)

    for p in performances:
        for guest in p.guests:
            add(p, f"with {guest.name}" + (f" ({guest.instrument})" if guest.instrument else ""), 1)
        for signal in p.signals:
            if signal.scope == "performance":
                add(p, f"picked by {signal.voice}", 1)
            else:
                add(p, f"its show was picked by {signal.voice}", 2)
        if p.previous and p.next and p.previous.song_id == p.next.song_id:
            add(p, f"inside {p.previous.title}", 1)
        else:
            for neighbor in (p.previous, p.next):
                if neighbor and meetings[neighbor.song_id] <= RARE_NEIGHBOR_MEETINGS:
                    add(p, f"next to {neighbor.title}", 3)
    patterns: list[str] = []
    for group, label, level in (
        (opened_show, "opened the show", 2),
        (encores, "encore", 2),
        (first_set, "in the first set", 2),
        (later_sets, "in a later set", 2),
        (opened_set, "opened a set", 3),
        (closed_set, "closed the set", 3),
    ):
        if not group or not rare(len(group)):
            continue
        if len(group) > PATTERN_THRESHOLD:
            years = sorted({p.year for p in group})
            span = str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"
            patterns.append(f"{label} {len(group)} times, {span}")
            continue
        for p in group:
            add(p, f"in {p.set_label}" if label == "in a later set" and p.set_label else label, level)

    by_year: dict[int, list[LifePerformance]] = defaultdict(list)
    for p in timed:
        by_year[p.year].append(p)
    for year, members in by_year.items():
        top = max(members, key=lambda p: (p.seconds, p.show_date))
        if top is not longest:
            add(top, f"longest of {year} ({clock(top.seconds)})", 2)

    for p in performances:
        if p.releases:
            more = len(p.releases) - 1
            add(p, f"released on {p.releases[0].split(':')[0]}" + (f" and {more} more" if more else ""), 4)

    # Within a tier, a version with more facts stands out more; ties keep date order.
    ranked = sorted(facts, key=lambda performance_id: (tier[performance_id], -len(facts[performance_id]), order[performance_id]))
    kept = sorted(ranked[:STANDOUT_CEILING], key=order.__getitem__)
    cut = len(ranked) - len(kept)
    if cut:
        logger.info("Cut %d of %d standouts to the ceiling of %d", cut, len(ranked), STANDOUT_CEILING)
    return (
        [
            {"performance_id": pid, "date": by_id[pid].show_date, "venue": by_id[pid].venue_name, "facts": facts[pid]}
            for pid in kept
        ],
        cut,
        patterns,
    )


def tool_payload(store: CanonicalStore, song: dict[str, str]) -> dict[str, Any]:
    """The model's view of a song's life: years in brief and the performances that stand out."""

    song_id = song["song_id"]
    title = song.get("title") or song_id
    performances = life_performances(store, song_id)
    items, cut, patterns = standouts(performances)
    payload: dict[str, Any] = {
        "song": {"song_id": song_id, "title": title},
        "performance_count": len(performances),
        "years": [
            {
                "year": row["year"],
                "count": row["count"],
                "typical_minutes": round(row["median_seconds"] / 60, 1) if row["median_seconds"] else None,
                "longest_minutes": round(row["longest"]["seconds"] / 60, 1) if row["longest"] else None,
            }
            for row in year_summaries(performances, title)
        ],
        "standouts": items,
        "patterns": patterns,
        "lengths_note": (
            "Lengths are official release tracks where a release carries the performance, otherwise "
            "Internet Archive tape tracks; a tape track can be partial."
        ),
        "stops_note": "A song_overview's representatives become stops on its timeline: give each a short label and a one-line why.",
    }
    if cut:
        payload["standouts_note"] = (
            f"Showing {len(items)} of {len(items) + cut} standouts; versions that stand out only for a release were cut first. "
            "get_song_notable_versions lists every released and picked version."
        )
    return payload
