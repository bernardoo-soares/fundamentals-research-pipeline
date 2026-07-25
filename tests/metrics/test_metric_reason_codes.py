from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.metric_reason_codes import (
    REASON_CODES,
    ReasonCode,
    validate_value_xor_reason,
)


def test_tstk_unavailable_is_in_the_closed_set() -> None:
    assert ReasonCode.TSTK_UNAVAILABLE in REASON_CODES
    assert ReasonCode.MIXED_ERA_WINDOW in REASON_CODES


def test_value_xor_reason_accepts_exactly_one() -> None:
    validate_value_xor_reason(1.0, None)
    validate_value_xor_reason(None, ReasonCode.MISSING_INPUT)


def test_value_xor_reason_rejects_both_or_neither() -> None:
    with pytest.raises(ValueError):
        validate_value_xor_reason(1.0, ReasonCode.MISSING_INPUT)
    with pytest.raises(ValueError):
        validate_value_xor_reason(None, None)


def test_value_xor_reason_rejects_unknown_code() -> None:
    with pytest.raises(ValueError):
        validate_value_xor_reason(None, "not_a_code")


def test_trend_schema_reexports_reason_code() -> None:
    from fundamentals_pipeline.contracts import stage2_metrics_schema as s

    assert s.ReasonCode.MISSING_INPUT == ReasonCode.MISSING_INPUT
    assert s.REASON_CODES is REASON_CODES
