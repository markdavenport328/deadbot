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
    assert y1979["longest"] == {"performance_id": "gd-1979-11-06-terrapin-station-2-1", "seconds": 925}
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
