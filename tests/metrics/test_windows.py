from __future__ import annotations

import math

import pandas as pd

from fundamentals_pipeline.contracts.stage2_metrics_schema import ReasonCode
from fundamentals_pipeline.metrics.windows import (
    cagr_metric,
    col,
    consistency_fraction_metric,
    count_years_metric,
    ratio,
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
