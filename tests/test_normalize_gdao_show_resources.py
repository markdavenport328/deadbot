"""Tests for the GDAO show-resource normalizer.

Every test builds its own raw file and its own canonical CSVs; nothing reads
``data/canonical`` and nothing reaches the network.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "normalize"))
import normalize_gdao_show_resources as ngs  # noqa: E402


SHOWS = [
    {"show_id": "gd-1977-05-22", "show_date": "1977-05-22"},
    {"show_id": "gd-1989-07-17", "show_date": "1989-07-17"},
    {"show_id": "gd-1989-07-18", "show_date": "1989-07-18"},
    # 1968-10-20 carries two canonical shows, an early and a late set.
    {"show_id": "gd-1968-10-20", "show_date": "1968-10-20"},
    {"show_id": "gd-1968-10-20-late", "show_date": "1968-10-20"},
]
EXISTING_RESOURCE = {
    "resource_id": "resource-gdao-veneta-field-trip-part-2",
    "resource_type": "eyewitness-memoir",
    "title": "A FIELD TRIP account",
    "creator": "Victor Zboralski",
    "source_name": "Grateful Dead Archive Online / UC Santa Cruz Library",
    "source_url": "https://www.gdao.org/items/show/1694370",
    "published_date": "2026-08-20",
    "notes": "Later personal recollection.",
}
EXISTING_SHOW_ROW = {
    "resource_id": "resource-gdao-veneta-field-trip-part-2",
    "show_id": "gd-1972-08-27",
    "relationship_type": "about",
    "notes": "Reviewed by hand.",
}


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def canonical_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "canonical"
    _write_csv(directory / "shows.csv", SHOWS, ["show_id", "show_date"])
    _write_csv(directory / "resources.csv", [EXISTING_RESOURCE], ngs.RESOURCE_FIELDS)
    _write_csv(directory / "resource_shows.csv", [EXISTING_SHOW_ROW], ngs.RESOURCE_SHOW_FIELDS)
    return directory


def item(
    item_id: int,
    *,
    title: str = "Sportatorium poster",
    item_type: str = "Poster",
    temporal: tuple[str, ...] = ("1977-05-22T00:00:00Z",),
    date: tuple[str, ...] = (),
    sortable: tuple[str, ...] = (),
    creator: str = "Kelley, Alton",
    coverage: tuple[str, ...] = ("Sportatorium - May 22, 1977",),
    description: str = "",
    queried_dates: tuple[str, ...] = ("1977-05-22",),
) -> dict:
    return {
        "source": "gdao",
        "source_record_id": str(item_id),
        "retrieved_at": "2026-09-08T00:00:00Z",
        "source_url": f"https://www.gdao.org/items/show/{item_id}",
        "raw_payload": {
            "record_type": "item",
            "host": "www.gdao.org",
            "site_name": "Grateful Dead Archive Online",
            "source_name": "Grateful Dead Archive Online / UC Santa Cruz Library",
            "item_id": item_id,
            "title": title,
            "item_type": item_type,
            "resource_template_id": 26,
            "collections": ["Grateful Dead Archive"],
            "dcterms_type": "",
            "format": "",
            "creator": creator,
            "date_fields": {"dcterms:temporal": list(temporal), "dcterms:date": list(date), "gdao:sortableDate": list(sortable)},
            "coverage": list(coverage),
            "description": description,
            "queried_dates": list(queried_dates),
            "request_url": "https://www.gdao.org/api/items?x=1",
            "http_status": 200,
        },
    }


def raw_file(tmp_path: Path, items: list[dict], *, requested: tuple[str, ...] = ("1977-05-22",), status: str = "ok") -> Path:
    path = tmp_path / "raw" / ngs.RAW_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    head = {
        "source": "gdao",
        "source_record_id": "gdao-show-items:www.gdao.org",
        "retrieved_at": "2026-09-08T00:00:00Z",
        "source_url": "https://www.gdao.org/api/items",
        "raw_payload": {
            "record_type": "pass_metadata",
            "host": "www.gdao.org",
            "site_name": "Grateful Dead Archive Online",
            "source_name": "Grateful Dead Archive Online / UC Santa Cruz Library",
            "status": status,
            "requested_dates": [{"date": date, "group": "target", "item_count": 0, "pages": 1, "status": "found"} for date in requested],
            "item_count": len(items),
        },
    }
    with path.open("w", encoding="utf-8") as handle:
        for record in [head, *items]:
            handle.write(json.dumps(record) + "\n")
    return path


def run(tmp_path: Path, items: list[dict], **kwargs) -> tuple[dict, Path]:
    requested = kwargs.pop("requested", ("1977-05-22",))
    status = kwargs.pop("status", "ok")
    out_dir = kwargs.pop("out_dir", tmp_path / "out")
    canonical = kwargs.pop("canonical", None) or canonical_dir(tmp_path)
    summary = ngs.normalize(
        raw_file(tmp_path, items, requested=requested, status=status),
        canonical,
        out_dir,
        tmp_path / "held.jsonl",
        **kwargs,
    )
    return summary, out_dir


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def held(tmp_path: Path) -> list[dict]:
    text = (tmp_path / "held.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# The mapping that works
# ---------------------------------------------------------------------------


def test_a_full_date_matching_one_show_maps_the_item_to_it(tmp_path):
    summary, out_dir = run(tmp_path, [item(101)])

    resource = rows(out_dir / "resources.csv")[-1]
    assert resource["resource_id"] == "resource-gdao-item-101"
    assert resource["resource_type"] == "archive-artifact"
    assert resource["title"] == "Sportatorium poster"
    assert resource["creator"] == "Kelley, Alton"
    assert resource["source_name"] == "Grateful Dead Archive Online / UC Santa Cruz Library"
    assert resource["source_url"] == "https://www.gdao.org/items/show/101"
    assert "GDAO item type: Poster." in resource["notes"]

    link = rows(out_dir / "resource_shows.csv")[-1]
    assert link == {
        "resource_id": "resource-gdao-item-101",
        "show_id": "gd-1977-05-22",
        "relationship_type": "about",
        "notes": "The item's Temporal Coverage names this show date (1977-05-22).",
    }
    assert summary["show_rows_written"] == 1
    assert summary["shows_mapped"] == 1
    assert summary["held"] == 0


def test_the_items_own_date_field_is_used_when_it_has_no_temporal_coverage(tmp_path):
    summary, out_dir = run(tmp_path, [item(102, temporal=(), date=("1977-05-22T00:00:00Z",))])

    assert rows(out_dir / "resource_shows.csv")[-1]["notes"] == "The item's Date field names this show date (1977-05-22)."
    assert rows(out_dir / "resources.csv")[-1]["published_date"] == "1977-05-22"
    assert summary["held"] == 0


def test_temporal_coverage_outranks_the_items_own_date(tmp_path):
    """An envelope postmarked in June is about the July show it asked for."""

    summary, out_dir = run(
        tmp_path,
        [item(103, item_type="Envelope", temporal=("1989-07-17T00:00:00Z",), date=("1989-06-03T00:00:00Z",), sortable=("1989-06-03T00:00:00Z",), queried_dates=("1989-07-17",))],
        requested=("1989-07-17",),
    )

    assert rows(out_dir / "resource_shows.csv")[-1]["show_id"] == "gd-1989-07-17"
    assert rows(out_dir / "resources.csv")[-1]["published_date"] == "1989-06-03"
    assert summary["held"] == 0


def test_a_sortable_date_is_used_when_no_higher_field_gives_a_full_date(tmp_path):
    _, out_dir = run(tmp_path, [item(104, temporal=("1977",), date=(), sortable=("1977-05-22T00:00:00Z",))])

    assert rows(out_dir / "resource_shows.csv")[-1]["notes"] == "The item's Sortable Date names this show date (1977-05-22)."


def test_the_item_type_decides_the_resource_type(tmp_path):
    items = [
        item(201, item_type="Poster"),
        item(202, item_type="Ticket"),
        item(203, item_type="Oral History"),
        item(204, item_type="Story"),
        item(205, item_type="Email"),
        item(206, item_type=""),
    ]
    _, out_dir = run(tmp_path, items)

    written = {row["resource_id"]: row["resource_type"] for row in rows(out_dir / "resources.csv")}
    assert written["resource-gdao-item-201"] == "archive-artifact"
    assert written["resource-gdao-item-202"] == "archive-artifact"
    assert written["resource-gdao-item-203"] == "first-person-account"
    assert written["resource-gdao-item-204"] == "first-person-account"
    assert written["resource-gdao-item-205"] == "first-person-account"
    assert written["resource-gdao-item-206"] == "archive-artifact"


# ---------------------------------------------------------------------------
# Hold, never guess
# ---------------------------------------------------------------------------


def test_a_date_carrying_two_canonical_shows_is_held(tmp_path):
    summary, out_dir = run(tmp_path, [item(301, temporal=("1968-10-20T00:00:00Z",), queried_dates=("1968-10-20",))], requested=("1968-10-20",))

    assert rows(out_dir / "resource_shows.csv") == [EXISTING_SHOW_ROW]
    assert summary["held"] == 1
    record = held(tmp_path)[0]
    assert record["resource_id"] == "resource-gdao-item-301"
    assert "more than one canonical show" in record["reason"]
    assert record["candidates"] == ["gd-1968-10-20", "gd-1968-10-20-late"]
    # The item is still cataloged as a resource; only the relationship waits.
    assert rows(out_dir / "resources.csv")[-1]["resource_id"] == "resource-gdao-item-301"


def test_a_partial_date_is_held(tmp_path):
    summary, _ = run(tmp_path, [item(302, temporal=("1977-00-00T00:00:00Z",), date=("1977",))])

    assert summary["held"] == 1
    record = held(tmp_path)[0]
    assert "partial date" in record["reason"]
    assert record["candidates"] == ["dcterms:temporal=1977-00-00T00:00:00Z", "dcterms:date=1977"]


def test_a_date_field_naming_more_than_one_date_is_held(tmp_path):
    summary, _ = run(
        tmp_path,
        [item(303, item_type="Envelope", temporal=("1989-07-17T00:00:00Z", "1989-07-18T00:00:00Z"), queried_dates=("1989-07-17",))],
        requested=("1989-07-17",),
    )

    assert summary["held"] == 1
    record = held(tmp_path)[0]
    assert "more than one date" in record["reason"]
    assert record["candidates"] == ["1989-07-17 (gd-1989-07-17)", "1989-07-18 (gd-1989-07-18)"]


def test_a_full_date_with_no_canonical_show_is_cataloged_but_unmapped(tmp_path):
    summary, out_dir = run(tmp_path, [item(304, temporal=("1966-01-08T00:00:00Z",))])

    assert summary["held"] == 0
    assert summary["dates_without_a_canonical_show"] == 1
    assert rows(out_dir / "resource_shows.csv") == [EXISTING_SHOW_ROW]
    assert rows(out_dir / "resources.csv")[-1]["resource_id"] == "resource-gdao-item-304"


# ---------------------------------------------------------------------------
# Undated items
# ---------------------------------------------------------------------------


def test_an_undated_item_naming_the_band_is_stored_unmapped(tmp_path):
    summary, out_dir = run(tmp_path, [item(401, title="Grateful Dead backstage pass", temporal=(), coverage=())])

    assert summary["undated_stored"] == 1
    assert summary["skipped_undated"] == 0
    assert rows(out_dir / "resources.csv")[-1]["resource_id"] == "resource-gdao-item-401"
    assert rows(out_dir / "resource_shows.csv") == [EXISTING_SHOW_ROW]


def test_an_undated_item_naming_a_venue_is_stored_unmapped(tmp_path):
    canonical = canonical_dir(tmp_path)
    _write_csv(canonical / "venues.csv", [{"venue_id": "venue-sportatorium-pembroke-pines", "name": "Sportatorium"}], ["venue_id", "name"])

    summary, out_dir = run(tmp_path, [item(402, title="Sportatorium marquee", temporal=(), coverage=())], canonical=canonical)

    assert summary["undated_stored"] == 1
    assert rows(out_dir / "resources.csv")[-1]["resource_id"] == "resource-gdao-item-402"


def test_an_undated_item_naming_neither_is_skipped(tmp_path):
    summary, out_dir = run(tmp_path, [item(403, title="Kristie Clendenning", temporal=(), coverage=())])

    assert summary["skipped_undated"] == 1
    assert [row["resource_id"] for row in rows(out_dir / "resources.csv")] == [EXISTING_RESOURCE["resource_id"]]


# ---------------------------------------------------------------------------
# Idempotency and existing rows
# ---------------------------------------------------------------------------


def test_a_rerun_reproduces_byte_identical_output(tmp_path):
    items = [item(101), item(301, temporal=("1968-10-20T00:00:00Z",), queried_dates=("1968-10-20",))]
    _, out_dir = run(tmp_path, items, requested=("1977-05-22", "1968-10-20"))
    first = {path.name: path.read_bytes() for path in sorted(out_dir.glob("*.csv"))}
    first_held = (tmp_path / "held.jsonl").read_bytes()

    run(tmp_path, items, requested=("1977-05-22", "1968-10-20"))

    assert {path.name: path.read_bytes() for path in sorted(out_dir.glob("*.csv"))} == first
    assert (tmp_path / "held.jsonl").read_bytes() == first_held


def test_the_canonical_directory_is_untouched_when_out_dir_is_elsewhere(tmp_path):
    canonical = canonical_dir(tmp_path)
    before = {path.name: path.read_bytes() for path in sorted(canonical.glob("*.csv"))}

    _, out_dir = run(tmp_path, [item(101)], canonical=canonical)

    assert {path.name: path.read_bytes() for path in sorted(canonical.glob("*.csv"))} == before
    assert rows(out_dir / "resources.csv")[0]["resource_id"] == EXISTING_RESOURCE["resource_id"]
    assert rows(out_dir / "resources.csv")[0]["notes"] == EXISTING_RESOURCE["notes"]


def test_running_into_the_canonical_directory_appends_in_place(tmp_path):
    canonical = canonical_dir(tmp_path)

    run(tmp_path, [item(101)], canonical=canonical, out_dir=canonical)

    written = rows(canonical / "resources.csv")
    assert [row["resource_id"] for row in written] == [EXISTING_RESOURCE["resource_id"], "resource-gdao-item-101"]

    # A second run adds nothing, because the row is already there.
    summary, _ = run(tmp_path, [item(101)], canonical=canonical, out_dir=canonical)
    assert summary["resources_written"] == 0
    assert summary["resources_already_present"] == 1
    assert len(rows(canonical / "resources.csv")) == 2


def test_an_item_url_already_cataloged_by_hand_keeps_its_own_row(tmp_path):
    summary, out_dir = run(tmp_path, [item(1694370)])

    assert summary["urls_already_cataloged"] == 1
    assert [row["resource_id"] for row in rows(out_dir / "resources.csv")] == [EXISTING_RESOURCE["resource_id"]]
    assert rows(out_dir / "resource_shows.csv") == [EXISTING_SHOW_ROW]


def test_an_incomplete_pass_is_not_normalized(tmp_path):
    summary, out_dir = run(tmp_path, [item(101)], requested=("1977-05-22",), status="aborted")

    assert summary["items_read"] == 0
    assert [row["resource_id"] for row in rows(out_dir / "resources.csv")] == [EXISTING_RESOURCE["resource_id"]]


def test_named_item_types_can_be_skipped(tmp_path):
    items = [item(501, item_type="Fan Tape"), item(502, item_type="Poster")]

    summary, out_dir = run(tmp_path, items, skip_item_types=frozenset({"fan tape"}))

    assert summary["skipped_by_item_type"] == 1
    assert [row["resource_id"] for row in rows(out_dir / "resources.csv")][-1] == "resource-gdao-item-502"


# ---------------------------------------------------------------------------
# The per-target outcome the status doc reports
# ---------------------------------------------------------------------------


def test_the_summary_reports_an_outcome_for_every_requested_date(tmp_path):
    items = [
        item(101),
        item(301, temporal=("1968-10-20T00:00:00Z",), queried_dates=("1968-10-20",)),
    ]
    summary, _ = run(tmp_path, items, requested=("1977-05-22", "1968-10-20", "1970-05-08"))

    by_date = summary["by_date"]
    assert by_date["1977-05-22"] == {"date": "1977-05-22", "group": "target", "items_found": 1, "mapped_to_this_show": 1, "held": 0, "status": "mapped"}
    assert by_date["1968-10-20"]["status"] == "held"
    assert by_date["1970-05-08"] == {"date": "1970-05-08", "group": "target", "items_found": 0, "mapped_to_this_show": 0, "held": 0, "status": "none-at-source"}
