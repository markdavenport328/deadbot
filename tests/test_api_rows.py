"""GET /api/rows/{row_id}: what a ranked row, chart bar or roster name opens to, from the library alone."""

import pytest
from fastapi.testclient import TestClient

from deadbot import row_details
from deadbot.api import create_app, focus_ids, focus_note
from deadbot.config import Settings
from deadbot.experience import AskFocus, DataChartBlock, RankedListBlock
from deadbot.sqlite_store import SqliteCanonicalStore


@pytest.fixture
def store(built_sqlite, tmp_path):
    return SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")


@pytest.fixture
def client(store):
    with TestClient(create_app(settings=Settings(), store=store, agent=object())) as test_client:
        yield test_client


def facts(body):
    return {fact["label"]: fact["value"] for fact in body["facts"]}


def test_a_song_opens_to_its_counts_a_picked_version_and_its_story(client):
    response = client.get("/api/rows/song-playing-in-the-band")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    body = response.json()
    assert (body["kind"], body["title"]) == ("song", "Playing In The Band")
    assert facts(body) == {"Played": "750 times", "Years": "1971–1995", "Most in": "1972, 82 times"}
    play = body["play"]
    assert play["why"].startswith("Picked by ")
    assert len(play["tracks"]) == 1 and play["tracks"][0]["audio_url"].startswith("https://archive.org/download/")
    assert body["ask"] == "The story of Playing In The Band on stage"


def test_the_same_song_always_plays_the_same_version(client):
    first = client.get("/api/rows/song-dark-star").json()["play"]
    second = client.get("/api/rows/song-dark-star").json()["play"]
    assert first == second


def test_a_guest_opens_to_their_shows_instruments_songs_and_a_night_they_sat_in(client):
    body = client.get("/api/rows/person-branford-marsalis").json()
    assert body["kind"] == "person"
    assert facts(body)["Shows"] == "5"
    assert facts(body)["Years"] == "1990–1994"
    assert facts(body)["Played"] == "saxophone"
    assert facts(body)["Most often on"].startswith("Dark Star (5)")
    # The night plays the songs he sat in on, from that night's tape.
    assert body["play"]["show_date"][:4] in {"1990", "1991", "1993", "1994"}
    assert body["play"]["tracks"]
    assert body["ask"] == "Tell me about Branford Marsalis with the Dead"


def test_a_guest_known_only_by_show_plays_a_night_they_were_there(client):
    body = client.get("/api/rows/person-ned-lagin").json()
    assert facts(body)["Shows"] == "33"
    assert "Most often on" not in facts(body)
    assert body["play"]["tracks"]
    assert body["ask"] == "Tell me about Ned Lagin with the Dead"


def test_a_band_member_asks_about_their_years_in_the_band(client):
    body = client.get("/api/rows/person-jerry-garcia").json()
    assert facts(body)["Shows"] == "2,267"
    assert body["ask"] == "Tell me about Jerry Garcia in the Grateful Dead"


def test_someone_who_sat_in_and_then_joined_has_both_counts(client):
    body = client.get("/api/rows/person-bruce-hornsby").json()
    assert facts(body)["Sat in"] == "16 shows"
    assert facts(body)["In the band"] == "102 shows"
    assert "Shows" not in facts(body)


def test_a_venue_opens_to_its_shows_and_place(client):
    body = client.get("/api/rows/venue-winterland-san-francisco").json()
    assert body["kind"] == "venue"
    assert facts(body) == {"Shows": "59", "Years": "1967–1978", "Place": "San Francisco, CA"}
    assert body["play"]["venue_name"] == "Winterland"
    assert body["ask"] == "The Grateful Dead at Winterland"


def test_a_release_opens_to_its_date_and_show(client):
    body = client.get("/api/rows/release-veneta-or-1972-08-27-complete-sunshine-daydream-concert").json()
    assert body["kind"] == "release"
    assert facts(body) == {"Released": "September 13, 2013", "Show": "August 27, 1972, Old Renaissance Faire Grounds"}
    assert body["play"]["show_date"] == "1972-08-27"


def test_a_year_opens_to_its_shows_and_within_a_song_to_that_songs_year(client):
    year = client.get("/api/rows/1972").json()
    assert (year["kind"], year["title"]) == ("year", "1972")
    assert facts(year)["Shows"] == "86"
    assert facts(year)["Most played"] == "Playing In The Band, 82 times"
    assert year["play"]["show_date"].startswith("1972-")
    assert year["ask"] == "The Grateful Dead in 1972"

    scoped = client.get("/api/rows/1972", params={"scope": "song-dark-star"}).json()
    assert scoped["title"] == "Dark Star in 1972"
    assert facts(scoped)["Played"] == "36 times in 1972"
    assert scoped["play"]["tracks"][0]["title"] == "Dark Star"
    assert scoped["ask"] == "Dark Star in 1972"


def test_unresolved_rows_are_not_found(client):
    for row_id in ("song-no-such-song", "person-nobody", "venue-nowhere", "release-none", "1950", "Winterland", "gd-1977-05-08"):
        assert client.get(f"/api/rows/{row_id}").status_code == 404, row_id


def test_rows_share_the_lookup_rate_limit(store):
    with TestClient(create_app(settings=Settings(grid_rate_limit_per_minute=1), store=store, agent=object())) as limited:
        assert limited.get("/api/rows/song-dark-star").status_code == 200
        assert limited.get("/api/rows/song-china-cat-sunflower").status_code == 429


def test_only_rows_the_library_holds_open(store):
    ids = ["song-dark-star", "song-no-such-song", "person-ned-lagin", "1972", "1950", "San Francisco", "venue-winterland-san-francisco"]
    assert row_details.openable_ids(store, ids) == ["song-dark-star", "person-ned-lagin", "1972", "venue-winterland-san-francisco"]


def aggregation(rows, group_by, filters=None):
    key = "year" if group_by == "year" else "label"
    return {
        "aggregation_id": "agg-1",
        "query": {"dataset": "performances", "group_by": group_by, "filters": filters or {}},
        "columns": [{"key": key, "label": group_by.title(), "type": "temporal" if group_by == "year" else "categorical"}, {"key": "value", "label": "Performances", "type": "quantitative"}],
        "rows": rows,
        "metric_label": "Performances",
        "total": sum(row["value"] for row in rows),
        "excluded_count": 0,
    }


def test_chart_and_ranked_list_rows_say_which_open(store):
    from deadbot import composition, record_refs

    payload = aggregation(
        [{"id": "song-dark-star", "label": "Dark Star", "value": 232}, {"id": "song-gone", "label": "Gone", "value": 3}],
        "song",
    )
    open_ids, scope = row_details.chart_openings(store, payload)
    assert (open_ids, scope) == (["song-dark-star"], None)
    chart = composition._data_chart(payload, title="Most played", note=None)
    assert isinstance(chart, DataChartBlock)

    years = aggregation([{"year": 1972, "value": 36}, {"year": 1973, "value": 30}], "year", {"song_id": "song-dark-star"})
    assert row_details.chart_openings(store, years) == (["1972", "1973"], "song-dark-star")
    ranked = record_refs.ranked_list_block(years, count=None, title=None, note=None, row_notes={})
    assert isinstance(ranked, RankedListBlock)
    assert [row.id for row in ranked.rows] == ["1972", "1973"]


def test_a_question_from_an_opened_row_names_where_it_came_from(store):
    focus = AskFocus(label="Ned Lagin", block_type="person_roster", block_id="Who sat in", ids=["person-ned-lagin"], facts=["Shows: 33"])
    known = focus_ids(store, focus)
    assert known == {"person-ned-lagin"}
    note = focus_note(focus, known)
    assert "a name they opened in a roster" in note
    assert "person-ned-lagin" in note
