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
from . import gross_profit as gp

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


def gross_margin_series() -> SeriesFn:
    """Annual gross margin: `(saleq - cogsq - dpq) / saleq`, indexed by year.

    Uses the shared rule in `metrics/gross_profit.py`, which records why
    depreciation is subtracted (Compustat states `cogsq` pre-depreciation; the
    uncorrected form overstates published gross margin by a median 4.09pp) and
    the disclosed conservative bias.

    A non-positive revenue yields NaN rather than a signed ratio, matching
    `ratio`'s zero-denominator policy. The arithmetic is legacy-era only, so any
    metric using this series must be era-guarded.
    """

    def _fn(frame: pd.DataFrame) -> pd.Series:
        indexed = frame.set_index("fiscal_year").sort_index()
        terms = [
            pd.to_numeric(indexed[gp.annual_field(field)], errors="coerce")
            for field in (gp.REVENUE_FIELD, gp.COST_FIELD, gp.DEPRECIATION_FIELD)
        ]
        revenue, cost, depreciation = terms
        profit = gp.gross_profit(revenue, cost, depreciation)
        return profit / revenue.where(revenue > 0)

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


def flag_mixed_era(compute: ComputeFn, span: int, *, flag: str) -> ComputeFn:
    """Flag, rather than null, any point whose window spans more than one era.

    The softer sibling of `require_single_era`, for the case where the
    cross-era divergence was MEASURED and found mild enough to publish. Nulling
    there would discard a mostly-correct value and a genuine Buffett criterion;
    publishing it unmarked would hide a known limitation from the UI. So the
    value ships with the limitation attached to it.

    `span` follows the same convention as `require_single_era`: the number of
    years before `as_of` the window covers.

    A point that is already null keeps its reason and gains no flag -- a flag
    on an absent value has nothing to qualify, and `validate_quality_flag`
    rejects it.
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        points = compute(frame)

        def _flagged(point: MetricPoint) -> MetricPoint:
            if point.value is None:
                return point
            return MetricPoint(
                point.as_of_year,
                point.value,
                point.reason_code,
                point.window_years_present,
                flag,
            )

        if SOURCE_ERA_COLUMN not in frame.columns:
            # Provenance unavailable: flag rather than assume purity, matching
            # `require_single_era`'s refusal to assume.
            return [_flagged(point) for point in points]

        eras = frame.set_index("fiscal_year").sort_index()[SOURCE_ERA_COLUMN]
        out: list[MetricPoint] = []
        for point in points:
            window = eras.loc[point.as_of_year - span : point.as_of_year]
            mixed = window.isna().any() or window.dropna().nunique() > 1
            out.append(_flagged(point) if mixed else point)
        return out

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


def annual_series_metric(series_fn: SeriesFn) -> ComputeFn:
    """Publish a derived per-year series as a one-year "window".

    The intermediate a threshold metric actually tests. `net_margin_ge20_years
    _10y` reports the fraction of years above 0.20, but the reader only sees
    `niq_annual` and `saleq_annual` in the operand grid and has to divide ten
    times to check which years cleared it. Publishing the ratio per year makes
    the verdict inspectable without the console deriving anything.

    Emits one point per year the series covers, with `missing_input` where the
    ratio is undefined -- never a gap, so an absent year is still a row that
    states why.
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        series = series_fn(frame)
        if series.empty:
            return []
        points: list[MetricPoint] = []
        for year in series.index:
            value = series.get(year)
            if value is None or pd.isna(value):
                points.append(MetricPoint(int(year), None, ReasonCode.MISSING_INPUT, 0))
            else:
                points.append(MetricPoint(int(year), float(value), None, 1))
        return points

    return _compute


def paired_window_sum_metric(
    sum_fn: SeriesFn, partner_fn: SeriesFn, n: int, *, min_present: int
) -> ComputeFn:
    """Sum one leg over the window years where BOTH legs are present.

    The masked total behind `sum_ratio_metric`, published so it can be shown.
    The mask is why it must be: the metric sums only paired years, so a reader
    adding up all ten values from the operand grid gets a DIFFERENT number
    than the metric used. Without this, the hand-check that the drilldown
    exists to enable would quietly disagree with the value above it.

    `partner_fn` is a real dependency, not context: change the partner's
    presence and this total changes. It is declared in `inputs` for that
    reason, and `test_declared_inputs.py` enforces it.
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        summed = sum_fn(frame)
        partner = partner_fn(frame)
        if summed.empty or partner.empty:
            return []
        years = sorted(set(summed.index) | set(partner.index))
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            paired = [
                float(summed.get(year))
                for year in range(as_of - n + 1, as_of + 1)
                if pd.notna(summed.get(year)) and pd.notna(partner.get(year))
            ]
            k = len(paired)
            if k < min_present:
                points.append(
                    MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k)
                )
                continue
            points.append(MetricPoint(as_of, float(sum(paired)), None, k))
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


def _consecutive_pairs(years: list[int]) -> list[tuple[int, int]]:
    """Adjacent year pairs, skipping gaps: (y, y+1) only when both are present.

    Shared by every YoY combinator so the pairing rule is defined once (S2.6).
    A gap must not be bridged: comparing 2014 to 2016 as if consecutive would
    silently measure a two-year change as a one-year one.
    """
    return [
        (years[i], years[i + 1])
        for i in range(len(years) - 1)
        if years[i + 1] == years[i] + 1
    ]


def sum_ratio_metric(
    num_fn: SeriesFn, den_fn: SeriesFn, n: int, *, min_present: int
) -> ComputeFn:
    """Sum(num) / Sum(den) over window years where BOTH legs are present.

    Both-present is required so the ratio has one consistent denominator basis:
    summing a numerator over 10 years against a denominator over 8 would
    overstate the ratio by construction. `min_present` is explicit rather than
    the shared 0.8*n floor because the catalog states a hard requirement for
    `capex_pct_net_income_avg10y` (">= 8 required").

    A non-positive denominator sum yields `negative_base`/`zero_denominator`
    rather than a signed ratio: capex against negative cumulative earnings is
    not a meaningful percentage.
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        numerator = num_fn(frame)
        denominator = den_fn(frame)
        if numerator.empty or denominator.empty:
            return []
        years = sorted(set(numerator.index) | set(denominator.index))
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            window = range(as_of - n + 1, as_of + 1)
            pairs = [
                (numerator.get(year), denominator.get(year))
                for year in window
                if pd.notna(numerator.get(year)) and pd.notna(denominator.get(year))
            ]
            k = len(pairs)
            if k < min_present:
                points.append(
                    MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k)
                )
                continue
            den_total = float(sum(pair[1] for pair in pairs))
            if den_total == 0:
                points.append(
                    MetricPoint(as_of, None, ReasonCode.ZERO_DENOMINATOR, k)
                )
            elif den_total < 0:
                points.append(MetricPoint(as_of, None, ReasonCode.NEGATIVE_BASE, k))
            else:
                num_total = float(sum(pair[0] for pair in pairs))
                points.append(MetricPoint(as_of, num_total / den_total, None, k))
        return points

    return _compute


def slope_metric(series_fn: SeriesFn, n: int) -> ComputeFn:
    """Ordinary-least-squares slope per year over the window's present years.

    Pins the catalog's underspecified "trend of ..." to an exact rule. OLS
    rather than last-minus-first because the latter is decided by two points and
    inverts on a single outlier year. Units are "change in the ratio per year",
    so a negative value means the series is falling.

    Needs at least two DISTINCT years for the slope to exist; a window whose
    present years collapse to one point yields `insufficient_history` rather
    than a zero slope, which would read as "flat" rather than "unknown".
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        series = series_fn(frame)
        if series.empty:
            return []
        years = list(series.index)
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            present = _window_present(series, as_of, n)
            k = len(present)
            if k < _min_present(n) or present.index.nunique() < 2:
                points.append(
                    MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k)
                )
                continue
            x = [float(year) for year in present.index]
            y = [float(value) for value in present]
            x_mean = sum(x) / len(x)
            y_mean = sum(y) / len(y)
            variance = sum((xi - x_mean) ** 2 for xi in x)
            covariance = sum(
                (xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y, strict=True)
            )
            points.append(MetricPoint(as_of, covariance / variance, None, k))
        return points

    return _compute


def direction_correspondence_metric(
    first_fn: SeriesFn, second_fn: SeriesFn, n: int
) -> ComputeFn:
    """Fraction of consecutive year-pairs where two series move the same way.

    A pair counts only when both series are present at both of its years. A zero
    change on EITHER side counts as NOT corresponding: a flat series has no
    direction, and treating it as agreement would let a dormant balance-sheet
    line read as tracking earnings.
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        first = first_fn(frame)
        second = second_fn(frame)
        if first.empty or second.empty:
            return []
        years = sorted(set(first.index) | set(second.index))
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            usable = [
                year
                for year in range(as_of - n + 1, as_of + 1)
                if pd.notna(first.get(year)) and pd.notna(second.get(year))
            ]
            k = len(usable)
            pairs = _consecutive_pairs(usable)
            if k < _min_present(n) or not pairs:
                points.append(
                    MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k)
                )
                continue
            corresponding = 0
            for earlier, later in pairs:
                delta_first = first[later] - first[earlier]
                delta_second = second[later] - second[earlier]
                if delta_first == 0 or delta_second == 0:
                    continue
                if (delta_first > 0) == (delta_second > 0):
                    corresponding += 1
            points.append(MetricPoint(as_of, corresponding / len(pairs), None, k))
        return points

    return _compute


def negative_equity_with_strong_earnings_metric(
    equity_fn: SeriesFn, earnings_fn: SeriesFn, n: int, *, min_profitable_years: int
) -> ComputeFn:
    """1.0 when equity is negative AND earnings were positive in enough years.

    The book's durable-advantage special case: negative book equity created by
    buybacks or dividends, alongside a long record of profits, is a strength
    rather than distress. Both conditions must hold, so this is a conjunction
    rather than two metrics -- reporting them separately would invite reading the
    negative-equity leg alone as a negative signal.

    Emits 0.0 (not a null) when the conditions simply do not hold: that is a
    real answer. Nulls are reserved for a missing equity reading
    (`missing_input`) or too little earnings history (`insufficient_history`).
    """

    def _compute(frame: pd.DataFrame) -> list[MetricPoint]:
        equity = equity_fn(frame)
        earnings = earnings_fn(frame)
        if equity.empty or earnings.empty:
            return []
        years = sorted(set(equity.index) | set(earnings.index))
        points: list[MetricPoint] = []
        for as_of in range(years[0] + n - 1, years[-1] + 1):
            present = _window_present(earnings, as_of, n)
            k = len(present)
            latest_equity = equity.get(as_of)
            if latest_equity is None or pd.isna(latest_equity):
                points.append(MetricPoint(as_of, None, ReasonCode.MISSING_INPUT, k))
                continue
            if k < _min_present(n):
                points.append(
                    MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k)
                )
                continue
            profitable = int((present > 0).sum())
            qualifies = latest_equity < 0 and profitable >= min_profitable_years
            points.append(MetricPoint(as_of, 1.0 if qualifies else 0.0, None, k))
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
            pairs = _consecutive_pairs(list(present.index))
            if not pairs:
                points.append(MetricPoint(as_of, None, ReasonCode.INSUFFICIENT_HISTORY, k))
            else:
                increases = sum(1 for a, b in pairs if present[b] > present[a])
                points.append(MetricPoint(as_of, increases / len(pairs), None, k))
        return points

    return _compute
