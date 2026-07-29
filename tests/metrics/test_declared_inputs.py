"""Every metric's declared `inputs` must match what it actually reads.

The console shows these fields as the audit trail behind a value. A declaration
that drifted from its compute function would put a false provenance on screen
in the one place that exists to prevent false numbers, so it is not taken on
trust.

The check: compute each metric twice -- once against a fully populated frame,
once against the same frame with every UNDECLARED value column nulled. If a
metric reads a column it did not declare, nulling that column changes its
output and the test fails.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.fundamentals_annual_schema import (
    ANNUAL_VALUE_COLUMNS,
)
from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
    SUPPORT_RAW_FIELDS,
)
from fundamentals_pipeline.metrics.quarterly_registry import QUARTERLY_REGISTRY
from fundamentals_pipeline.metrics.registry import REGISTRY

LEGACY = "legacy_compustat"
YEARS = list(range(2010, 2025))
QUARTERLY_FIELDS = (*CORE_RAW_FIELDS, *SUPPORT_RAW_FIELDS, *EXTENDED_RAW_FIELDS)


# Revenue must dominate the cost lines, or gross profit (saleq - cogsq - dpq)
# comes out negative and every gross-profit-denominated metric returns
# negative_base. That made three drift checks vacuously pass on an all-null
# comparison until the "guard the guard" test below caught it.
REVENUE_COLUMNS = frozenset({"saleq", "saleq_annual"})
REVENUE_SCALE = 20.0


def _value(column: str, index: int) -> float:
    """A deterministic, column-distinct, strictly positive value.

    Distinct per column so that substituting one column for another changes the
    result; positive and growing so that CAGR, slope and up-year metrics all
    produce real values rather than reasoned nulls. No randomness, per
    AGENTS.md S3.2.
    """
    seed = sum(ord(character) for character in column)
    base = 100.0 + (seed % 37) * 3.0 + index * (1.0 + (seed % 5) * 0.25)
    return base * REVENUE_SCALE if column in REVENUE_COLUMNS else base


def _annual_frame() -> pd.DataFrame:
    rows = []
    for index, year in enumerate(YEARS):
        row = {"ticker": "TEST", "fiscal_year": year, "source_era": LEGACY}
        for column in ANNUAL_VALUE_COLUMNS:
            row[column] = _value(column, index)
        rows.append(row)
    return pd.DataFrame(rows)


def _quarterly_frame() -> pd.DataFrame:
    rows = []
    index = 0
    for year in YEARS:
        for quarter in (1, 2, 3, 4):
            row = {
                "ticker": "TEST",
                "year": year,
                "quarter": quarter,
                "source_era": LEGACY,
            }
            for column in QUARTERLY_FIELDS:
                row[column] = _value(column, index)
            rows.append(row)
            index += 1
    return pd.DataFrame(rows)


def _blank_undeclared(frame: pd.DataFrame, keep: tuple[str, ...], value_columns):
    """Null every value column the metric did not declare."""
    out = frame.copy()
    for column in value_columns:
        if column not in keep:
            out[column] = float("nan")
    return out


def _points(compute, frame) -> list[tuple]:
    return [
        (p.as_of_year if hasattr(p, "as_of_year") else (p.year, p.quarter),
         p.value, p.reason_code, getattr(p, "quality_flag", None))
        for p in compute(frame)
    ]


@pytest.mark.parametrize("metric", REGISTRY, ids=lambda m: m.metric_id)
def test_trend_metric_reads_only_its_declared_inputs(metric):
    full = _annual_frame()
    trimmed = _blank_undeclared(full, metric.inputs, ANNUAL_VALUE_COLUMNS)
    assert _points(metric.compute, full) == _points(metric.compute, trimmed), (
        f"{metric.metric_id} changes when columns outside "
        f"{list(metric.inputs)} are nulled, so its declared inputs are wrong."
    )


@pytest.mark.parametrize("metric", QUARTERLY_REGISTRY, ids=lambda m: m.metric_id)
def test_quarterly_metric_reads_only_its_declared_inputs(metric):
    full = _quarterly_frame()
    trimmed = _blank_undeclared(full, metric.inputs, QUARTERLY_FIELDS)
    assert _points(metric.compute, full) == _points(metric.compute, trimmed), (
        f"{metric.metric_id} changes when fields outside "
        f"{list(metric.inputs)} are nulled, so its declared inputs are wrong."
    )


@pytest.mark.parametrize("metric", REGISTRY, ids=lambda m: m.metric_id)
def test_trend_fixture_produces_real_values_not_vacuous_nulls(metric):
    """Guard the guard: an all-null output would make the check meaningless."""
    points = metric.compute(_annual_frame())
    assert any(p.value is not None for p in points), (
        f"{metric.metric_id} produced no values on the fixture, so the "
        "declared-inputs check above proves nothing for it."
    )


@pytest.mark.parametrize("metric", QUARTERLY_REGISTRY, ids=lambda m: m.metric_id)
def test_quarterly_fixture_produces_real_values_not_vacuous_nulls(metric):
    points = metric.compute(_quarterly_frame())
    assert any(p.value is not None for p in points), (
        f"{metric.metric_id} produced no values on the fixture, so the "
        "declared-inputs check above proves nothing for it."
    )


def test_every_declared_input_is_a_real_column():
    """A typo'd input would render an empty audit trail rather than an error."""
    annual = set(ANNUAL_VALUE_COLUMNS)
    for metric in REGISTRY:
        unknown = sorted(set(metric.inputs) - annual)
        assert not unknown, f"{metric.metric_id}: not annual columns: {unknown}"

    quarterly = set(QUARTERLY_FIELDS)
    for metric in QUARTERLY_REGISTRY:
        unknown = sorted(set(metric.inputs) - quarterly)
        assert not unknown, f"{metric.metric_id}: not Stage 1 fields: {unknown}"
