"""Contract for the price and valuation layer (platform spec sections 6.2, 9).

Compute-free: table schemas, column contracts and the valuation reason-code
vocabulary. Ingestion lives in `connectors/`, computation in `prices/`.

SOURCE DECISION (2026-07-28, supersedes D6 and platform spec section 9)
----------------------------------------------------------------------
The spec chose Stooq for "free EOD CSV endpoints, no API key". Measured on
2026-07-28, every Stooq CSV endpoint (`.com` and `.pl`, with and without
browser headers) returns a JavaScript proof-of-work anti-bot challenge instead
of CSV. That premise no longer holds, and the challenge is deliberately not
circumvented.

SimFin's `us-shareprices-daily` replaces it and adds NO new dependency: SimFin
is already a configured provider with a key and a cache-first loader. It is one
bulk download rather than ~500 throttled per-ticker requests, so the spec's
throttling, retry and per-ticker failure isolation are unnecessary, and it
carries `Adj. Close` and `Dividend` -- which Stooq does not -- so the deferred
total-return work stays open rather than being foreclosed.

Cost, disclosed: history begins 2020-08-31 rather than Stooq's deeper archive,
so valuation cannot predate FY2020. D7 already fixes FY2024 as the analysis
year.

NO TICKER ALIASING
------------------
12 of 384 FY2024 tickers have no SimFin price row. The tempting fixes are
WRONG: `BRK.B` -> `BRK-A` would price Class B share counts at Class A's
~$700k/share, and `GOOGL`/`FOXA`/`NWSA` -> `GOOG`/`FOX`/`NWS` are likewise
distinct share classes. Genuine renames exist but SimFin's company file carries
no SimFinId for them, so nothing can be verified by id. Joining is by exact
ticker; the unpriced 12 yield a null valuation with `price_unavailable`.
"""

from __future__ import annotations

from enum import StrEnum

PRICES_PIPELINE_VERSION = "prices-1.0"

# The provider tag stamped on every stored price row (S1.1: never a literal in
# a builder, and the column exists so a future second source is distinguishable
# rather than silently blended).
PRICE_SOURCE_SIMFIN = "simfin_shareprices_daily"

# A daily move beyond this is flagged for review, never dropped (spec 9.3).
MAX_ABSOLUTE_DAILY_MOVE = 0.50

# A gap longer than this many calendar days between consecutive observations is
# flagged (spec 9.3). Measured baseline: AAPL's largest gap is 4 days.
MAX_TRADING_GAP_DAYS = 10


class ValuationReasonCode(StrEnum):
    """Why a valuation figure is absent.

    Separate from the metric-grain `ReasonCode`: these explain a price-dependent
    quantity that could not be formed, which is a different failure from a
    missing fundamental.
    """

    PRICE_UNAVAILABLE = "price_unavailable"
    SHARES_UNAVAILABLE = "shares_unavailable"
    EPS_UNAVAILABLE = "eps_unavailable"
    # eps_ttm <= 0, so a P/E would be negative or infinite. A negative P/E is
    # not a cheap stock; publishing one would invite exactly that misreading.
    NON_POSITIVE_EPS = "non_positive_eps"


PRICES_DAILY_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "close",
    "adj_close",
    "volume",
    "dividend",
    "shares_outstanding",
    "source",
    "computed_at",
    "pipeline_version",
)

VALUATION_CURRENT_COLUMNS: tuple[str, ...] = (
    "ticker",
    "price_date",
    "close",
    "shares_outstanding",
    "market_cap",
    "eps_ttm",
    "pe_ttm",
    "earnings_yield",
    "reason_code",
    "quality_flag",
    "computed_at",
    "pipeline_version",
)


def create_prices_daily_ddl() -> str:
    """DDL for the `prices_daily` table."""
    return (
        "CREATE TABLE prices_daily (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  date DATE NOT NULL,\n"
        "  close DOUBLE,\n"
        "  adj_close DOUBLE,\n"
        "  volume DOUBLE,\n"
        "  dividend DOUBLE,\n"
        "  shares_outstanding DOUBLE,\n"
        "  source VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, date)\n"
        ")"
    )


def create_valuation_current_ddl() -> str:
    """DDL for the `valuation_current` table.

    Deliberately NOT named `metrics_*`. A scorer reads only the `metrics_*`
    tables (spec 7.1), so keeping valuation outside that namespace makes the
    "scores never see prices" guarantee structural rather than a convention
    someone could forget.
    """
    return (
        "CREATE TABLE valuation_current (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  price_date DATE NOT NULL,\n"
        "  close DOUBLE,\n"
        "  shares_outstanding DOUBLE,\n"
        "  market_cap DOUBLE,\n"
        "  eps_ttm DOUBLE,\n"
        "  pe_ttm DOUBLE,\n"
        "  earnings_yield DOUBLE,\n"
        "  reason_code VARCHAR,\n"
        "  quality_flag VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, price_date)\n"
        ")"
    )
