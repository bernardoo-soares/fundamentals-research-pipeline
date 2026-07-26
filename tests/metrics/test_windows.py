from __future__ import annotations

import math

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.stage2_metrics_schema import ReasonCode
from fundamentals_pipeline.metrics.windows import (
    _consecutive_pairs,
    cagr_metric,
    col,
    consistency_fraction_metric,
    count_years_metric,
    direction_correspondence_metric,
    negative_equity_with_strong_earnings_metric,
    ratio,
    require_single_era,
    slope_metric,
    sum_ratio_metric,
    up_year_fraction_metric,
)


def _annual(rows: dict[int, dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"fiscal_year": y, **cols} for y, cols in sorted(rows.items())]
    )


def test_cagr_happy_path() -> None:
    frame = _annual({2020: {"x": 100.0}, 2021: {"x": 110.0}, 2022: {"x": 121.0}})
    points = {p.as_of_year: p for p in cagr_metric(col("x"), 2)(frame)}
    # as_of 2022: (121/100)^(1/2) - 1 = 0.1
    assert math.isclose(points[2022].value, 0.1, rel_tol=1e-9)
    assert points[2022].reason_code is None


def test_cagr_negative_base() -> None:
    frame = _annual({2020: {"x": -5.0}, 2021: {"x": 10.0}, 2022: {"x": 20.0}})
    points = {p.as_of_year: p for p in cagr_metric(col("x"), 2)(frame)}
    assert points[2022].value is None
    assert points[2022].reason_code == ReasonCode.NEGATIVE_BASE


def test_cagr_missing_endpoint() -> None:
    frame = _annual({2020: {"x": 100.0}, 2021: {"x": 110.0}, 2022: {"x": None}})
    points = {p.as_of_year: p for p in cagr_metric(col("x"), 2)(frame)}
    assert points[2022].value is None
    assert points[2022].reason_code == ReasonCode.MISSING_INPUT


def test_cagr_negative_end_is_reasoned_not_complex() -> None:
    # negative ending value would make (v_end/v_start)^(1/n) complex -> must be nulled
    frame = _annual({2020: {"x": 100.0}, 2021: {"x": 50.0}, 2022: {"x": -20.0}})
    points = {p.as_of_year: p for p in cagr_metric(col("x"), 2)(frame)}
    assert points[2022].value is None
    assert points[2022].reason_code == ReasonCode.NEGATIVE_BASE


def test_consistency_fraction_and_insufficient_history() -> None:
    # 10 present years, 6 with x > 0.2
    rows = {y: {"x": (0.30 if i < 6 else 0.10)} for i, y in enumerate(range(2013, 2023))}
    frame = _annual(rows)
    pts = {p.as_of_year: p for p in consistency_fraction_metric(col("x"), 0.20, 10)(frame)}
    assert math.isclose(pts[2022].value, 0.6, rel_tol=1e-9)
    assert pts[2022].window_years_present == 10
    # only 7 present in the 10y window -> insufficient (< ceil(0.8*10)=8)
    sparse = _annual({y: {"x": 0.30} for y in [2013, 2014, 2015, 2016, 2017, 2018, 2022]})
    pts2 = {p.as_of_year: p for p in consistency_fraction_metric(col("x"), 0.20, 10)(sparse)}
    assert pts2[2022].value is None
    assert pts2[2022].reason_code == ReasonCode.INSUFFICIENT_HISTORY


def test_count_years() -> None:
    rows = {y: {"x": (5.0 if i % 2 == 0 else 0.0)} for i, y in enumerate(range(2013, 2023))}
    frame = _annual(rows)
    pts = {p.as_of_year: p for p in count_years_metric(col("x"), 0.0, 10)(frame)}
    assert pts[2022].value == 5.0  # 5 years with x > 0


def test_up_year_fraction() -> None:
    # strictly increasing -> fraction 1.0
    rows = {y: {"x": float(i)} for i, y in enumerate(range(2013, 2023))}
    frame = _annual(rows)
    pts = {p.as_of_year: p for p in up_year_fraction_metric(col("x"), 10)(frame)}
    assert math.isclose(pts[2022].value, 1.0, rel_tol=1e-9)


def test_ratio_series_guards_zero_denominator() -> None:
    frame = _annual({2021: {"n": 10.0, "d": 0.0}, 2022: {"n": 10.0, "d": 50.0}})
    s = ratio("n", "d")(frame)
    assert pd.isna(s.loc[2021])       # den 0 -> NaN (not present)
    assert math.isclose(s.loc[2022], 0.2, rel_tol=1e-9)


def _era_frame(years, eras, values):
    return pd.DataFrame(
        {"fiscal_year": years, "source_era": eras, "x": values}
    )


def test_require_single_era_allows_a_pure_window():
    frame = _era_frame(
        list(range(2013, 2024)),
        ["legacy_compustat"] * 11,
        [100.0 * (1.1**i) for i in range(11)],
    )
    guarded = require_single_era(cagr_metric(col("x"), 10), span=10)
    point = next(p for p in guarded(frame) if p.as_of_year == 2023)
    assert point.value is not None
    assert point.reason_code is None


def test_require_single_era_nulls_a_boundary_crossing_window():
    """cogsq-class fields: 13.6% of companies flip the 40% gross-margin
    threshold purely by provider, so a crossing window is not computable."""
    frame = _era_frame(
        list(range(2013, 2024)),
        ["legacy_compustat"] * 10 + ["simfin"],
        [100.0 * (1.1**i) for i in range(11)],
    )
    guarded = require_single_era(cagr_metric(col("x"), 10), span=10)
    point = next(p for p in guarded(frame) if p.as_of_year == 2023)
    assert point.value is None
    assert point.reason_code == ReasonCode.MIXED_ERA_WINDOW


def test_require_single_era_refuses_when_provenance_is_missing():
    """Absent provenance is never assumed pure."""
    frame = pd.DataFrame(
        {"fiscal_year": list(range(2013, 2024)), "x": [100.0] * 11}
    )
    guarded = require_single_era(cagr_metric(col("x"), 10), span=10)
    assert all(p.reason_code == ReasonCode.MIXED_ERA_WINDOW for p in guarded(frame))


def test_require_single_era_treats_null_era_as_mixed():
    frame = _era_frame(
        list(range(2013, 2024)),
        ["legacy_compustat"] * 5 + [None] + ["legacy_compustat"] * 5,
        [100.0] * 11,
    )
    guarded = require_single_era(cagr_metric(col("x"), 10), span=10)
    point = next(p for p in guarded(frame) if p.as_of_year == 2023)
    assert point.reason_code == ReasonCode.MIXED_ERA_WINDOW


def test_require_single_era_span_matches_window_metrics():
    """A 10-year window metric passes span=9, so 2014-2023 is the window."""
    frame = _era_frame(
        list(range(2013, 2024)),
        ["simfin"] + ["legacy_compustat"] * 10,  # only 2013 differs
        [1.0] * 11,
    )
    guarded = require_single_era(count_years_metric(col("x"), 0.0, 10), span=9)
    point = next(p for p in guarded(frame) if p.as_of_year == 2023)
    assert point.value is not None  # 2013 is outside the 2014-2023 window


def test_require_single_era_preserves_a_more_specific_reason():
    """Regression: an impure window must not relabel missing_input as
    mixed_era_window, or reason-code tallies attribute genuine data gaps to
    era mixing."""
    frame = _era_frame(
        list(range(2013, 2024)),
        ["legacy_compustat"] * 10 + ["simfin"],
        [100.0] * 10 + [float("nan")],  # 2023 endpoint missing
    )
    guarded = require_single_era(cagr_metric(col("x"), 10), span=10)
    point = next(p for p in guarded(frame) if p.as_of_year == 2023)
    assert point.reason_code == ReasonCode.MISSING_INPUT


def test_era_guard_marks_the_compute_function():
    from fundamentals_pipeline.metrics.windows import is_era_guarded

    plain = cagr_metric(col("x"), 10)
    assert not is_era_guarded(plain)
    assert is_era_guarded(require_single_era(plain, span=10))


# --- SP3 completion combinators ---


def _yearly(rows):
    """Annual frame from (year, **cols) tuples."""
    return pd.DataFrame([{"fiscal_year": y, **c} for y, c in rows])


def test_sum_ratio_requires_both_legs_present():
    """A year missing either leg must be excluded from BOTH sums.

    Summing capex over 10 years against earnings over 8 would overstate the
    ratio by construction, which is why both-present is required rather than
    each leg being summed independently.
    """
    rows = [(2013 + i, {"capxy_annual": 10.0, "niq_annual": 100.0}) for i in range(10)]
    rows[3] = (2016, {"capxy_annual": 10.0, "niq_annual": None})
    metric = sum_ratio_metric(
        col("capxy_annual"), col("niq_annual"), 10, min_present=8
    )
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    # 9 usable years: 90 / 900, NOT 100 / 900
    assert point.value == pytest.approx(90.0 / 900.0)
    assert point.window_years_present == 9


def test_sum_ratio_enforces_its_explicit_minimum():
    rows = [(2013 + i, {"capxy_annual": 10.0, "niq_annual": 100.0}) for i in range(10)]
    for i in (0, 1, 2):  # leave only 7 usable years
        rows[i] = (2013 + i, {"capxy_annual": 10.0, "niq_annual": None})
    metric = sum_ratio_metric(
        col("capxy_annual"), col("niq_annual"), 10, min_present=8
    )
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    assert point.value is None
    assert point.reason_code == ReasonCode.INSUFFICIENT_HISTORY


def test_sum_ratio_negative_denominator_is_reasoned_null():
    """Capex against cumulative losses is not a meaningful percentage."""
    rows = [(2013 + i, {"capxy_annual": 10.0, "niq_annual": -100.0}) for i in range(10)]
    metric = sum_ratio_metric(
        col("capxy_annual"), col("niq_annual"), 10, min_present=8
    )
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    assert point.value is None
    assert point.reason_code == ReasonCode.NEGATIVE_BASE


def test_slope_metric_recovers_a_known_gradient():
    """OLS slope on an exactly linear series must equal its gradient."""
    rows = [(2013 + i, {"r": 0.20 - 0.01 * i}) for i in range(10)]
    point = {p.as_of_year: p for p in slope_metric(col("r"), 10)(_yearly(rows))}[2022]
    assert point.value == pytest.approx(-0.01)


def test_slope_metric_uses_every_point_not_just_the_endpoints():
    """The property that justifies OLS over last-minus-first.

    Both series share identical first and last values, so last-minus-first is
    IDENTICAL for them and reads "flat" for both. The interior differs: one
    body sits high, the other low. OLS separates them and gives opposite signs.

    Note OLS is not outlier-immune -- a large enough final spike does move it.
    The claim here is only that interior years count, which last-minus-first
    ignores entirely.
    """
    high_early = [0.20, 0.30, 0.30, 0.30, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20]
    high_late = [0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.30, 0.30, 0.30, 0.20]
    assert high_early[-1] - high_early[0] == 0
    assert high_late[-1] - high_late[0] == 0

    def _slope(values):
        rows = [(2013 + i, {"r": v}) for i, v in enumerate(values)]
        return {
            p.as_of_year: p for p in slope_metric(col("r"), 10)(_yearly(rows))
        }[2022].value

    assert _slope(high_early) == pytest.approx(-0.009091, abs=1e-6)
    assert _slope(high_late) == pytest.approx(+0.009091, abs=1e-6)


def test_slope_metric_single_distinct_year_is_insufficient_not_flat():
    """One point has no slope; reporting 0.0 would read as 'flat', not 'unknown'."""
    rows = [(2013 + i, {"r": None}) for i in range(9)] + [(2022, {"r": 0.2})]
    point = {p.as_of_year: p for p in slope_metric(col("r"), 10)(_yearly(rows))}[2022]
    assert point.value is None
    assert point.reason_code == ReasonCode.INSUFFICIENT_HISTORY


def test_direction_correspondence_counts_only_same_direction_moves():
    """Inventory and earnings rising together counts; diverging does not."""
    inventory = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0]
    earnings = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
    rows = [
        (2013 + i, {"invtq_q4": inventory[i], "niq_annual": earnings[i]})
        for i in range(10)
    ]
    metric = direction_correspondence_metric(col("invtq_q4"), col("niq_annual"), 10)
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    assert point.value == pytest.approx(1.0)  # all 9 pairs rise together

    earnings_falling = [20.0 - i for i in range(10)]
    rows = [
        (2013 + i, {"invtq_q4": inventory[i], "niq_annual": earnings_falling[i]})
        for i in range(10)
    ]
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    assert point.value == pytest.approx(0.0)  # inventory up, earnings down


def test_direction_correspondence_treats_a_flat_series_as_non_corresponding():
    """A dormant line must not read as tracking earnings (spec 4.2)."""
    rows = [
        (2013 + i, {"invtq_q4": 100.0, "niq_annual": 10.0 + i}) for i in range(10)
    ]
    metric = direction_correspondence_metric(col("invtq_q4"), col("niq_annual"), 10)
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    assert point.value == pytest.approx(0.0)


def test_negative_equity_strong_earnings_requires_both_conditions():
    """Negative equity is a strength only alongside a long profit record."""
    metric = negative_equity_with_strong_earnings_metric(
        col("ceqq_q4"), col("niq_annual"), 10, min_profitable_years=8
    )

    def _value(equity, earnings):
        rows = [
            (2013 + i, {"ceqq_q4": equity, "niq_annual": earnings[i]})
            for i in range(10)
        ]
        return {p.as_of_year: p for p in metric(_yearly(rows))}[2022]

    profitable = [100.0] * 10
    assert _value(-500.0, profitable).value == pytest.approx(1.0)
    # negative equity but only 7 profitable years -> fails the earnings leg
    assert _value(-500.0, [100.0] * 7 + [-1.0] * 3).value == pytest.approx(0.0)
    # long profit record but positive equity -> not the special case
    assert _value(500.0, profitable).value == pytest.approx(0.0)


def test_negative_equity_missing_equity_is_missing_input_not_zero():
    """0.0 means 'does not qualify'; a missing reading must not claim that."""
    metric = negative_equity_with_strong_earnings_metric(
        col("ceqq_q4"), col("niq_annual"), 10, min_profitable_years=8
    )
    rows = [(2013 + i, {"ceqq_q4": None, "niq_annual": 100.0}) for i in range(10)]
    point = {p.as_of_year: p for p in metric(_yearly(rows))}[2022]
    assert point.value is None
    assert point.reason_code == ReasonCode.MISSING_INPUT


def test_consecutive_pairs_never_bridges_a_gap():
    """Comparing 2014 to 2016 would measure a two-year change as one year."""
    assert _consecutive_pairs([2013, 2014, 2016, 2017]) == [(2013, 2014), (2016, 2017)]
    assert _consecutive_pairs([2013]) == []
