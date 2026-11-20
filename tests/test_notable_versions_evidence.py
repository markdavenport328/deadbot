"""How get_song_notable_versions weighs and labels its evidence."""

import json

from deadbot.data import CanonicalStore
from deadbot.selection_signals import performance_show_date, release_families, release_family_root
from deadbot.tools import build_tools
from test_data import store_with_selection_evidence


def _versions(song: str, limit: int = 30) -> dict:
    tools = {tool.name: tool for tool in build_tools(store_with_selection_evidence())}
    return json.loads(tools["get_song_notable_versions"].invoke({"song_id_or_title": song, "limit": limit}))


def _on(payload: dict, show_date: str) -> list[dict]:
    return [item for item in payload["versions"] if item["show_date"] == show_date]


def test_a_release_family_is_one_decision():
    titles = {
        "album": "Europe ’72",
        "box": "Europe ’72: The Complete Recordings",
        "volume": "Europe ’72, Vol. 08: Rheinhalle, Düsseldorf",
        "lyceum": "Lyceum ’72: The Complete Recordings",
        "standalone": "Rockin’ the Rhein with the Grateful Dead",
        "live_dead": "Live/Dead",
    }
    dates = {
        "album": {"1972-04-24", "1972-05-03", "1972-05-26"},
        "box": {"1972-04-24", "1972-05-03"},
        "volume": {"1972-04-24"},
        "lyceum": {"1972-05-23", "1972-05-24"},
        "standalone": {"1972-04-24"},
        "live_dead": {"1969-01-26", "1969-02-27"},
    }
    family = release_families(titles, dates)
    assert len({family[key] for key in ("album", "box", "volume", "lyceum", "standalone")}) == 1
    assert family["live_dead"] != family["album"]


def test_two_editions_of_one_night_are_one_family_and_a_compilation_stays_separate():
    titles = {
        "a": "Here Comes Sunshine 1973",
        "b": "[1973‐06‐09] Here Comes Sunshine 1973 – Live at RFK Stadium",
        "c": "RFK Stadium, Washington, D.C. 6/10/73",
        "d": "June 10 1973 (RFK Stadium, Washington, D.C.)",
        "e": "Without a Net",
    }
    dates = {"a": {"1973-05-13", "1973-06-09", "1973-06-10"}, "b": {"1973-06-09"}, "c": {"1973-06-10"}, "d": {"1973-06-10"}, "e": {"1990-03-29", "1989-10-09"}}
    family = release_families(titles, dates)
    assert family["a"] == family["b"]
    assert family["c"] == family["d"]
    assert family["e"] not in {family["a"], family["c"]}


def test_family_root_and_show_date_helpers():
    assert release_family_root("Fillmore West 1969 February 27th") == release_family_root("Fillmore West 1969: The Complete Recordings")
    assert performance_show_date("gd-1972-08-27-dark-star") == "1972-08-27"
    assert performance_show_date("not-a-performance") is None


def test_release_families_count_once_in_the_source_count():
    payload = _versions("Dark Star")
    for item in payload["versions"]:
        assert item["release_families"] <= len(item["official_releases"])
        assert item["source_count"] == item["release_families"] + item["evidence"]["picks_naming_this_performance"]
    europe = _on(payload, "1972-04-08")[0]
    assert len(europe["official_releases"]) > europe["release_families"] >= 1
    assert all(release["release_family"] for release in europe["official_releases"])


def test_a_dark_star_vote_is_not_praise_for_the_nights_other_songs():
    # Headyversion records only Dark Star and Bird Song; none of its votes may reach another song.
    playing = _versions("Playing in the Band")
    assert not any(s["source"] == "headyversion" for item in playing["versions"] for s in item["selections"])
    morning_dew = _versions("Morning Dew")
    assert not any(s["source"] == "headyversion" and s["names"] == "the whole show" for item in morning_dew["versions"] for s in item["selections"])
    # The vote stays on Dark Star, naming the performance.
    dark_star = _versions("Dark Star")
    veneta = _on(dark_star, "1972-08-27")[0]
    vote = next(s for s in veneta["selections"] if s["source"] == "headyversion")
    assert vote["names"] == "this performance" and vote["fan_vote_count"] > 400 and vote["kind"] == "fan vote"


def test_a_pick_of_the_night_is_labeled_as_the_whole_show():
    versions = _versions("Playing in the Band")
    shows = [s for item in versions["versions"] for s in item["selections"] if s["source"] == "rolling-stone-australia"]
    assert shows and all(s["names"] == "the whole show" for s in shows)
    show_only = [item for item in versions["versions"] if item["evidence"]["picks_naming_the_whole_show"] and not item["evidence"]["picks_naming_this_performance"]]
    assert show_only and all(item["source_count"] == item["release_families"] for item in show_only)


def test_two_renditions_in_one_night_do_not_get_a_pin_it_cannot_make():
    # Headyversion's 1972-04-24 Dark Star: two Dark Stars that night, so neither is "this performance".
    versions = _on(_versions("Dark Star"), "1972-04-24")
    assert len(versions) == 2
    for item in versions:
        vote = next(s for s in item["selections"] if s["source"] == "headyversion")
        assert vote["names"].startswith("this song that night")
        assert item["evidence"]["picks_naming_this_performance"] == 0


def test_named_performances_lead_the_versions_fans_would_check_first():
    expected = {
        "Dark Star": {"1969-02-27", "1972-08-27"},
        "Morning Dew": {"1977-05-08"},
        "Scarlet Begonias": {"1977-05-08"},
        "Fire on the Mountain": {"1977-05-08"},
    }
    for song, dates in expected.items():
        top = {item["show_date"] for item in _versions(song, limit=5)["versions"]}
        assert dates <= top, (song, top)
    assert _versions("Morning Dew", limit=1)["versions"][0]["show_date"] == "1977-05-08"


def test_critic_performance_lists_are_attributed_and_carry_their_role():
    cornell = _on(_versions("Morning Dew"), "1977-05-08")[0]
    pick = next(s for s in cornell["selections"] if s["source"] == "guitar-world-50-best")
    assert pick["picked_by"] == "Blair Jackson, Guitar World"
    assert pick["kind"] == "critic's pick" and pick["pick_role"] == "main pick"
    assert pick["source_url"].startswith("https://www.guitarworld.com/")
    assert pick["names"] == "this performance"


def test_without_selection_evidence_versions_still_order_by_release_families():
    tools = {tool.name: tool for tool in build_tools(CanonicalStore())}
    payload = json.loads(tools["get_song_notable_versions"].invoke({"song_id_or_title": "Dark Star", "limit": 5}))
    counts = [item["source_count"] for item in payload["versions"]]
    assert counts == sorted(counts, reverse=True)
    assert payload["signal_summary"]["selection_evidence_available"] is False
