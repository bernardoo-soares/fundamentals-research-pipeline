"""Build `market_history`: long-run closes for the index and the universe.

Callable core dispatched from the CLI. The client is injectable so this is
testable without a network.

Every symbol that could not be fetched is returned in the result and logged --
never silently absent. A comparison missing a company it was asked to include
must say which, or the reader takes the survivors' return for the basket's.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ..connectors.yahoo_price_client import (
    SymbolNotFound,
    YahooPriceClient,
    YahooUnavailable,
)
from ..contracts.yahoo_market_schema import (
    BENCHMARK_ROLE,
    BENCHMARK_SYMBOL,
    CONSTITUENT_ROLE,
    HISTORY_START,
    MARKET_HISTORY_COLUMNS,
    UNRESOLVED_SYMBOLS,
    YAHOO_PIPELINE_VERSION,
    YAHOO_SOURCE,
    create_market_history_ddl,
    to_yahoo_symbol,
)
from ..core.logging import get_logger
from .connection import open_warehouse

LOG = get_logger(__name__)

MARKET_HISTORY_TABLE = "market_history"


def _rows_for(
    client: YahooPriceClient,
    *,
    ticker: str,
    symbol: str,
    role: str,
    start: date,
    end: date,
    refresh: bool,
) -> pd.DataFrame:
    frame = client.load(symbol, start=start, end=end, refresh=refresh)
    if frame.empty:
        return frame
    return frame.assign(ticker=ticker, yahoo_symbol=symbol, role=role)


def build_market_history(
    *,
    warehouse_path: str | Path,
    client: YahooPriceClient | None = None,
    cache_dir: str | Path | None = None,
    tickers: tuple[str, ...] | None = None,
    start: date = HISTORY_START,
    end: date | None = None,
    refresh: bool = False,
    pipeline_version: str = YAHOO_PIPELINE_VERSION,
) -> dict[str, object]:
    """Fetch the benchmark and every scored ticker into `market_history`.

    `tickers` defaults to every ticker in `scores`, so the comparison covers
    exactly the companies the console can rank.
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    if client is None:
        if cache_dir is None:
            raise ValueError("Provide either a client or a cache_dir.")
        client = YahooPriceClient(cache_dir=cache_dir)

    end = end or datetime.now(UTC).date()

    if tickers is None:
        with open_warehouse(path, read_only=True) as conn:
            tickers = tuple(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT ticker FROM scores ORDER BY ticker"
                ).fetchall()
            )

    frames: list[pd.DataFrame] = []
    unresolved: list[tuple[str, str]] = []
    fetched = 0
    from_cache = 0

    # The benchmark first: without it the page has nothing to compare against,
    # so failing here should fail loudly rather than produce a half-built table.
    benchmark = _rows_for(
        client,
        ticker=BENCHMARK_SYMBOL,
        symbol=BENCHMARK_SYMBOL,
        role=BENCHMARK_ROLE,
        start=start,
        end=end,
        refresh=refresh,
    )
    if benchmark.empty:
        raise RuntimeError(
            f"No history for the benchmark {BENCHMARK_SYMBOL}. Refusing to "
            "publish: every comparison would silently have nothing to compare "
            "against."
        )
    frames.append(benchmark)

    for ticker in tickers:
        symbol = to_yahoo_symbol(ticker)
        if symbol is None:
            unresolved.append((ticker, UNRESOLVED_SYMBOLS[ticker]))
            continue
        # Cache-first, so a run interrupted by a rate limit resumes where
        # it stopped instead of starting over.
        cached_before = client.cache_path(symbol).exists() and not refresh
        try:
            frame = _rows_for(
                client,
                ticker=ticker,
                symbol=symbol,
                role=CONSTITUENT_ROLE,
                start=start,
                end=end,
                refresh=refresh,
            )
        except SymbolNotFound:
            unresolved.append((ticker, f"Yahoo has no series for {symbol!r}"))
            continue
        except YahooUnavailable as error:
            # A transport failure is NOT the same as a missing symbol, and
            # must not be recorded as one: the company exists and this run
            # simply could not reach it.
            unresolved.append((ticker, f"not fetched this run: {error}"))
            LOG.warning("Could not fetch %s (%s): %s", ticker, symbol, error)
            continue
        if frame.empty:
            unresolved.append((ticker, f"empty series for {symbol!r}"))
            continue
        if cached_before:
            from_cache += 1
        else:
            fetched += 1
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True).assign(
        source=YAHOO_SOURCE,
        computed_at=datetime.now(UTC).replace(tzinfo=None),
        pipeline_version=pipeline_version,
    )[list(MARKET_HISTORY_COLUMNS)]

    with open_warehouse(path, read_only=False) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {MARKET_HISTORY_TABLE}")
        conn.execute(create_market_history_ddl())
        conn.register("market_frame", combined)
        conn.execute(
            f"INSERT INTO {MARKET_HISTORY_TABLE} SELECT * FROM market_frame"
        )
        conn.unregister("market_frame")

    covered = combined.loc[combined["role"] == CONSTITUENT_ROLE, "ticker"].nunique()
    if unresolved:
        LOG.info(
            "%d ticker(s) have no market history: %s",
            len(unresolved),
            ", ".join(t for t, _ in unresolved),
        )
    return {
        "market_history_rows": len(combined),
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "benchmark_rows": len(benchmark),
        "tickers_requested": len(tickers),
        "tickers_covered": covered,
        "tickers_unresolved": len(unresolved),
        "fetched_this_run": fetched,
        "served_from_cache": from_cache,
        "unresolved": [t for t, _ in unresolved],
        "first_date": str(combined["date"].min()),
        "last_date": str(combined["date"].max()),
    }
