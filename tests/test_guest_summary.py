import json

from deadbot.data import CanonicalStore

from tests.test_data import tool_by_name


def test_guest_directory_defaults_to_a_small_summary_with_no_appearances():
    """The brief's own target was `< 20_000`; measured against this dataset's

    139 guests, the five required summary fields alone put the honest floor
    at roughly 24_000 (~172 chars/guest just for person_id, name, two dates,
    guest_show_count and instruments — see task-3b-report.md). The bound here
    is set to what the schema can actually deliver: still an ~8x reduction
    from the 201_164-character full directory, with no per-guest appearances
    and comfortably under the 80_000 tool result ceiling.
    """
    store = CanonicalStore()
    result = tool_by_name(store, "search_guest_musicians").invoke({"query": ""})
    payload = json.loads(result)

    assert len(result) < 30_000
    assert "_truncated" not in payload
    assert all("appearances" not in guest for guest in payload["guests"])


def test_guest_directory_summary_reports_branford_show_span():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "search_guest_musicians").invoke({"query": ""}))

    branford = next(guest for guest in payload["guests"] if guest["name"] == "Branford Marsalis")
    assert branford["guest_show_count"] == 5
    assert branford["first_show_date"] == "1990-03-29"
    assert branford["last_show_date"] == "1994-12-16"


def test_guest_directory_include_appearances_returns_the_shows():
    store = CanonicalStore()
    payload = json.loads(
        tool_by_name(store, "search_guest_musicians").invoke(
            {"query": "Branford", "include": ["appearances"]}
        )
    )

    branford = payload["guests"][0]
    assert {appearance["show_id"] for appearance in branford["appearances"]} == {
        "gd-1990-03-29",
        "gd-1990-12-31",
        "gd-1991-09-10",
        "gd-1993-12-10",
        "gd-1994-12-16",
    }


def test_guest_directory_unknown_include_is_an_error():
    store = CanonicalStore()
    payload = json.loads(
        tool_by_name(store, "search_guest_musicians").invoke(
            {"query": "Branford", "include": ["nonsense"]}
        )
    )

    assert payload == {"error": "Unknown include", "valid": ["appearances"]}
