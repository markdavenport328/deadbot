# Life of a Song: Song Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a song card's year chart into an explorable timeline: two views, model-chosen stops with a listening path, and a year panel to play, see all, or ask.

**Architecture:** `deadbot/song_life.py` reads every fact about a song's performances from the store (lengths, set neighbors, tapes, releases, picks, guests) and shapes three outputs: the card's data, one year's full list, and the model's `get_song_life` digest. `web/src/SongTimeline.tsx` draws the card with hand-made SVG and plays through the shared player. Phase 1 (done) is new files only; Phase 2 wires them into shared files after the grid branch merges.

**Tech Stack:** Python 3 / FastAPI / Pydantic; React 19 / TypeScript / Vite / Vitest; the CSV, SQLite and PostgreSQL canonical stores.

**Spec:** `docs/superpowers/specs/2026-10-10-song-life-timeline-design.md`

> **Status, 2026-10-11:** Phase 1 shipped (PR #66). Phase 2 was built on `claude/song-timeline-phase2` with the owner's revisions recorded at the top of the spec (no code-chosen pick, history retired into the timeline, unranked standouts by kind, a mobile pass). Where Phase 2 below differs from the branch, the branch and the spec's Revisions are right.

## Global Constraints

- AGENTS.md: code guards facts and transport; the model owns judgment. No check, cap or rule that only polices the model's choices.
- Read the plan leniently; an unresolved stop renders the model's words without a Play, never dropped.
- Colors by role: gold hears (`--listen`), rose reads (`--read`), blue asks (`--ask`); 2px corners (`--r`); Fraunces for the year numeral.
- Store reads use only `rows_in`, `one` and `filtered_rows`.
- Lengths: official release track seconds, else tape track seconds; under 60 seconds is unknown.
- `get_song_life` payload under 9,000 characters (measured: Terrapin 7,400; Dark Star 8,500; Sugar Magnolia 7,700).
- Phase 1 touches new files only. Phase 2 starts from fresh main after `claude/whereyouworkmatters-research-8634ea` merges.
- Run Python tests with `PYTHONPATH=. ../../../.venv/bin/python -m pytest` from the worktree root (the shared virtualenv lives in the main checkout); web tests with `npm --prefix web test`.
- Agents commit locally; the owner pushes (see AGENTS.md).

---

# Phase 1: new files only (complete)

Phase 1 was built and verified while planning: every code block below is the committed file, so the plan and the code cannot drift. Commits: `cd5e9d8`, `311d09b`, `b6708f5`, `fe79528`, `d0ba2b8`, `daa0132`, then two commits of fixes from the final review (`b2758f0`, `b45abe1`):

- Release lengths: when several releases carry a performance and disagree, take the one nearest the tape, else the longest (a 30 Days of Dead excerpt no longer beats the full release).
- Fallback pick: a picked version outranks a picked show; Dead.net release confirmations are not picks.
- The tooltip and Ask follow the model's stop for a year, not the library's pick.
- Pins are placed left to right whatever the model's order, and the chart grows at the top for each extra pin row.
- Count gridlines never repeat for songs played once or twice.
- A slower year lookup for an earlier Length dot never replaces a later choice.
- "usually followed by" replaces "usually into", since the count includes songs that followed without a segue.

### Task 1: Song-life data module

**Files:**
- Create: `deadbot/song_life.py`
- Test: `tests/test_song_life.py`

**Interfaces:**
- Consumes: `store.filtered_rows/rows_in/one`; `deadbot.sequences._archive_tracks(store, ids) -> dict[str, Track]`; `deadbot.selection_signals.load_selection_signals(store)` (SQLite/PostgreSQL only; raises `SelectionSignalError` on the CSV store); `deadbot.canonical_import._selector_name(entry) -> str | None`.
- Produces: `life_performances(store, song_id) -> list[LifePerformance]`; `year_summaries(performances, title) -> list[dict]`; `card_data(store, song_id) -> dict | None`; `year_detail(store, song_id, year) -> dict | None`; `standouts(performances) -> tuple[list[dict], int, list[str]]`; `tool_payload(store, song_row) -> dict`; `LifePerformance.to_json(title)`, `LifePerformance.track_json(title)`.

- [x] **Step 1: Write the failing tests** (`tests/test_song_life.py`)

```python
import json

import pytest

from deadbot import song_life
from deadbot.data import CanonicalStore
from deadbot.song_life import LifePerformance, Neighbor, Signal, standouts, year_summaries

TERRAPIN = "song-terrapin-station"


@pytest.fixture(scope="module")
def csv_store():
    return CanonicalStore()


@pytest.fixture(scope="module")
def sqlite_store(built_sqlite, tmp_path_factory):
    from deadbot.sqlite_store import SqliteCanonicalStore

    return SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path_factory.mktemp("cache") / "cache.sqlite")


@pytest.fixture(scope="module")
def terrapin(csv_store):
    return song_life.life_performances(csv_store, TERRAPIN)


def by_date(performances, date):
    return next(p for p in performances if p.show_date == date)


def test_every_dated_performance_in_order(terrapin):
    assert len(terrapin) == 302
    assert terrapin[0].show_date == "1977-02-26"
    assert terrapin[-1].show_date == "1995-07-08"
    assert [p.show_date for p in terrapin] == sorted(p.show_date for p in terrapin)
    assert sum(1 for p in terrapin if p.year == 1979) == 23


def test_set_neighbors_carry_segues(terrapin):
    msg = by_date(terrapin, "1979-01-08")
    assert msg.previous.title == "Samson And Delilah"
    assert msg.next == Neighbor("song-playing-in-the-band", "Playing In The Band", True)
    assert msg.venue_name == "Madison Square Garden"
    assert msg.city == "New York, NY"


def test_length_prefers_release_then_tape_and_ignores_partial_tracks(terrapin):
    boston = by_date(terrapin, "1993-09-29")
    assert (boston.seconds, boston.length_source) == (1514, "tape")
    debut = by_date(terrapin, "1977-02-26")
    assert debut.length_source == "release"
    # A 14-second tape track is a fragment, not the performance's length.
    assert by_date(terrapin, "1977-02-27").seconds is None


def test_releases_and_guests(terrapin):
    assert by_date(terrapin, "1977-05-28").releases[0].startswith("To Terrapin")
    assert [g.name for g in by_date(terrapin, "1989-12-06").guests] == ["Clarence Clemons"]


def test_year_summaries_span_every_year_with_counts_and_lengths(terrapin):
    rows = year_summaries(terrapin, "Terrapin Station")
    assert [row["year"] for row in rows] == list(range(1977, 1996))
    y1979 = next(row for row in rows if row["year"] == 1979)
    assert y1979["count"] == 23
    assert y1979["top_next"] == {"title": "Playing In The Band", "count": 20}
    assert y1979["longest"] == {"performance_id": "gd-1979-11-06-terrapin-station-2-1", "seconds": 937}
    assert y1979["median_seconds"] == 758
    assert y1979["pick"]["track"]["audio_url"].startswith("https://archive.org/download/")


def test_gap_years_are_zero_and_have_no_pick(csv_store):
    rows = year_summaries(song_life.life_performances(csv_store, "song-dark-star"), "Dark Star")
    y1975 = next(row for row in rows if row["year"] == 1975)
    assert y1975 == {"year": 1975, "count": 0, "median_seconds": None, "longest": None, "top_next": None, "pick": None}


def test_a_song_played_once(csv_store):
    data = song_life.card_data(csv_store, "song-i-ll-go-crazy")
    assert data["performance_count"] == 1
    assert len(data["year_summaries"]) == 1
    assert data["year_summaries"][0]["pick"]["basis"] in {"first", "released", "picked", "show_picked"}


def test_card_data_carries_length_points_without_venues(csv_store):
    data = song_life.card_data(csv_store, TERRAPIN)
    assert data["title"] == "Terrapin Station"
    assert len(data["length_points"]) == sum(1 for p in song_life.life_performances(csv_store, TERRAPIN) if p.seconds)
    assert set(data["length_points"][0]) == {"performance_id", "show_date", "seconds"}


def test_year_detail_lists_one_year_with_full_facts(csv_store):
    detail = song_life.year_detail(csv_store, TERRAPIN, 1979)
    assert detail["year"] == 1979
    assert len(detail["performances"]) == 23
    first = detail["performances"][0]
    assert first["show_date"] == "1979-01-08"
    assert first["next"]["segued"] is True
    assert song_life.year_detail(csv_store, TERRAPIN, 1975)["performances"] == []
    assert song_life.year_detail(csv_store, "song-no-such-song", 1979) is None


def test_fallback_pick_prefers_picked_then_released_then_first(sqlite_store):
    rows = song_life.card_data(sqlite_store, TERRAPIN)["year_summaries"]
    y1979 = next(row for row in rows if row["year"] == 1979)
    assert (y1979["pick"]["basis"], y1979["pick"]["show_date"], y1979["pick"]["basis_detail"]) == ("show_picked", "1979-01-08", "Charlie Miller")
    y1978 = next(row for row in rows if row["year"] == 1978)
    assert y1978["pick"]["basis"] == "released"


def test_stores_agree_on_facts(csv_store, sqlite_store):
    csv_rows = song_life.life_performances(csv_store, TERRAPIN)
    sqlite_rows = song_life.life_performances(sqlite_store, TERRAPIN)
    key = lambda p: (p.performance_id, p.seconds, p.previous, p.next, p.releases, p.guests, p.audio_url)
    assert [key(p) for p in csv_rows] == [key(p) for p in sqlite_rows]


def test_standouts_state_facts_across_the_songs_life(sqlite_store):
    items, cut, patterns = standouts(song_life.life_performances(sqlite_store, TERRAPIN))
    facts = {item["date"]: item["facts"] for item in items}
    assert "first performance" in facts["1977-02-26"]
    assert "last performance" in facts["1995-07-08"]
    assert "longest on record (25:14)" in facts["1993-09-29"]
    assert "inside Playing In The Band" in facts["1981-12-31"]
    assert "its show was picked by Charlie Miller" in facts["1981-12-31"]
    assert "with Clarence Clemons (saxophone)" in facts["1989-12-06"]
    assert len(items) == song_life.STANDOUT_CEILING and cut > 0
    assert [item["date"] for item in items] == sorted(item["date"] for item in items)
    # Standouts reach the song's later years, not only its first.
    assert sum(1 for item in items if item["date"] >= "1985") >= 8
    assert "opened a set 17 times, 1977–1991" in patterns


def test_common_placements_become_patterns_not_standouts(sqlite_store):
    items, _cut, patterns = standouts(song_life.life_performances(sqlite_store, "song-dark-star"))
    assert "opened the show 20 times, 1968–1970" in patterns
    assert not any("opened the show" in fact for item in items for fact in item["facts"])


def test_standouts_of_a_tiny_song():
    lone = LifePerformance(
        performance_id="p1", show_id="s1", show_date="1970-01-01", venue_name="Hall", city=None, set_number=2,
        set_label="Set 2", position_in_set=3, encore=False, previous=None, next=None, seconds=300,
        length_source="tape", audio_url=None, tape_seconds=300, releases=(), signals=(Signal("Charlie Miller", "performance"),), guests=(),
    )
    items, cut, patterns = standouts([lone])
    assert items[0]["facts"][:3] == ["first performance", "last performance", "longest on record (5:00)"]
    assert "picked by Charlie Miller" in items[0]["facts"]
    assert cut == 0
    assert standouts([]) == ([], 0, [])


@pytest.mark.parametrize("song_id", [TERRAPIN, "song-dark-star", "song-sugar-magnolia"])
def test_tool_payload_stays_compact(sqlite_store, song_id):
    payload = song_life.tool_payload(sqlite_store, sqlite_store.one("songs", song_id))
    assert len(json.dumps(payload, ensure_ascii=False)) < 9000
    assert payload["years"][0]["count"] > 0
    assert payload["stops_note"]


def test_disagreeing_releases_take_the_length_nearest_the_tape(sqlite_store):
    # A 30 Days of Dead excerpt (447s) must not beat the full release (1263s); the tape runs 1244s.
    pitb = by_date(song_life.life_performances(sqlite_store, "song-playing-in-the-band"), "1974-02-22")
    assert (pitb.seconds, pitb.length_source) == (1263, "release")
    assert song_life._release_length([447, 1263], None) == 1263
    assert song_life._release_length([30], 500) == 30


def test_a_picked_version_outranks_an_earlier_picked_show(sqlite_store):
    rows = song_life.card_data(sqlite_store, "song-fire-on-the-mountain")["year_summaries"]
    pick = next(row for row in rows if row["year"] == 1977)["pick"]
    assert (pick["basis"], pick["show_date"], pick["basis_detail"]) == ("picked", "1977-05-13", "Charlie Miller")
    # Release confirmations are not picks.
    assert not any(s.voice == "Dead.net" for p in song_life.life_performances(sqlite_store, TERRAPIN) for s in p.signals)
```

- [x] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_song_life.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'deadbot.song_life'`

- [x] **Step 3: Write the module** (`deadbot/song_life.py`)

```python
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
```

- [x] **Step 4: Run the tests**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_song_life.py -q`
Expected: `19 passed`

- [x] **Step 5: Commit**

```bash
git add deadbot/song_life.py tests/test_song_life.py
git commit -m "Gather a song's life on stage: every performance's facts, year summaries and standouts"
```

### Task 2: Terrapin fixtures from the real library

**Files:**
- Create: `scripts/export_song_timeline_fixture.py`
- Create (generated): `web/src/fixtures/song-timeline-terrapin.json`, `web/src/fixtures/song-timeline-terrapin-years.json`

**Interfaces:**
- Consumes: `song_life.card_data`, `song_life.life_performances`, `song_life.year_detail`.
- Produces: a card JSON matching `SongTimelineData` (Task 3) and a `{ "<year>": SongYearDetail }` JSON.

- [x] **Step 1: Write the script**

```python
"""Write the song timeline's preview fixtures from the real library.

The card data and every year's performances are the library's own, read
through deadbot.song_life from the real SQLite catalog. The stops, the open
year and the year questions stand in for what the model writes in the app;
they are marked as stand-ins in the fixture. Run from the repository root:

    PYTHONPATH=. python scripts/export_song_timeline_fixture.py

It writes web/src/fixtures/song-timeline-terrapin.json (the card) and
web/src/fixtures/song-timeline-terrapin-years.json (every year's See all list).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from deadbot import song_life
from deadbot.sqlite_build import build_database
from deadbot.sqlite_store import SqliteCanonicalStore

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "fixtures"
SONG_ID = "song-terrapin-station"

# Stand-ins for the model's stops: (show date, label, why).
STAND_IN_STOPS = [
    ("1977-02-26", "The debut", "First time out, opening the show five months before the studio album."),
    ("1977-05-28", "Hartford, the version of record", "Released on its own as To Terrapin. The spring 1977 arrangement at full strength."),
    ("1978-09-15", "At the pyramids", "Played at the foot of the Great Pyramid, coming out of Space."),
    ("1979-01-08", "Charlie Miller's pick", "The 1979 show Charlie Miller singles out, and the one from the visitor's first question."),
    ("1981-12-31", "New Year's, inside Playin'", "Tucked into the middle of Playing in the Band on New Year's Eve."),
    ("1989-12-06", "With Clarence Clemons", "Clemons sits in on sax and the song stretches to almost 23 minutes."),
    ("1993-09-29", "The longest", "Over 25 minutes in Boston, the longest Terrapin on record."),
    ("1995-07-08", "The last", "The final Terrapin, at Soldier Field the night before the band's last show."),
]
STAND_IN_QUESTIONS = {
    1977: "How did Terrapin change between its debut and the fall of 1977?",
    1979: "How did the 1979 Terrapins differ from 1977?",
    1980: "Why did Terrapin start leading into Drums in 1980?",
    1989: "What did Clarence Clemons add to Terrapin?",
    1993: "What made the Boston '93 Terrapin run 25 minutes?",
}


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        store = SqliteCanonicalStore(build_database(Path(folder) / "deadbot.sqlite").path, response_cache_path=Path(folder) / "cache.sqlite")
        card = song_life.card_data(store, SONG_ID)
        if card is None:
            raise SystemExit(f"{SONG_ID} is not in the library")
        performances = {p.show_date: p for p in song_life.life_performances(store, SONG_ID)}
        stops = []
        for show_date, label, why in STAND_IN_STOPS:
            performance = performances[show_date]
            stops.append(
                {
                    "performance_id": performance.performance_id,
                    "label": label,
                    "why": why,
                    "show_date": performance.show_date,
                    "venue_name": performance.venue_name,
                    "seconds": performance.seconds,
                    "track": performance.track_json(card["title"]),
                }
            )
        card.update(
            {
                "_note": "Stops, open_year, chart_view and year_questions are stand-ins for the model's choices; every other fact is the library's.",
                "stops": stops,
                "open_year": 1979,
                "chart_view": "count",
                "year_questions": [{"year": year, "question": question} for year, question in STAND_IN_QUESTIONS.items()],
            }
        )
        years = {
            str(row["year"]): song_life.year_detail(store, SONG_ID, row["year"])
            for row in card["year_summaries"]
            if row["count"]
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "song-timeline-terrapin.json").write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n")
    (OUT / "song-timeline-terrapin-years.json").write_text(json.dumps(years, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"Wrote the card ({len(card['year_summaries'])} years, {len(stops)} stops) and {len(years)} years of performances")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Run it**

Run: `PYTHONPATH=. ../../../.venv/bin/python scripts/export_song_timeline_fixture.py`
Expected: `Wrote the card (19 years, 8 stops) and 19 years of performances`

- [x] **Step 3: Commit**

```bash
git add scripts/export_song_timeline_fixture.py web/src/fixtures/song-timeline-terrapin.json web/src/fixtures/song-timeline-terrapin-years.json
git commit -m "Export Terrapin timeline fixtures from the real library, stops marked as stand-ins"
```

### Task 3: Timeline types, geometry, copy and year lookup client

**Files:**
- Create: `web/src/song-timeline-types.ts`, `web/src/song-timeline-geometry.ts`, `web/src/song-timeline-text.ts`, `web/src/song-year.ts`
- Test: `web/src/song-timeline-helpers.test.ts`

**Interfaces:**
- Consumes: `clock(seconds)` from `web/src/VersionStrip.tsx`.
- Produces: the types `SongTimelineData`, `YearSummary`, `YearPick`, `LengthPoint`, `TimelineStop`, `TimelineTrack`, `SongYearDetail`, `YearPerformance`, `TimelineFocus`, `ChartView`; geometry `frame`, `bandX`, `pointX`, `dayFraction`, `countTicks`, `lengthTicks`, `yFor`, `yearLabelStep`, `pinRows`, `pinY`, `MARGIN`; copy `yearFacts`, `pickEyebrow`, `askQuestion`, `flowLine`, `performanceTags`, `focusFor`, `initialYear`, `longDate`, `monthDay`, `shortDate`, `plural`; client `fetchSongYear: FetchYear`, `songYearUrl`, `forgetSongYears`.

- [x] **Step 1: Install web dependencies** (once per worktree): `npm --prefix web ci`

- [x] **Step 2: Write the failing tests** (`web/src/song-timeline-helpers.test.ts`)

```ts
import { afterEach, expect, test, vi } from "vitest";
import { bandX, countTicks, dayFraction, frame, lengthTicks, pinRows, pinY, pointX, yFor, yearLabelStep } from "./song-timeline-geometry";
import { askQuestion, flowLine, focusFor, initialYear, pickEyebrow, performanceTags, yearFacts } from "./song-timeline-text";
import type { SongTimelineData, YearPerformance, YearSummary } from "./song-timeline-types";
import { fetchSongYear, forgetSongYears, songYearUrl } from "./song-year";

const y1979: YearSummary = {
  year: 1979,
  count: 23,
  median_seconds: 758,
  longest: { performance_id: "p-long", seconds: 925 },
  top_next: { title: "Playing In The Band", count: 20 },
  pick: {
    performance_id: "p-msg",
    show_date: "1979-01-08",
    venue_name: "Madison Square Garden",
    set_label: "Set 2",
    seconds: 735,
    basis: "show_picked",
    basis_detail: "Charlie Miller",
    track: null
  }
};

const data: SongTimelineData = {
  song_id: "song-terrapin-station",
  title: "Terrapin Station",
  performance_count: 23,
  year_summaries: [{ year: 1978, count: 0, median_seconds: null, longest: null, top_next: null, pick: null }, y1979],
  length_points: [],
  stops: [],
  open_year: null,
  chart_view: null,
  year_questions: [{ year: 1979, question: "How did the 1979 Terrapins differ from 1977?" }]
};

const performance: YearPerformance = {
  performance_id: "p-msg",
  show_id: "gd-1979-01-08",
  show_date: "1979-01-08",
  venue_name: "Madison Square Garden",
  city: "New York, NY",
  set_label: "Set 2",
  position_in_set: 4,
  encore: false,
  previous: { song_id: "song-samson", title: "Samson And Delilah", segued: false },
  next: { song_id: "song-playin", title: "Playing In The Band", segued: true },
  seconds: 735,
  length_source: "tape",
  track: null,
  releases: [],
  signals: [{ voice: "Charlie Miller", scope: "show" }],
  guests: []
};

afterEach(() => {
  forgetSongYears();
  vi.unstubAllGlobals();
});

test("years get equal bands and dates fall inside their year's band", () => {
  const f = frame(636, [1977, 1978, 1979], "count");
  expect(f.bandWidth).toBe(198);
  expect(bandX(f, 1979)).toBe(36 + 2 * 198);
  expect(dayFraction("1979-01-01")).toBeCloseTo(0.5 / 366);
  const x = pointX(f, "1979-07-02");
  expect(x).toBeGreaterThan(bandX(f, 1979));
  expect(x).toBeLessThan(bandX(f, 1979) + f.bandWidth);
});

test("the vertical scales round up to tidy gridlines", () => {
  expect(countTicks(28)).toEqual([0, 10, 20, 30]);
  expect(countTicks(3)).toEqual([0, 1, 2, 3]);
  expect(lengthTicks(1514)).toEqual([0, 300, 600, 900, 1200, 1500, 1800]);
  const f = frame(600, [1977], "length");
  expect(yFor(f, 0, 1800)).toBe(f.plotBottom);
  expect(yFor(f, 1800, 1800)).toBe(f.plotTop);
});

test("crowded pins stack into rows and year labels thin out when narrow", () => {
  expect(pinRows([10, 15, 60, 70, 74, 120])).toEqual([0, 1, 0, 1, 2, 0]);
  // Stops arrive in listening order; rows are assigned left to right.
  expect(pinRows([500, 100, 300, 112, 510])).toEqual([0, 0, 0, 1, 1]);
  expect(countTicks(1)).toEqual([0, 1]);
  expect(countTicks(2)).toEqual([0, 1, 2]);
  const roomy = frame(600, [1977], "count", 3);
  expect(roomy.plotTop - frame(600, [1977], "count").plotTop).toBe(38);
  expect(pinY(roomy, 2)).toBeGreaterThan(0);
  expect(yearLabelStep(50)).toBe(1);
  expect(yearLabelStep(25)).toBe(3);
  expect(yearLabelStep(12)).toBe(6);
});

test("a year's facts, pick and question read from the data", () => {
  expect(yearFacts(y1979)).toBe("23 performances · typically 12:38 · usually followed by Playing In The Band (20 of 23)");
  expect(pickEyebrow(y1979.pick!, null)).toBe("Show picked by Charlie Miller");
  expect(pickEyebrow(y1979.pick!, { number: 4, label: "Charlie Miller's pick" })).toBe("Stop 4 · Charlie Miller's pick");
  expect(pickEyebrow({ ...y1979.pick!, basis: "released", basis_detail: "Dave's Picks, Volume 31: Uptown Theatre" }, null)).toBe("On Dave's Picks, Volume 31");
  expect(askQuestion(data, 1979)).toBe("How did the 1979 Terrapins differ from 1977?");
  expect(askQuestion(data, 1980)).toBe("Tell me about Terrapin Station in 1980");
});

test("a performance's flow joins segues with › and names its tags", () => {
  expect(flowLine(performance, "Terrapin Station")).toBe("Terrapin Station › Playing In The Band");
  expect(flowLine({ ...performance, previous: { ...performance.previous!, segued: true }, next: null }, "Terrapin Station")).toBe(
    "Samson And Delilah › Terrapin Station, closing the set"
  );
  expect(performanceTags({ ...performance, releases: ["X"] }, 4)).toEqual(["Stop 4", "Show picked by Charlie Miller", "Released"]);
});

test("focus names the song, the year and its pick; the open year falls back to a played year", () => {
  expect(focusFor(data, y1979)).toEqual({
    label: "Terrapin Station in 1979",
    song_id: "song-terrapin-station",
    year: 1979,
    ids: ["song-terrapin-station", "p-msg"],
    facts: ["23 performances · typically 12:38 · usually followed by Playing In The Band (20 of 23)"]
  });
  expect(initialYear(data)).toBe(1979);
  expect(initialYear({ ...data, open_year: 1978 })).toBe(1979);
});

test("the year lookup asks once per song and year and retries after a failure", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 503 })
    .mockResolvedValue({ ok: true, json: async () => ({ song_id: "s", title: "T", year: 1979, performances: [] }) });
  vi.stubGlobal("fetch", fetchMock);
  expect(songYearUrl("song-terrapin-station", 1979)).toBe("/api/songs/song-terrapin-station/years/1979");
  await expect(fetchSongYear("s", 1979)).rejects.toThrow("The 1979 list could not load (503).");
  await fetchSongYear("s", 1979);
  await fetchSongYear("s", 1979);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
```

- [x] **Step 3: Run them to see them fail**

Run: `cd web && npx vitest run src/song-timeline-helpers.test.ts`
Expected: FAIL, cannot resolve `./song-timeline-geometry`

- [x] **Step 4: Write the types** (`web/src/song-timeline-types.ts`)

```ts
// The song timeline's data, mirroring deadbot/song_life.py's JSON. Phase 2
// replaces these with types generated from the API schema.

export type TimelineTrack = {
  performance_id: string;
  title: string;
  audio_url: string;
  duration_seconds: number | null;
  set_label: string | null;
};

export type PickBasis = "picked" | "show_picked" | "released" | "first";

export type YearPick = {
  performance_id: string;
  show_date: string;
  venue_name: string | null;
  set_label: string | null;
  seconds: number | null;
  basis: PickBasis;
  basis_detail: string | null;
  track: TimelineTrack | null;
};

export type YearSummary = {
  year: number;
  count: number;
  median_seconds: number | null;
  longest: { performance_id: string; seconds: number } | null;
  top_next: { title: string; count: number } | null;
  pick: YearPick | null;
};

export type LengthPoint = { performance_id: string; show_date: string; seconds: number };

// The model's stop; a stop the library could not resolve has only its words.
export type TimelineStop = {
  performance_id: string;
  label: string | null;
  why: string | null;
  show_date?: string | null;
  venue_name?: string | null;
  seconds?: number | null;
  track?: TimelineTrack | null;
};

export type ChartView = "count" | "length";

export type SongTimelineData = {
  song_id: string;
  title: string;
  performance_count: number;
  year_summaries: YearSummary[];
  length_points: LengthPoint[];
  stops: TimelineStop[];
  open_year: number | null;
  chart_view: ChartView | null;
  year_questions: { year: number; question: string }[];
};

export type Neighbor = { song_id: string; title: string; segued: boolean };

export type YearPerformance = {
  performance_id: string;
  show_id: string;
  show_date: string;
  venue_name: string | null;
  city: string | null;
  set_label: string | null;
  position_in_set: number;
  encore: boolean;
  previous: Neighbor | null;
  next: Neighbor | null;
  seconds: number | null;
  length_source: "release" | "tape" | null;
  track: TimelineTrack | null;
  releases: string[];
  signals: { voice: string; scope: "performance" | "show" }[];
  guests: { name: string; instrument: string | null }[];
};

export type SongYearDetail = { song_id: string; title: string; year: number; performances: YearPerformance[] };

// What the visitor was pointing at when they asked; phase 2 sends it as AskFocus.
export type TimelineFocus = { label: string; song_id: string; year: number; ids: string[]; facts: string[] };
```

- [x] **Step 5: Write the geometry** (`web/src/song-timeline-geometry.ts`)

```ts
// Where the song timeline draws things: one band per year, bars or dots on a
// shared vertical scale, and gold pins for the model's stops. Pure functions,
// so the chart's layout is tested without a browser.
import type { ChartView } from "./song-timeline-types";

export const MARGIN = { left: 36, right: 6, top: 44, bottom: 26 };
const NARROW = 560;
const PIN_ROW_HEIGHT = 19;

export type Frame = {
  width: number;
  height: number;
  firstYear: number;
  yearCount: number;
  bandWidth: number;
  barWidth: number;
  plotTop: number;
  plotBottom: number;
};

export function chartHeight(view: ChartView, width: number): number {
  const narrow = width < NARROW;
  return view === "length" ? (narrow ? 250 : 290) : narrow ? 230 : 270;
}

// `pinRows` is how many rows of stop pins sit above the plot; each extra row
// adds room at the top so no pin is drawn off the chart.
export function frame(width: number, years: number[], view: ChartView, pinRows = 1): Frame {
  const extra = Math.max(0, pinRows - 1) * PIN_ROW_HEIGHT;
  const height = chartHeight(view, width) + extra;
  const yearCount = Math.max(1, years.length);
  const bandWidth = (width - MARGIN.left - MARGIN.right) / yearCount;
  return {
    width,
    height,
    firstYear: years[0] ?? 0,
    yearCount,
    bandWidth,
    barWidth: Math.min(26, bandWidth * 0.64),
    plotTop: MARGIN.top + extra,
    plotBottom: height - MARGIN.bottom
  };
}

export function bandX(f: Frame, year: number): number {
  return MARGIN.left + (year - f.firstYear) * f.bandWidth;
}

// How far through its year a date falls, from just above 0 to just below 1.
export function dayFraction(date: string): number {
  const year = Number(date.slice(0, 4));
  const day = (Date.UTC(year, Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10))) - Date.UTC(year, 0, 1)) / 86_400_000;
  return (day + 0.5) / 366;
}

// A performance's place inside its year's band, inset so dots stay off the band edges.
export function pointX(f: Frame, date: string): number {
  return bandX(f, Number(date.slice(0, 4))) + f.bandWidth * 0.1 + dayFraction(date) * f.bandWidth * 0.8;
}

const NICE = [1, 2, 5, 10];

// Gridlines for counts: a round step giving four or five intervals.
export function countTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  // Counts are whole numbers, so the step is never below one.
  const step = Math.max(1, (NICE.find((n) => n * power >= raw) ?? 10) * power);
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top + step / 2; value += step) ticks.push(Math.round(value));
  return ticks;
}

// Gridlines for lengths, in seconds, every five minutes up past the longest.
export function lengthTicks(maxSeconds: number): number[] {
  const top = Math.max(300, Math.ceil(maxSeconds / 300) * 300);
  const ticks: number[] = [];
  for (let value = 0; value <= top; value += 300) ticks.push(value);
  return ticks;
}

export function yFor(f: Frame, value: number, top: number): number {
  return f.plotBottom - (top > 0 ? value / top : 0) * (f.plotBottom - f.plotTop);
}

// Label every year when there is room, otherwise every third or sixth.
export function yearLabelStep(bandWidth: number): number {
  return bandWidth >= 40 ? 1 : bandWidth >= 22 ? 3 : 6;
}

// Each pin's row above the chart, returned in the input's order: placed left
// to right, a pin too close to the last one in a row moves up a row. Stops
// arrive in the model's listening order, so they are placed by x here.
export function pinRows(xs: number[], minGap = 20): number[] {
  const lastInRow: number[] = [];
  const rows = new Array<number>(xs.length).fill(0);
  const byX = xs.map((x, index) => ({ x, index })).sort((a, b) => a.x - b.x);
  for (const { x, index } of byX) {
    let row = 0;
    while (lastInRow[row] !== undefined && x - lastInRow[row] < minGap) row += 1;
    lastInRow[row] = x;
    rows[index] = row;
  }
  return rows;
}

export function pinY(f: Frame, row: number): number {
  return f.plotTop - 22 - row * PIN_ROW_HEIGHT;
}
```

- [x] **Step 6: Write the copy helpers** (`web/src/song-timeline-text.ts`)

```ts
// The song timeline's words: every line is built from library facts or the
// model's own text, never invented here.
import { clock } from "./VersionStrip";
import type { SongTimelineData, TimelineFocus, YearPerformance, YearPick, YearSummary } from "./song-timeline-types";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function longDate(iso: string): string {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}, ${iso.slice(0, 4)}`;
}

export function monthDay(iso: string): string {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1].slice(0, 3)} ${Number(iso.slice(8, 10))}`;
}

export function shortDate(iso: string): string {
  return `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}/${iso.slice(2, 4)}`;
}

export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

// "23 performances · typically 12:38 · usually followed by Playing In The Band (20 of 23)".
// The count includes songs that followed without a segue, so it says "followed by"
export function yearFacts(summary: YearSummary): string {
  const parts = [plural(summary.count, "performance")];
  if (summary.median_seconds != null) parts.push(`typically ${clock(summary.median_seconds)}`);
  const next = summary.top_next;
  if (next) parts.push(`${next.count * 2 > summary.count ? "usually" : "most often"} followed by ${next.title} (${next.count} of ${summary.count})`);
  return parts.join(" · ");
}

// Why this is the year's pick: the model's stop if it named one, else the library's reason.
export function pickEyebrow(pick: YearPick, stop: { number: number; label: string | null } | null): string {
  if (stop) return stop.label ? `Stop ${stop.number} · ${stop.label}` : `Stop ${stop.number}`;
  const detail = pick.basis_detail ?? "";
  switch (pick.basis) {
    case "picked":
      return `Picked by ${detail}`;
    case "show_picked":
      return `Show picked by ${detail}`;
    case "released":
      return `On ${detail.split(":")[0]}`;
    default:
      return "First of the year";
  }
}

export function askQuestion(data: SongTimelineData, year: number): string {
  return data.year_questions.find((item) => item.year === year)?.question ?? `Tell me about ${data.title} in ${year}`;
}

// "Samson And Delilah › Terrapin Station › Playing In The Band": a segue joins with ›.
export function flowLine(performance: YearPerformance, title: string): string {
  const before = performance.previous?.segued ? `${performance.previous.title} › ` : "";
  const next = performance.next;
  const after = next ? (next.segued ? ` › ${next.title}` : `, then ${next.title}`) : ", closing the set";
  return `${before}${title}${after}`;
}

export function performanceTags(performance: YearPerformance, stopNumber: number | null): string[] {
  const tags: string[] = [];
  if (stopNumber) tags.push(`Stop ${stopNumber}`);
  for (const signal of performance.signals) tags.push(`${signal.scope === "show" ? "Show picked" : "Picked"} by ${signal.voice}`);
  for (const guest of performance.guests) tags.push(`With ${guest.name}`);
  if (performance.releases.length) tags.push("Released");
  return tags;
}

// `chosenId` is the performance the panel shows for the year: the model's stop
// when it named one, else the library's pick.
export function focusFor(data: SongTimelineData, summary: YearSummary, chosenId: string | null = summary.pick?.performance_id ?? null): TimelineFocus {
  return {
    label: `${data.title} in ${summary.year}`,
    song_id: data.song_id,
    year: summary.year,
    ids: [data.song_id, ...(chosenId ? [chosenId] : [])],
    facts: [yearFacts(summary)]
  };
}

// The model's open year when it was played; otherwise the first year with a pick.
export function initialYear(data: SongTimelineData): number | null {
  const played = data.year_summaries.filter((summary) => summary.count > 0);
  if (data.open_year != null && played.some((summary) => summary.year === data.open_year)) return data.open_year;
  return (played.find((summary) => summary.pick) ?? played[0])?.year ?? null;
}
```

- [x] **Step 7: Write the year lookup client** (`web/src/song-year.ts`)

```ts
// The year lookup behind "See all": one song's performances in one year,
// fetched once per song and year and kept for the session. Library facts do
// not change between deploys, so a kept answer never goes stale.
import type { SongYearDetail } from "./song-timeline-types";

export type FetchYear = (songId: string, year: number) => Promise<SongYearDetail>;

const kept = new Map<string, Promise<SongYearDetail>>();

export function songYearUrl(songId: string, year: number): string {
  return `/api/songs/${encodeURIComponent(songId)}/years/${year}`;
}

export const fetchSongYear: FetchYear = (songId, year) => {
  const key = `${songId}:${year}`;
  let pending = kept.get(key);
  if (!pending) {
    pending = fetch(songYearUrl(songId, year)).then(async (response) => {
      if (!response.ok) throw new Error(`The ${year} list could not load (${response.status}).`);
      return (await response.json()) as SongYearDetail;
    });
    // A failed lookup is forgotten so the visitor's retry asks again.
    pending.catch(() => kept.delete(key));
    kept.set(key, pending);
  }
  return pending;
};

export function forgetSongYears(): void {
  kept.clear();
}
```

- [x] **Step 8: Run the tests and the type check**

Run: `cd web && npx vitest run src/song-timeline-helpers.test.ts && npx tsc -p tsconfig.json --noEmit`
Expected: all pass, no type errors

- [x] **Step 9: Commit**

```bash
git add web/src/song-timeline-types.ts web/src/song-timeline-geometry.ts web/src/song-timeline-text.ts web/src/song-year.ts web/src/song-timeline-helpers.test.ts
git commit -m "Add the song timeline's types, chart geometry, copy and year lookup client"
```

### Task 4: The timeline component

**Files:**
- Create: `web/src/SongTimeline.tsx`, `web/src/SongTimeline.css`
- Test: `web/src/SongTimeline.test.tsx`

**Interfaces:**
- Consumes: Task 3's types, geometry, copy and `fetchSongYear`; `usePlayer()` and `PlayerTrack` from `web/src/player.tsx`; `toTrack(track, meta)` from `web/src/listen-control.tsx`.
- Produces: `SongTimeline({ data: SongTimelineData; onAsk(question: string, focus: TimelineFocus): void; fetchYear?: FetchYear })`.

- [x] **Step 1: Write the failing tests** (`web/src/SongTimeline.test.tsx`)

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { PlayerProvider, usePlayer } from "./player";
import { SongTimeline } from "./SongTimeline";
import type { SongTimelineData, SongYearDetail, TimelineTrack } from "./song-timeline-types";

const track = (id: string): TimelineTrack => ({ performance_id: id, title: "Terrapin Station", audio_url: `https://archive.org/download/gd/${id}.mp3`, duration_seconds: 600, set_label: "Set 2" });

const data: SongTimelineData = {
  song_id: "song-terrapin-station",
  title: "Terrapin Station",
  performance_count: 3,
  year_summaries: [
    {
      year: 1977,
      count: 2,
      median_seconds: 640,
      longest: { performance_id: "p-hartford", seconds: 671 },
      top_next: { title: "Playing In The Band", count: 1 },
      pick: { performance_id: "p-debut", show_date: "1977-02-26", venue_name: "Swing Auditorium", set_label: "Set 1", seconds: 668, basis: "released", basis_detail: "Dave's Picks, Volume 29: Swing", track: track("p-debut") }
    },
    { year: 1978, count: 0, median_seconds: null, longest: null, top_next: null, pick: null },
    {
      year: 1979,
      count: 1,
      median_seconds: 735,
      longest: { performance_id: "p-msg", seconds: 735 },
      top_next: { title: "Playing In The Band", count: 1 },
      pick: { performance_id: "p-msg", show_date: "1979-01-08", venue_name: "Madison Square Garden", set_label: "Set 2", seconds: 735, basis: "show_picked", basis_detail: "Charlie Miller", track: track("p-msg") }
    }
  ],
  length_points: [
    { performance_id: "p-debut", show_date: "1977-02-26", seconds: 668 },
    { performance_id: "p-hartford", show_date: "1977-05-28", seconds: 671 },
    { performance_id: "p-msg", show_date: "1979-01-08", seconds: 735 }
  ],
  stops: [
    { performance_id: "p-debut", label: "The debut", why: "First time out.", show_date: "1977-02-26", venue_name: "Swing Auditorium", seconds: 668, track: track("p-debut") },
    { performance_id: "p-lost", label: "A lost night", why: "Not in the library.", show_date: null },
    { performance_id: "p-msg", label: "Charlie Miller's pick", why: "From your first question.", show_date: "1979-01-08", venue_name: "Madison Square Garden", seconds: 735, track: track("p-msg") }
  ],
  open_year: 1979,
  chart_view: null,
  year_questions: [{ year: 1979, question: "How did the 1979 Terrapins differ from 1977?" }]
};

const detail1979: SongYearDetail = {
  song_id: "song-terrapin-station",
  title: "Terrapin Station",
  year: 1979,
  performances: [
    {
      performance_id: "p-msg",
      show_id: "gd-1979-01-08",
      show_date: "1979-01-08",
      venue_name: "Madison Square Garden",
      city: "New York, NY",
      set_label: "Set 2",
      position_in_set: 4,
      encore: false,
      previous: { song_id: "song-samson", title: "Samson And Delilah", segued: false },
      next: { song_id: "song-playin", title: "Playing In The Band", segued: true },
      seconds: 735,
      length_source: "tape",
      track: track("p-msg"),
      releases: [],
      signals: [{ voice: "Charlie Miller", scope: "show" }],
      guests: []
    }
  ]
};

function Queue() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((item) => item.id).join(" > ")}</output>;
}

function setup(overrides: Partial<SongTimelineData> = {}, fetchYear = vi.fn().mockResolvedValue(detail1979)) {
  const onAsk = vi.fn();
  const view = render(
    <PlayerProvider>
      <SongTimeline data={{ ...data, ...overrides }} onAsk={onAsk} fetchYear={fetchYear} />
      <Queue />
    </PlayerProvider>
  );
  return { ...view, onAsk, fetchYear };
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

test("played years are buttons; a year it was not played is not", () => {
  setup();
  expect(screen.getByRole("button", { name: /^1977: 2 performances/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^1979: 1 performance ·/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^1978/ })).not.toBeInTheDocument();
});

test("the model's open year opens first with its facts and pick", () => {
  setup();
  const panel = screen.getByRole("region", { name: "1979" });
  expect(within(panel).getByText("1 performance · typically 12:15 · usually followed by Playing In The Band (1 of 1)")).toBeInTheDocument();
  expect(within(panel).getByText("Stop 3 · Charlie Miller's pick")).toBeInTheDocument();
  expect(within(panel).getByText("From your first question.")).toBeInTheDocument();
});

test("choosing a year opens it, and arrows skip the years it was not played", async () => {
  const user = userEvent.setup();
  setup({ open_year: null });
  await user.click(screen.getByRole("button", { name: /^1979:/ }));
  expect(screen.getByRole("region", { name: "1979" })).toBeInTheDocument();
  screen.getByRole("button", { name: /^1977:/ }).focus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("region", { name: "1977" })).toBeInTheDocument();
  expect(screen.getByText("Stop 1 · The debut")).toBeInTheDocument();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("region", { name: "1979" })).toBeInTheDocument();
});

test("a year without a stop shows the library's pick and why", async () => {
  const user = userEvent.setup();
  setup({ stops: [] });
  expect(screen.getByText("Show picked by Charlie Miller")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /^1977:/ }));
  expect(screen.getByText("On Dave's Picks, Volume 29")).toBeInTheDocument();
});

test("the Length view draws one dot per performance with a length", async () => {
  const user = userEvent.setup();
  const { container } = setup();
  expect(container.querySelectorAll(".st-dot")).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Length" }));
  expect(container.querySelectorAll(".st-dot")).toHaveLength(3);
  expect(screen.getByRole("button", { name: "Length" })).toHaveAttribute("aria-pressed", "true");
});

test("See all loads a year once and lists its performances", async () => {
  const user = userEvent.setup();
  const { fetchYear } = setup();
  await user.click(screen.getByRole("button", { name: "See all 1 from 1979" }));
  expect(await screen.findByText("Terrapin Station › Playing In The Band")).toBeInTheDocument();
  expect(screen.getByText(/New York, NY · Stop 3 · Show picked by Charlie Miller/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Hide the 1979 list" }));
  await user.click(screen.getByRole("button", { name: "See all 1 from 1979" }));
  expect(fetchYear).toHaveBeenCalledTimes(1);
  expect(fetchYear).toHaveBeenCalledWith("song-terrapin-station", 1979);
});

test("a failed year lookup says so and can try again", async () => {
  const user = userEvent.setup();
  const fetchYear = vi.fn().mockRejectedValueOnce(new Error("The 1979 list could not load (503).")).mockResolvedValue(detail1979);
  setup({}, fetchYear);
  await user.click(screen.getByRole("button", { name: "See all 1 from 1979" }));
  expect(await screen.findByText(/could not load \(503\)/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Terrapin Station › Playing In The Band")).toBeInTheDocument();
});

test("Play the path queues the stops that have tapes, in order", async () => {
  const user = userEvent.setup();
  setup();
  await user.click(screen.getByRole("button", { name: /Play the path/ }));
  expect(screen.getByTestId("queue")).toHaveTextContent("p-debut > p-msg");
});

test("asking sends the year's question with the year as focus", async () => {
  const user = userEvent.setup();
  const { onAsk } = setup();
  await user.click(screen.getByRole("button", { name: /How did the 1979 Terrapins differ from 1977\?/ }));
  expect(onAsk).toHaveBeenCalledWith("How did the 1979 Terrapins differ from 1977?", {
    label: "Terrapin Station in 1979",
    song_id: "song-terrapin-station",
    year: 1979,
    ids: ["song-terrapin-station", "p-msg"],
    facts: ["1 performance · typically 12:15 · usually followed by Playing In The Band (1 of 1)"]
  });
});

test("a stop the library could not resolve keeps the model's words without a Play", () => {
  setup();
  expect(screen.getByText("A lost night")).toBeInTheDocument();
  expect(screen.getByText("Not in the library.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /A lost night/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play stop 1, The debut" })).toBeInTheDocument();
});

test("a song with no dated performances says so", () => {
  setup({ year_summaries: [], length_points: [], stops: [] });
  expect(screen.getByText("No dated performances of Terrapin Station are in the library.")).toBeInTheDocument();
});

test("a dot plays its performance once its year has loaded", async () => {
  const user = userEvent.setup();
  const { container } = setup();
  await user.click(screen.getByRole("button", { name: "Length" }));
  const msgDot = [...container.querySelectorAll(".st-dot")][2];
  await user.click(msgDot.querySelector(".st-dot-hit")!);
  await waitFor(() => expect(screen.getByTestId("queue")).toHaveTextContent("p-msg"));
});

test("a year with a stop asks about the stop, not the library's pick", async () => {
  const user = userEvent.setup();
  const { onAsk } = setup();
  await user.click(screen.getByRole("button", { name: /^1977:/ }));
  await user.click(screen.getByRole("button", { name: /Tell me about Terrapin Station in 1977/ }));
  expect(onAsk.mock.calls[0][1].ids).toEqual(["song-terrapin-station", "p-debut"]);
});

test("a slow lookup for an earlier dot does not replace a later choice", async () => {
  const user = userEvent.setup();
  let finish1977: (detail: SongYearDetail) => void = () => undefined;
  const fetchYear = vi.fn((_song: string, year: number) =>
    year === 1977 ? new Promise<SongYearDetail>((resolve) => (finish1977 = resolve)) : Promise.resolve(detail1979)
  );
  const { container } = setup({}, fetchYear);
  await user.click(screen.getByRole("button", { name: "Length" }));
  const dots = [...container.querySelectorAll(".st-dot-hit")];
  await user.click(dots[1]);
  await user.click(dots[2]);
  await waitFor(() => expect(screen.getByTestId("queue")).toHaveTextContent("p-msg"));
  finish1977({ ...detail1979, year: 1977, performances: [{ ...detail1979.performances[0], performance_id: "p-hartford", show_date: "1977-05-28", track: track("p-hartford") }] });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.getByTestId("queue")).toHaveTextContent("p-msg");
  expect(screen.getByTestId("queue")).not.toHaveTextContent("p-hartford");
});
```

- [x] **Step 2: Run them to see them fail**

Run: `cd web && npx vitest run src/SongTimeline.test.tsx`
Expected: FAIL, cannot resolve `./SongTimeline`

- [x] **Step 3: Write the component** (`web/src/SongTimeline.tsx`)

```tsx
// A song's life on stage as one explorable timeline: plays or lengths per
// year, the model's stops as gold pins and a listening path, and a panel for
// any year with three ways in. Play it (gold) and See all (rose) are library
// facts served without the model; Ask (blue) starts a new turn with the year
// attached. Every fact comes from the card's data; the stops, their words, the
// open year and the first view are the model's.
import { useCallback, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode, type RefObject } from "react";
import { toTrack } from "./listen-control";
import { usePlayer, type PlayerTrack } from "./player";
import { clock } from "./VersionStrip";
import { MARGIN, bandX, countTicks, frame, lengthTicks, pinRows, pinY, pointX, yFor, yearLabelStep, type Frame } from "./song-timeline-geometry";
import {
  askQuestion,
  flowLine,
  focusFor,
  initialYear,
  longDate,
  monthDay,
  performanceTags,
  pickEyebrow,
  plural,
  shortDate,
  yearFacts
} from "./song-timeline-text";
import type { ChartView, LengthPoint, SongTimelineData, SongYearDetail, TimelineFocus, TimelineStop, TimelineTrack, YearSummary } from "./song-timeline-types";
import { fetchSongYear, type FetchYear } from "./song-year";
import "./SongTimeline.css";

type Props = {
  data: SongTimelineData;
  onAsk: (question: string, focus: TimelineFocus) => void;
  fetchYear?: FetchYear;
};

type YearState = { status: "loading" } | { status: "ready"; detail: SongYearDetail } | { status: "error"; message: string };

// A stop the library resolved: it has a date, so it can sit on the chart.
type PlacedStop = TimelineStop & { show_date: string; number: number };

const VIEW_CAPTION: Record<ChartView, string> = {
  count: "Each bar is a year. Gold marks are the stops below. Choose a year to open it.",
  length: "Each dot is one performance, by minutes; the pale line is that year's typical length. Choose a dot to play it."
};

function asPlayerTrack(track: TimelineTrack, showDate?: string | null, venueName?: string | null): PlayerTrack {
  return toTrack(track, { showDate: showDate ?? null, venueName: venueName ?? null });
}

function useWidth(ref: RefObject<HTMLDivElement | null>): number {
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

function PlayIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true">
      <path d="M3.5 1.5v11l9-5.5z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true">
      <path d="M3 1.5h3v11H3zM8 1.5h3v11H8z" fill="currentColor" />
    </svg>
  );
}

export function SongTimeline({ data, onAsk, fetchYear = fetchSongYear }: Props) {
  const player = usePlayer();
  const wrapRef = useRef<HTMLDivElement>(null);
  const width = useWidth(wrapRef);
  const [view, setView] = useState<ChartView>(data.chart_view ?? "count");
  const [year, setYear] = useState<number | null>(() => initialYear(data));
  const [listOpen, setListOpen] = useState(false);
  const [years, setYears] = useState<Record<number, YearState>>({});
  // The latest dot the visitor chose; a slower lookup for an earlier dot is ignored.
  const latestPoint = useRef<string | null>(null);

  const summaries = useMemo(() => new Map(data.year_summaries.map((summary) => [summary.year, summary])), [data]);
  const playedYears = useMemo(() => data.year_summaries.filter((summary) => summary.count > 0).map((summary) => summary.year), [data]);
  const stops = useMemo(
    () =>
      data.stops.flatMap((stop, index): PlacedStop[] =>
        stop.show_date ? [{ ...stop, show_date: stop.show_date, number: index + 1 }] : []
      ),
    [data]
  );
  const stopNumbers = useMemo(() => new Map(data.stops.map((stop, index) => [stop.performance_id, index + 1])), [data]);
  const pathQueue = useMemo(
    () => stops.flatMap((stop) => (stop.track ? [asPlayerTrack(stop.track, stop.show_date, stop.venue_name)] : [])),
    [stops]
  );

  const currentId = player.currentTrack?.id ?? null;
  const playingId = player.status === "playing" || player.status === "loading" ? currentId : null;

  const play = useCallback(
    (track: PlayerTrack, queue?: PlayerTrack[]) => {
      if (currentId === track.id) player.toggle();
      else player.play(track, queue);
    },
    [currentId, player]
  );

  const loadYear = useCallback(
    (target: number): Promise<SongYearDetail | null> => {
      const known = years[target];
      if (known?.status === "ready") return Promise.resolve(known.detail);
      setYears((current) => ({ ...current, [target]: { status: "loading" } }));
      return fetchYear(data.song_id, target).then(
        (detail) => {
          setYears((current) => ({ ...current, [target]: { status: "ready", detail } }));
          return detail;
        },
        (error: unknown) => {
          const message = error instanceof Error ? error.message : `The ${target} list could not load.`;
          setYears((current) => ({ ...current, [target]: { status: "error", message } }));
          return null;
        }
      );
    },
    [data.song_id, fetchYear, years]
  );

  const selectYear = useCallback(
    (target: number) => {
      if (target !== year) setListOpen(false);
      setYear(target);
    },
    [year]
  );

  const playPoint = useCallback(
    (point: LengthPoint) => {
      const target = Number(point.show_date.slice(0, 4));
      latestPoint.current = point.performance_id;
      selectYear(target);
      void loadYear(target).then((detail) => {
        if (latestPoint.current !== point.performance_id) return;
        const performance = detail?.performances.find((item) => item.performance_id === point.performance_id);
        if (performance?.track) play(asPlayerTrack(performance.track, performance.show_date, performance.venue_name));
      });
    },
    [loadYear, play, selectYear]
  );

  const playStop = useCallback(
    (stop: PlacedStop) => {
      selectYear(Number(stop.show_date.slice(0, 4)));
      if (!stop.track) return;
      play(asPlayerTrack(stop.track, stop.show_date, stop.venue_name), pathQueue);
    },
    [pathQueue, play, selectYear]
  );

  if (playedYears.length === 0) {
    return <p className="st-empty-note">No dated performances of {data.title} are in the library.</p>;
  }

  const summary = year != null ? summaries.get(year) : undefined;
  const allYears = data.year_summaries.map((item) => item.year);
  // Pins sit in rows above the plot, except Length-view pins that sit on their own dot.
  const inRows = (stop: PlacedStop) => !(view === "length" && stop.seconds != null);
  const base = width > 0 ? frame(width, allYears, view) : null;
  const rows = base ? pinRows(stops.map((stop) => (inRows(stop) ? pointX(base, stop.show_date) : -1e9))) : [];
  const rowCount = 1 + Math.max(0, ...rows.filter((_row, index) => inRows(stops[index])));
  const f = width > 0 ? frame(width, allYears, view, rowCount) : null;

  return (
    <div className="song-timeline">
      <div className="st-view-bar">
        <div className="st-views" role="group" aria-label="Chart view">
          {(["count", "length"] as ChartView[]).map((option) => (
            <button key={option} type="button" className="st-view" aria-pressed={view === option} onClick={() => setView(option)}>
              {option === "count" ? "Times played" : "Length"}
            </button>
          ))}
        </div>
      </div>
      <p className="st-caption">{VIEW_CAPTION[view]}</p>
      <div className="st-chart" ref={wrapRef}>
        {f && (
          <TimelineChart
            data={data}
            f={f}
            view={view}
            selectedYear={year}
            playedYears={playedYears}
            stops={stops}
            rows={rows}
            playingId={playingId}
            onSelectYear={selectYear}
            onPlayStop={playStop}
            onPlayPoint={playPoint}
          />
        )}
      </div>
      <YearTable data={data} />
      {summary && summary.count > 0 && f && (
        <YearPanel
          data={data}
          summary={summary}
          caretX={bandX(f, summary.year) + f.bandWidth / 2}
          stop={stops.find((stop) => stop.show_date.startsWith(String(summary.year))) ?? null}
          stopNumbers={stopNumbers}
          playedYears={playedYears}
          listOpen={listOpen}
          yearState={years[summary.year]}
          playingId={playingId}
          pathQueue={pathQueue}
          onSelectYear={selectYear}
          onToggleList={() => {
            const opening = !listOpen;
            setListOpen(opening);
            if (opening) void loadYear(summary.year);
          }}
          onRetry={() => void loadYear(summary.year)}
          onPlay={play}
          onAsk={onAsk}
        />
      )}
      {data.stops.length > 0 && (
        <StopPath data={data} stops={stops} pathQueue={pathQueue} playingId={playingId} onPlayStop={playStop} onPlayPath={() => pathQueue[0] && player.play(pathQueue[0], pathQueue)} />
      )}
    </div>
  );
}

function TimelineChart({
  data,
  f,
  view,
  selectedYear,
  playedYears,
  stops,
  rows,
  playingId,
  onSelectYear,
  onPlayStop,
  onPlayPoint
}: {
  data: SongTimelineData;
  f: Frame;
  view: ChartView;
  selectedYear: number | null;
  playedYears: number[];
  stops: PlacedStop[];
  rows: number[];
  playingId: string | null;
  onSelectYear: (year: number) => void;
  onPlayStop: (stop: PlacedStop) => void;
  onPlayPoint: (point: LengthPoint) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const ticks =
    view === "count"
      ? countTicks(Math.max(1, ...data.year_summaries.map((item) => item.count)))
      : lengthTicks(Math.max(300, ...data.length_points.map((point) => point.seconds)));
  const top = ticks[ticks.length - 1];
  const step = yearLabelStep(f.bandWidth);
  const stopIds = new Set(stops.map((stop) => stop.performance_id));

  const tipAt = (event: MouseEvent, content: ReactNode) => {
    const box = svgRef.current?.getBoundingClientRect();
    setTip({ x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0), content });
  };

  const moveTo = (from: number, direction: 1 | -1) => {
    const index = playedYears.indexOf(from);
    const target = playedYears[index + direction];
    if (target === undefined) return;
    onSelectYear(target);
    requestAnimationFrame(() => svgRef.current?.querySelector<SVGGElement>(`[data-year="${target}"]`)?.focus());
  };

  const bandTip = (summary: YearSummary): ReactNode => {
    const stop = stops.find((item) => item.show_date.startsWith(String(summary.year)));
    const chosen = stop ? { venue: stop.venue_name, date: stop.show_date } : summary.pick ? { venue: summary.pick.venue_name, date: summary.pick.show_date } : null;
    return view === "count" ? (
      <>
        <strong>
          {plural(summary.count, "performance")} in {summary.year}
        </strong>
        {chosen && (
          <span className="st-tip-gold">
            ▸ {chosen.venue}, {monthDay(chosen.date)}
          </span>
        )}
        <span className="st-tip-hint">Choose to open {summary.year}</span>
      </>
    ) : (
      <>
        <strong>{summary.year}</strong>
        <span>Typically {clock(summary.median_seconds)}</span>
        {summary.longest && <span>Longest {clock(summary.longest.seconds)}</span>}
        <span className="st-tip-hint">Choose to open {summary.year}</span>
      </>
    );
  };

  return (
    <>
      <svg ref={svgRef} className="st-svg" width={f.width} height={f.height} viewBox={`0 0 ${f.width} ${f.height}`} role="group" aria-label={`${data.title} by year`}>
        <g aria-hidden="true">
          {ticks.map((value) => (
            <g key={value}>
              <line x1={MARGIN.left} x2={f.width - MARGIN.right} y1={yFor(f, value, top)} y2={yFor(f, value, top)} className="st-grid" />
              <text x={MARGIN.left - 8} y={yFor(f, value, top) + 4} textAnchor="end" className="st-axis">
                {view === "count" ? value : `${value / 60}m`}
              </text>
            </g>
          ))}
          {data.year_summaries.map((summary, index) =>
            index % step === 0 ? (
              <text
                key={summary.year}
                x={bandX(f, summary.year) + f.bandWidth / 2}
                y={f.height - 6}
                textAnchor="middle"
                className={summary.year === selectedYear ? "st-axis st-axis-selected" : "st-axis"}
              >
                {summary.year}
              </text>
            ) : null
          )}
        </g>
        {data.year_summaries.map((summary) => {
          const x = bandX(f, summary.year);
          const center = x + f.bandWidth / 2;
          const selected = summary.year === selectedYear;
          if (summary.count === 0) return <g key={summary.year} className="st-band st-band-empty" aria-hidden="true" />;
          return (
            <g
              key={summary.year}
              className={selected ? "st-band st-band-selected" : "st-band"}
              data-year={summary.year}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${summary.year}: ${yearFacts(summary)}. Open the year.`}
              onClick={() => onSelectYear(summary.year)}
              onKeyDown={(event: KeyboardEvent) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectYear(summary.year);
                } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                  event.preventDefault();
                  moveTo(summary.year, event.key === "ArrowRight" ? 1 : -1);
                }
              }}
              onMouseMove={(event) => tipAt(event, bandTip(summary))}
              onMouseLeave={() => setTip(null)}
              onFocus={() => setTip({ x: center, y: f.plotTop, content: bandTip(summary) })}
              onBlur={() => setTip(null)}
            >
              <rect className="st-band-bg" x={x + 1} y={f.plotTop - 6} width={Math.max(0, f.bandWidth - 2)} height={f.plotBottom - f.plotTop + 6} rx={2} />
              {view === "count" ? (
                <rect
                  className="st-bar"
                  x={center - f.barWidth / 2}
                  y={yFor(f, summary.count, top)}
                  width={f.barWidth}
                  height={f.plotBottom - yFor(f, summary.count, top)}
                  rx={2}
                />
              ) : (
                summary.median_seconds != null && (
                  <line
                    className="st-median"
                    x1={x + f.bandWidth * 0.12}
                    x2={x + f.bandWidth * 0.88}
                    y1={yFor(f, summary.median_seconds, top)}
                    y2={yFor(f, summary.median_seconds, top)}
                  />
                )
              )}
            </g>
          );
        })}
        {view === "length" && (
          <g aria-hidden="true">
            {data.length_points.map((point) => {
              const x = pointX(f, point.show_date);
              const y = yFor(f, point.seconds, top);
              const inYear = point.show_date.startsWith(String(selectedYear));
              return (
                <g
                  key={point.performance_id}
                  className="st-dot"
                  onClick={(event) => {
                    event.stopPropagation();
                    onPlayPoint(point);
                  }}
                  onMouseMove={(event) =>
                    tipAt(
                      event,
                      <>
                        <strong>{longDate(point.show_date)}</strong>
                        <span>{clock(point.seconds)}</span>
                        <span className="st-tip-hint">Choose to play</span>
                      </>
                    )
                  }
                  onMouseLeave={() => setTip(null)}
                >
                  <circle cx={x} cy={y} r={7} className="st-dot-hit" />
                  {!stopIds.has(point.performance_id) && <circle cx={x} cy={y} r={2.6} className={inYear ? "st-dot-mark st-dot-in-year" : "st-dot-mark"} />}
                </g>
              );
            })}
          </g>
        )}
        {stops.map((stop, index) => {
          const x = pointX(f, stop.show_date);
          const onChart = view === "length" && stop.seconds != null;
          const y = onChart ? yFor(f, stop.seconds!, top) : pinY(f, rows[index]);
          const stopYear = data.year_summaries.find((item) => stop.show_date.startsWith(String(item.year)));
          const active = playingId === stop.performance_id;
          return (
            <g
              key={stop.performance_id}
              className={active ? "st-pin st-pin-active" : "st-pin"}
              role="button"
              tabIndex={0}
              aria-label={`Play stop ${stop.number}${stop.label ? `, ${stop.label}` : ""}, ${longDate(stop.show_date)}`}
              onClick={() => onPlayStop(stop)}
              onKeyDown={(event: KeyboardEvent) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onPlayStop(stop);
                }
              }}
              onMouseMove={(event) =>
                tipAt(
                  event,
                  <>
                    <span className="st-tip-gold">
                      Stop {stop.number}
                      {stop.label ? ` · ${stop.label}` : ""}
                    </span>
                    <strong>{stop.venue_name}</strong>
                    <span>
                      {longDate(stop.show_date)} · {clock(stop.seconds)}
                    </span>
                  </>
                )
              }
              onMouseLeave={() => setTip(null)}
            >
              {!onChart && view === "count" && stopYear && (
                <line className="st-pin-stem" x1={x} x2={x} y1={y + 8} y2={yFor(f, stopYear.count, top) - 1} />
              )}
              <circle cx={x} cy={y} r={8.5} className="st-pin-dot" />
              <text x={x} y={y + 3.5} textAnchor="middle" className="st-pin-number">
                {stop.number}
              </text>
            </g>
          );
        })}
      </svg>
      {tip && (
        <div className="st-tip" role="tooltip" style={{ left: Math.min(Math.max(0, tip.x + 14), f.width - 200), top: Math.max(0, tip.y - 70) }}>
          {tip.content}
        </div>
      )}
    </>
  );
}

// The full-data alternative to the drawing: every year, its count and typical length.
function YearTable({ data }: { data: SongTimelineData }) {
  return (
    <table className="visually-hidden">
      <caption>{data.title} by year, full data table</caption>
      <thead>
        <tr>
          <th scope="col">Year</th>
          <th scope="col">Performances</th>
          <th scope="col">Typical length</th>
        </tr>
      </thead>
      <tbody>
        {data.year_summaries.map((summary) => (
          <tr key={summary.year}>
            <td>{summary.year}</td>
            <td>{summary.count}</td>
            <td>{summary.median_seconds != null ? clock(summary.median_seconds) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function YearPanel({
  data,
  summary,
  caretX,
  stop,
  stopNumbers,
  playedYears,
  listOpen,
  yearState,
  playingId,
  pathQueue,
  onSelectYear,
  onToggleList,
  onRetry,
  onPlay,
  onAsk
}: {
  data: SongTimelineData;
  summary: YearSummary;
  caretX: number;
  stop: PlacedStop | null;
  stopNumbers: Map<string, number>;
  playedYears: number[];
  listOpen: boolean;
  yearState: YearState | undefined;
  playingId: string | null;
  pathQueue: PlayerTrack[];
  onSelectYear: (year: number) => void;
  onToggleList: () => void;
  onRetry: () => void;
  onPlay: (track: PlayerTrack, queue?: PlayerTrack[]) => void;
  onAsk: (question: string, focus: TimelineFocus) => void;
}) {
  const index = playedYears.indexOf(summary.year);
  const previous = playedYears[index - 1];
  const next = playedYears[index + 1];
  const pick = summary.pick;
  // The year's pick: the model's stop when it named one, else the library's.
  const chosen = stop
    ? { id: stop.performance_id, venue: stop.venue_name, date: stop.show_date, setLabel: null, seconds: stop.seconds ?? null, track: stop.track ?? null, why: stop.why }
    : pick
      ? { id: pick.performance_id, venue: pick.venue_name, date: pick.show_date, setLabel: pick.set_label, seconds: pick.seconds, track: pick.track, why: null }
      : null;
  const eyebrow = stop ? `Stop ${stop.number}${stop.label ? ` · ${stop.label}` : ""}` : pick ? pickEyebrow(pick, null) : "";
  const question = askQuestion(data, summary.year);
  const playingChosen = chosen != null && playingId === chosen.id;

  return (
    <section className="st-year" aria-label={String(summary.year)} style={{ ["--st-caret" as string]: `${caretX}px` }}>
      <div className="st-year-head">
        <h4 className="st-year-number">{summary.year}</h4>
        <p className="st-year-facts">{yearFacts(summary)}</p>
        <div className="st-year-step">
          <button type="button" disabled={previous === undefined} onClick={() => previous !== undefined && onSelectYear(previous)} aria-label="Previous year">
            ← {previous ?? ""}
          </button>
          <button type="button" disabled={next === undefined} onClick={() => next !== undefined && onSelectYear(next)} aria-label="Next year">
            {next ?? ""} →
          </button>
        </div>
      </div>
      {chosen && (
        <div className="st-pick">
          <button
            type="button"
            className="st-play-big"
            disabled={!chosen.track}
            aria-label={`${playingChosen ? "Pause" : "Play"} ${data.title}, ${chosen.venue ?? ""}, ${longDate(chosen.date)}`}
            onClick={() => chosen.track && onPlay(asPlayerTrack(chosen.track, chosen.date, chosen.venue), stop ? pathQueue : undefined)}
          >
            {playingChosen ? <PauseIcon size={16} /> : <PlayIcon size={16} />}
          </button>
          <div className="st-pick-body">
            <span className="st-eyebrow-gold">{eyebrow}</span>
            <span className="st-pick-title">{chosen.venue}</span>
            <span className="st-pick-meta">
              {[longDate(chosen.date), chosen.setLabel, chosen.seconds != null ? clock(chosen.seconds) : null].filter(Boolean).join(" · ")}
            </span>
            {chosen.why && <p className="st-pick-why">{chosen.why}</p>}
          </div>
        </div>
      )}
      <div className="st-actions">
        <button type="button" className="st-see-all" aria-expanded={listOpen} onClick={onToggleList}>
          {listOpen ? `Hide the ${summary.year} list` : `See all ${summary.count} from ${summary.year}`}
        </button>
        <button type="button" className="st-ask" onClick={() => onAsk(question, focusFor(data, summary, chosen?.id ?? null))}>
          <span className="st-ask-mark" aria-hidden="true">
            ?
          </span>
          {question}
        </button>
      </div>
      {listOpen && <YearList data={data} yearState={yearState} chosenId={chosen?.id ?? null} stopNumbers={stopNumbers} playingId={playingId} onRetry={onRetry} onPlay={onPlay} year={summary.year} />}
    </section>
  );
}

function YearList({
  data,
  year,
  yearState,
  chosenId,
  stopNumbers,
  playingId,
  onRetry,
  onPlay
}: {
  data: SongTimelineData;
  year: number;
  yearState: YearState | undefined;
  chosenId: string | null;
  stopNumbers: Map<string, number>;
  playingId: string | null;
  onRetry: () => void;
  onPlay: (track: PlayerTrack, queue?: PlayerTrack[]) => void;
}) {
  if (!yearState || yearState.status === "loading") return <p className="st-list-note">Loading the {year} list…</p>;
  if (yearState.status === "error")
    return (
      <p className="st-list-note">
        {yearState.message}{" "}
        <button type="button" className="st-see-all" onClick={onRetry}>
          Try again
        </button>
      </p>
    );
  const performances = yearState.detail.performances;
  const queue = performances.flatMap((item) => (item.track ? [asPlayerTrack(item.track, item.show_date, item.venue_name)] : []));
  return (
    <ol className="st-list">
      {performances.map((performance) => {
        const tags = performanceTags(performance, stopNumbers.get(performance.performance_id) ?? null);
        const playing = playingId === performance.performance_id;
        return (
          <li key={performance.performance_id} className={performance.performance_id === chosenId ? "st-row st-row-chosen" : "st-row"}>
            <button
              type="button"
              className="st-play-small"
              disabled={!performance.track}
              aria-label={performance.track ? `${playing ? "Pause" : "Play"} ${performance.venue_name ?? ""}, ${longDate(performance.show_date)}` : `No tape for ${longDate(performance.show_date)}`}
              onClick={() => performance.track && onPlay(asPlayerTrack(performance.track, performance.show_date, performance.venue_name), queue)}
            >
              {playing ? <PauseIcon size={10} /> : <PlayIcon size={10} />}
            </button>
            <span className="st-row-date">{monthDay(performance.show_date)}</span>
            <span className="st-row-venue">
              {performance.venue_name}
              <small>
                {[performance.city, ...tags].filter(Boolean).join(" · ")}
              </small>
            </span>
            <span className="st-row-flow">{flowLine(performance, data.title)}</span>
            <span className="st-row-length">{clock(performance.seconds)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function StopPath({
  data,
  stops,
  pathQueue,
  playingId,
  onPlayStop,
  onPlayPath
}: {
  data: SongTimelineData;
  stops: PlacedStop[];
  pathQueue: PlayerTrack[];
  playingId: string | null;
  onPlayStop: (stop: PlacedStop) => void;
  onPlayPath: () => void;
}) {
  const placed = new Map(stops.map((stop) => [stop.performance_id, stop]));
  const total = stops.reduce((sum, stop) => sum + (stop.seconds ?? 0), 0);
  const minutes = Math.round(total / 60);
  const length = minutes >= 60 ? `${Math.floor(minutes / 60)} hr ${minutes % 60} min` : `${minutes} min`;
  return (
    <section className="st-path" aria-label="Listening path">
      <div className="st-path-head">
        <div>
          <h4>Hear its life in {plural(data.stops.length, "stop")}</h4>
          {total > 0 && <p>{length} of listening</p>}
        </div>
        {pathQueue.length > 0 && (
          <button type="button" className="st-play-path" onClick={onPlayPath}>
            <PlayIcon size={14} />
            Play the path
          </button>
        )}
      </div>
      <ol className="st-stops">
        {data.stops.map((stop, index) => {
          const place = placed.get(stop.performance_id);
          const body = (
            <>
              <span className="st-stop-number" aria-hidden="true">
                {index + 1}
              </span>
              <span className="st-stop-text">
                {stop.label && <span className="st-stop-label">{stop.label}</span>}
                {place && (
                  <span className="st-stop-meta">
                    {[place.venue_name, shortDate(place.show_date), place.seconds != null ? clock(place.seconds) : null].filter(Boolean).join(" · ")}
                  </span>
                )}
                {stop.why && <span className="st-stop-why">{stop.why}</span>}
              </span>
            </>
          );
          return (
            <li key={`${stop.performance_id}-${index}`}>
              {place && place.track ? (
                <button
                  type="button"
                  className={playingId === stop.performance_id ? "st-stop st-stop-playing" : "st-stop"}
                  aria-label={`Play stop ${index + 1}${stop.label ? `, ${stop.label}` : ""}`}
                  onClick={() => onPlayStop(place)}
                >
                  {body}
                </button>
              ) : (
                <div className="st-stop st-stop-text-only">{body}</div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
```

- [x] **Step 4: Write the styles** (`web/src/SongTimeline.css`)

```css
/* The song timeline. Gold hears, rose reads, blue asks; 2px corners; the
   app's tokens from styles.css. */
.song-timeline { display: flex; flex-direction: column; gap: var(--space-part, 1rem); }
.st-empty-note { margin: 0; color: var(--muted); }

.st-view-bar { display: flex; justify-content: space-between; align-items: end; gap: 1rem; flex-wrap: wrap; border-bottom: 1px solid var(--hair); }
.st-views { display: flex; gap: 1.5rem; }
.st-view { background: none; border: 0; padding: 0.4rem 0 0.65rem; margin-bottom: -1px; color: var(--muted); font-size: 0.92rem; border-bottom: 2px solid transparent; }
.st-view:hover { color: var(--cream); }
.st-view[aria-pressed="true"] { color: var(--cream); border-bottom-color: var(--cream); }
.st-caption { margin: 0; color: var(--muted); font-size: 0.85rem; }

.st-chart { position: relative; min-height: 230px; }
.st-svg { display: block; max-width: 100%; overflow: visible; }
.st-grid { stroke: var(--hair); }
.st-axis { fill: var(--quiet); font-size: 11px; font-variant-numeric: tabular-nums; }
.st-axis-selected { fill: var(--cream); font-weight: 600; }
.st-band { cursor: pointer; outline: none; }
.st-band-bg { fill: transparent; }
.st-band-selected .st-band-bg { fill: rgba(243, 240, 226, 0.06); }
.st-band:focus-visible .st-band-bg { stroke: var(--focus); stroke-width: 1.5; }
.st-bar { fill: var(--muted); }
.st-band:hover .st-bar { fill: var(--text); }
.st-band-selected .st-bar { fill: var(--cream); }
.st-median { stroke: rgba(243, 240, 226, 0.55); stroke-width: 2; }
.st-band-selected .st-median { stroke: var(--cream); }
.st-dot { cursor: pointer; }
.st-dot-hit { fill: transparent; }
.st-dot-mark { fill: var(--muted); opacity: 0.6; }
.st-dot-in-year { fill: var(--cream); opacity: 0.95; }
.st-dot:hover .st-dot-mark { fill: var(--listen); opacity: 1; }
.st-pin { cursor: pointer; outline: none; }
.st-pin-stem { stroke: var(--listen); stroke-opacity: 0.45; stroke-dasharray: 2 2; }
.st-pin-dot { fill: var(--ground); stroke: var(--listen); stroke-width: 1.5; }
.st-pin-number { fill: var(--listen); font-size: 10px; font-weight: 700; }
.st-pin:hover .st-pin-dot, .st-pin-active .st-pin-dot { fill: var(--listen); }
.st-pin:hover .st-pin-number, .st-pin-active .st-pin-number { fill: var(--listen-ink); }
.st-pin:focus-visible .st-pin-dot { stroke: var(--focus); stroke-width: 2; }

.st-tip { position: absolute; z-index: 5; pointer-events: none; display: flex; flex-direction: column; gap: 0.1rem; min-width: 10rem; max-width: 16rem; padding: 0.5rem 0.7rem; background: var(--bar-scrim); border: 1px solid var(--hair); border-radius: var(--r); color: var(--text); font-size: 0.8rem; line-height: 1.4; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
.st-tip strong { color: var(--cream); font-size: 0.92rem; }
.st-tip-gold { color: var(--listen); }
.st-tip-hint { color: var(--quiet); font-size: 0.72rem; margin-top: 0.2rem; }

.st-year { position: relative; display: flex; flex-direction: column; gap: 1rem; padding: 1.25rem 1.25rem 1rem; border: 1px solid var(--hair); border-radius: var(--r); background: var(--panel); }
.st-year::before { content: ""; position: absolute; top: -7px; left: var(--st-caret, 50%); width: 12px; height: 12px; background: var(--ground); border-left: 1px solid var(--hair); border-top: 1px solid var(--hair); transform: translateX(-50%) rotate(45deg); }
.st-year-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.5rem 1rem; }
.st-year-number { margin: 0; font-family: var(--serif); font-variation-settings: "SOFT" 40; font-size: 1.9rem; font-weight: 600; line-height: 1; color: var(--cream); font-variant-numeric: tabular-nums; }
.st-year-facts { flex: 1 1 18rem; margin: 0; color: var(--muted); font-size: 0.88rem; }
.st-year-step { display: flex; gap: 0.25rem; }
.st-year-step button { background: none; border: 1px solid var(--hair); border-radius: var(--r); color: var(--muted); padding: 0.2rem 0.55rem; font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.st-year-step button:hover:not(:disabled) { color: var(--cream); }
.st-year-step button:disabled { opacity: 0.35; cursor: default; }

.st-pick { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.9rem; align-items: start; }
.st-play-big { display: grid; place-items: center; width: 44px; height: 44px; border: 0; border-radius: 50%; background: var(--listen); color: var(--listen-ink); transition: transform 160ms var(--ease-out); }
.st-play-big:hover:not(:disabled) { transform: scale(1.05); }
.st-play-big:active:not(:disabled) { transform: scale(0.96); }
.st-play-big:disabled { background: var(--hair); color: var(--quiet); cursor: default; }
.st-pick-body { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
.st-eyebrow-gold { color: var(--listen); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; }
.st-pick-title { color: var(--cream); font-weight: 600; font-size: 1.05rem; }
.st-pick-meta { color: var(--muted); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
.st-pick-why { margin: 0.35rem 0 0; max-width: 60ch; color: var(--text); font-size: 0.92rem; }

.st-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem 1.25rem; }
.st-see-all { background: none; border: 0; padding: 0; color: var(--read); font-size: 0.9rem; text-decoration: underline; text-underline-offset: 0.2em; text-decoration-color: rgba(232, 119, 154, 0.45); }
.st-see-all:hover { text-decoration-color: var(--read); }
.st-ask { display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.35rem 0.75rem; background: none; border: 1px solid rgba(63, 149, 220, 0.55); border-radius: var(--r); color: #8fc3ee; font-size: 0.86rem; text-align: left; }
.st-ask:hover { border-color: var(--ask); color: #b9dbf6; background: rgba(63, 149, 220, 0.08); }
.st-ask-mark { color: var(--ask); font-weight: 700; }

.st-list-note { margin: 0; color: var(--muted); font-size: 0.88rem; }
.st-list { list-style: none; margin: 0; padding: 0; max-height: 26rem; overflow-y: auto; border-top: 1px solid var(--hair); }
.st-row { display: grid; grid-template-columns: 28px 3.8rem minmax(0, 1.2fr) minmax(0, 1.6fr) 3.2rem; gap: 0.75rem; align-items: center; padding: 0.55rem 0; border-bottom: 1px solid var(--hair); font-size: 0.86rem; }
.st-row-chosen { margin-inline: -0.5rem; padding-inline: 0.5rem; background: rgba(231, 185, 78, 0.1); }
.st-row-date { color: var(--cream); font-variant-numeric: tabular-nums; }
.st-row-venue { min-width: 0; color: var(--text); }
.st-row-venue small { display: block; color: var(--quiet); font-size: 0.76rem; }
.st-row-flow { min-width: 0; color: var(--muted); }
.st-row-length { color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }
.st-play-small { display: grid; place-items: center; width: 26px; height: 26px; padding: 0; border: 1px solid var(--listen-soft); border-radius: 50%; background: none; color: var(--listen); }
.st-play-small:hover:not(:disabled) { background: var(--listen); color: var(--listen-ink); }
.st-play-small:disabled { border-color: var(--hair); color: var(--quiet); cursor: default; }

.st-path { display: flex; flex-direction: column; gap: 0.5rem; }
.st-path-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; }
.st-path-head h4 { margin: 0; font-family: var(--serif); font-variation-settings: "SOFT" 40; font-size: 1.3rem; font-weight: 600; color: var(--cream); }
.st-path-head p { margin: 0.1rem 0 0; color: var(--muted); font-size: 0.85rem; }
.st-play-path { display: inline-flex; align-items: center; gap: 0.55rem; padding: 0.5rem 1.1rem 0.5rem 0.8rem; border: 0; border-radius: 999px; background: var(--listen); color: var(--listen-ink); font-weight: 600; font-size: 0.88rem; }
.st-play-path:hover { filter: brightness(1.06); }
.st-stops { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 2rem; }
.st-stop { display: grid; grid-template-columns: 24px minmax(0, 1fr); gap: 0.75rem; align-items: start; width: 100%; padding: 0.75rem 0; background: none; border: 0; border-top: 1px solid var(--hair); color: inherit; text-align: left; font: inherit; }
button.st-stop:hover .st-stop-label, .st-stop-playing .st-stop-label { color: var(--listen); }
.st-stop-number { display: grid; place-items: center; width: 22px; height: 22px; margin-top: 0.1rem; border: 1.5px solid var(--listen); border-radius: 50%; color: var(--listen); font-size: 0.72rem; font-weight: 700; }
.st-stop-playing .st-stop-number { background: var(--listen); color: var(--listen-ink); }
.st-stop-text-only .st-stop-number { border-color: var(--hair); color: var(--quiet); }
.st-stop-text { display: flex; flex-direction: column; min-width: 0; }
.st-stop-label { color: var(--cream); font-weight: 600; font-size: 0.95rem; transition: color 120ms; }
.st-stop-meta { color: var(--muted); font-size: 0.82rem; font-variant-numeric: tabular-nums; }
.st-stop-why { margin-top: 0.2rem; color: var(--text); font-size: 0.85rem; }

@media (max-width: 760px) {
  .st-stops { grid-template-columns: minmax(0, 1fr); }
  .st-row { grid-template-columns: 28px 3.4rem minmax(0, 1fr) 3rem; }
  .st-row-flow { grid-column: 3 / 5; grid-row: 2; font-size: 0.8rem; }
}
@media (prefers-reduced-motion: reduce) {
  .st-play-big, .st-stop-label { transition: none; }
}
```

- [x] **Step 5: Run the component tests, the whole web suite and the type check**

Run: `cd web && npx vitest run && npx tsc -p tsconfig.json --noEmit`
Expected: all test files pass (`14` in `SongTimeline.test.tsx`), no type errors

- [x] **Step 6: Commit**

```bash
git add web/src/SongTimeline.tsx web/src/SongTimeline.css web/src/SongTimeline.test.tsx
git commit -m "Draw a song's life as an explorable timeline: two views, stops, year panel, path"
```

### Task 5: Dev-only preview page

**Files:**
- Create: `web/song-timeline-preview.html`, `web/src/song-timeline-preview.tsx`

**Interfaces:**
- Consumes: `SongTimeline`, the Task 2 fixtures, `PlayerProvider`, `usePlayer`, `formatClockTime`.
- Produces: `http://localhost:<port>/song-timeline-preview.html` under `npm --prefix web run dev`; not in `vite build` output (Vite builds `index.html` only).

- [x] **Step 1: Write the page shell** (`web/song-timeline-preview.html`)

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#16231c" />
    <title>Song timeline preview</title>
    <link rel="preload" href="/fonts/fraunces-latin.woff2" as="font" type="font/woff2" crossorigin />
    <link rel="preload" href="/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/song-timeline-preview.tsx"></script>
  </body>
</html>
```

- [x] **Step 2: Write the preview entry** (`web/src/song-timeline-preview.tsx`)

```tsx
// A dev-only page for the song timeline, served by `npm run dev` at
// /song-timeline-preview.html and left out of the production build. It reads
// the Terrapin fixtures, so it needs no API; Ask is shown on the page instead
// of starting a turn. Phase 2 registers a visual fixture and retires this.
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import card from "./fixtures/song-timeline-terrapin.json";
import years from "./fixtures/song-timeline-terrapin-years.json";
import { PlayerProvider, formatClockTime, usePlayer } from "./player";
import { SongTimeline } from "./SongTimeline";
import type { SongTimelineData, SongYearDetail, TimelineFocus } from "./song-timeline-types";
import "./styles.css";

const data = card as unknown as SongTimelineData;
const yearDetails = years as unknown as Record<string, SongYearDetail>;

function fetchYear(_songId: string, year: number): Promise<SongYearDetail> {
  const detail = yearDetails[String(year)];
  return detail ? Promise.resolve(detail) : Promise.reject(new Error(`The ${year} list is not in the fixture.`));
}

function NowPlaying() {
  const player = usePlayer();
  const track = player.currentTrack;
  if (!track) return null;
  return (
    <div className="preview-player" role="status">
      <button type="button" onClick={player.toggle}>
        {player.status === "playing" ? "Pause" : "Play"}
      </button>
      <span>
        {track.title} · {track.showDate} · {track.venueName}
      </span>
      <span>
        {formatClockTime(player.position)} / {formatClockTime(player.duration)}
      </span>
      {player.hasNext && (
        <button type="button" onClick={player.next}>
          Next
        </button>
      )}
    </div>
  );
}

function Preview() {
  const [asked, setAsked] = useState<{ question: string; focus: TimelineFocus }[]>([]);
  return (
    <PlayerProvider>
      <main className="preview-page">
        <p className="preview-note">Preview: real library data; the stops, open year and year questions stand in for the model's choices.</p>
        <h2 className="preview-heading">The song's life on stage</h2>
        <section className="card song-overview preview-card">
          <h3>{data.performance_count} performances across the Dead's career</h3>
          <SongTimeline data={data} fetchYear={fetchYear} onAsk={(question, focus) => setAsked((items) => [...items, { question, focus }])} />
        </section>
        {asked.length > 0 && (
          <section className="preview-asked" aria-label="Questions asked">
            {asked.map((item, index) => (
              <p key={index}>
                <strong>{item.question}</strong> <code>{JSON.stringify(item.focus)}</code>
              </p>
            ))}
          </section>
        )}
      </main>
      <NowPlaying />
    </PlayerProvider>
  );
}

const style = document.createElement("style");
style.textContent = `
  .preview-page { width: min(980px, calc(100% - 2rem)); margin: 0 auto; padding: 2rem 0 6rem; display: flex; flex-direction: column; gap: 1.25rem; }
  .preview-note { margin: 0; color: var(--quiet); font-size: 0.85rem; }
  .preview-heading { color: var(--cream); font-size: 1.6rem; }
  .preview-card { display: flex; flex-direction: column; gap: 1.25rem; }
  .preview-card h3 { color: var(--cream); font-size: 1.65rem; }
  .preview-asked { color: var(--muted); font-size: 0.85rem; }
  .preview-asked code { color: var(--quiet); word-break: break-word; }
  .preview-player { position: fixed; left: 0; right: 0; bottom: 0; display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; padding: 0.75rem 1.5rem; background: var(--bar-scrim); border-top: 1px solid var(--hair); color: var(--text); font-size: 0.85rem; }
  .preview-player button { background: var(--listen); color: var(--listen-ink); border: 0; border-radius: 999px; padding: 0.35rem 0.9rem; font-weight: 600; }
`;
document.head.appendChild(style);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Preview />
  </StrictMode>
);
```

- [x] **Step 3: Look at it and confirm the build leaves it out**

Run: `npm --prefix web run dev -- --port 5181`, open `/song-timeline-preview.html`, switch to Length, open See all for 1979 (23 rows). Then `npm --prefix web run build` and confirm `web/dist/assets` holds no preview file.

- [x] **Step 4: Commit**

```bash
git add web/song-timeline-preview.html web/src/song-timeline-preview.tsx
git commit -m "Add a dev-only preview page for the song timeline on the Terrapin fixtures"
```

---

# Phase 2: wire into the app (after the grid branch merges)

Start from fresh main once `claude/whereyouworkmatters-research-8634ea` has merged (it adds `AskFocus`, `askRequestBody`, the grid lookup rate limiter, and edits every shared file below). Rebase this branch onto main first: `git fetch origin && git rebase origin/main`. Line numbers below are from main at `ffd8d98` and will move; find the named symbols.

### Task 6: Register `get_song_life`

**Files:**
- Modify: `deadbot/tools.py` (beside `get_song`, inside the tool builder)
- Test: `tests/test_research_tools.py`

**Interfaces:**
- Consumes: `song_life.tool_payload(store, song_row)`, `store.resolve_song`, the module's `_json` helper.
- Produces: a tool named `get_song_life` in `build_tools(store)`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_research_tools.py`)

```python
def test_get_song_life_states_years_and_standouts(built_sqlite, tmp_path):
    import json
    from deadbot.sqlite_store import SqliteCanonicalStore
    from deadbot.tools import build_tools

    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tool = next(t for t in build_tools(store) if t.name == "get_song_life")
    payload = json.loads(tool.invoke({"song_id_or_title": "Terrapin Station"}))
    assert payload["performance_count"] == 302
    assert payload["years"][0] == {"year": 1977, "count": 28, "typical_minutes": payload["years"][0]["typical_minutes"], "longest_minutes": 14.9}
    assert any("longest on record (25:14)" in item["facts"] for item in payload["standouts"])
    missing = json.loads(tool.invoke({"song_id_or_title": "No Such Song"}))
    assert missing["error"] == "Song not found or ambiguous"
```

- [ ] **Step 2: Run it to see it fail**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_research_tools.py -k get_song_life -q`
Expected: FAIL with `StopIteration`

- [ ] **Step 3: Add the tool** (right after `get_song` in `deadbot/tools.py`)

```python
    @tool
    def get_song_life(song_id_or_title: str) -> str:
        """Get one song's life on stage: each year in brief and the performances that stand out.

        Use it to build a song_overview timeline (visible_facets with by_year)
        or to answer how a song changed over the years. `years` gives each
        year's count and typical and longest minutes. `standouts` are the
        performances whose facts stand out, each with its ID and plain facts:
        first, last and longest, the longest of each year, picks with who made
        them, releases, rare placements, guests, and rare neighbors. `patterns`
        names placements too common to list one by one. Choose your stops from
        these and from what you know; give each a short label and a one-line
        why in the song_overview's representatives.
        """
        from deadbot import song_life

        song = store.resolve_song(song_id_or_title)
        if not song:
            return _json({"error": "Song not found or ambiguous", "query": song_id_or_title})
        return _json(song_life.tool_payload(store, song))
```

- [ ] **Step 4: Run the test**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_research_tools.py -k get_song_life -q`
Expected: PASS. If a tool-count test in `tests/test_graph.py` or `tests/test_research_tools.py` lists every tool name, add `get_song_life` to it.

- [ ] **Step 5: Commit**

```bash
git add deadbot/tools.py tests/test_research_tools.py
git commit -m "Give the model get_song_life: a song's years in brief and the performances that stand out"
```

### Task 7: Plan and page schema for stops and the timeline

**Files:**
- Modify: `deadbot/finish.py` (`SongOverviewRef`, and the `song_overview` branch of item resolution that calls `composition._song_overview`)
- Modify: `deadbot/experience.py` (`SongRepresentativePerformance`, `SongOverviewBlock`, new timeline models)
- Modify: `deadbot/composition.py` (`_song_overview`)
- Test: `tests/test_finish.py`, `tests/test_experience.py`

**Interfaces:**
- Consumes: `song_life.card_data(store, song_id)`.
- Produces on `SongOverviewBlock`: `representative_performances[*].label/why`, `open_year: int | None`, `chart_view: Literal["count","length"] | None`, `year_questions: list[YearQuestion]`, `year_summaries: list[SongYearSummary]`, `length_points: list[SongLengthPoint]`, and each representative's `seconds`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_finish.py`:

```python
def test_song_overview_reads_stops_and_the_old_ids_key():
    from deadbot.finish import SongOverviewRef

    ref = SongOverviewRef.model_validate({
        "type": "song_overview", "song_id": "song-terrapin-station",
        "representatives": [{"performance_id": "gd-1979-01-08-terrapin-station-2-4", "label": "Charlie Miller's pick", "why": "The 1979 one."}],
        "open_year": 1979, "chart_view": "length",
        "year_questions": [{"year": 1979, "question": "How did 1979 differ?"}],
    })
    assert ref.representatives[0].label == "Charlie Miller's pick"
    assert ref.open_year == 1979 and ref.chart_view == "length"
    old = SongOverviewRef.model_validate({"type": "song_overview", "song_id": "song-terrapin-station", "representative_performance_ids": ["p1", "p2"]})
    assert [stop.performance_id for stop in old.representatives] == ["p1", "p2"]
    loose = SongOverviewRef.model_validate({
        "type": "song_overview", "song_id": "s", "chart_view": "sideways", "open_year": "1979",
        "representatives": ["p1", {"performance_id": "p2", "label": "Two"}, 7],
        "year_questions": [{"year": 1979, "question": "Q?"}, {"question": "no year"}],
    })
    assert loose.chart_view is None and loose.open_year == 1979
    assert [stop.performance_id for stop in loose.representatives] == ["p1", "p2"]
    assert [q.year for q in loose.year_questions] == [1979]
```

In `tests/test_experience.py` (using the CSV store):

```python
def test_song_overview_with_by_year_carries_the_timeline():
    from deadbot import composition
    from deadbot.data import CanonicalStore

    store = CanonicalStore()
    song = store.one("songs", "song-terrapin-station")
    block = composition._song_overview(
        store.song_context(song), store, visible_facets=["by_year", "representatives"],
        representatives=[{"performance_id": "gd-1979-01-08-terrapin-station-2-4", "label": "Charlie Miller's pick", "why": "The 1979 one."}],
        open_year=1979, chart_view="length", year_questions=[{"year": 1979, "question": "How did 1979 differ?"}],
    )
    assert [row.year for row in block.year_summaries][:3] == [1977, 1978, 1979]
    assert len(block.length_points) == 280
    stop = block.representative_performances[0]
    assert (stop.label, stop.why, stop.seconds) == ("Charlie Miller's pick", "The 1979 one.", 735)
    assert block.open_year == 1979 and block.chart_view == "length"
```

- [ ] **Step 2: Run them to see them fail**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_finish.py tests/test_experience.py -k "stops_and_the_old or carries_the_timeline" -q`
Expected: FAIL (unknown fields)

- [ ] **Step 3: Add the plan fields** (`deadbot/finish.py`)

Beside `SongOverviewRef`:

```python
class SongStop(_PlanModel):
    """One stop through a song's life: a performance, a few words, and why."""

    model_config = ConfigDict(extra="ignore")

    performance_id: str
    label: str | None = Field(default=None, description="A few words a fan would recognize: 'The debut', 'At the pyramids'.")
    why: str | None = Field(default=None, description="One line on why this performance is worth hearing.")


class YearQuestion(_PlanModel):
    model_config = ConfigDict(extra="ignore")

    year: int
    question: str
```

In `SongOverviewRef`, replace `representative_performance_ids` with:

```python
    representatives: list[SongStop] = Field(
        default_factory=list,
        description=(
            "Your stops through the song's life, in listening order. With by_year they mark the timeline and "
            "form a listening path; otherwise they list as chosen renditions. Retrieve concrete rendition IDs first "
            "(get_song_life lists the standouts)."
        ),
    )
    open_year: int | None = Field(default=None, description="With by_year: the year whose panel opens first, such as the year the visitor asked about.")
    chart_view: Literal["count", "length"] | None = Field(default=None, description="With by_year: open on times played (count) or lengths (length).")
    year_questions: list[YearQuestion] = Field(default_factory=list, description="With by_year: a follow-up question for any years you choose.")

    @model_validator(mode="before")
    @classmethod
    def _read_leniently(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if "representatives" not in value and isinstance(value.get("representative_performance_ids"), list):
            value["representatives"] = [{"performance_id": pid} for pid in value["representative_performance_ids"] if isinstance(pid, str)]
        # Keep every usable stop; a bare ID string is a stop without words.
        value["representatives"] = [
            {"performance_id": item} if isinstance(item, str) else item
            for item in value.get("representatives") or []
            if isinstance(item, str) or (isinstance(item, dict) and isinstance(item.get("performance_id"), str))
        ]
        if value.get("chart_view") not in (None, "count", "length"):
            value["chart_view"] = None
        year = value.get("open_year")
        value["open_year"] = int(year) if isinstance(year, int) or (isinstance(year, str) and year.strip().isdigit()) else None
        # One bad year question is dropped, never the whole card.
        value["year_questions"] = [
            item for item in value.get("year_questions") or []
            if isinstance(item, dict) and isinstance(item.get("year"), int) and isinstance(item.get("question"), str)
        ]
        return value
```

Update the `history` facet description to end: "With by_year, the timeline carries this and the History tab is not shown." In the `song_overview` resolution branch, pass every stop in the model's order, marking which ones are grounded, instead of `representative_performance_ids`:

```python
                representatives=[{**stop.model_dump(), "grounded": stop.performance_id in grounded.ids} for stop in item.representatives],
                open_year=item.open_year,
                chart_view=item.chart_view,
                year_questions=[question.model_dump() for question in item.year_questions],
```

`_song_overview` keeps that one list in order. A stop resolves only when it is grounded and is a performance of this song; any other stop (ungrounded, or another song's performance) stays in its place with only `performance_id`, `label` and `why`, so the model's numbering and words survive.

- [ ] **Step 4: Add the page models** (`deadbot/experience.py`)

On `SongRepresentativePerformance` add `label: str | None = None`, `why: str | None = None`, `seconds: int | None = Field(default=None, ge=0)`, and make `show_id` and `show_label` default to `""` so an unresolved stop validates. Add:

```python
class SongYearPick(ExperienceModel):
    performance_id: str
    show_date: str
    venue_name: str | None = None
    set_label: str | None = None
    seconds: int | None = Field(default=None, ge=0)
    basis: Literal["picked", "show_picked", "released", "first"]
    basis_detail: str | None = None
    track: PlayableTrack | None = None


class SongYearSummary(ExperienceModel):
    year: int
    count: int = Field(ge=0)
    median_seconds: int | None = Field(default=None, ge=0)
    longest: dict[str, Any] | None = None
    top_next: dict[str, Any] | None = None
    pick: SongYearPick | None = None


class SongLengthPoint(ExperienceModel):
    performance_id: str
    show_date: str
    seconds: int = Field(ge=0)


class SongYearQuestion(ExperienceModel):
    year: int
    question: str
```

On `SongOverviewBlock` add `open_year: int | None = None`, `chart_view: Literal["count", "length"] | None = None`, `year_questions: list[SongYearQuestion]` and `year_summaries: list[SongYearSummary]` (both `Field(default_factory=list, max_length=LIST_CEILING)`), and `length_points: list[SongLengthPoint] = Field(default_factory=list)` with **no** `max_length`: Drums has 1,407 points and Space 1,136, above `LIST_CEILING` (1,000), and a validation failure would break the card. If a ceiling is wanted, set one far above (for example 5,000) in `_song_overview`, trimming and logging. Note the size: Drums' card data is about 146 KB.

- [ ] **Step 5: Fill them** (`deadbot/composition.py`, `_song_overview`)

Replace the `representative_performance_ids` parameter with `representatives: list[dict] | None = None` (each `{performance_id, label, why, grounded}`), `open_year`, `chart_view`, `year_questions`. Walk the list in order: a grounded stop that is one of this song's performances builds as today, adding `label`, `why`, and `seconds` from `song_life` (`{p.performance_id: p.seconds for p in song_life.life_performances(store, song_id)}`); every other stop becomes `SongRepresentativePerformance(performance_id=..., label=..., why=...)` in the same position. When `"by_year" in facets`, set `year_summaries` and `length_points` from `song_life.card_data(store, song_id)`.

- [ ] **Step 6: Run the tests and the existing suites that build song cards**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_finish.py tests/test_experience.py tests/test_experience_contract.py tests/test_lean_rendering.py -q`
Expected: PASS. Fix any existing test that passed `representative_performance_ids` to `_song_overview` by passing `representatives=[{"performance_id": ...}]`.

- [ ] **Step 7: Commit**

```bash
git add deadbot/finish.py deadbot/experience.py deadbot/composition.py tests/test_finish.py tests/test_experience.py
git commit -m "Let the model name a song's stops, open year, first view and year questions"
```

### Task 8: Year lookup endpoint

**Files:**
- Modify: `deadbot/api.py`, `deadbot/experience.py` (`SongYearDetail` and `SongYearPerformance` models)
- Test: `tests/test_api_song_year.py` (new)

**Interfaces:**
- Consumes: `song_life.year_detail`; the grid branch's `_enforce_rate_limit(http_request, grid=True)` (rename its keyword to a shared lookup limit if the merged code allows).
- Produces: `GET /api/songs/{song_id}/years/{year}` returning `SongYearDetail`, with `Cache-Control: public, max-age=86400`.

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore


def client():
    return TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=object()))


def test_song_year_lists_one_year_and_caches():
    response = client().get("/api/songs/song-terrapin-station/years/1979")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"
    body = response.json()
    assert body["year"] == 1979 and len(body["performances"]) == 23
    assert body["performances"][0]["next"]["title"] == "Playing In The Band"


def test_song_year_unknown_song_and_empty_year():
    assert client().get("/api/songs/song-no-such/years/1979").status_code == 404
    assert client().get("/api/songs/song-terrapin-station/years/1975").json()["performances"] == []
```

- [ ] **Step 2: Run it to see it fail**

Run: `PYTHONPATH=. ../../../.venv/bin/python -m pytest tests/test_api_song_year.py -q`
Expected: FAIL with 404 on the first request

- [ ] **Step 3: Add the models and the route**

In `deadbot/experience.py`, `SongYearPerformance` mirrors `LifePerformance.to_json` (`performance_id`, `show_id`, `show_date`, `venue_name`, `city`, `set_label`, `position_in_set`, `encore`, `previous`/`next` as `{song_id, title, segued}`, `seconds`, `length_source`, `track: PlayableTrack | None`, `releases: list[str]`, `signals: list[{voice, scope}]`, `guests: list[{name, instrument}]`), and `SongYearDetail` has `song_id`, `title`, `year`, `performances`. In `create_app`:

```python
    @app.get("/api/songs/{song_id}/years/{year}", response_model=SongYearDetail)
    def song_year(song_id: str, year: int, http_request: Request, response: Response) -> SongYearDetail:
        """One song's performances in one year, every fact from the library; no model call."""

        _enforce_rate_limit(http_request, grid=True)
        detail = song_life.year_detail(app.state.store, song_id, year)
        if detail is None:
            raise HTTPException(status_code=404, detail="The library has no such song.")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return SongYearDetail.model_validate(detail)
```

- [ ] **Step 4: Run the test**: expected PASS.

- [ ] **Step 5: Commit**

```bash
git add deadbot/api.py deadbot/experience.py tests/test_api_song_year.py
git commit -m "Serve one song's year of performances for See all, cached, without the model"
```

### Task 9: Put the timeline on the song card and ask with focus

**Files:**
- Modify: `deadbot/experience.py` (`AskFocus.block_type`), `web/src/App.tsx` (`SongOverviewUnit`), `web/openapi.json`, `web/src/generated/api.ts`, `web/src/song-timeline-types.ts`, `web/src/visual-fixtures.ts`
- Delete: `web/song-timeline-preview.html`, `web/src/song-timeline-preview.tsx`
- Test: `web/src/App.test.tsx` or the existing song-card test, `tests/test_api_focus.py`

**Interfaces:**
- Consumes: `SongTimeline`, the grid branch's `FollowUp = (question, focus?: AskFocus) => void`.
- Produces: song cards with `by_year` render `SongTimeline`; Ask sends `AskFocus{block_type: "song_overview", block_id: song_id, label, ids, facts}`.

- [ ] **Step 1: Widen the focus type**: `block_type: Literal["grid", "song_overview"]` in `AskFocus`; add a case to `tests/test_api_focus.py` posting a `song_overview` focus whose `ids` include `song-terrapin-station` and a performance ID, and assert both reach the grounded IDs.

- [ ] **Step 2: Regenerate the API types**: `PYTHONPATH=. ../../../.venv/bin/python scripts/export_openapi.py && npm --prefix web run gen:types`. Replace the hand-written types in `web/src/song-timeline-types.ts` with re-exports of the generated ones (keep the file so imports do not change).

- [ ] **Step 3: Map the block to the timeline in `SongOverviewUnit`**

```tsx
function timelineData(block: SongOverviewBlockT): SongTimelineData {
  return {
    song_id: block.song_id,
    title: block.title,
    performance_count: block.known_performance_count,
    year_summaries: block.year_summaries,
    length_points: block.length_points,
    stops: block.representative_performances.map((stop) => ({
      performance_id: stop.performance_id,
      label: stop.label ?? null,
      why: stop.why ?? null,
      show_date: stop.show_date ?? null,
      venue_name: stop.venue_name ?? null,
      seconds: stop.seconds ?? null,
      track: stop.audio_url ? { performance_id: stop.performance_id, title: block.title, audio_url: stop.audio_url, duration_seconds: stop.duration_seconds ?? null, set_label: stop.set_label ?? null } : null
    })),
    open_year: block.open_year ?? null,
    chart_view: block.chart_view ?? null,
    year_questions: block.year_questions
  };
}
```

When `showsFacet("by_year") && block.year_summaries.length > 0`, render `<SongTimeline data={timelineData(block)} onAsk={(question, focus) => onFollowUp(question, { block_type: "song_overview", block_id: focus.song_id, label: focus.label, ids: focus.ids, facts: focus.facts })} />` in place of the `DataChart` and the representatives list, and leave the History tab out of `tabs`. Cards without `by_year` keep today's rendering. Give the timeline `key={`${block.song_id}:${block.open_year ?? ""}:${block.chart_view ?? ""}`}`: App keeps the same element when the final page replaces the streamed draft, and `SongTimeline` reads `open_year` and `chart_view` only when it mounts, so without the key a final page that changes them would be ignored.

- [ ] **Step 4: Register the visual fixture** from `song-timeline-terrapin.json` in `web/src/visual-fixtures.ts` the way the grid fixtures are registered, and delete the preview page files.

- [ ] **Step 5: Run everything**: `npm --prefix web test && npx --prefix web tsc -p web/tsconfig.json --noEmit && PYTHONPATH=. ../../../.venv/bin/python -m pytest -q`. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A deadbot web tests
git commit -m "Put the song timeline on song cards and ask about a year with the year as focus"
```

### Task 10: Live runs and the owner's look

- [ ] **Step 1:** Run the owner's questions live against the worktree API (see the local-replay notes in memory): "How often did they play Terrapin", "How did Dark Star change over the years", "Best Sugar Magnolias", a rarity, and a cover. For each, record whether the model called `get_song_life`, chose stops with labels and reasons that are not just first-of-year, set `open_year` from the question, and the turn's added latency.
- [ ] **Step 2:** Score the pages with `scripts/page_eval.py`; compare with the pre-change runs.
- [ ] **Step 3:** If the model rarely chooses stops, ask what it was missing (AGENTS.md "When an answer is weak") before touching the prompt: check that `get_song_life` appears in its tool calls and that the field descriptions read clearly.
- [ ] **Step 4:** Known data gap to watch in the runs: the library marks only 2 performances as encores (encores are mostly stored as "Set 3"), so the "encore" standout rarely fires and encores read as "in Set 3" or "closed the set". Note it for a data pass rather than working around it in code.
- [ ] **Step 5:** Update `docs/UX-NEXT-STEPS.md` with the outcome, then hand the owner the push command.
