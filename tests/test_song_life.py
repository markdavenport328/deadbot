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
    rows = year_summaries(terrapin)
    assert [row["year"] for row in rows] == list(range(1977, 1996))
    y1979 = next(row for row in rows if row["year"] == 1979)
    assert y1979["count"] == 23
    assert y1979["top_next"] == {"title": "Playing In The Band", "count": 20}
    assert y1979["longest"] == {"performance_id": "gd-1979-11-06-terrapin-station-2-1", "seconds": 937}
    assert y1979["median_seconds"] == 758
    # The library states each year's facts; choosing what to feature is the model's.
    assert "pick" not in y1979


def test_gap_years_are_zero_and_have_no_pick(csv_store):
    rows = year_summaries(song_life.life_performances(csv_store, "song-dark-star"))
    y1975 = next(row for row in rows if row["year"] == 1975)
    assert y1975 == {"year": 1975, "count": 0, "median_seconds": None, "longest": None, "top_next": None}


def test_a_song_played_once(csv_store):
    data = song_life.card_data(csv_store, "song-i-ll-go-crazy")
    assert data["performance_count"] == 1
    assert [row["count"] for row in data["year_summaries"]] == [1]


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


def test_stores_agree_on_facts(csv_store, sqlite_store):
    csv_rows = song_life.life_performances(csv_store, TERRAPIN)
    sqlite_rows = song_life.life_performances(sqlite_store, TERRAPIN)
    key = lambda p: (p.performance_id, p.seconds, p.previous, p.next, p.releases, p.guests, p.audio_url)
    assert [key(p) for p in csv_rows] == [key(p) for p in sqlite_rows]


def test_standouts_are_grouped_by_kind_in_date_order_without_ranking(sqlite_store):
    kinds, left_out, patterns = standouts(song_life.life_performances(sqlite_store, TERRAPIN))
    assert list(kinds) == [kind for kind in song_life.STANDOUT_KINDS if kind in kinds]
    facts = {(kind, item["date"]): item["facts"] for kind, items in kinds.items() for item in items}
    assert facts[("firsts_and_lasts", "1977-02-26")] == ["first performance"]
    assert facts[("firsts_and_lasts", "1995-07-08")] == ["last performance"]
    assert facts[("longest", "1993-09-29")] == ["longest on record (25:14)"]
    assert facts[("inside_another_song", "1981-12-31")] == ["inside Playing In The Band"]
    assert facts[("show_picks", "1981-12-31")] == ["its show was picked by Charlie Miller"]
    assert facts[("guests", "1989-12-06")] == ["with Clarence Clemons (saxophone)"]
    for items in kinds.values():
        assert len(items) <= song_life.STANDOUT_GROUP_CEILING
        assert [item["date"] for item in items] == sorted(item["date"] for item in items)
    # A long kind keeps a sample spanning the song's life and says how many it left out.
    releases = [item["date"] for item in kinds["releases"]]
    assert releases[0][:4] == "1977" and releases[-1][:4] == "1991" and left_out["releases"] > 0
    assert "opened a set 17 times, 1977–1991" in patterns


def test_a_long_kind_is_sampled_evenly():
    assert song_life._spread(list(range(10)), 4) == [0, 3, 6, 9]
    assert song_life._spread([1, 2], 6) == [1, 2]


def test_common_placements_become_patterns_not_standouts(sqlite_store):
    kinds, _left_out, patterns = standouts(song_life.life_performances(sqlite_store, "song-dark-star"))
    assert "opened the show 20 times, 1968–1970" in patterns
    assert not any("opened the show" in fact for items in kinds.values() for item in items for fact in item["facts"])


def test_standouts_of_a_tiny_song():
    lone = LifePerformance(
        performance_id="p1", show_id="s1", show_date="1970-01-01", venue_name="Hall", city=None, set_number=2,
        set_label="Set 2", position_in_set=3, encore=False, previous=None, next=None, seconds=300,
        length_source="tape", audio_url=None, tape_seconds=300, releases=(), signals=(Signal("Charlie Miller", "performance"),), guests=(),
    )
    kinds, left_out, patterns = standouts([lone])
    assert kinds["firsts_and_lasts"][0]["facts"] == ["first performance", "last performance"]
    assert kinds["longest"][0]["facts"] == ["longest on record (5:00)"]
    assert kinds["picks"][0]["facts"] == ["picked by Charlie Miller"]
    assert left_out == {} and patterns == []
    assert standouts([]) == ({}, {}, [])


@pytest.mark.parametrize("song_id", [TERRAPIN, "song-dark-star", "song-sugar-magnolia", "song-drums"])
def test_tool_payload_stays_compact(sqlite_store, song_id):
    payload = song_life.tool_payload(sqlite_store, sqlite_store.one("songs", song_id))
    assert len(json.dumps(payload, ensure_ascii=False)) < 10000
    assert payload["years"][0]["count"] > 0
    assert payload["stops_note"]


def test_disagreeing_releases_take_the_length_nearest_the_tape(sqlite_store):
    # A 30 Days of Dead excerpt (447s) must not beat the full release (1263s); the tape runs 1244s.
    pitb = by_date(song_life.life_performances(sqlite_store, "song-playing-in-the-band"), "1974-02-22")
    assert (pitb.seconds, pitb.length_source) == (1263, "release")
    assert song_life._release_length([447, 1263], None) == 1263
    assert song_life._release_length([30], 500) == 30


def test_version_picks_and_show_picks_are_told_apart(sqlite_store):
    fire = by_date(song_life.life_performances(sqlite_store, "song-fire-on-the-mountain"), "1977-05-13")
    assert Signal("Charlie Miller", "performance") in fire.signals
    # Release confirmations are not picks.
    assert not any(s.voice == "Dead.net" for p in song_life.life_performances(sqlite_store, TERRAPIN) for s in p.signals)


def test_picks_of_a_performance_and_of_its_show_are_separate_kinds(sqlite_store):
    kinds, _left_out, _patterns = standouts(song_life.life_performances(sqlite_store, "song-dark-star"), per_kind=2)
    assert kinds["picks"] and all(fact.startswith("picked by") for item in kinds["picks"] for fact in item["facts"])
    assert all(fact.startswith("its show was picked by") for item in kinds.get("show_picks", []) for fact in item["facts"])
