"""Pure TTM and point-in-time quarterly-metric helpers and combinators.

A compute function maps one ticker's quarterly frame (the fundamentals_quarterly
columns, one row per quarter) to a list[QuarterPoint], one per quarter. No I/O.

Era purity for TTM sums is enforced here from contracts/field_era_semantics.py:
a TTM on a field the two providers do not measure identically
(eras_equivalent=False) whose four-quarter window spans more than one
source_era is nulled `mixed_era_window`. A TTM on an equivalent field mixes
freely. Point-in-time stock values are single-quarter, hence single-era.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from ..contracts.field_era_semantics import semantics_for
from ..contracts.metric_reason_codes import ReasonCode
from ..contracts.metrics_quarterly_schema import QuarterPoint

ComputeFn = Callable[[pd.DataFrame], list[QuarterPoint]]

QUARTERS_PER_YEAR = 4
TTM_QUARTERS = 4
YEAR_COLUMN = "year"
QUARTER_COLUMN = "quarter"
SOURCE_ERA_COLUMN = "source_era"
QUARTER_INDEX_COLUMN = "_quarter_index"

# (value, reason_code, quality_flag) for one as-of quarter.
ValueFn = Callable[[int], "tuple[float | None, str | None, str | None]"]


def _quarter_index(year: int, quarter: int) -> int:
    """Dense monotonic index over calendar quarters (consecutive => +1)."""
    return year * QUARTERS_PER_YEAR + (quarter - 1)


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the quarter index and sort by it (determinism, S3)."""
    prepared = frame.copy()
    prepared[QUARTER_INDEX_COLUMN] = [
        _quarter_index(int(year), int(quarter))
        for year, quarter in zip(
            prepared[YEAR_COLUMN], prepared[QUARTER_COLUMN], strict=True
        )
    ]
    return prepared.sort_values(QUARTER_INDEX_COLUMN).reset_index(drop=True)


def _era_of(value: object) -> str | None:
    return str(value) if pd.notna(value) else None


@dataclass(frozen=True)
class TtmResult:
    total: float
    mixed_non_equivalent: bool


@dataclass(frozen=True)
class StockResult:
    value: float | None
    source_era: str | None


def ttm_flow(frame: pd.DataFrame, field: str) -> dict[int, TtmResult]:
    """TTM sum keyed by as-of quarter index; only full consecutive four-runs.

    A window is present only when all four preceding-and-current quarter indices
    exist with non-null values (a calendar gap leaves an index absent). Marks
    the result mixed when the field is not cross-era equivalent and the window
    is not provably a single era -- either it spans more than one era or any
    quarter's provenance is unknown. Unknown provenance is treated as impure
    rather than trusted, mirroring windows.require_single_era (refuse rather
    than assume purity); imputing purity is exactly the failure S4.2 forbids.
    """
    equivalent = semantics_for(field).eras_equivalent
    values = pd.to_numeric(frame[field], errors="coerce")
    value_by_index = dict(zip(frame[QUARTER_INDEX_COLUMN], values, strict=True))
    era_by_index = dict(
        zip(frame[QUARTER_INDEX_COLUMN], frame[SOURCE_ERA_COLUMN], strict=True)
    )
    out: dict[int, TtmResult] = {}
    for as_of in frame[QUARTER_INDEX_COLUMN]:
        window = [as_of - offset for offset in range(TTM_QUARTERS - 1, -1, -1)]
        window_values = [value_by_index.get(index) for index in window]
        if any(value is None or pd.isna(value) for value in window_values):
            continue
        eras = {_era_of(era_by_index.get(index)) for index in window}
        impure = None in eras or len(eras) > 1
        mixed = (not equivalent) and impure
        out[int(as_of)] = TtmResult(float(sum(window_values)), mixed)
    return out


def stock_at(frame: pd.DataFrame, field: str) -> dict[int, StockResult]:
    """Point-in-time value at each quarter, with that quarter's source_era."""
    values = pd.to_numeric(frame[field], errors="coerce")
    out: dict[int, StockResult] = {}
    for as_of, value, era in zip(
        frame[QUARTER_INDEX_COLUMN], values, frame[SOURCE_ERA_COLUMN], strict=True
    ):
        clean = float(value) if pd.notna(value) else None
        out[int(as_of)] = StockResult(clean, _era_of(era))
    return out


def _denominator_reason(denominator: float) -> str | None:
    """Shared denominator policy: 0 => zero_denominator, <0 => negative_base."""
    if denominator == 0:
        return ReasonCode.ZERO_DENOMINATOR
    if denominator < 0:
        return ReasonCode.NEGATIVE_BASE
    return None


def _points_over_frame(frame: pd.DataFrame, value_for: ValueFn) -> list[QuarterPoint]:
    """Emit one QuarterPoint per quarter; value_for maps as-of index -> outcome."""
    points: list[QuarterPoint] = []
    for year, quarter, as_of, era in zip(
        frame[YEAR_COLUMN],
        frame[QUARTER_COLUMN],
        frame[QUARTER_INDEX_COLUMN],
        frame[SOURCE_ERA_COLUMN],
        strict=True,
    ):
        value, reason, flag = value_for(int(as_of))
        points.append(
            QuarterPoint(int(year), int(quarter), value, reason, flag, _era_of(era))
        )
    return points


def ttm_ratio(num_field: str, den_field: str) -> ComputeFn:
    """num_ttm / den_ttm (both flows)."""

    def _compute(frame: pd.DataFrame) -> list[QuarterPoint]:
        prepared = _prepare(frame)
        num = ttm_flow(prepared, num_field)
        den = ttm_flow(prepared, den_field)

        def value_for(as_of: int):
            n = num.get(as_of)
            d = den.get(as_of)
            if n is None or d is None:
                return None, ReasonCode.MISSING_INPUT, None
            if n.mixed_non_equivalent or d.mixed_non_equivalent:
                return None, ReasonCode.MIXED_ERA_WINDOW, None
            reason = _denominator_reason(d.total)
            if reason is not None:
                return None, reason, None
            return n.total / d.total, None, None

        return _points_over_frame(prepared, value_for)

    return _compute


def ttm_over_stock(num_field: str, den_field: str) -> ComputeFn:
    """num_ttm (flow) / den_latest (stock)."""

    def _compute(frame: pd.DataFrame) -> list[QuarterPoint]:
        prepared = _prepare(frame)
        num = ttm_flow(prepared, num_field)
        den = stock_at(prepared, den_field)

        def value_for(as_of: int):
            n = num.get(as_of)
            d = den.get(as_of)
            if n is None or d is None or d.value is None:
                return None, ReasonCode.MISSING_INPUT, None
            if n.mixed_non_equivalent:
                return None, ReasonCode.MIXED_ERA_WINDOW, None
            reason = _denominator_reason(d.value)
            if reason is not None:
                return None, reason, None
            return n.total / d.value, None, None

        return _points_over_frame(prepared, value_for)

    return _compute


def stock_over_ttm(num_field: str, den_field: str) -> ComputeFn:
    """num_latest (stock) / den_ttm (flow)."""

    def _compute(frame: pd.DataFrame) -> list[QuarterPoint]:
        prepared = _prepare(frame)
        num = stock_at(prepared, num_field)
        den = ttm_flow(prepared, den_field)

        def value_for(as_of: int):
            n = num.get(as_of)
            d = den.get(as_of)
            if n is None or n.value is None or d is None:
                return None, ReasonCode.MISSING_INPUT, None
            if d.mixed_non_equivalent:
                return None, ReasonCode.MIXED_ERA_WINDOW, None
            reason = _denominator_reason(d.total)
            if reason is not None:
                return None, reason, None
            return n.value / d.total, None, None

        return _points_over_frame(prepared, value_for)

    return _compute


def stock_ratio(num_field: str, den_field: str) -> ComputeFn:
    """num_latest / den_latest (both stocks)."""

    def _compute(frame: pd.DataFrame) -> list[QuarterPoint]:
        prepared = _prepare(frame)
        num = stock_at(prepared, num_field)
        den = stock_at(prepared, den_field)

        def value_for(as_of: int):
            n = num.get(as_of)
            d = den.get(as_of)
            if n is None or n.value is None or d is None or d.value is None:
                return None, ReasonCode.MISSING_INPUT, None
            reason = _denominator_reason(d.value)
            if reason is not None:
                return None, reason, None
            return n.value / d.value, None, None

        return _points_over_frame(prepared, value_for)

    return _compute


LIABILITIES_FIELD = "ltq"
EQUITY_FIELD = "ceqq"
TREASURY_FIELD = "tstkq"


def debt_to_equity_adj_metric() -> ComputeFn:
    """ltq / (ceqq + tstkq); tstkq null => ltq / ceqq flagged tstk_unavailable."""

    def _compute(frame: pd.DataFrame) -> list[QuarterPoint]:
        prepared = _prepare(frame)
        liabilities = stock_at(prepared, LIABILITIES_FIELD)
        equity = stock_at(prepared, EQUITY_FIELD)
        treasury = stock_at(prepared, TREASURY_FIELD)

        def value_for(as_of: int):
            debt = liabilities.get(as_of)
            eq = equity.get(as_of)
            tstk = treasury.get(as_of)
            if debt is None or debt.value is None or eq is None or eq.value is None:
                return None, ReasonCode.MISSING_INPUT, None
            tstk_missing = tstk is None or tstk.value is None
            denominator = eq.value if tstk_missing else eq.value + tstk.value
            reason = _denominator_reason(denominator)
            if reason is not None:
                return None, reason, None
            flag = ReasonCode.TSTK_UNAVAILABLE if tstk_missing else None
            return debt.value / denominator, None, flag

        return _points_over_frame(prepared, value_for)

    return _compute


def apply_era_restriction(
    points: list[QuarterPoint],
    supported_eras: frozenset[str] | None,
) -> list[QuarterPoint]:
    """Null every point whose source_era falls outside the declared set.

    Returns points unchanged when `supported_eras` is None (the metric applies
    everywhere). Otherwise a point outside the set becomes a reasoned null with
    ERA_NOT_SUPPORTED, keeping its year/quarter/source_era so the row stays
    addressable and its provenance auditable.

    A point whose provenance is unknown (source_era None) is nulled too:
    refusing rather than assuming membership, mirroring
    windows.require_single_era. Assuming membership would be imputation (S4.2).

    Relabel only points that still carry a value. A point already nulled with
    `missing_input` or `negative_base` keeps that reason: the more specific
    diagnosis is the useful one, and overwriting it would attribute genuine
    data gaps to era restriction in downstream reason-code tallies. This
    mirrors windows.require_single_era's `_blocked` helper. A relabelled point
    has its quality_flag cleared, since a flag may not survive on a null.
    """
    if supported_eras is None:
        return points
    restricted: list[QuarterPoint] = []
    for point in points:
        if point.source_era is not None and point.source_era in supported_eras:
            restricted.append(point)
            continue
        if point.reason_code is not None:
            restricted.append(point)
            continue
        restricted.append(
            QuarterPoint(
                point.year,
                point.quarter,
                None,
                ReasonCode.ERA_NOT_SUPPORTED,
                None,
                point.source_era,
            )
        )
    return restricted


def presence_flag(field: str, *, threshold: float) -> ComputeFn:
    """1.0 if the latest value > threshold, else 0.0; null if the value absent."""

    def _compute(frame: pd.DataFrame) -> list[QuarterPoint]:
        prepared = _prepare(frame)
        stock = stock_at(prepared, field)

        def value_for(as_of: int):
            point = stock.get(as_of)
            if point is None or point.value is None:
                return None, ReasonCode.MISSING_INPUT, None
            return (1.0 if point.value > threshold else 0.0), None, None

        return _points_over_frame(prepared, value_for)

    return _compute
