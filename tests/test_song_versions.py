"""song_versions: chosen versions of one song, hydrated from the store."""

import logging

import pytest

from deadbot import finish
from deadbot.data import CanonicalStore

FIRST = "gd-1968-01-17-dark-star-1-2"
DAVES_PICKS = "gd-1969-11-02-dark-star-1-12"
LONGEST = "gd-1973-12-06-dark-star-2-5"
NO_TAPE = "gd-1968-01-26-dark-star-1-11"


@pytest.fixture(scope="module")
def store():
    return CanonicalStore()


def _item(ids, **extra):
    return finish.validate_body_item({"type": "song_versions", "performance_ids": ids, **extra}, where="planned")


def _resolve(store, ids, grounded_ids=None, **extra):
    payloads = [{"versions": [{"performance_id": pid} for pid in (grounded_ids if grounded_ids is not None else ids)]}]
    grounded = finish.grounded_context(payloads)
    return finish.resolve_items([_item(ids, **extra)], grounded, payloads, store)[0]


def test_rows_hydrate_in_the_model_order(store):
    (block,) = _resolve(store, [LONGEST, FIRST], title="Two Dark Stars")
    assert block.type == "song_versions" and block.title == "Two Dark Stars"
    assert block.song.song_id == "song-dark-star" and block.song.title == "Dark Star"
    assert [row.performance_id for row in block.rows] == [LONGEST, FIRST]
    cleveland = block.rows[0]
    assert cleveland.venue_name == "Cleveland Convention Center" and cleveland.show_date == "1973-12-06"
    assert cleveland.city == "Cleveland, OH"
    assert cleveland.tape_seconds == 2612 and cleveland.length_seconds == 2612
    assert cleveland.track.audio_url.endswith("gd73-12-06d3t01.mp3") and cleveland.track.title == "Dark Star"
    assert cleveland.release is None


def test_the_release_length_is_preferred_over_the_tape(store):
    (block,) = _resolve(store, [FIRST, DAVES_PICKS])
    row = block.rows[1]
    assert row.length_seconds == 1832 and row.tape_seconds == 1806
    assert row.release.release_id.startswith("release-daves-picks-volume-43")
    assert row.release.url and row.track is not None


def test_a_version_without_a_tape_keeps_its_row(store):
    (block,) = _resolve(store, [NO_TAPE, FIRST])
    row = block.rows[0]
    assert row.performance_id == NO_TAPE and row.track is None and row.tape_seconds is None
    assert row.venue_name


def test_an_ungrounded_or_unknown_id_is_dropped_with_a_log(store, caplog):
    caplog.set_level(logging.INFO)
    (block,) = _resolve(store, [FIRST, LONGEST, "gd-nowhere-dark-star-1-1"], grounded_ids=[FIRST, "gd-nowhere-dark-star-1-1"])
    assert [row.performance_id for row in block.rows] == [FIRST]
    assert "dropped" in caplog.text


def test_nothing_resolved_keeps_the_models_title_as_text(store):
    blocks = _resolve(store, [FIRST, LONGEST], grounded_ids=[], title="Two Dark Stars")
    assert [block.type for block in blocks] == ["editorial"]


def test_more_than_eight_are_truncated_not_rejected(store, caplog):
    ids = [r["performance_id"] for r in store.rows_in("performances", "song_id", ["song-dark-star"])][:12]
    (block,) = _resolve(store, ids)
    assert [row.performance_id for row in block.rows] == ids[:8]
    assert "truncated" in caplog.text


def test_notes_attach_only_where_given(store):
    (block,) = _resolve(store, [FIRST, LONGEST], notes={FIRST: " The first one on tape. ", "unknown": "x"})
    assert [row.note for row in block.rows] == ["The first one on tape.", None]


def test_the_plan_reads_leniently():
    item = finish.validate_body_item(
        {"type": "song_versions", "performance_ids": [FIRST, LONGEST], "titel": "misspelt", "extra": 1}, where="planned"
    )
    assert item.type == "song_versions" and item.title is None and item.notes is None
    plan = finish.FinishPlan.model_validate(
        {"lead": "Five of them.", "groups": [{"presentation": "collection", "items": [{"type": "song_versions", "performance_ids": [FIRST, LONGEST], "notes": {FIRST: "First."}}]}]}
    )
    assert plan.groups[0].items[0].type == "song_versions"


def test_criteria_and_judgments_compare_the_versions(store):
    (block,) = _resolve(
        store,
        [FIRST, LONGEST],
        criteria=["Length", "What follows"],
        judgments={FIRST: ["Under three minutes", "China Cat"], LONGEST: ["Over forty minutes", 7], "elsewhere": ["x"]},
    )
    assert block.criteria == ["Length", "What follows"]
    assert block.rows[0].judgments == ["Under three minutes", "China Cat"]
    # A judgment that is not text keeps its place, empty, so the rest still line up with the criteria.
    assert block.rows[1].judgments == ["Over forty minutes", ""]


def test_bad_criteria_or_notes_keep_the_rows(store):
    (block,) = _resolve(store, [FIRST, LONGEST], criteria="Length", judgments=["x"], notes={FIRST: "The first.", LONGEST: 3})
    assert block.criteria == [] and [row.judgments for row in block.rows] == [[], []]
    assert block.rows[0].note == "The first." and block.rows[1].note is None
