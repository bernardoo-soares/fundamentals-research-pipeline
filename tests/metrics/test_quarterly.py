from __future__ import annotations

import math

import pandas as pd

from fundamentals_pipeline.contracts.era_resolution import SourceEra
from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.contracts.metrics_quarterly_schema import QuarterPoint
from fundamentals_pipeline.metrics.quarterly import (
    apply_era_restriction,
    debt_to_equity_adj_metric,
    presence_flag,
    stock_over_ttm,
    stock_ratio,
    ttm_over_stock,
    ttm_ratio,
)

LEGACY_ONLY = frozenset({SourceEra.LEGACY})


def _era_point(era, value=1.5):
    """Build a lone QuarterPoint for era-restriction tests.

    Named distinctly from the pre-existing `_point(points, year, quarter)`
    lookup helper below (17 call sites) to avoid shadowing it; the brief's
    original snippet named this helper `_point` too, which would have
    silently broken every existing test in this file.
    """
    return QuarterPoint(2023, 1, value, None, None, era)


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _q(year: int, quarter: int, era: str, **fields) -> dict:
    row = {"year": year, "quarter": quarter, "source_era": era}
    row.update(fields)
    return row


def _four_quarters(era: str = "simfin", **fields) -> list[dict]:
    # fields map name -> (q1, q2, q3, q4)
    rows = []
    for i, quarter in enumerate((1, 2, 3, 4)):
        rows.append(_q(2023, quarter, era, **{k: v[i] for k, v in fields.items()}))
    return rows


def _point(points, year, quarter):
    return next(p for p in points if p.year == year and p.quarter == quarter)


def test_ttm_ratio_sums_four_consecutive_quarters() -> None:
    rows = _four_quarters(
        niq=(1.0, 2.0, 3.0, 4.0), saleq=(10.0, 10.0, 10.0, 10.0)
    )
    points = ttm_ratio("niq", "saleq")(_frame(rows))
    p = _point(points, 2023, 4)
    assert p.value == (1.0 + 2.0 + 3.0 + 4.0) / 40.0
    assert p.reason_code is None
    # 2023Q1..Q3 lack a full trailing four-run -> missing_input
    assert _point(points, 2023, 1).reason_code == ReasonCode.MISSING_INPUT


def test_ttm_ratio_missing_quarter_yields_missing_input() -> None:
    rows = _four_quarters(
        niq=(1.0, 2.0, 3.0, 4.0), saleq=(10.0, 10.0, 10.0, 10.0)
    )
    rows[1]["niq"] = None  # gap in the window
    points = ttm_ratio("niq", "saleq")(_frame(rows))
    assert _point(points, 2023, 4).reason_code == ReasonCode.MISSING_INPUT


def test_ttm_ratio_zero_denominator() -> None:
    rows = _four_quarters(niq=(1.0, 1.0, 1.0, 1.0), saleq=(0.0, 0.0, 0.0, 0.0))
    points = ttm_ratio("niq", "saleq")(_frame(rows))
    assert _point(points, 2023, 4).reason_code == ReasonCode.ZERO_DENOMINATOR


def test_non_equivalent_ttm_across_eras_is_mixed_era_window() -> None:
    # xintq is eras_equivalent=False; a window ending 2023Q1 covers 2022Q2-Q4
    # (legacy) + 2023Q1 (simfin) -> mixed.
    rows = [
        _q(2022, 2, "legacy_compustat", xintq=1.0, oiadpq=10.0),
        _q(2022, 3, "legacy_compustat", xintq=1.0, oiadpq=10.0),
        _q(2022, 4, "legacy_compustat", xintq=1.0, oiadpq=10.0),
        _q(2023, 1, "simfin", xintq=-5.0, oiadpq=10.0),
    ]
    points = ttm_ratio("xintq", "oiadpq")(_frame(rows))
    assert _point(points, 2023, 1).reason_code == ReasonCode.MIXED_ERA_WINDOW


def test_non_equivalent_ttm_with_unknown_provenance_is_mixed_era_window() -> None:
    # A null source_era in the window must be refused, not assumed pure
    # (mirrors windows.require_single_era). xintq is non-equivalent.
    rows = [
        _q(2023, 1, "simfin", xintq=1.0, oiadpq=10.0),
        _q(2023, 2, "simfin", xintq=1.0, oiadpq=10.0),
        _q(2023, 3, None, xintq=1.0, oiadpq=10.0),
        _q(2023, 4, "simfin", xintq=1.0, oiadpq=10.0),
    ]
    points = ttm_ratio("xintq", "oiadpq")(_frame(rows))
    assert _point(points, 2023, 4).reason_code == ReasonCode.MIXED_ERA_WINDOW


def test_equivalent_ttm_across_eras_is_allowed() -> None:
    # niq is eras_equivalent=True; the same boundary window computes a value.
    rows = [
        _q(2022, 2, "legacy_compustat", niq=1.0, saleq=10.0),
        _q(2022, 3, "legacy_compustat", niq=1.0, saleq=10.0),
        _q(2022, 4, "legacy_compustat", niq=1.0, saleq=10.0),
        _q(2023, 1, "simfin", niq=1.0, saleq=10.0),
    ]
    points = ttm_ratio("niq", "saleq")(_frame(rows))
    assert _point(points, 2023, 1).value == 4.0 / 40.0


def test_ttm_over_stock_negative_base() -> None:
    rows = _four_quarters(niq=(1.0, 1.0, 1.0, 1.0), ceqq=(0.0, 0.0, 0.0, -5.0))
    points = ttm_over_stock("niq", "ceqq")(_frame(rows))
    assert _point(points, 2023, 4).reason_code == ReasonCode.NEGATIVE_BASE


def test_stock_ratio_null_denominator_is_missing_input() -> None:
    rows = [_q(2023, 4, "simfin", dlcq=5.0, dlttq=None)]
    points = stock_ratio("dlcq", "dlttq")(_frame(rows))
    assert _point(points, 2023, 4).reason_code == ReasonCode.MISSING_INPUT


def test_stock_over_ttm_uses_point_numerator_and_ttm_denominator() -> None:
    rows = _four_quarters(dlttq=(0.0, 0.0, 0.0, 60.0), niq=(2.0, 2.0, 2.0, 2.0))
    points = stock_over_ttm("dlttq", "niq")(_frame(rows))
    assert _point(points, 2023, 4).value == 60.0 / 8.0


def test_debt_to_equity_adj_tstk_present_no_flag() -> None:
    rows = [_q(2022, 4, "legacy_compustat", ltq=100.0, ceqq=40.0, tstkq=0.0)]
    points = debt_to_equity_adj_metric()(_frame(rows))
    p = _point(points, 2022, 4)
    assert p.value == 100.0 / 40.0
    assert p.quality_flag is None


def test_debt_to_equity_adj_tstk_null_flags_and_keeps_value() -> None:
    rows = [_q(2023, 4, "simfin", ltq=100.0, ceqq=40.0, tstkq=None)]
    points = debt_to_equity_adj_metric()(_frame(rows))
    p = _point(points, 2023, 4)
    assert p.value == 100.0 / 40.0
    assert p.quality_flag == ReasonCode.TSTK_UNAVAILABLE


def test_debt_to_equity_adj_nonpositive_denominator_is_null() -> None:
    rows = [_q(2023, 4, "simfin", ltq=100.0, ceqq=-40.0, tstkq=None)]
    points = debt_to_equity_adj_metric()(_frame(rows))
    assert _point(points, 2023, 4).reason_code == ReasonCode.NEGATIVE_BASE


def test_presence_flag() -> None:
    rows = [
        _q(2023, 4, "simfin", tstkq=5.0),
        _q(2023, 3, "simfin", tstkq=0.0),
        _q(2023, 2, "simfin", tstkq=None),
    ]
    points = presence_flag("tstkq", threshold=0.0)(_frame(rows))
    assert _point(points, 2023, 4).value == 1.0
    assert _point(points, 2023, 3).value == 0.0
    assert _point(points, 2023, 2).reason_code == ReasonCode.MISSING_INPUT


def test_no_nan_or_inf_reaches_a_value() -> None:
    rows = _four_quarters(niq=(1.0, 1.0, 1.0, 1.0), saleq=(0.0, 0.0, 0.0, 0.0))
    for p in ttm_ratio("niq", "saleq")(_frame(rows)):
        if p.value is not None:
            assert math.isfinite(p.value)


def test_apply_era_restriction_passes_through_when_unrestricted():
    """supported_eras=None means the metric applies to every era."""
    points = [_era_point(SourceEra.SIMFIN)]
    assert apply_era_restriction(points, None) == points


def test_apply_era_restriction_keeps_supported_eras():
    point = _era_point(SourceEra.LEGACY)
    (out,) = apply_era_restriction([point], LEGACY_ONLY)
    assert out.value == 1.5
    assert out.reason_code is None


def test_apply_era_restriction_nulls_unsupported_eras():
    (out,) = apply_era_restriction([_era_point(SourceEra.SIMFIN)], LEGACY_ONLY)
    assert out.value is None
    assert out.reason_code == ReasonCode.ERA_NOT_SUPPORTED
    assert out.year == 2023 and out.quarter == 1
    assert out.source_era == SourceEra.SIMFIN, "provenance is preserved"


def test_apply_era_restriction_nulls_unknown_provenance():
    """Refuse rather than assume membership, mirroring require_single_era."""
    (out,) = apply_era_restriction([_era_point(None)], LEGACY_ONLY)
    assert out.reason_code == ReasonCode.ERA_NOT_SUPPORTED


def test_apply_era_restriction_clears_a_quality_flag():
    """A flag may not survive on a nulled value (QuarterPoint invariant)."""
    flagged = QuarterPoint(
        2023, 1, 4.67, None, ReasonCode.TSTK_UNAVAILABLE, SourceEra.SIMFIN
    )
    (out,) = apply_era_restriction([flagged], LEGACY_ONLY)
    assert out.value is None
    assert out.quality_flag is None


def test_apply_era_restriction_overrides_an_existing_reason():
    """Outside a supported era the metric does not apply at all, so
    era_not_supported wins over whatever else was missing. Deterministic."""
    missing = QuarterPoint(
        2023, 1, None, ReasonCode.MISSING_INPUT, None, SourceEra.SIMFIN
    )
    (out,) = apply_era_restriction([missing], LEGACY_ONLY)
    assert out.reason_code == ReasonCode.ERA_NOT_SUPPORTED
