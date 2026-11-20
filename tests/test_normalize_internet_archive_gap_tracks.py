"""The gap pass: a tape track for a song that has none, only where play starts on that song."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import normalize_internet_archive_gap_tracks as gap  # noqa: E402
import normalize_internet_archive_tracks as ia  # noqa: E402

SONGS = {
    "s-gl": "Good Lovin'",
    "s-drums": "Drums",
    "s-space": "Space",
    "s-crypt": "Cryptical Envelopment",
    "s-other": "The Other One",
    "s-truckin": "Truckin'",
    "s-nfa": "Not Fade Away",
    "s-gdtrfb": "Goin' Down The Road Feelin' Bad",
    "s-dupree": "Dupree's Diamond Blues",
    "s-star": "Dark Star",
    "s-scarlet": "Scarlet Begonias",
    "s-fire": "Fire On The Mountain",
    "s-sugar": "Sugar Magnolia",
    "s-comes": "Comes A Time",
    "s-bertha": "Bertha",
}
MATCHER = gap.Matcher(SONGS)


def _show(*song_ids: str) -> list[dict]:
    return [{"performance_id": f"p{index}", "song_id": song_id, "set_number": "1"} for index, song_id in enumerate(song_ids)]


def _fill(show, anchors, tracks, medleys=True, wanted=None):
    wanted = set(range(len(show))) - set(anchors) if wanted is None else wanted
    found, _covered = gap.fill_gaps_on_tape(show, SONGS, anchors, tracks, wanted, MATCHER, medleys=medleys, whole_songs=True)
    return found


def test_a_title_names_a_song_by_shorthand_initials_or_a_fragment():
    assert MATCHER.relation("Drumz >", "Drums") == ("shorthand", False)
    assert MATCHER.relation("GDTRFB>", "Goin' Down The Road Feelin' Bad") == ("initials", False)
    assert MATCHER.relation("Dupree's", "Dupree's Diamond Blues") == ("fragment", False)
    assert MATCHER.relation("Dark Star Jam >", "Dark Star") == ("fragment", False)
    # Another song's exact name is never a fragment of this one.
    assert MATCHER.relation("The Other One", "Cryptical Envelopment") == ("", False)


def test_words_around_a_title_that_mean_something_else_are_refused():
    assert MATCHER.relation("Jam out of Truckin'", "Truckin'") == ("", False)
    assert MATCHER.relation("Not Fade Away tease", "Not Fade Away") == ("", False)
    assert MATCHER.relation("Sugar Magnolia - Comes A Time", "Comes A Time") == ("", False)
    assert MATCHER.relation("Jam", "Dark Star") == ("", False)


def test_a_medley_file_names_only_the_song_it_opens_with():
    assert MATCHER.relation("Scarlet Begonias > Fire On The Mountain", "Scarlet Begonias") == ("title", True)
    assert MATCHER.relation("Scarlet Begonias > Fire On The Mountain", "Fire On The Mountain") == ("", False)
    assert MATCHER.relation("That's It For The Other One ->", "Cryptical Envelopment") == ("suite", True)
    assert MATCHER.relation("That's It For The Other One ->", "The Other One") == ("", False)
    # A trailing segue mark is not a medley.
    assert MATCHER.relation("Dark Star>", "Dark Star") == ("title", False)


def test_a_variant_title_between_its_neighbours_is_linked():
    show = _show("s-bertha", "s-drums", "s-space", "s-sugar")
    found = _fill(show, {0: 1, 3: 4}, {1: "Bertha", 2: "Drumz >", 3: "Space >", 4: "Sugar Magnolia"})
    assert found == [(1, 2, "shorthand", False), (2, 3, "title", False)]


def test_one_track_for_a_song_played_twice_goes_to_the_first_pass_when_it_follows_its_neighbour():
    show = _show("s-bertha", "s-gl", "s-drums", "s-gl", "s-sugar")
    tracks = {1: "Bertha", 2: "Good Lovin'", 3: "Sugar Magnolia"}
    assert _fill(show, {0: 1, 4: 3}, tracks) == [(1, 2, "title", False)]
    # The later pass is inside that file, so it is reported as covered, not left to another tape.
    _found, covered = gap.fill_gaps_on_tape(show, SONGS, {0: 1, 4: 3}, tracks, {1, 2, 3}, MATCHER, whole_songs=True)
    assert covered == {1: {3}}
    # With an unexplained track between the neighbour and the song's track, nothing is linked.
    tracks = {1: "Bertha", 2: "Unknown Jam", 3: "Good Lovin'", 4: "Sugar Magnolia"}
    assert _fill(show, {0: 1, 4: 4}, tracks) == []


def test_a_song_already_linked_elsewhere_still_competes_for_this_tapes_track():
    # The first Good Lovin' plays from another tape. This tape's one "Good
    # Lovin'" track is still that first pass, never the reprise.
    show = _show("s-bertha", "s-gl", "s-drums", "s-gl", "s-sugar")
    tracks = {1: "Bertha", 2: "Good Lovin'", 3: "Sugar Magnolia"}
    assert _fill(show, {0: 1, 4: 3}, tracks, wanted={2, 3}) == []


def test_a_file_that_runs_on_into_the_next_song_is_recognized():
    show = _show("s-bertha", "s-scarlet", "s-fire", "s-sugar")
    # "Scarlet Begonias" then directly "Sugar Magnolia": Fire has no track, so the file holds it too.
    assert gap.runs_on(1, 2, {0: 1, 1: 2, 3: 3}, [1, 2, 3], show)
    # A track between them may be the missing song under another name.
    assert not gap.runs_on(1, 2, {0: 1, 1: 2, 3: 4}, [1, 2, 3, 4], show)
    # A song played around a break is the whole of that song.
    sandwich = _show("s-bertha", "s-gl", "s-drums", "s-gl", "s-sugar")
    assert not gap.runs_on(1, 2, {0: 1, 1: 2, 4: 3}, [1, 2, 3], sandwich)


def test_medleys_are_left_out_unless_asked_for_and_never_reach_the_second_song():
    show = _show("s-bertha", "s-scarlet", "s-fire", "s-sugar")
    tracks = {1: "Bertha", 2: "Scarlet Begonias > Fire On The Mountain", 3: "Sugar Magnolia"}
    assert _fill(show, {0: 1, 3: 3}, tracks, medleys=False) == []
    assert _fill(show, {0: 1, 3: 3}, tracks, medleys=True) == [(1, 2, "title", True)]


def test_a_tape_whose_order_disagrees_with_the_setlist_is_left_alone():
    show = _show("s-bertha", "s-drums", "s-sugar")
    assert _fill(show, {0: 5, 2: 3}, {3: "Sugar Magnolia", 4: "Drumz", 5: "Bertha"}) == []


def test_a_track_is_playable_only_with_an_mp3_that_runs_to_the_end():
    flac = {"name": "t01.flac", "source": "original", "format": "Flac", "track": "1", "title": "Bertha", "length": "400.0"}
    whole = {"name": "t01.mp3", "source": "derivative", "format": "VBR MP3", "original": "t01.flac", "length": "06:40"}
    cut = {**whole, "length": "03:00"}
    assert gap.playable({"raw_payload": {"files": [flac, whole]}}, flac)
    assert not gap.playable({"raw_payload": {"files": [flac, cut]}}, flac)
    assert not gap.playable({"raw_payload": {"files": [flac]}}, flac)


def test_canonical_gap_rows_never_double_a_song_or_a_track():
    with (ROOT / "data" / "canonical" / "performance_recordings.csv").open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["notes"].startswith(gap.GAP_NOTE_PREFIX)]
    performances = [row["performance_id"] for row in rows]
    assert len(performances) == len(set(performances))
    tracks = [(row["recording_id"], row["track_number"]) for row in rows]
    assert len(tracks) == len(set(tracks))
    assert all(not row["start_seconds"] for row in rows)
