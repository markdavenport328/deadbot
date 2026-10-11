"""Tests for scripts/normalize_jerrybase_performers.py's instrument splitting."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import normalize_jerrybase_performers as njp  # noqa: E402

CANONICAL = Path(__file__).parents[1] / "data" / "canonical"


def test_perc_abbreviation_expands_only_as_a_whole_token():
    assert njp.instruments("drums, perc") == ["drums", "percussion"]
    assert njp.instruments("percussion") == ["percussion"]
    assert njp.instruments("perc, percussion") == ["percussion"]


def test_keys_abbreviation_expands_only_as_a_whole_token():
    assert njp.instruments("keys") == ["keyboards"]
    assert njp.instruments("keyboards") == ["keyboards"]
    assert njp.instruments("monkeys") == ["monkeys"]


def test_and_splits_into_separate_instruments():
    assert njp.instruments("vocals and harmonica") == ["vocals", "harmonica"]


def test_canonical_show_performers_have_no_doubled_expansions():
    with (CANONICAL / "show_performers.csv").open(newline="", encoding="utf-8") as handle:
        instruments = {row["instrument"] for row in csv.DictReader(handle)}
    doubled = {value for value in instruments if "percussionussion" in value or "keyboardsboards" in value}
    assert doubled == set()


def _person(person_id, name, birth=""):
    return {"person_id": person_id, "name": name, "birth_date": birth, "death_date": "", "notes": "Added."}


def _row(show_id, person_id, instrument, notes="JerryBase source event 1; JerryBase source instrument: piano."):
    return {"show_id": show_id, "person_id": person_id, "role": "guest", "instrument": instrument, "notes": notes}


def test_a_qualified_person_folds_onto_the_plain_person_with_its_scope():
    people = [
        _person("person-bruce-hornsby", "Bruce Hornsby"),
        _person("person-bruce-hornsby-complete-show", "Bruce Hornsby (complete show)", "1954-11-23"),
    ]
    rows = [
        _row("gd-1988-06-25", "person-bruce-hornsby", "accordion"),
        _row("gd-1995-06-24", "person-bruce-hornsby-complete-show", "piano"),
    ]

    people, rows, folded = njp.fold_qualified_people(people, rows)

    assert folded == {"person-bruce-hornsby-complete-show": "person-bruce-hornsby"}
    assert [person["person_id"] for person in people] == ["person-bruce-hornsby"]
    assert people[0]["birth_date"] == "1954-11-23"
    assert {row["person_id"] for row in rows} == {"person-bruce-hornsby"}
    moved = next(row for row in rows if row["show_id"] == "gd-1995-06-24")
    assert "JerryBase source participation scope: complete show" in moved["notes"]
    assert "JerryBase source name: Bruce Hornsby (complete show)" in moved["notes"]


def test_a_non_participation_qualifier_folds_the_identity_without_a_scope():
    people = [
        _person("person-marvin-boxley", "Marvin Boxley"),
        _person("person-marvin-boxley-songs-unknown", "Marvin Boxley (songs unknown)"),
    ]
    rows = [_row("gd-1967-01-14-0", "person-marvin-boxley-songs-unknown", "harmonica")]

    _, rows, _ = njp.fold_qualified_people(people, rows)

    assert rows[0]["person_id"] == "person-marvin-boxley"
    assert "participation scope" not in rows[0]["notes"]


def test_a_folded_row_that_collides_merges_notes_instead_of_duplicating():
    people = [_person("person-ned-lagin", "Ned Lagin"), _person("person-ned-lagin-complete-show", "Ned Lagin (complete show)")]
    rows = [
        _row("gd-1975-03-23", "person-ned-lagin", "keyboards", "JerryBase source event A."),
        _row("gd-1975-03-23", "person-ned-lagin-complete-show", "keyboards", "JerryBase source event B."),
    ]

    _, rows, _ = njp.fold_qualified_people(people, rows)

    assert len(rows) == 1
    assert "event A" in rows[0]["notes"] and "event B" in rows[0]["notes"]


def test_a_qualifier_without_a_plain_person_is_never_merged():
    people = [_person("person-someone-complete-show", "Someone (complete show)")]
    rows = [_row("gd-1970-01-01", "person-someone-complete-show", "piano")]

    people_out, rows_out, folded = njp.fold_qualified_people(people, rows)

    assert folded == {}
    assert people_out == people and rows_out == rows


def test_canonical_people_hold_no_qualified_duplicate_of_a_plain_person():
    with (CANONICAL / "people.csv").open(newline="", encoding="utf-8") as handle:
        people = list(csv.DictReader(handle))
    _, _, folded = njp.fold_qualified_people(people, [])
    assert folded == {}
    surname_only = {row["person_id"] for row in people} & {
        "person-bralove", "person-wasserman", "person-bruce-welnick", "person-leiber", "person-stoller"
    }
    assert surname_only == set()
