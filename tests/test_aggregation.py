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


def test_average_duration_is_rejected_with_coverage_reason():
    with pytest.raises(ValidationError) as excinfo:
        parse_request({"dataset": "performances", "group_by": "song", "measure": "average_duration"})
    assert "66.5%" in str(excinfo.value)


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
    result = assemble_result(request, [], date_range)
    assert result.empty_reason == "No shows match these filters."
    assert result.total == 0
    assert result.date_range == date_range
    assert result.rows == []
    assert result.excluded_count == 0


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
