"""Measure a delivered page's song stops against library facts.

The song-stops eval (scripts/stop_eval.py, evals/song-stops-v1.json) asks
song questions live and scores each page here. Nothing here runs in the app
or is expected of the model: it reports what the model chose (a song card, a
timeline, how many stops with words, how widely they span the song's life)
and checks every claim a stop's words make that the library can confirm: a
debut, a last performance, a longest, a length, a venue, a year.
"""

from __future__ import annotations

import re
from typing import Any

from deadbot.song_life import LifePerformance

# How far a stated length may sit from the library's before it is a wrong fact.
CLOCK_TOLERANCE_SECONDS = 90
MINUTES_TOLERANCE = 3

# "The debut" claims the stop; "after its debut" only refers to it.
FIRST_CLAIM = re.compile(r"(?<!after )(?<!since )(?<!before )\b(the debut|debut performance|debuted|first performance|first time|first known|first-ever|first ever|premiere)\b")
LAST_CLAIM = re.compile(
    r"\b(final|last) (known |ever |documented |cataloged |recorded |live )?(performance|time|version|rendition|one|terrapin|reading)\b"
    r"|^the (last|final)\b"
)
LONGEST_CLAIM = re.compile(r"\blongest\b")
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
MINUTES = re.compile(r"\b(\d{1,2})[- ]minutes?\b")
YEAR = re.compile(r"\b(19[6-9]\d)\b")


def _song_card(response: dict[str, Any], song_id: str) -> dict[str, Any] | None:
    cards = [block for block in response.get("blocks", []) if block.get("type") == "song_overview"]
    return next((card for card in cards if card.get("song_id") == song_id), cards[0] if cards else None)


def _thirds(year: int, first: int, last: int) -> int:
    if last <= first:
        return 0
    return min(2, int(3 * (year - first) / (last - first + 1)))


def _claim_issues(label: str, why: str, performance: LifePerformance, life: list[LifePerformance], venues: set[str]) -> tuple[list[str], int]:
    """Wrong facts in one stop's words, and how many claims the library could not check.

    Debut, last, longest and length claims are read in the label and the why.
    A venue or year is read in the label alone: the label names the stop, while
    the why often places it among other nights ("a stage life that began at
    Fillmore West", "before the 1969 expansion").
    """

    issues: list[str] = []
    unverifiable = 0
    text = " ".join(part for part in (label, why) if part)
    lowered = text.lower()
    if FIRST_CLAIM.search(lowered) and performance is not life[0]:
        issues.append(f"says first/debut but the debut is {life[0].show_date}")
    if LAST_CLAIM.search(lowered) and performance is not life[-1]:
        issues.append(f"says last but the last is {life[-1].show_date}")
    # "the longest ... among the highlighted versions" is qualified, not a library claim.
    if LONGEST_CLAIM.search(lowered) and " among " not in lowered:
        timed = [p for p in life if p.seconds is not None]
        overall = max(timed, key=lambda p: p.seconds) if timed else None
        in_year = [p for p in timed if p.year == performance.year]
        year_longest = max(in_year, key=lambda p: p.seconds) if in_year else None
        if performance.seconds is None:
            unverifiable += 1
        elif performance is not overall and performance is not year_longest:
            issues.append("says longest but it is the longest neither overall nor in its year")
    for minutes, seconds in CLOCK.findall(text):
        stated = int(minutes) * 60 + int(seconds)
        if performance.seconds is None:
            unverifiable += 1
        elif abs(stated - performance.seconds) > CLOCK_TOLERANCE_SECONDS:
            issues.append(f"says {minutes}:{seconds} but the library has {performance.seconds // 60}:{performance.seconds % 60:02d}")
    # "the year's typical versions ran about 27 minutes" describes the year, not the stop.
    for minutes in ([] if "typical" in lowered else MINUTES.findall(lowered)):
        if performance.seconds is None:
            unverifiable += 1
        elif abs(int(minutes) - performance.seconds / 60) > MINUTES_TOLERANCE:
            issues.append(f"says {minutes} minutes but the library has {round(performance.seconds / 60)}")
    own = (performance.venue_name or "").lower()
    label_lowered = (label or "").lower()
    for venue in venues:
        name = venue.lower()
        if len(name) > 6 and name in label_lowered and name not in own and own not in name:
            issues.append(f"names {venue} but the performance was at {performance.venue_name}")
    years = {int(year) for year in YEAR.findall(label or "")}
    if years and performance.year not in years:
        issues.append(f"names {', '.join(map(str, sorted(years)))} but the performance is from {performance.year}")
    return issues, unverifiable


def score_stops(
    response: dict[str, Any] | None,
    case: dict[str, Any],
    life: list[LifePerformance],
    tools: list[str] | None = None,
    seconds: float | None = None,
) -> dict[str, Any]:
    """What one delivered page did with the song's stops, measured against the library."""

    tools = list(tools or [])
    score: dict[str, Any] = {
        "song_card": False,
        "timeline": False,
        "other_blocks": [],
        "stops_total": 0,
        "stops_resolved": 0,
        "labeled": 0,
        "with_why": 0,
        "years_spanned": 0,
        "span_share": 0.0,
        "thirds": 0,
        "beyond_calendar": 0,
        "fact_issues": [],
        "unverifiable": 0,
        "open_year": None,
        "open_year_ok": None,
        "year_questions": 0,
        "tools": tools,
        "used_song_life": "get_song_life" in tools,
        "seconds": seconds,
    }
    if response is None:
        return score
    score["other_blocks"] = sorted({block.get("type", "?") for block in response.get("blocks", []) if block.get("type") != "song_overview"})
    card = _song_card(response, case["song_id"])
    if card is None:
        return score
    score["song_card"] = True
    score["timeline"] = "by_year" in (card.get("visible_facets") or []) and bool(card.get("year_summaries"))
    score["open_year"] = card.get("open_year")
    if case.get("year") is not None:
        score["open_year_ok"] = card.get("open_year") == case["year"]
    score["year_questions"] = len(card.get("year_questions") or [])

    stops = card.get("representative_performances") or []
    by_id = {p.performance_id: p for p in life}
    score["stops_total"] = len(stops)
    score["labeled"] = sum(1 for stop in stops if stop.get("label"))
    score["with_why"] = sum(1 for stop in stops if stop.get("why"))
    placed = [by_id[stop["performance_id"]] for stop in stops if stop.get("performance_id") in by_id]
    score["stops_resolved"] = len(placed)
    if not life or not placed:
        return score

    first, last = life[0].year, life[-1].year
    years = sorted({p.year for p in placed})
    score["years_spanned"] = len(years)
    score["span_share"] = round((years[-1] - years[0]) / (last - first), 2) if last > first else 1.0
    score["thirds"] = len({_thirds(year, first, last) for year in years}) if last > first else 1
    timed = [p for p in life if p.seconds is not None]
    longest = max(timed, key=lambda p: p.seconds) if timed else None
    calendar = {id(life[0]), id(life[-1]), id(longest) if longest else None}
    score["beyond_calendar"] = sum(1 for p in placed if id(p) not in calendar)

    venues = {p.venue_name for p in life if p.venue_name}
    for stop in stops:
        performance = by_id.get(stop.get("performance_id"))
        if performance is None:
            continue
        issues, unverifiable = _claim_issues(stop.get("label") or "", stop.get("why") or "", performance, life, venues)
        score["fact_issues"] += [f"{performance.show_date}: {issue}" for issue in issues]
        score["unverifiable"] += unverifiable
    return score
