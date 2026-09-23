import pytest
from pydantic import ValidationError

from deadbot.aggregation import (
    _MEASURES_BY_COMBO,
    AggregationFilters,
    AggregationRequest,
    AggregationRow,
    apply_limit,
    assemble_result,
    parse_request,
    sort_rows,
    stable_aggregation_id,
    zero_fill_years,
)
from deadbot.data import CanonicalStore


# ---------------------------------------------------------------------------
# Combination validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dataset,group_by,measure",
    [
        (dataset, group_by, measure)
        for (dataset, group_by), measures in _MEASURES_BY_COMBO.items()
        for measure in measures
    ],
)
def test_every_allowed_combination_validates(dataset, group_by, measure):
    request = parse_request({"dataset": dataset, "group_by": group_by, "measure": measure})
    assert request.dataset == dataset
    assert request.group_by == group_by
    assert request.measure == measure


def test_dataset_does_not_support_group_by():
    with pytest.raises(ValidationError):
        parse_request({"dataset": "shows", "group_by": "song", "measure": "count"})


def test_combo_does_not_support_measure_distinct_songs():
    with pytest.raises(ValidationError):
        parse_request({"dataset": "performances", "group_by": "song", "measure": "distinct_songs"})


def test_combo_does_not_support_measure_distinct_shows():
    with pytest.raises(ValidationError):
        parse_request({"dataset": "guest_appearances", "group_by": "guest", "measure": "distinct_shows"})


def test_average_duration_is_not_an_accepted_measure():
    with pytest.raises(ValidationError):
        parse_request({"dataset": "performances", "group_by": "song", "measure": "average_duration"})


def test_performance_id_is_not_an_accepted_filter():
    with pytest.raises(ValidationError):
        parse_request(
            {
                "dataset": "performances",
                "group_by": "song",
                "measure": "count",
                "filters": {"performance_id": "performance-dark-star"},
            }
        )


def test_unknown_top_level_field_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {"dataset": "shows", "group_by": "year", "measure": "count", "bogus": True}
        )


def test_unknown_filters_field_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {
                "dataset": "shows",
                "group_by": "year",
                "measure": "count",
                "filters": {"bogus": "x"},
            }
        )


def test_filter_not_valid_for_dataset_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {
                "dataset": "shows",
                "group_by": "year",
                "measure": "count",
                "filters": {"song_id": "deal"},
            }
        )


def test_year_combined_with_year_from_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {
                "dataset": "shows",
                "group_by": "year",
                "measure": "count",
                "filters": {"year": 1977, "year_from": 1975},
            }
        )


def test_year_from_greater_than_year_to_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {
                "dataset": "shows",
                "group_by": "year",
                "measure": "count",
                "filters": {"year_from": 1978, "year_to": 1975},
            }
        )


def test_fill_missing_with_non_year_group_by_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {
                "dataset": "shows",
                "group_by": "venue",
                "measure": "count",
                "fill_missing": True,
            }
        )


def test_sort_label_with_group_by_year_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {"dataset": "shows", "group_by": "year", "measure": "count", "sort": "label"}
        )


def test_sort_chronological_with_non_year_group_by_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {"dataset": "shows", "group_by": "venue", "measure": "count", "sort": "chronological"}
        )


def test_limit_zero_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {"dataset": "shows", "group_by": "year", "measure": "count", "limit": 0}
        )


def test_limit_fifty_one_raises():
    with pytest.raises(ValidationError):
        parse_request(
            {"dataset": "shows", "group_by": "year", "measure": "count", "limit": 51}
        )


# ---------------------------------------------------------------------------
# stable_aggregation_id
# ---------------------------------------------------------------------------


def test_stable_id_collapses_explicit_default_sort_and_omitted_sort():
    explicit = parse_request(
        {"dataset": "shows", "group_by": "year", "measure": "count", "sort": "chronological"}
    )
    omitted = parse_request({"dataset": "shows", "group_by": "year", "measure": "count"})
    assert stable_aggregation_id(explicit) == stable_aggregation_id(omitted)


def test_stable_id_differs_when_limit_differs():
    base = parse_request({"dataset": "shows", "group_by": "year", "measure": "count", "limit": 20})
    different_limit = parse_request(
        {"dataset": "shows", "group_by": "year", "measure": "count", "limit": 30}
    )
    assert stable_aggregation_id(base) != stable_aggregation_id(different_limit)


# ---------------------------------------------------------------------------
# Row shaping
# ---------------------------------------------------------------------------


def test_zero_fill_years_fills_gaps_with_zero():
    filters = AggregationFilters(year_from=1965, year_to=1968)
    rows = [AggregationRow(year=1966, value=7)]
    filled = zero_fill_years(rows, filters)
    assert [(r.year, r.value) for r in filled] == [
        (1965, 0),
        (1966, 7),
        (1967, 0),
        (1968, 0),
    ]


def test_zero_fill_years_no_bounds_no_rows_returns_empty_unchanged():
    filters = AggregationFilters()
    rows: list[AggregationRow] = []
    assert zero_fill_years(rows, filters) == []


def test_zero_fill_years_one_sided_bound_no_rows_returns_empty_unchanged():
    # A bound with no matching data (e.g. year_from=2050) and empty rows must
    # not fall through to min()/max() over an empty sequence.
    filters = AggregationFilters(year_from=2050)
    rows: list[AggregationRow] = []
    assert zero_fill_years(rows, filters) == []


def test_zero_fill_years_both_bounds_no_rows_fills_the_full_range():
    # Both bounds come from filters directly, so this must still zero-fill
    # correctly on empty rows rather than being over-guarded into a no-op.
    filters = AggregationFilters(year_from=2050, year_to=2052)
    rows: list[AggregationRow] = []
    filled = zero_fill_years(rows, filters)
    assert [(r.year, r.value) for r in filled] == [
        (2050, 0),
        (2051, 0),
        (2052, 0),
    ]


def test_sort_rows_value_desc_stable_casefold_tiebreak():
    request = parse_request({"dataset": "shows", "group_by": "venue", "measure": "count"})
    rows = [
        AggregationRow(id="b", label="Barton Hall", value=5),
        AggregationRow(id="a", label="alpine valley", value=5),
    ]
    ordered = sort_rows(rows, request)
    assert [r.label for r in ordered] == ["alpine valley", "Barton Hall"]


def test_apply_limit_returns_excluded_count():
    rows = [AggregationRow(id=str(i), label=str(i), value=i) for i in range(5)]
    limited, excluded = apply_limit(rows, 3)
    assert len(limited) == 3
    assert excluded == 2


def test_apply_limit_no_excess_returns_zero_excluded():
    rows = [AggregationRow(id=str(i), label=str(i), value=i) for i in range(3)]
    limited, excluded = apply_limit(rows, 3)
    assert len(limited) == 3
    assert excluded == 0


# ---------------------------------------------------------------------------
# assemble_result
# ---------------------------------------------------------------------------


def test_assemble_result_on_empty_rows():
    request = parse_request({"dataset": "shows", "group_by": "year", "measure": "count"})
    date_range = {"start": 1965, "end": 1995}
    result = assemble_result(request, [], date_range, 0)
    assert result.empty_reason == "No shows match these filters."
    assert result.total == 0
    assert result.date_range == date_range
    assert result.rows == []
    assert result.excluded_count == 0
    assert result.setlist_coverage is None
    assert "setlist_coverage" not in result.to_payload()


def test_assemble_result_chronological_sort_is_never_truncated():
    # A year-grouped time series (effective_sort == "chronological") must
    # never be silently cut off by the default/explicit limit, even when the
    # explicit limit is far smaller than the row count.
    request = parse_request(
        {"dataset": "shows", "group_by": "year", "measure": "count", "limit": 1}
    )
    raw_rows = [
        AggregationRow(year=1972, value=3),
        AggregationRow(year=1973, value=5),
        AggregationRow(year=1974, value=2),
    ]
    result = assemble_result(request, raw_rows, {"from": 1972, "to": 1974}, 10)
    assert len(result.rows) == 3
    assert result.excluded_count == 0
    assert result.total == 10


def test_assemble_result_non_chronological_sort_still_truncates():
    # A ranked list (e.g. group_by="song", value_desc) must still truncate
    # and report a nonzero excluded_count -- proving the chronological-only
    # exemption did not also disable truncation here.
    request = parse_request(
        {
            "dataset": "performances",
            "group_by": "song",
            "measure": "count",
            "sort": "value_desc",
            "limit": 2,
        }
    )
    raw_rows = [
        AggregationRow(id="song-a", label="A", value=10),
        AggregationRow(id="song-b", label="B", value=5),
        AggregationRow(id="song-c", label="C", value=1),
    ]
    result = assemble_result(request, raw_rows, None, 16)
    assert len(result.rows) == 2
    assert result.excluded_count == 1
    assert result.total == 16


def test_assemble_result_carries_setlist_coverage_through_to_the_payload():
    request = parse_request({"dataset": "performances", "group_by": "year", "measure": "count"})
    coverage = {
        "shows_on_record": 5,
        "shows_with_setlist": 3,
        "by_year": [{"year": 1972, "shows_on_record": 5, "shows_with_setlist": 3}],
    }
    result = assemble_result(request, [], None, 0, coverage)
    assert result.setlist_coverage == coverage
    assert result.to_payload()["setlist_coverage"] == coverage


# ---------------------------------------------------------------------------
# CanonicalStore.aggregate (CSV reference implementation)
# ---------------------------------------------------------------------------


def test_aggregate_performances_by_year_filtered_to_dark_star():
    store = CanonicalStore()
    request = parse_request(
        {
            "dataset": "performances",
            "group_by": "year",
            "measure": "count",
            "filters": {"song_id": "song-dark-star"},
        }
    )
    result = store.aggregate(request)
    assert result.rows, "expected Dark Star performances in at least one year"
    years = [row["year"] for row in result.rows]
    assert years == sorted(years)
    for row in result.rows:
        assert isinstance(row["value"], int)
        assert row["value"] > 0
    assert result.total == sum(row["value"] for row in result.rows)


def test_aggregate_performances_by_year_fill_missing_has_no_gaps():
    store = CanonicalStore()
    request = parse_request(
        {
            "dataset": "performances",
            "group_by": "year",
            "measure": "count",
            "filters": {"song_id": "song-dark-star"},
            "fill_missing": True,
        }
    )
    result = store.aggregate(request)
    years = [row["year"] for row in result.rows]
    assert years == list(range(years[0], years[-1] + 1))
    present_years = {
        row["year"]
        for row in store.aggregate(
            parse_request(
                {
                    "dataset": "performances",
                    "group_by": "year",
                    "measure": "count",
                    "filters": {"song_id": "song-dark-star"},
                }
            )
        ).rows
    }
    for row in result.rows:
        if row["year"] not in present_years:
            assert row["value"] == 0


def test_aggregate_shows_by_year_date_range_spans_decades():
    store = CanonicalStore()
    request = parse_request({"dataset": "shows", "group_by": "year", "measure": "count"})
    result = store.aggregate(request)
    assert result.date_range is not None
    assert result.date_range["from"] <= 1970
    assert result.date_range["to"] >= 1990


def test_aggregate_performances_by_song_top_five_non_increasing():
    store = CanonicalStore()
    request = parse_request(
        {
            "dataset": "performances",
            "group_by": "song",
            "measure": "count",
            "sort": "value_desc",
            "limit": 5,
        }
    )
    result = store.aggregate(request)
    assert len(result.rows) == 5
    values = [row["value"] for row in result.rows]
    assert values == sorted(values, reverse=True)
    assert result.excluded_count > 0


def test_aggregate_performances_by_venue_distinct_shows_ids_resolve():
    store = CanonicalStore()
    request = parse_request(
        {"dataset": "performances", "group_by": "venue", "measure": "distinct_shows"}
    )
    result = store.aggregate(request)
    assert result.rows
    for row in result.rows[:3]:
        venue = store.one("venues", row["id"])
        assert venue is not None
        assert venue.get("name") == row["label"]


def test_aggregate_guest_appearances_by_guest_includes_jack_casady():
    store = CanonicalStore()
    request = parse_request(
        {
            "dataset": "guest_appearances",
            "group_by": "guest",
            "measure": "count",
            "filters": {"guest_id": "person-jack-casady"},
        }
    )
    result = store.aggregate(request)
    rows_by_id = {row["id"]: row["value"] for row in result.rows}
    assert "person-jack-casady" in rows_by_id
    assert rows_by_id["person-jack-casady"] >= 1


def test_aggregate_guest_appearances_by_year_filtered_to_guest_only_shows_their_years():
    store = CanonicalStore()
    shows_by_id = store.by_id["shows"]
    expected_years = set()
    for assignment in store.rows("show_performers"):
        if assignment.get("role") != "guest" or assignment.get("person_id") != "person-jack-casady":
            continue
        show = shows_by_id.get(assignment.get("show_id", ""))
        date = (show or {}).get("show_date", "")
        if len(date) >= 4 and date[:4].isdigit():
            expected_years.add(int(date[:4]))

    request = parse_request(
        {
            "dataset": "guest_appearances",
            "group_by": "year",
            "measure": "distinct_shows",
            "filters": {"guest_id": "person-jack-casady"},
        }
    )
    result = store.aggregate(request)
    assert result.rows
    actual_years = {row["year"] for row in result.rows}
    assert actual_years == expected_years


def test_aggregate_one_sided_year_bound_with_no_matching_rows_does_not_crash():
    # Live crash repro: year_from far beyond the catalog's span, combined
    # with fill_missing, used to raise ValueError from min()/max() over an
    # empty sequence inside zero_fill_years.
    store = CanonicalStore()
    request = parse_request(
        {
            "dataset": "performances",
            "group_by": "year",
            "measure": "count",
            "filters": {"song_id": "song-dark-star", "year_from": 2050},
            "fill_missing": True,
        }
    )
    result = store.aggregate(request)
    assert result.rows == []
    assert result.empty_reason is not None


def test_aggregate_impossible_filter_returns_empty_result():
    store = CanonicalStore()
    request = parse_request(
        {
            "dataset": "performances",
            "group_by": "year",
            "measure": "count",
            "filters": {"song_id": "song-dark-star", "show_id": "gd-1900-01-01"},
        }
    )
    result = store.aggregate(request)
    assert result.rows == []
    assert result.total == 0
    assert result.empty_reason is not None
    assert result.date_range is None


def test_aggregate_performances_distinct_songs_by_year_total_is_the_whole_set_not_a_row_sum():
    # total must be the number of distinct songs across every year combined,
    # not the sum of each year's distinct-song count -- a song played across
    # multiple years would otherwise be counted once per year it appeared in.
    store = CanonicalStore()
    request = parse_request(
        {"dataset": "performances", "group_by": "year", "measure": "distinct_songs", "limit": 50}
    )
    result = store.aggregate(request)
    naive_row_sum = sum(row["value"] for row in result.rows)
    assert result.total < naive_row_sum
    all_songs = {p["song_id"] for p in store.rows("performances") if p.get("song_id")}
    assert result.total == len(all_songs)


def test_aggregate_performances_distinct_shows_by_song_total_is_the_whole_set_not_a_row_sum():
    # Likewise for distinct_shows grouped by song: a show that performed more
    # than one grouped song would otherwise be double-counted in a naive sum.
    store = CanonicalStore()
    request = parse_request(
        {"dataset": "performances", "group_by": "song", "measure": "distinct_shows", "limit": 50}
    )
    result = store.aggregate(request)
    naive_row_sum = sum(row["value"] for row in result.rows)
    assert result.total < naive_row_sum
    all_shows = {p["show_id"] for p in store.rows("performances")}
    assert result.total == len(all_shows)


def test_aggregate_performances_count_by_song_total_still_equals_all_performances():
    # count never double-counts a fact across groups (every performance
    # belongs to exactly one song group), so its total is unaffected by this
    # task's change: the count of every performance, regardless of limit or
    # how many rows got truncated off the top-ranked list.
    store = CanonicalStore()
    request = parse_request(
        {"dataset": "performances", "group_by": "song", "measure": "count", "limit": 5, "sort": "value_desc"}
    )
    result = store.aggregate(request)
    assert result.excluded_count > 0
    assert result.total == len(store.rows("performances"))


def test_aggregate_performances_by_song_top_ranked_at_least_dark_star():
    store = CanonicalStore()
    top_request = parse_request(
        {
            "dataset": "performances",
            "group_by": "song",
            "measure": "count",
            "sort": "value_desc",
            "limit": 1,
        }
    )
    top_result = store.aggregate(top_request)
    assert len(top_result.rows) == 1

    dark_star_request = parse_request(
        {
            "dataset": "performances",
            "group_by": "song",
            "measure": "count",
            "filters": {"song_id": "song-dark-star"},
        }
    )
    dark_star_result = store.aggregate(dark_star_request)
    assert len(dark_star_result.rows) == 1
    dark_star_value = dark_star_result.rows[0]["value"]

    assert top_result.rows[0]["value"] >= dark_star_value
