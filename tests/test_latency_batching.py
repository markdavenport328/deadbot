"""These tests pin the batched query shapes that keep one tool call from
issuing hundreds of queries."""

import json

import pytest

from deadbot.data import CanonicalStore
from deadbot.sqlite_store import query_cache_scope
from deadbot.tools import build_tools
from sqlite_toy import TABLES, toy_store


@pytest.fixture
def store(tmp_path):
    result = toy_store(tmp_path)
    yield result
    result.close()


@pytest.fixture
def tools(store):
    return {tool.name: tool for tool in build_tools(store)}


def test_entity_search_over_a_whole_question_issues_one_query_per_table(store, tools):
    before = len(store.statements)
    payload = json.loads(tools["search_entities"].invoke({"query": "What are the best versions of Dark Star?"}))
    issued = store.statements[before:]
    # songs, people, venues, equipment, official_releases, shows: one each,
    # plus one rows_in per table pathways_for reads to attach pathways for
    # the matched song (performances, resource_songs, resource_performances,
    # official_release_tracks, resources) and one attempt at selection rows.
    # Every added query is one batched read for the whole matched set, never
    # one per matched row.
    assert len(issued) == 12
    assert any(match["id"] == "song-dark-star" for match in payload["matches"])


def test_entity_search_still_finds_a_venue_and_a_show_from_a_combined_phrase(tools):
    payload = json.loads(tools["search_entities"].invoke({"query": "Veneta Bird Song"}))
    kinds = {(match["entity_type"], match["id"]) for match in payload["matches"]}
    assert ("show", "show-1972-08-27") in kinds
    assert ("venue", "venue-old-renaissance") in kinds


def test_listing_song_performances_looks_shows_up_in_one_batch(store, tools):
    before = len(store.statements)
    payload = json.loads(tools["list_song_performances"].invoke({"song_id_or_title": "song-dark-star"}))
    show_queries = [sql for sql, _ in store.statements[before:] if 'FROM "shows"' in sql]
    assert payload["performance_count"] == len(
        [row for row in TABLES["performances"] if row["song_id"] == "song-dark-star"]
    )
    assert len(show_queries) == 1
    assert all(row["show_date"] for row in payload["performances"])


def test_matching_rows_any_ranks_exact_matches_first_on_both_stores(store):
    csv_store = CanonicalStore()
    csv_store.__dict__["tables"] = TABLES
    for either in (csv_store, store):
        rows = either.matching_rows_any("songs", ["dark", "Ripple"], ("title", "slug"))
        assert [row["song_id"] for row in rows] == ["song-ripple", "song-dark-star"]
        assert either.matching_rows_any("songs", ["", "   "], ("title",)) == []


def test_query_cache_serves_repeated_reads_within_one_scope_only(store):
    with query_cache_scope() as cache:
        before = len(store.statements)
        first = store.one("shows", "show-1972-08-27")
        second = store.one("shows", "show-1972-08-27")
        assert first == second
        assert len(store.statements) - before == 1
        assert len(cache) == 1
        # A cached row is a copy: mutating it never poisons later reads.
        second["show_date"] = "changed"
        assert store.one("shows", "show-1972-08-27")["show_date"] == "1972-08-27"
    before = len(store.statements)
    store.one("shows", "show-1972-08-27")
    assert len(store.statements) - before == 1


def test_a_shared_cache_dict_carries_across_scopes(store):
    shared: dict = {}
    with query_cache_scope(shared):
        store.one("venues", "venue-old-renaissance")
    before = len(store.statements)
    with query_cache_scope(shared):
        store.one("venues", "venue-old-renaissance")
    assert len(store.statements) - before == 0
