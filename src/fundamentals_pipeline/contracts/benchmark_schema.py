"""Contract for the market benchmark series (platform spec section 8.3).

Compute-free.

THE BENCHMARK IS SPY, NOT ^SPX — AND THAT IS A DISCLOSURE, NOT A DETAIL
----------------------------------------------------------------------
The spec names `^SPX`, the S&P 500 price index. No index series is available:
SimFin's `us-shareprices-daily` carries 5,891 **tradeable** symbols and no
index, and the Stooq path that might have supplied one is behind a JavaScript
proof-of-work challenge that this project deliberately does not circumvent
(see `prices_schema.py`).

SPY, the ETF that tracks the index, IS in the file and is used instead. That is
a good proxy for a **price-return** comparison and a bad one for anything else:

- The S&P 500 price index excludes dividends by construction. SPY's price drops
  on each ex-dividend date. So both sides of a price-return comparison exclude
  dividends, which is exactly the symmetry the spec requires.
- SPY still differs from the index by its expense ratio (~0.09%/yr) and by
  tracking error. Over a 4-year window that is a fraction of a percent, but it
  is not zero and the console says so rather than calling SPY "the S&P 500".

Verified 2026-08-31 → 2025-08-01: 349.31 → 621.72, a +78.0% price return, with
no null closes and a largest gap of 4 days.

WHY A SEPARATE TABLE FROM `prices_daily`
----------------------------------------
Identical shape, different meaning. In `prices_daily`, `ticker` is a company in
the research universe; here it is a market proxy that is deliberately NOT a
constituent to be ranked or scored. Merging them would make one column mean two
things (AGENTS.md S4.3) and would let a benchmark leak into a company ranking.
"""

from __future__ import annotations

BENCHMARK_PIPELINE_VERSION = "benchmark-1.0"

# The symbol standing in for the index, and the role it plays. Named so the
# substitution is greppable rather than buried in a builder.
BENCHMARK_TICKER = "SPY"
BENCHMARK_LABEL = "SPY (S&P 500 ETF)"
BENCHMARK_IS_PROXY_FOR = "^SPX"

BENCHMARK_DAILY_COLUMNS: tuple[str, ...] = (
    "ticker",
    "date",
    "close",
    "adj_close",
    "volume",
    "source",
    "computed_at",
    "pipeline_version",
)


def create_benchmark_daily_ddl() -> str:
    """DDL for the `benchmark_daily` table."""
    return (
        "CREATE TABLE benchmark_daily (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  date DATE NOT NULL,\n"
        "  close DOUBLE,\n"
        "  adj_close DOUBLE,\n"
        "  volume DOUBLE,\n"
        "  source VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, date)\n"
        ")"
    )


# Look-back windows the console offers, in years.
#
# 5 and 10 are ABSENT because the data cannot support them, not because they
# were not wanted: the price history begins 2020-08-31 and ends 2025-08-01, a
# span of 4.92 years, so a 5-year window would start one day before the first
# available price. Offering a window the data cannot fill would either silently
# shorten it or silently drop every ticker.
AVAILABLE_WINDOW_YEARS: tuple[int, ...] = (1, 2, 3, 4)

# Why the longer windows are missing, stated wherever they would have appeared.
WINDOW_LIMIT_REASON = (
    "Windows longer than 4 years are not offered: the price history runs "
    "2020-08-31 to 2025-08-01 (4.92 years), a limit of the SimFin free tier."
)

# The caveat the spec requires printed on the chart itself (section 8.3). It is
# a constant rather than prose in a view so it cannot be edited away or drift
# between surfaces.
LOOKBACK_CAVEAT = (
    "Descriptive look-back of today's selection. The selection uses current "
    "fundamentals (look-ahead) and current index membership (survivorship). "
    "This is not evidence of strategy performance."
)

RETURN_BASIS_NOTE = (
    "Price return on both sides, dividends excluded on both sides — symmetric "
    "by construction. The benchmark is SPY, the ETF, standing in for ^SPX; it "
    "differs from the index by its expense ratio and tracking error."
)
