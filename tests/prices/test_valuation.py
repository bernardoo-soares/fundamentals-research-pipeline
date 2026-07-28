"""Pure valuation rules. Mechanics here; the corpus golden is in test_builder."""

from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.prices_schema import ValuationReasonCode
from fundamentals_pipeline.prices.valuation import ValuationInputs, value


def test_market_cap_is_price_times_shares() -> None:
    # 5.0 million of earnings against a 100 million market cap -> P/E 20.
    result = value(ValuationInputs(close=100.0, shares_outstanding=1_000_000.0, net_income_ttm=5.0))
    assert result.market_cap == pytest.approx(100_000_000.0)
    assert result.pe_ttm == pytest.approx(20.0)
    assert result.earnings_yield == pytest.approx(0.05)
    assert result.reason_code is None


def test_no_price_yields_nulls_and_a_reason_never_a_zero() -> None:
    """A zero market cap would sort as the smallest company, not the unknown one."""
    result = value(ValuationInputs(close=None, shares_outstanding=1e6, net_income_ttm=5.0))
    assert result.market_cap is None
    assert result.reason_code == ValuationReasonCode.PRICE_UNAVAILABLE


def test_no_shares_yields_nulls_and_a_reason() -> None:
    result = value(ValuationInputs(close=100.0, shares_outstanding=None, net_income_ttm=5.0))
    assert result.market_cap is None
    assert result.reason_code == ValuationReasonCode.SHARES_UNAVAILABLE


def test_absent_eps_still_publishes_market_cap() -> None:
    """A missing earnings figure says nothing about the market's valuation."""
    result = value(ValuationInputs(close=100.0, shares_outstanding=1e6, net_income_ttm=None))
    assert result.market_cap == pytest.approx(1e8)
    assert result.pe_ttm is None
    assert result.earnings_yield is None
    assert result.reason_code is None
    assert result.pe_reason_code == ValuationReasonCode.EPS_UNAVAILABLE


def test_negative_eps_nulls_pe_but_keeps_earnings_yield() -> None:
    """A negative P/E would rank as "cheap"; a negative yield is just true.

    This asymmetry is deliberate. Sorting a screen by P/E ascending would put
    loss-making companies at the top if a negative P/E were published, which is
    the exact misreading the book warns against. The earnings yield carries the
    same information correctly signed, so it is kept.
    """
    result = value(ValuationInputs(close=50.0, shares_outstanding=2e6, net_income_ttm=-2.0))
    assert result.market_cap == pytest.approx(1e8)
    assert result.pe_ttm is None
    # -2.0 million of earnings against a 100 million market cap.
    assert result.earnings_yield == pytest.approx(-0.02)
    assert result.reason_code is None
    assert result.pe_reason_code == ValuationReasonCode.NON_POSITIVE_EPS


def test_zero_eps_is_treated_as_non_positive() -> None:
    """Zero EPS would make P/E infinite, which must never reach a column."""
    result = value(ValuationInputs(close=50.0, shares_outstanding=2e6, net_income_ttm=0.0))
    assert result.pe_ttm is None
    assert result.pe_reason_code == ValuationReasonCode.NON_POSITIVE_EPS
    assert result.earnings_yield == pytest.approx(0.0)


def test_golden_apple_market_cap_2025_08_01() -> None:
    """Real corpus values, hand-checked.

    SimFin 2025-08-01: AAPL close 202.38, shares outstanding 14,840,390,000.
    202.38 x 14,840,390,000 = 3,003,439,132,200 -- about $3.00 trillion, which
    matches Apple's market capitalisation on that date.
    """
    result = value(
        ValuationInputs(close=202.38, shares_outstanding=14_840_390_000.0, net_income_ttm=None)
    )
    assert result.market_cap == pytest.approx(202.38 * 14_840_390_000.0)
    assert result.market_cap / 1e12 == pytest.approx(3.0034, abs=1e-4)


def test_pe_is_invariant_to_split_adjustment() -> None:
    """The defect this arithmetic exists to prevent.

    SimFin's prices are split-adjusted while `epspxq` is as-reported, so
    `close / eps_ttm` mixes two share bases. BKNG FY2024 carries a close of
    198.74 with a correspondingly inflated share count against a real ~4,900;
    the per-share P/E read 1.1 against a true ~28. Deriving from totals, the
    adjustment cancels: halving the price while doubling the share count must
    leave P/E untouched.
    """
    unadjusted = value(
        ValuationInputs(close=4000.0, shares_outstanding=33_000_000.0, net_income_ttm=5_800.0)
    )
    adjusted = value(
        ValuationInputs(close=2000.0, shares_outstanding=66_000_000.0, net_income_ttm=5_800.0)
    )
    assert adjusted.market_cap == pytest.approx(unadjusted.market_cap)
    assert adjusted.pe_ttm == pytest.approx(unadjusted.pe_ttm)
    assert adjusted.earnings_yield == pytest.approx(unadjusted.earnings_yield)
    # Sanity: a large-cap P/E, not the 1.1 the per-share form produced.
    assert 20.0 < adjusted.pe_ttm < 25.0
