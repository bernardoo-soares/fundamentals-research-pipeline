from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.contracts.metrics_quarterly_schema import (
    METRICS_QUARTERLY_COLUMNS,
    QUALITY_FLAGS,
    QuarterPoint,
    create_metrics_quarterly_ddl,
)


def test_value_point_ok() -> None:
    p = QuarterPoint(2023, 4, 0.25, None, None, "simfin")
    assert p.value == 0.25


def test_reason_point_ok() -> None:
    p = QuarterPoint(2023, 1, None, ReasonCode.MISSING_INPUT, None, "simfin")
    assert p.reason_code == ReasonCode.MISSING_INPUT


def test_value_and_reason_together_rejected() -> None:
    with pytest.raises(ValueError):
        QuarterPoint(2023, 4, 0.25, ReasonCode.MISSING_INPUT, None, "simfin")


def test_quality_flag_requires_a_value() -> None:
    with pytest.raises(ValueError):
        QuarterPoint(
            2023, 4, None, ReasonCode.MISSING_INPUT,
            ReasonCode.TSTK_UNAVAILABLE, "simfin",
        )


def test_quality_flag_must_be_known() -> None:
    with pytest.raises(ValueError):
        QuarterPoint(2023, 4, 1.0, None, "bogus_flag", "simfin")


def test_quality_flag_on_value_ok() -> None:
    p = QuarterPoint(2023, 4, 4.67, None, ReasonCode.TSTK_UNAVAILABLE, "simfin")
    assert p.quality_flag == ReasonCode.TSTK_UNAVAILABLE
    assert ReasonCode.TSTK_UNAVAILABLE in QUALITY_FLAGS


def test_columns_and_ddl_agree() -> None:
    for column in METRICS_QUARTERLY_COLUMNS:
        assert column in create_metrics_quarterly_ddl()
    assert (
        "PRIMARY KEY (ticker, year, quarter, metric_id)"
        in create_metrics_quarterly_ddl()
    )
