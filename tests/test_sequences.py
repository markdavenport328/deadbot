"""Song pairings: the get_segue_pairing tool, store parity, and the version_strip primitive."""

import json

import pytest
from langchain_core.messages import AIMessageChunk

from deadbot import finish, sequences
from deadbot.data import CanonicalStore
from deadbot.plan_stream import PlanStreamer
from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools

CHINA = "song-china-cat-sunflower"
RIDER = "song-i-know-you-rider"
CHINA_RIDER = sequences.pairing_id(CHINA, RIDER)
PROVIDENCE = "gd-1974-06-26:2:5"
MUNICH = "gd-1972-05-18:1:8"

# Pairings with different shapes: a segue that always segues, one that
# only sometimes segues, and the reverse order.
PAIRS = [
    (CHINA, RIDER),
    ("song-scarlet-begonias", "song-fire-on-the-mountain"),
    ("song-playing-in-the-band", "song-uncle-john-s-band"),
    ("song-sugar-magnolia", "song-dark-star"),
    (RIDER, CHINA),
]


@pytest.fixture(scope="module")
def csv_store():
    return CanonicalStore()


@pytest.fixture
def sqlite_store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def _tool(store, name="get_segue_pairing"):
    return next(item for item in build_tools(store) if item.name == name)


def _pairing(store, **arguments):
    return json.loads(_tool(store).invoke({"first_song": "China Cat Sunflower", "second_song": "I Know You Rider", **arguments}))


def test_china_cat_into_rider_counts_every_segued_night_by_year(csv_store):
    payload = _pairing(csv_store)
    assert payload["pairing_id"] == CHINA_RIDER
    assert payload["count"] == 544
    assert payload["counts"] == {"segue": 544, "followed_without_segue": 0}
    by_year = {row["year"]: row["count"] for row in payload["by_year"]}
    assert (min(by_year), max(by_year)) == (1969, 1995)
    assert by_year[1970] == 64 and by_year[1974] == 21 and by_year[1995] == 8
    assert [by_year[year] for year in (1975, 1976, 1977, 1978)] == [0, 0, 1, 0]
    assert sum(by_year.values()) == 544


def test_the_summary_names_the_extremes_and_asks_before_listing_every_version(csv_store):
    payload = _pairing(csv_store)
    assert "versions" not in payload
    assert payload["available"]["versions"]["count"] == 544
    longest = payload["lengths"]["first_song"]["longest"]
    assert longest["pair_id"] == PROVIDENCE
    assert (longest["first_seconds"], longest["second_seconds"]) == (784, 365)
    assert longest["venue_name"] == "Providence Civic Center"
    assert longest["first_track_url"].endswith("20ChinaCatSunflower.mp3")
    assert payload["lengths"]["first_song"]["shortest"]["first_seconds"] > 0
    assert [row["era"] for row in payload["by_era"]][0] == "1965–1970"
    assert all("median_first_seconds" in row for row in payload["by_era"])


def test_versions_arrive_on_request_and_narrow_by_year(csv_store):
    payload = _pairing(csv_store, include=["versions"], year_from=1974, year_to=1974)
    assert payload["year_range"] == {"from": 1974, "to": 1974, "count": 21}
    assert len(payload["versions"]) == 21
    assert {version["show_date"][:4] for version in payload["versions"]} == {"1974"}
    assert PROVIDENCE in {version["pair_id"] for version in payload["versions"]}


def test_transition_any_counts_nights_the_second_song_only_followed(csv_store):
    segue = json.loads(_tool(csv_store).invoke({"first_song": "Sugar Magnolia", "second_song": "Dark Star"}))
    every = json.loads(_tool(csv_store).invoke({"first_song": "Sugar Magnolia", "second_song": "Dark Star", "transition": "any"}))
    assert segue["counts"]["followed_without_segue"] > 0
    assert every["count"] == segue["counts"]["segue"] + segue["counts"]["followed_without_segue"]
    assert every["count"] > segue["count"]
    assert {version["segue"] for version in every["versions"]} == {True, False}


def test_bad_arguments_return_errors_naming_what_is_valid(csv_store):
    assert _pairing(csv_store, include=["everything"])["valid"] == ["versions"]
    assert _pairing(csv_store, transition="sometimes")["valid"] == list(sequences.TRANSITIONS)
    missing = json.loads(_tool(csv_store).invoke({"first_song": "Not A Song Title", "second_song": "I Know You Rider"}))
    assert missing["error"] == "Song not found or ambiguous"


@pytest.mark.parametrize("first, second", PAIRS)
def test_sqlite_pairs_match_the_csv_store(sqlite_store, csv_store, first, second):
    assert sqlite_store.sequence_pairs(first, second) == csv_store.sequence_pairs(first, second)
    assert sequences.versions(sqlite_store, first, second) == sequences.versions(csv_store, first, second)


def test_sqlite_tool_output_matches_the_csv_store(sqlite_store, csv_store):
    for arguments in ({}, {"include": ["versions"], "year_from": 1973, "year_to": 1974}, {"transition": "any"}):
        assert _pairing(sqlite_store, **arguments) == _pairing(csv_store, **arguments)


# ---- version_strip -------------------------------------------------------


def _strip_payloads(store):
    return [_pairing(store, include=["versions"], year_from=1972, year_to=1974)]


def _strip_item(**overrides):
    item = {
        "type": "version_strip",
        "pairing_id": CHINA_RIDER,
        "pair_ids": [PROVIDENCE, MUNICH],
        "title": "The China half kept growing",
        "note": "Providence is the long ride.",
        "show_year_counts": True,
    }
    return {**item, **overrides}


def test_a_version_strip_hydrates_the_chosen_nights_in_the_model_order(csv_store):
    payloads = _strip_payloads(csv_store)
    grounded = finish.grounded_context(payloads)
    item = finish.validate_body_item(_strip_item(), where="planned")
    blocks, _ = finish.resolve_items([item], grounded, payloads, csv_store)
    assert len(blocks) == 1
    strip = blocks[0]
    assert strip.type == "version_strip"
    assert [row.pair_id for row in strip.rows] == [PROVIDENCE, MUNICH]
    providence = strip.rows[0]
    assert (providence.first_seconds, providence.second_seconds) == (784, 365)
    assert providence.venue_name == "Providence Civic Center" and providence.show_date == "1974-06-26"
    assert providence.first_track.title == "China Cat Sunflower" and providence.second_track.title == "I Know You Rider"
    assert providence.second_track.audio_url.endswith("21IKnowYouRider.mp3")
    assert strip.total_count == 544
    assert {entry.year: entry.count for entry in strip.year_counts}[1977] == 1


def test_a_version_strip_drops_nights_the_tools_did_not_return(csv_store):
    payloads = _strip_payloads(csv_store)
    grounded = finish.grounded_context(payloads)
    outside_the_range = "gd-1995-06-28:2:1"
    item = finish.validate_body_item(_strip_item(pair_ids=[outside_the_range, PROVIDENCE], show_year_counts=False), where="planned")
    blocks, _ = finish.resolve_items([item], grounded, payloads, csv_store)
    assert [row.pair_id for row in blocks[0].rows] == [PROVIDENCE]
    assert blocks[0].year_counts == []

    only_ungrounded = finish.validate_body_item(_strip_item(pair_ids=[outside_the_range]), where="planned")
    assert finish.resolve_items([only_ungrounded], grounded, payloads, csv_store)[0] == []
    unretrieved_pairing = finish.validate_body_item(_strip_item(pairing_id=sequences.pairing_id(RIDER, CHINA)), where="planned")
    assert finish.resolve_items([unretrieved_pairing], grounded, payloads, csv_store)[0] == []


def test_a_version_strip_survives_the_streamed_and_final_paths(csv_store):
    payloads = _strip_payloads(csv_store)
    grounded = finish.grounded_context(payloads)
    plan_args = {
        "chat_answer": "It is one piece in two halves.",
        "title": "One song in two halves",
        "lead": None,
        "groups": [{"presentation": "collection", "items": [_strip_item()]}],
    }

    def resolve(items):
        return finish.resolve_items(items, grounded, payloads, csv_store)[0]

    streamer = PlanStreamer(resolve)
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "finish_response", "args": json.dumps(plan_args), "id": "f1", "index": 0, "type": "tool_call_chunk"}],
    )
    streamed = [event.payload["block"] for event in streamer.feed(chunk) if event.type == "block"]

    plan = finish.FinishPlan.model_validate(plan_args)
    assert len(plan.groups) == 1 and len(plan.groups[0].items) == 1
    final, _ = finish.resolve_items(plan.groups[0].items, grounded, payloads, csv_store)

    assert len(streamed) == 1 and len(final) == 1
    assert final[0].type == "version_strip"
    assert streamed[0] == final[0].model_dump(mode="json")
