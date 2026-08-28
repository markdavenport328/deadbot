"""Behavior validation for the structured provenance columns added by
`scripts/add_provenance_columns.py` to shows.csv, performances.csv, and
show_performers.csv.

Per docs/collection-methodology.md's "validate every pass at three levels",
this is the relational/behavioral check that the migration's fail-closed
guarantee holds: every row that should have a machine-readable citation has
one, and the only rows without a real source_record_id are the documented,
hand-curated Veneta exceptions -- never a silent, unexplained gap.
"""

from deadbot.data import CanonicalStore

VENETA_SHOW_ID = "gd-1972-08-27"

# Known row counts at the time this migration was written (see
# docs/data-audit-2026-08-27.md). A change here should be deliberate, not a
# side effect of an unrelated edit.
EXPECTED_SHOWS = 2358
EXPECTED_PERFORMANCES = 39774
EXPECTED_SHOW_PERFORMERS = 26265


def test_row_counts_match_known_totals():
    store = CanonicalStore()
    assert len(store.rows("shows")) == EXPECTED_SHOWS
    assert len(store.rows("performances")) == EXPECTED_PERFORMANCES
    assert len(store.rows("show_performers")) == EXPECTED_SHOW_PERFORMERS


def test_all_shows_and_show_performers_rows_have_a_source_key():
    store = CanonicalStore()
    for table in ("shows", "show_performers"):
        rows = store.rows(table)
        assert rows, f"{table} unexpectedly empty"
        missing = [row for row in rows if not row.get("source_key")]
        assert not missing, (
            f"{table} has {len(missing)} row(s) with an empty source_key: "
            f"{missing[:5]}"
        )


def test_almost_all_performances_have_a_source_key_and_manual_is_only_veneta():
    store = CanonicalStore()
    rows = store.rows("performances")
    assert rows

    with_source_key = [row for row in rows if row.get("source_key")]
    coverage = len(with_source_key) / len(rows)
    assert coverage >= 0.999, f"performances source_key coverage {coverage:.4%} below 99.9%"

    manual_rows = [row for row in rows if row.get("source_key") == "manual"]
    manual_show_ids = {row["show_id"] for row in manual_rows}
    assert manual_show_ids == {VENETA_SHOW_ID}, (
        "expected the only 'manual' performances rows to be the hand-curated "
        f"Veneta ({VENETA_SHOW_ID}) performances, found show_ids: {manual_show_ids}"
    )
    assert len(manual_rows) == 20, (
        f"expected exactly 20 manual Veneta performances, found {len(manual_rows)}"
    )
    # Every performance for the Veneta show is one of the manual rows -- no
    # partial coverage where some Veneta performances got a real citation
    # and others didn't.
    veneta_performance_ids = {row["performance_id"] for row in rows if row["show_id"] == VENETA_SHOW_ID}
    manual_performance_ids = {row["performance_id"] for row in manual_rows}
    assert veneta_performance_ids == manual_performance_ids


def test_every_non_manual_row_has_a_non_empty_source_record_id():
    store = CanonicalStore()
    for table in ("shows", "performances", "show_performers"):
        rows = store.rows(table)
        non_manual = [row for row in rows if row.get("source_key") and row["source_key"] != "manual"]
        missing_record_id = [row for row in non_manual if not row.get("source_record_id")]
        assert not missing_record_id, (
            f"{table} has {len(missing_record_id)} non-manual row(s) with an "
            f"empty source_record_id: {missing_record_id[:5]}"
        )


def test_manual_rows_have_an_empty_source_record_id():
    store = CanonicalStore()
    for table in ("shows", "performances", "show_performers"):
        manual_rows = [row for row in store.rows(table) if row.get("source_key") == "manual"]
        non_empty = [row for row in manual_rows if row.get("source_record_id")]
        assert not non_empty, (
            f"{table} has {len(non_empty)} 'manual' row(s) with a non-empty "
            f"source_record_id, which should have been left empty: {non_empty[:5]}"
        )


def test_source_key_values_are_from_the_known_set():
    store = CanonicalStore()
    known = {"gdshowsdb", "jerrybase", "manual"}
    for table in ("shows", "performances", "show_performers"):
        seen = {row["source_key"] for row in store.rows(table) if row.get("source_key")}
        assert seen <= known, f"{table} has unexpected source_key value(s): {seen - known}"


def test_shows_and_show_performers_are_fully_covered_by_real_sources():
    """shows.csv and show_performers.csv are cited 100% of the time by a real
    source (gdshowsdb or jerrybase) -- neither table has a 'manual' row,
    unlike performances.csv's 20 documented Veneta exceptions."""
    store = CanonicalStore()
    for table in ("shows", "show_performers"):
        manual_rows = [row for row in store.rows(table) if row.get("source_key") == "manual"]
        assert not manual_rows, f"{table} unexpectedly has 'manual' row(s): {manual_rows[:5]}"
