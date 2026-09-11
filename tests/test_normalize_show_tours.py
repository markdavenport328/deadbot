"""Tests for scripts/normalize_show_tours.py's tour_name promotion rules."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import normalize_show_tours as nst  # noqa: E402


def make_show(show_id: str, show_date: str, tour_name: str = "", notes: str = "") -> dict[str, str]:
    return {
        "show_id": show_id,
        "show_date": show_date,
        "venue_id": "venue-x",
        "tour_name": tour_name,
        "event_name": "",
        "notes": notes,
        "source_key": "gdshowsdb",
        "source_record_id": show_id,
    }


def tour(name: str, start: str, end: str, source_url: str = "https://api.relisten.net/x", retrieved_at: str = "2026-09-11T00:00:00Z") -> dict:
    return {
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "uuid": "tour-uuid",
        "start_date": start,
        "end_date": end,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }


def test_fills_blank_tour_name_for_a_named_tour_date():
    shows = [make_show("gd-1972-04-08", "1972-04-08")]
    named = {"1972-04-08": tour("Europe 1972", "1972-04-07T00:00:00Z", "1972-05-26T00:00:00Z")}

    result, review, counts = nst.normalize(shows, named)

    assert result[0]["tour_name"] == "Europe 1972"
    assert "Tour sourced from Relisten" in result[0]["notes"]
    assert counts["filled_from_relisten"] == 1
    assert review == []


def test_leaves_blank_when_no_named_tour_for_the_date():
    shows = [make_show("gd-1965-05-05", "1965-05-05")]

    result, review, counts = nst.normalize(shows, {})

    assert result[0]["tour_name"] == ""
    assert counts["no_named_tour_for_date"] == 1


def test_never_overwrites_a_preexisting_foreign_tour_name():
    shows = [
        make_show(
            "gd-1972-08-27",
            "1972-08-27",
            tour_name="Grateful Dead Summer 1972 West Coast/Mountain",
            notes="Normalized from JerryBase event 19720827-01.",
        )
    ]
    # Even if the date happened to also carry a Relisten named tour, the
    # existing hand-curated value must not be replaced.
    named = {"1972-08-27": tour("Europe 1972", "1972-04-07T00:00:00Z", "1972-05-26T00:00:00Z")}

    result, review, counts = nst.normalize(shows, named)

    assert result[0]["tour_name"] == "Grateful Dead Summer 1972 West Coast/Mountain"
    assert result[0]["notes"] == "Normalized from JerryBase event 19720827-01."
    assert counts["already_had_tour_name"] == 1
    assert counts["filled_from_relisten"] == 0


def test_holds_an_unrecognized_source_tour_name_instead_of_promoting_it():
    shows = [make_show("gd-1999-01-01", "1999-01-01")]
    named = {"1999-01-01": tour("Reunion Tour 1999", "1999-01-01T00:00:00Z", "1999-01-02T00:00:00Z")}

    result, review, counts = nst.normalize(shows, named)

    assert result[0]["tour_name"] == ""
    assert counts["unrecognized_tour_name_held"] == 1
    assert review[0]["review_type"] == "unrecognized-relisten-tour-name"
    assert review[0]["source_tour_name"] == "Reunion Tour 1999"


def test_shared_date_shows_both_get_the_tour_and_note_each_other():
    shows = [
        make_show("gd-1970-05-15-0", "1970-05-15"),
        make_show("gd-1970-05-15-1", "1970-05-15"),
    ]
    named = {"1970-05-15": tour("Spring 1970", "1970-04-26T00:00:00Z", "1970-05-17T00:00:00Z")}

    result, review, counts = nst.normalize(shows, named)

    assert all(row["tour_name"] == "Spring 1970" for row in result)
    assert "gd-1970-05-15-1" in result[0]["notes"]
    assert "gd-1970-05-15-0" in result[1]["notes"]
    assert counts["filled_from_relisten"] == 2


def test_rerun_is_idempotent_recomputing_a_previously_written_row():
    shows = [make_show("gd-1972-04-08", "1972-04-08")]
    named = {"1972-04-08": tour("Europe 1972", "1972-04-07T00:00:00Z", "1972-05-26T00:00:00Z")}

    first_pass, _, _ = nst.normalize(shows, named)
    second_pass, _, counts = nst.normalize(first_pass, named)

    assert first_pass == second_pass
    # The row is recomputed from scratch (not skipped as "already had a
    # foreign tour_name"), because it carries this normalizer's own marker.
    assert counts["already_had_tour_name"] == 0
    assert counts["filled_from_relisten"] == 1


def test_rerun_clears_a_previously_written_row_if_the_source_no_longer_supports_it():
    shows = [make_show("gd-1972-04-08", "1972-04-08")]
    named = {"1972-04-08": tour("Europe 1972", "1972-04-07T00:00:00Z", "1972-05-26T00:00:00Z")}
    first_pass, _, _ = nst.normalize(shows, named)

    # Simulate a rerun against a raw file that no longer carries this date's
    # tour (e.g. a corrected upstream record).
    second_pass, _, counts = nst.normalize(first_pass, {})

    assert second_pass[0]["tour_name"] == ""
    assert "Tour sourced from Relisten" not in second_pass[0]["notes"]
    assert counts["no_named_tour_for_date"] == 1
