"""Encores in the canonical performances: marked, labeled, and nothing else moved."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from deadbot import listening, song_life
from deadbot.experience import PlayableTrack

CANONICAL = Path(__file__).resolve().parents[1] / "data" / "canonical"
LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "corrections" / "encores-derived.jsonl"


def _shows() -> dict[str, dict[int, list[dict[str, str]]]]:
    shows: dict[str, dict[int, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    with (CANONICAL / "performances.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            shows[row["show_id"]][int(row["set_number"])].append(row)
    return shows


def test_the_encores_named_in_the_owner_reports_are_labeled_encore():
    shows = _shows()
    for show_id, songs in {
        "gd-1977-05-08": ["one-more-saturday-night"],
        "gd-1989-07-07": ["knockin-on-heaven-s-door"],
        "gd-1990-03-29": ["knockin-on-heaven-s-door"],
        "gd-1995-07-09": ["black-muddy-river", "box-of-rain"],
    }.items():
        last = shows[show_id][max(shows[show_id])]
        assert [row["song_id"].removeprefix("song-") for row in last] == songs
        assert {(row["set_label"], row["encore"]) for row in last} == {("Encore", "true")}


def test_set_numbers_and_ids_are_untouched_and_a_label_always_matches_its_flag():
    for show_id, sets in _shows().items():
        assert sorted(sets) == list(range(1, len(sets) + 1)), show_id
        for number, rows in sets.items():
            for row in rows:
                assert row["performance_id"].startswith(show_id)
                if row["set_label"] == "Encore":
                    assert row["encore"] == "true"
                else:
                    assert row["set_label"] == f"Set {number}" or row["encore"] == "true" or row["set_label"].startswith("Disc")


def test_only_a_short_final_set_or_a_tape_named_one_is_an_encore():
    shows = _shows()
    for line in LOG.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        sets = shows[entry["show_id"]]
        assert entry["set_number"] == max(sets)
        size = len(sets[entry["set_number"]])
        if entry["rule"] == "structure":
            assert len(sets) >= 3 and size <= 2 and len(sets[entry["set_number"] - 1]) >= 5
        else:
            assert entry["rule"] == "tape" and size <= 4 and entry["evidence"]


def test_early_and_two_set_shows_without_tape_evidence_keep_their_sets():
    shows = _shows()
    # 1966-12-23 has a six-song set and a one-song "second set": that may be all the tape holds.
    assert {row["set_label"] for row in shows["gd-1966-12-23"][2]} == {"Set 2"}
    # A real third set (more than a few songs) stays a set.
    assert {row["set_label"] for row in shows["gd-1970-01-31"][3]} == {"Set 3"}


def test_veneta_keeps_its_hand_marked_encores_inside_the_third_set():
    labels = {(row["song_id"], row["set_label"], row["encore"]) for rows in _shows()["gd-1972-08-27"].values() for row in rows if row["encore"] == "true"}
    assert labels == {("song-casey-jones", "Set 3", "true"), ("song-one-more-saturday-night", "Set 3", "true")}


def _life(set_number: int, label: str, encore: bool, previous=None, next_=None, show="s1", date="1977-05-08") -> song_life.LifePerformance:
    return song_life.LifePerformance(
        performance_id=f"p-{show}-{set_number}", show_id=show, show_date=date, venue_name="Hall", city=None, set_number=set_number,
        set_label=label, position_in_set=1, encore=encore, previous=previous, next=next_, seconds=None,
        length_source=None, audio_url=None, tape_seconds=None, releases=(), signals=(), guests=(),
    )


def test_an_encore_is_its_own_pattern_not_a_later_set_or_an_opener():
    performances = [_life(3, "Encore", True, show=f"s{i}", date=f"197{i % 10}-05-08") for i in range(3)]
    performances += [_life(1, "Set 1", False, show=f"t{i}", date=f"198{i}-05-08") for i in range(40)]
    kinds, _left_out, patterns = song_life.standouts(performances)
    facts = [fact for items in kinds.values() for item in items for fact in item["facts"]]
    assert "encore" in facts
    assert not any("later set" in fact or "Encore" in fact or "opened a set" in fact for fact in facts + patterns)


def test_play_set_three_still_starts_at_the_encore():
    tracks = [
        PlayableTrack(performance_id="a", title="Scarlet Begonias", audio_url="https://archive.org/download/x/1.mp3", set_label="Set 2"),
        PlayableTrack(performance_id="b", title="One More Saturday Night", audio_url="https://archive.org/download/x/2.mp3", set_label="Encore"),
    ]
    numbers = {"a": "2", "b": "3"}
    assert listening._start_index(tracks, "Encore", None, numbers) == 1
    assert listening._start_index(tracks, "Set 3", None, numbers) == 1
    assert listening._start_index(tracks, "3", None, numbers) == 1
    assert listening._start_index(tracks, "Set 2", None, numbers) == 0
    assert listening._start_index(tracks, "Set 9", None, numbers) == 0
