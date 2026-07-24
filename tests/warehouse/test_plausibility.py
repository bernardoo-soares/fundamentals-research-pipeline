"""Tests for the impossible-value plausibility gate."""

from __future__ import annotations

import pandas as pd

from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    NON_NEGATIVE_FIELDS,
)
from fundamentals_pipeline.warehouse.plausibility import (
    VIOLATION_COLUMNS,
    apply_non_negative_gate,
)


def _frame(**fields):
    base = {"ticker": ["MAR"], "year": [2023], "quarter": [4]}
    return pd.DataFrame({**base, **{k: [v] for k, v in fields.items()}})


def test_negative_revenue_is_nulled_and_recorded():
    """Marriott's real SimFin FY2023 Q4 revenue was -11318, which halved the
    annual figure (6300 against a true 23713). A null beats a wrong total."""
    result = apply_non_negative_gate(_frame(saleq=-11318.0))
    assert pd.isna(result.frame["saleq"].iloc[0])
    assert result.nulled_count == 1
    violation = result.violations.iloc[0]
    assert violation["field_name"] == "saleq"
    assert violation["observed_value"] == -11318.0
    assert violation["action"] == "nulled"
    assert tuple(result.violations.columns) == VIOLATION_COLUMNS


def test_positive_and_zero_values_are_untouched():
    result = apply_non_negative_gate(_frame(saleq=100.0, cogsq=0.0))
    assert result.frame["saleq"].iloc[0] == 100.0
    assert result.frame["cogsq"].iloc[0] == 0.0
    assert result.nulled_count == 0
    assert result.violations.empty


def test_legitimately_negative_fields_are_not_gated():
    """A loss, a tax benefit and a net cash outflow are all real business
    facts; gating them would destroy genuine data."""
    for field in ("niq", "oiadpq", "xintq", "txtq", "oancfq", "capxq", "prstkcy"):
        assert field not in NON_NEGATIVE_FIELDS
    result = apply_non_negative_gate(_frame(niq=-500.0, oiadpq=-20.0))
    assert result.frame["niq"].iloc[0] == -500.0
    assert result.nulled_count == 0


def test_nulls_pass_through_unchanged():
    result = apply_non_negative_gate(_frame(saleq=None))
    assert pd.isna(result.frame["saleq"].iloc[0])
    assert result.nulled_count == 0


def test_gate_does_not_mutate_the_input_frame():
    original = _frame(saleq=-1.0)
    apply_non_negative_gate(original)
    assert original["saleq"].iloc[0] == -1.0


def test_missing_columns_are_skipped():
    result = apply_non_negative_gate(pd.DataFrame({"ticker": ["A"], "year": [2023], "quarter": [4]}))
    assert result.nulled_count == 0
