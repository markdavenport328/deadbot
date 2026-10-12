import json

import pytest

from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools
from deadbot.tours import matching_tours, normalize_tour

KNOWN = ["Europe 1972", "Fall 1993", "Spring 1977", "Grateful Dead Summer 1972 West Coast/Mountain"]


@pytest.mark.parametrize(
    "spelling, stored",
    [
        ("Europe '72", "Europe 1972"),
        ("Europe ’72", "Europe 1972"),
        ("Europe 72", "Europe 1972"),
        ("Europe 1972", "Europe 1972"),
        ("europe '72 tour", "Europe 1972"),
        ("Spring '77", "Spring 1977"),
        ("Fall 1973", None),
        ("fall '93", "Fall 1993"),
        ("Fall, 1993!", "Fall 1993"),
    ],
)
def test_fan_spellings_land_on_the_stored_name(spelling, stored):
    assert matching_tours(KNOWN, spelling) == ([stored] if stored else [])


def test_normalizer_keeps_four_digit_years_and_drops_the_word_tour():
    assert normalize_tour("Summer 1974 Tour") == "summer 1974"


def test_grid_takes_a_fan_spelling_of_a_tour(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tool = next(t for t in build_tools(store) if t.name == "get_grid")
    try:
        payload = json.loads(tool.invoke({"row_kind": "show", "column_kind": "song", "columns": ["Dark Star"], "tour": "Europe '72"}))
        assert "error" not in payload and payload["grid_id"]
        missing = json.loads(tool.invoke({"row_kind": "show", "column_kind": "song", "columns": ["Dark Star"], "tour": "Europe Spring Fling"}))
        assert missing["error"] == "No shows on that tour" and missing["closest_tours"]
    finally:
        store.close()
