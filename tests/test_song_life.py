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


def test_length_is_the_tape_track_that_plays_and_ignores_fragments(terrapin):
    boston = by_date(terrapin, "1993-09-29")
    assert (boston.seconds, boston.length_source) == (1514, "tape")
    # Dave's Picks 29 runs the debut 12:25; the tape track the page plays is 11:07.
    debut = by_date(terrapin, "1977-02-26")
    assert (debut.seconds, debut.length_source, debut.tape_seconds) == (667, "tape", 667)
    # A 13-second tape track is a fragment, not the performance's length.
    assert by_date(terrapin, "1977-02-27").seconds is None


def test_the_one_length_rule():
    from deadbot.sequences import Track

    lp = song_life.ReleaseLength("release-lp", "Europe '72", 786)
    box = song_life.ReleaseLength("release-box", "Europe '72: The Complete Recordings", 1137)
    tape = Track(url="https://archive.org/download/tape/t01.mp3", duration_seconds=541)
    # A playable tape track is the length, whatever any release runs.
    assert song_life.stated_length(tape, [lp, box], "p") == song_life.Length(541, "tape")
    # No tape track: the fullest release, named, so it is never read as another record's.
    fullest = song_life.stated_length(None, [lp, box], "p")
    assert fullest == song_life.Length(1137, "release", "Europe '72: The Complete Recordings")
    assert fullest.fields() == {"length_seconds": 1137, "length_from_release": "Europe '72: The Complete Recordings"}
    assert song_life.Length(541, "tape").fields() == {"length_seconds": 541}
    # A tape track with no length, or a fragment, leaves the length unknown
    # instead of putting a release's length beside the tape's play button.
    untimed = Track(url=tape.url, duration_seconds=None)
    fragment = Track(url=tape.url, duration_seconds=13)
    assert song_life.stated_length(untimed, [box], "p") is None
    assert song_life.stated_length(fragment, [box], "p") is None
    assert song_life.stated_length(None, [], "p") is None
    excerpt = song_life.ReleaseLength("release-30", "30 Days of Dead", 447)
    full = song_life.ReleaseLength("release-dp", "Dave's Picks", 1263)
    assert song_life.fullest_release([excerpt, full]) == full
    assert song_life.fullest_release([song_life.ReleaseLength("r", "R", 30)]).seconds == 30


def test_releases_and_guests(terrapin):
    assert by_date(terrapin, "1977-05-28").releases[0].startswith("To Terrapin")
    assert [g.name for g in by_date(terrapin, "1989-12-06").guests] == ["Clarence Clemons"]


def test_year_summaries_span_every_year_with_counts_and_lengths(terrapin):
    rows = year_summaries(terrapin)
    assert [row["year"] for row in rows] == list(range(1977, 1996))
    y1979 = next(row for row in rows if row["year"] == 1979)
    assert y1979["count"] == 23
    assert y1979["top_next"] == {"title": "Playing In The Band", "count": 20}
    assert y1979["longest"] == {"performance_id": "gd-1979-11-06-terrapin-station-2-1", "seconds": 926}
    assert y1979["median_seconds"] == 767
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
    assert facts[("longest", "1993-09-29")] == ["longest ever (25:14)"]
    assert facts[("inside_another_song", "1981-12-31")] == ["inside Playing In The Band"]
    assert facts[("show_picks", "1981-12-31")] == ["its show was picked by Charlie Miller"]
    assert facts[("guests", "1989-12-06")] == ["with Clarence Clemons (saxophone)"]
    for items in kinds.values():
        assert len(items) <= song_life.STANDOUT_GROUP_CEILING
        assert [item["date"] for item in items] == sorted(item["date"] for item in items)
    # A long kind keeps a sample spanning the song's life and says how many it left out.
    releases = [item["date"] for item in kinds["releases"]]
    assert releases[0][:4] == "1977" and releases[-1][:4] == "1991" and left_out["releases"] > 0
    # Encores are their own pattern, not also "a later set" or "opened a set".
    assert "encore 6 times, 1977–1991" in patterns
    assert "opened a set 12 times, 1977–1985" in patterns


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
    assert kinds["longest"][0]["facts"] == ["longest ever (5:00)"]
    assert kinds["picks"][0]["facts"] == ["picked by Charlie Miller"]
    assert left_out == {} and patterns == []
    assert standouts([]) == ({}, {}, [])


@pytest.mark.parametrize("song_id", [TERRAPIN, "song-dark-star", "song-sugar-magnolia", "song-drums"])
def test_tool_payload_stays_compact(sqlite_store, song_id):
    payload = song_life.tool_payload(sqlite_store, sqlite_store.one("songs", song_id))
    assert len(json.dumps(payload, ensure_ascii=False)) < 10000
    assert payload["years"][0]["count"] > 0


def test_a_released_performance_with_a_tape_states_the_tape_length(sqlite_store):
    pitb = by_date(song_life.life_performances(sqlite_store, "song-playing-in-the-band"), "1974-02-22")
    assert (pitb.seconds, pitb.length_source) == (1244, "tape")
    # The tape track of the Lyceum Truckin' runs 9:01; Europe '72 cuts it to
    # 13:06 with the jam and the complete recordings run 18:57. Each release
    # keeps its own length under its own title.
    truckin = by_date(song_life.life_performances(sqlite_store, "song-truckin"), "1972-05-26")
    assert (truckin.seconds, truckin.length_source, truckin.tape_seconds) == (541, "tape", 541)
    on_releases = {r.title: r.seconds for r in song_life.release_lengths(sqlite_store, [truckin.performance_id])[truckin.performance_id]}
    assert on_releases["Europe ’72"] == 786 and on_releases["Europe ’72: The Complete Recordings"] == 1137


def test_every_tool_states_the_same_length_as_the_timeline(sqlite_store):
    import json

    from deadbot.tools import build_tools

    tools = {tool.name: tool for tool in build_tools(sqlite_store)}
    lengths = song_life.performance_lengths(sqlite_store, ["gd-1974-03-23-cassidy-1-12", "gd-1972-05-26-truckin-2-1"])
    assert lengths == {"gd-1974-03-23-cassidy-1-12": 232, "gd-1972-05-26-truckin-2-1": 541}
    versions = json.loads(tools["get_song_notable_versions"].invoke({"song_id_or_title": "Cassidy", "limit": 30}))
    debut = next(item for item in versions["versions"] if item["performance_id"] == "gd-1974-03-23-cassidy-1-12")
    assert debut["length"] == "3:52"
    assert "archive_track_duration_seconds" not in json.dumps(versions)
    listed = json.loads(tools["list_song_performances"].invoke({"song_id_or_title": "Cassidy", "offset": 0, "limit": 5}))
    assert listed["performances"][0]["length"] == "3:52"
    assert "archive_track_duration_seconds" not in json.dumps(listed)
    show = json.loads(tools["get_show"].invoke({"show_id_or_date": "1972-05-26"}))
    row = next(row for row in show["performances"] if row["performance_id"] == "gd-1972-05-26-truckin-2-1")
    assert row["length"] == "9:01" and row["audio"] is True and "length_from_release" not in row
    one = json.loads(tools["get_performance"].invoke({"performance_id": "gd-1972-05-26-truckin-2-1"}))
    assert one["length"] == "9:01"
    albums = {release["title"]: release.get("length") for release in one["official_releases"]}
    assert albums["Europe ’72"] == "13:06" and albums["Europe ’72: The Complete Recordings"] == "18:57"


def test_version_picks_and_show_picks_are_told_apart(sqlite_store):
    fire = by_date(song_life.life_performances(sqlite_store, "song-fire-on-the-mountain"), "1977-05-13")
    assert Signal("Charlie Miller", "performance") in fire.signals
    # Release confirmations are not picks.
    assert not any(s.voice == "Dead.net" for p in song_life.life_performances(sqlite_store, TERRAPIN) for s in p.signals)


def test_picks_of_a_performance_and_of_its_show_are_separate_kinds(sqlite_store):
    kinds, _left_out, _patterns = standouts(song_life.life_performances(sqlite_store, "song-dark-star"), per_kind=2)
    assert kinds["picks"] and all(fact.startswith("picked by") for item in kinds["picks"] for fact in item["facts"])
    assert all(fact.startswith("its show was picked by") for item in kinds.get("show_picks", []) for fact in item["facts"])
