import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_song_cohort_candidates import make_candidates


def test_cohort_is_stratified_and_reproducible():
    first = make_candidates()
    second = make_candidates()
    assert first == second
    assert 50 <= len(first) <= 100
    assert [row["queue_position"] for row in first] == list(range(1, len(first) + 1))
    assert all(row["span_years"] >= 10 for row in first)
    assert all(row["first_year"] // 10 != row["last_year"] // 10 for row in first)


def test_materialized_csv_matches_derived_queue():
    path = Path(__file__).parents[1] / "data" / "editorial" / "song-cohort-candidates.csv"
    with path.open(newline="", encoding="utf-8") as f:
        materialized = list(csv.DictReader(f))
    assert len(materialized) == len(make_candidates())
    assert materialized[0]["song_id"] == make_candidates()[0]["song_id"]
