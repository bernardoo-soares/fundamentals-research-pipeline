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


SOURCE_ERA_COLUMN = "source_era"

# Marker set on a guarded compute function so the registry can verify that a
# metric declaring `requires_single_era` is actually wrapped. Without this the
# flag is inert: declaring it would change nothing and the metric would still
# compute across the provider boundary.
ERA_GUARD_ATTRIBUTE = "__single_era_guarded__"


def is_era_guarded(compute: ComputeFn) -> bool:
    """Whether a compute function has been wrapped by `require_single_era`."""
    return bool(getattr(compute, ERA_GUARD_ATTRIBUTE, False))


def require_single_era(compute: ComputeFn, span: int) -> ComputeFn:
    """Null any point whose window spans more than one provider era.

    For fields the two providers do not measure the same way -- declared
    `eras_equivalent=False` in `contracts/field_era_semantics.py` -- a window
    crossing the boundary compares incomparable quantities. `cogsq` is the
    motivating case: 13.6% of companies cross the >40% gross-margin threshold
    purely by which provider served the row.

    `span` is the number of years before `as_of` that the window covers, so a
    CAGR over N years passes `span=N` (endpoints N apart) and an N-year window
    metric passes `span=N-1`.

    A null `source_era` marks a ticker-year whose provider was not uniform, and
    is treated as mixed rather than trusted.
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        points = compute(frame)

        def _blocked(point: MetricPoint) -> MetricPoint:
            """Relabel only points that still carry a value.

            A point already nulled with `missing_input` or `negative_base`
            keeps that reason: the more specific diagnosis is the useful one,
            and overwriting it would attribute genuine data gaps to era mixing
            in downstream reason-code tallies.
            """
            if point.reason_code is not None:
                return point
            return MetricPoint(
                point.as_of_year,
                None,
                ReasonCode.MIXED_ERA_WINDOW,
                point.window_years_present,
            )

        if SOURCE_ERA_COLUMN not in frame.columns:
            # Provenance unavailable: refuse rather than assume purity.
            return [_blocked(point) for point in points]

        eras = frame.set_index("fiscal_year").sort_index()[SOURCE_ERA_COLUMN]
        guarded: list[MetricPoint] = []
        for point in points:
            window = eras.loc[point.as_of_year - span : point.as_of_year]
            impure = window.isna().any() or window.dropna().nunique() > 1
            guarded.append(_blocked(point) if impure else point)
        return guarded

    setattr(_compute, ERA_GUARD_ATTRIBUTE, True)
    return _compute


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
