"""Pure window/CAGR helpers and combinators for trend metrics.

A `series_fn` maps one ticker's annual frame to a `pd.Series` indexed by
`fiscal_year`. A combinator turns a `series_fn` into a `compute(frame) ->
list[MetricPoint]`. No I/O.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pandas as pd

from ..contracts.stage2_metrics_schema import MetricPoint, ReasonCode

SeriesFn = Callable[[pd.DataFrame], pd.Series]
ComputeFn = Callable[[pd.DataFrame], list[MetricPoint]]


def col(name: str) -> SeriesFn:
    """Series of one annual column, indexed by fiscal_year."""

    def _fn(frame: pd.DataFrame) -> pd.Series:
        indexed = frame.set_index("fiscal_year").sort_index()
        return pd.to_numeric(indexed[name], errors="coerce")

    return _fn


def ratio(num: str, den: str) -> SeriesFn:
    """Series of num/den per year; a zero/NaN denominator yields NaN."""

    def _fn(frame: pd.DataFrame) -> pd.Series:
        indexed = frame.set_index("fiscal_year").sort_index()
        numerator = pd.to_numeric(indexed[num], errors="coerce")
        denominator = pd.to_numeric(indexed[den], errors="coerce")
        return numerator / denominator.where(denominator != 0)

    return _fn


def _min_present(n: int) -> int:
    return math.ceil(0.8 * n)


def cagr_metric(series_fn: SeriesFn, n: int) -> ComputeFn:
    """CAGR over n years using the two endpoints (spec 6.1.2)."""

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        series = series_fn(frame)
        if series.empty:
            return []
        years = list(series.index)
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n, years[-1] + 1):
            start_year = as_of - n
            v_end = series.get(as_of)
            v_start = series.get(start_year)
            present = int(series.loc[start_year:as_of].notna().sum())
            if v_end is None or v_start is None or pd.isna(v_end) or pd.isna(v_start):
                points.append(MetricPoint(as_of, None, ReasonCode.MISSING_INPUT, present))
            elif v_start <= 0 or v_end < 0:
                # start <= 0 is the spec's negative_base; a negative end makes the
                # ratio negative -> fractional root undefined, so null it too.
                points.append(MetricPoint(as_of, None, ReasonCode.NEGATIVE_BASE, present))
            else:
                value = (v_end / v_start) ** (1.0 / n) - 1.0
                points.append(MetricPoint(as_of, float(value), None, present))
        return points

    return _compute


def _window_present(series: pd.Series, as_of: int, n: int) -> pd.Series:
    """Non-null values in the n-year window ending at as_of, indexed by year."""
    return series.loc[as_of - n + 1 : as_of].dropna()


def consistency_fraction_metric(series_fn: SeriesFn, threshold: float, n: int) -> ComputeFn:
    """Fraction of present window years with value > threshold (spec 6.1.3)."""

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        series = series_fn(frame)
        if series.empty:
            return []
        years = list(series.index)
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            present = _window_present(series, as_of, n)
            k = len(present)
            if k < _min_present(n):
                points.append(MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k))
            else:
                fraction = float((present > threshold).sum()) / k
                points.append(MetricPoint(as_of, fraction, None, k))
        return points

    return _compute


def count_years_metric(series_fn: SeriesFn, threshold: float, n: int) -> ComputeFn:
    """Count of present window years with value > threshold (spec 6.1.3)."""

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        series = series_fn(frame)
        if series.empty:
            return []
        years = list(series.index)
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            present = _window_present(series, as_of, n)
            k = len(present)
            if k < _min_present(n):
                points.append(MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k))
            else:
                count = float((present > threshold).sum())
                points.append(MetricPoint(as_of, count, None, k))
        return points

    return _compute


def up_year_fraction_metric(series_fn: SeriesFn, n: int) -> ComputeFn:
    """Fraction of YoY increases among consecutive present years (spec 6.1.3)."""

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        series = series_fn(frame)
        if series.empty:
            return []
        years = list(series.index)
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            present = _window_present(series, as_of, n)
            k = len(present)
            if k < _min_present(n):
                points.append(MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k))
                continue
            present_years = list(present.index)
            pairs = [
                (present_years[i], present_years[i + 1])
                for i in range(len(present_years) - 1)
                if present_years[i + 1] == present_years[i] + 1
            ]
            if not pairs:
                points.append(MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k))
            else:
                increases = sum(1 for a, b in pairs if present[b] > present[a])
                points.append(MetricPoint(as_of, increases / len(pairs), None, k))
        return points

    return _compute
