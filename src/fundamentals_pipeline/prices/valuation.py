"""Pure valuation arithmetic (platform spec section 6.2).

Frame in -> values out. No I/O, no clock, no randomness. `prices/builder.py` is
the I/O edge.

WHY SHARES COME FROM THE PRICE FILE, NOT `cshfdq`
-------------------------------------------------
Spec 6.2 writes `market_cap = close_latest x cshfdq_latest x 1e6`. This module
uses the price file's own daily `Shares Outstanding` instead, because it is
contemporaneous with the close being multiplied by it. `cshoq` is a quarter-end
figure: measured 2026-07-28 against the 2025-08-01 price date it agrees with
SimFin's daily share count for only 45.2% of tickers within 1%, median relative
difference 1.13% -- ordinary buyback drift between quarter end and the price
date, not a defect in either. Pairing today's price with today's share count is
the correct arithmetic; pairing it with a share count up to a quarter stale is
not.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts.prices_schema import ValuationReasonCode

# `niq` is stated in millions across both providers, while a price file share
# count is in actual shares -- so a market cap is in units and total earnings
# must be scaled before the two are divided.
MILLIONS = 1_000_000.0


@dataclass(frozen=True)
class ValuationInputs:
    """Everything needed to value one ticker at one price date.

    `net_income_ttm` (millions), NOT `eps_ttm`, drives the earnings ratios.
    Measured 2026-07-28: SimFin's prices are split-adjusted while `epspxq` is
    as-reported, so `close / eps_ttm` silently mixes two share bases. BKNG
    FY2024 carries a close of 198.74 against a real ~4,900 with a
    correspondingly inflated share count -- market cap comes out right because
    the adjustment cancels, but the per-share P/E read 1.1 against a true ~28.
    Deriving from totals is invariant to split adjustment by construction.
    """

    close: float | None
    shares_outstanding: float | None
    net_income_ttm: float | None


@dataclass(frozen=True)
class Valuation:
    """The three price-dependent figures, or the reason they are absent.

    `reason_code` explains a missing `market_cap` -- the headline quantity. A
    present market cap alongside a null `pe_ttm` is normal and expected, and is
    explained by `pe_reason_code` rather than by nulling the whole row.
    """

    market_cap: float | None
    net_income_ttm: float | None
    pe_ttm: float | None
    earnings_yield: float | None
    reason_code: str | None
    pe_reason_code: str | None


def value(inputs: ValuationInputs) -> Valuation:
    """Compute market cap, trailing P/E and earnings yield.

    Null policy, per spec 6.2 and 6.3:

    - no price, or no share count: nothing is computable, so every figure is
      null with the reason. Never a zero market cap.
    - `eps_ttm` absent: `pe_ttm` and `earnings_yield` are null with
      `eps_unavailable`; market cap is unaffected and still published.
    - `eps_ttm <= 0`: `pe_ttm` is null with `non_positive_eps`. A negative P/E
      would sort as "cheap" in a screen, which is the exact misreading the book
      warns against. `earnings_yield` IS still published -- a negative earnings
      yield is meaningful and correctly signed, and nulling it would discard a
      real fact.
    """
    if inputs.close is None:
        return Valuation(
            None, inputs.net_income_ttm, None, None,
            ValuationReasonCode.PRICE_UNAVAILABLE,
            ValuationReasonCode.PRICE_UNAVAILABLE,
        )
    if inputs.shares_outstanding is None:
        return Valuation(
            None, inputs.net_income_ttm, None, None,
            ValuationReasonCode.SHARES_UNAVAILABLE,
            ValuationReasonCode.SHARES_UNAVAILABLE,
        )

    market_cap = inputs.close * inputs.shares_outstanding

    if inputs.net_income_ttm is None:
        return Valuation(
            market_cap, None, None, None, None,
            ValuationReasonCode.EPS_UNAVAILABLE,
        )

    earnings = inputs.net_income_ttm * MILLIONS
    if market_cap <= 0:
        return Valuation(
            None, inputs.net_income_ttm, None, None,
            ValuationReasonCode.PRICE_UNAVAILABLE,
            ValuationReasonCode.PRICE_UNAVAILABLE,
        )

    earnings_yield = earnings / market_cap
    if earnings <= 0:
        return Valuation(
            market_cap,
            inputs.net_income_ttm,
            None,
            earnings_yield,
            None,
            ValuationReasonCode.NON_POSITIVE_EPS,
        )

    return Valuation(
        market_cap,
        inputs.net_income_ttm,
        market_cap / earnings,
        earnings_yield,
        None,
        None,
    )
