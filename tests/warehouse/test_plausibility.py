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


def test_share_scale_gate_nulls_a_basic_count_that_lost_its_scale() -> None:
    """The MCD FY2024 defect, pinned.

    SimFin published `Shares (Basic)` as 718 against a diluted 722,000,000 for
    two quarters of one fiscal year, having read 722,000,000 for the other two.
    Carried through it made derived EPS 2,809,192 per share and a trailing P/E
    of 0.0, putting McDonald's at the top of a cheapest-stock screen.
    """
    from fundamentals_pipeline.warehouse.plausibility import apply_share_scale_gate

    frame = pd.DataFrame(
        [
            {"ticker": "MCD", "year": 2024, "quarter": 2,
             "cshoq": 722_000_000.0, "cshfdq": 726_000_000.0},
            {"ticker": "MCD", "year": 2024, "quarter": 4,
             "cshoq": 718.0, "cshfdq": 722_000_000.0},
        ]
    )
    result = apply_share_scale_gate(frame)

    assert result.nulled_count == 1
    assert pd.isna(result.frame.loc[1, "cshoq"])
    # The good quarter is untouched, and the diluted count survives both.
    assert result.frame.loc[0, "cshoq"] == 722_000_000.0
    assert result.frame["cshfdq"].notna().all()
    assert result.violations.loc[0, "rule"] == "share_count_scale"


def test_share_scale_gate_leaves_ordinary_dilution_alone() -> None:
    """Real dilution is a few percent; the gate must not touch it."""
    from fundamentals_pipeline.warehouse.plausibility import apply_share_scale_gate

    frame = pd.DataFrame(
        [{"ticker": "AAPL", "year": 2024, "quarter": 4,
          "cshoq": 15_171_990_000.0, "cshfdq": 15_242_860_000.0}]
    )
    result = apply_share_scale_gate(frame)

    assert result.nulled_count == 0
    assert result.frame["cshoq"].notna().all()


def test_share_scale_gate_ignores_a_missing_counterpart() -> None:
    """A coverage gap is not a scale defect and must not be nulled."""
    from fundamentals_pipeline.warehouse.plausibility import apply_share_scale_gate

    frame = pd.DataFrame(
        [{"ticker": "X", "year": 2024, "quarter": 4, "cshoq": 100.0, "cshfdq": None}]
    )
    result = apply_share_scale_gate(frame)

    assert result.nulled_count == 0
    assert result.frame.loc[0, "cshoq"] == 100.0


def test_share_scale_gate_also_nulls_the_derived_eps_it_poisoned() -> None:
    """SimFin epspxq is Net Income / Shares (Basic) -- the rejected field.

    Nulling only the share count would leave a per-share figure six orders of
    magnitude wrong in place, which is what put MCD atop a cheapest-stock
    screen at a P/E of 0.0.
    """
    from fundamentals_pipeline.warehouse.plausibility import apply_share_scale_gate

    frame = pd.DataFrame(
        [{"ticker": "MCD", "year": 2024, "quarter": 4, "cshoq": 718.0,
          "cshfdq": 722_000_000.0, "epspxq": 2_809_192.2, "source_era": "simfin"}]
    )
    result = apply_share_scale_gate(frame)

    assert pd.isna(result.frame.loc[0, "cshoq"])
    assert pd.isna(result.frame.loc[0, "epspxq"])
    assert set(result.violations["field_name"]) == {"cshoq", "epspxq"}


def test_share_scale_gate_leaves_legacy_as_reported_eps_alone() -> None:
    """Legacy epspxq is as-reported, not a function of cshoq."""
    from fundamentals_pipeline.warehouse.plausibility import apply_share_scale_gate

    frame = pd.DataFrame(
        [{"ticker": "X", "year": 2019, "quarter": 4, "cshoq": 1.0,
          "cshfdq": 1_000_000.0, "epspxq": 3.25,
          "source_era": "legacy_compustat"}]
    )
    result = apply_share_scale_gate(frame)

    assert pd.isna(result.frame.loc[0, "cshoq"])
    assert result.frame.loc[0, "epspxq"] == 3.25
