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
