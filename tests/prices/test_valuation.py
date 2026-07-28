"""Pure valuation rules. Mechanics here; the corpus golden is in test_builder."""

from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.prices_schema import ValuationReasonCode
from fundamentals_pipeline.prices.valuation import ValuationInputs, value


def test_market_cap_is_price_times_shares() -> None:
    result = value(ValuationInputs(close=100.0, shares_outstanding=1_000_000.0, eps_ttm=5.0))
    assert result.market_cap == pytest.approx(100_000_000.0)
    assert result.pe_ttm == pytest.approx(20.0)
    assert result.earnings_yield == pytest.approx(0.05)
    assert result.reason_code is None


def test_no_price_yields_nulls_and_a_reason_never_a_zero() -> None:
    """A zero market cap would sort as the smallest company, not the unknown one."""
    result = value(ValuationInputs(close=None, shares_outstanding=1e6, eps_ttm=5.0))
    assert result.market_cap is None
    assert result.reason_code == ValuationReasonCode.PRICE_UNAVAILABLE


def test_no_shares_yields_nulls_and_a_reason() -> None:
    result = value(ValuationInputs(close=100.0, shares_outstanding=None, eps_ttm=5.0))
    assert result.market_cap is None
    assert result.reason_code == ValuationReasonCode.SHARES_UNAVAILABLE


def test_absent_eps_still_publishes_market_cap() -> None:
    """A missing earnings figure says nothing about the market's valuation."""
    result = value(ValuationInputs(close=100.0, shares_outstanding=1e6, eps_ttm=None))
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
    result = value(ValuationInputs(close=50.0, shares_outstanding=2e6, eps_ttm=-2.0))
    assert result.market_cap == pytest.approx(1e8)
    assert result.pe_ttm is None
    assert result.earnings_yield == pytest.approx(-0.04)
    assert result.reason_code is None
    assert result.pe_reason_code == ValuationReasonCode.NON_POSITIVE_EPS


def test_zero_eps_is_treated_as_non_positive() -> None:
    """Zero EPS would make P/E infinite, which must never reach a column."""
    result = value(ValuationInputs(close=50.0, shares_outstanding=2e6, eps_ttm=0.0))
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
        ValuationInputs(close=202.38, shares_outstanding=14_840_390_000.0, eps_ttm=None)
    )
    assert result.market_cap == pytest.approx(202.38 * 14_840_390_000.0)
    assert result.market_cap / 1e12 == pytest.approx(3.0034, abs=1e-4)
