"""Contract for long-run market history from Yahoo Finance.

Compute-free.

WHY THIS SOURCE EXISTS ALONGSIDE SIMFIN
---------------------------------------
SimFin's price file gave the valuation layer what it needs -- a close and a
contemporaneous share count -- but it made two things impossible that the
comparison page actually wants:

1. **A real index.** SimFin carries 5,891 tradeable symbols and no index, so
   the benchmark had to be SPY, an ETF standing in for `^SPX`, differing from
   the index by expense ratio and tracking error. Yahoo carries `^GSPC`
   itself.
2. **Long windows.** SimFin runs 2020-08-31 to 2025-08-01 -- 4.92 years -- so
   5- and 10-year comparisons could not be offered at all. Measured
   2026-07-29, Yahoo returns 14,263 daily points for `^GSPC` beginning
   1970-01-02.

So this source is added for the comparison layer and does NOT replace SimFin
for valuation: `valuation_history` needs the share count that sits beside
SimFin's close, and mixing two vendors' closes into one market-cap figure
would be exactly the cross-source blending this project forbids. The two live
in different tables with different source tags.

MEASURED SEMANTICS (2026-07-29) -- verified before any transform was written
---------------------------------------------------------------------------
- `close` is **split-adjusted but NOT dividend-adjusted**. NVDA runs smoothly
  through its 2024-06-10 ten-for-one split (115.00, 116.44, 122.44, ...) with
  no 10x step, while KO's `adjclose / close` is 0.930113 -- the dividend
  adjustment Yahoo applies only to `adjclose`.
- That makes `close` exactly the right basis here: price return, dividends
  excluded, on both the selection and the benchmark, symmetric by
  construction. `adjclose` is deliberately not used.
"""

from __future__ import annotations

from datetime import date

YAHOO_PIPELINE_VERSION = "yahoo-market-1.0"
YAHOO_SOURCE = "yahoo_finance_chart_v8"

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
CHART_INTERVAL = "1d"

# The real S&P 500 index, not an ETF tracking it.
BENCHMARK_SYMBOL = "^GSPC"
BENCHMARK_LABEL = "S&P 500 (^GSPC)"

# How far back to fetch. Yahoo serves `^GSPC` from 1970, but 25 years is more
# than the deepest window offered and keeps the on-disk cache proportionate.
# Declared rather than inlined so extending it is a one-line change.
HISTORY_START = date(2000, 1, 1)

# Politeness. This is a public endpoint and no access control is being
# circumvented, but it is someone else's service.
#
# The rate is deliberately low. Measured 2026-07-29: Yahoo's edge returns
# "Edge: Too Many Requests" on a per-IP rolling window, and once tripped it
# stays tripped for minutes regardless of how slowly the next request comes.
# A burst is therefore far more expensive than a slow crawl, and the whole
# fetch is cached and resumable so a trip costs progress, not the run.
DEFAULT_REQUESTS_PER_SECOND = 1.0
DEFAULT_MAX_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 30

# Yahoo rejects an unset or scripted-looking agent on some paths.
USER_AGENT = "Mozilla/5.0 (compatible; fundamentals-research/0.2)"

# --- Symbol mapping ---------------------------------------------------------
# Measured across all 494 scored tickers on 2026-07-29: 491 resolve unchanged,
# 1 needs the separator swapped, 2 do not resolve at all.

# Class-share separator. This warehouse writes BRK.B; Yahoo writes BRK-B.
# A formatting difference in one symbol alphabet, NOT an alias: it never maps
# one company's symbol onto another's.
WAREHOUSE_CLASS_SEPARATOR = "."
YAHOO_CLASS_SEPARATOR = "-"

# Corporate renames, each carrying its evidence.
#
# THIS IS NOT THE SHARE-CLASS ALIASING THAT `prices_schema.py` FORBIDS. That
# rule exists because BRK.B -> BRK-A would price Class B share counts at Class
# A's ~$700k/share, and GOOGL -> GOOG are distinct securities. A rename is the
# same company, same security, same listing, under a new symbol -- and it is
# only recorded here once that has been checked, never inferred from a
# near-match.
VERIFIED_RENAMES: dict[str, tuple[str, str]] = {
    "BK": (
        "BNY",
        "Verified 2026-07-29 via Yahoo's search endpoint: BNY resolves to "
        "'The Bank of New York Mellon Corporation', EQUITY, exchange NYQ -- "
        "the same company and the same primary listing. BK itself returns "
        "404 'symbol may be delisted'.",
    ),
}

# Symbols with no Yahoo series and no verified successor. Named so their
# absence from a comparison is a stated fact rather than a silent gap.
UNRESOLVED_SYMBOLS: dict[str, str] = {
    "HOLX": (
        "Yahoo returns 404 for HOLX and its search endpoint returns no match "
        "for 'Hologic', so there is no successor symbol to verify. Excluded "
        "rather than guessed."
    ),
}


class SymbolAliasRejected(ValueError):
    """A proposed alias could not be accepted."""


def to_yahoo_symbol(ticker: str) -> str | None:
    """Map a warehouse ticker to its Yahoo symbol, or None if unresolved.

    Order matters: a verified rename wins over the separator transform, since
    a renamed symbol may also contain a class separator.
    """
    symbol = ticker.strip().upper()
    if symbol in UNRESOLVED_SYMBOLS:
        return None
    if symbol in VERIFIED_RENAMES:
        return VERIFIED_RENAMES[symbol][0]
    return symbol.replace(WAREHOUSE_CLASS_SEPARATOR, YAHOO_CLASS_SEPARATOR)


def validate_renames(renames: dict[str, tuple[str, str]] = None) -> None:
    """Reject a rename that looks like a share-class alias, or lacks evidence.

    Guards the one way this table could quietly become dangerous: someone
    adding `BRK.B -> BRK-A` because it "resolves". A rename must change the
    root symbol, not just the class suffix, and must carry a justification.
    """
    entries = VERIFIED_RENAMES if renames is None else renames
    for source, value in entries.items():
        target, evidence = value
        if not evidence.strip():
            raise SymbolAliasRejected(
                f"{source} -> {target}: a rename must record how it was "
                "verified. An unevidenced alias is a guess."
            )
        source_root = source.split(WAREHOUSE_CLASS_SEPARATOR)[0]
        target_root = target.split(YAHOO_CLASS_SEPARATOR)[0]
        if source_root == target_root and source != target:
            raise SymbolAliasRejected(
                f"{source} -> {target}: this changes only the share class, "
                "which is a different security, not a rename. See "
                "prices_schema.py's NO TICKER ALIASING note."
            )


validate_renames()


# --- Storage ----------------------------------------------------------------
BENCHMARK_ROLE = "benchmark"
CONSTITUENT_ROLE = "constituent"
MARKET_ROLES: frozenset[str] = frozenset({BENCHMARK_ROLE, CONSTITUENT_ROLE})

MARKET_HISTORY_COLUMNS: tuple[str, ...] = (
    "ticker",
    "yahoo_symbol",
    "role",
    "date",
    "close",
    "source",
    "computed_at",
    "pipeline_version",
)


def create_market_history_ddl() -> str:
    """DDL for `market_history`.

    One table for both the benchmark and the constituents, because here they
    are one concept: a price series to index to 100 and compare. `role`
    disambiguates them explicitly, so nothing can mistake the index for a
    company to be ranked -- which is the risk that kept them apart when the
    only distinguishing feature would have been the ticker's spelling.

    `ticker` is the warehouse's spelling and the join key; `yahoo_symbol` is
    what was actually requested, kept so a mapping can be audited without
    re-deriving it.
    """
    return (
        "CREATE TABLE market_history (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  yahoo_symbol VARCHAR NOT NULL,\n"
        "  role VARCHAR NOT NULL,\n"
        "  date DATE NOT NULL,\n"
        "  close DOUBLE,\n"
        "  source VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, date)\n"
        ")"
    )


# The caveat the platform spec requires printed on the chart itself (8.3).
# A constant rather than prose in a view, so it cannot be edited away or
# drift between surfaces.
LOOKBACK_CAVEAT = (
    "Descriptive look-back of today's selection. The selection uses "
    "current fundamentals (look-ahead) and current index membership "
    "(survivorship). This is not evidence of strategy performance."
)

# Windows the console offers once long history is loaded. Measured coverage
# decides which are actually selectable at runtime; this is the menu.
CANDIDATE_WINDOW_YEARS: tuple[int, ...] = (1, 2, 3, 5, 10, 20)
