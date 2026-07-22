from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.stage2_metrics_schema import (
    METRICS_TREND_COLUMNS,
    REASON_CODES,
    MetricPoint,
    ReasonCode,
    TrendMetric,
    create_metrics_trend_ddl,
)
from fundamentals_pipeline.warehouse.connection import open_warehouse


def test_reason_codes_closed_set() -> None:
    assert ReasonCode.INSUFFICIENT_HISTORY in REASON_CODES
    assert ReasonCode.NEGATIVE_BASE in REASON_CODES
    assert ReasonCode.MISSING_INPUT in REASON_CODES
    # full spec set is declared for later slices
    assert {
        "missing_input",
        "incomplete_year",
        "negative_base",
        "zero_denominator",
        "not_applicable_sector",
        "insufficient_history",
        "tstk_unavailable",
    } == set(REASON_CODES)


def test_metric_point_requires_exactly_one_of_value_or_reason() -> None:
    MetricPoint(2024, 0.1, None, 10)                 # value only: ok
    MetricPoint(2024, None, ReasonCode.NEGATIVE_BASE, 3)  # reason only: ok
    with pytest.raises(ValueError):
        MetricPoint(2024, 0.1, ReasonCode.NEGATIVE_BASE, 10)  # both
    with pytest.raises(ValueError):
        MetricPoint(2024, None, None, 10)            # neither
    with pytest.raises(ValueError):
        MetricPoint(2024, None, "not_a_code", 10)    # invalid code


def test_metrics_trend_columns_and_ddl(tmp_path) -> None:
    assert METRICS_TREND_COLUMNS == (
        "ticker",
        "as_of_year",
        "metric_id",
        "value",
        "reason_code",
        "window_length",
        "window_years_present",
        "metric_version",
        "computed_at",
        "pipeline_version",
    )
    db = tmp_path / "w.duckdb"
    with open_warehouse(db) as conn:
        conn.execute(create_metrics_trend_ddl())
        cols = [
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'metrics_trend' ORDER BY ordinal_position"
            ).fetchall()
        ]
    assert cols == list(METRICS_TREND_COLUMNS)


def test_trend_metric_fields() -> None:
    m = TrendMetric("x", "1", 10, "formula", compute=lambda frame: [])
    assert (m.metric_id, m.version, m.window_length, m.formula) == ("x", "1", 10, "formula")
    assert callable(m.compute)
