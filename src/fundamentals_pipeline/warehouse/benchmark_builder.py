"""Build `benchmark_daily` from the SimFin share-price file.

Callable core: a plain function returning a structured result, dispatched from
the CLI. The vendor connector is injectable so this is testable without a
6-million-row download.

The benchmark is SPY standing in for `^SPX`; see
`contracts/benchmark_schema.py` for why, and for what that substitution does
and does not claim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..connectors.simfin_price_loader import SimfinPriceConnector
from ..contracts.benchmark_schema import (
    BENCHMARK_DAILY_COLUMNS,
    BENCHMARK_PIPELINE_VERSION,
    BENCHMARK_TICKER,
    create_benchmark_daily_ddl,
)
from ..contracts.prices_schema import PRICE_SOURCE_SIMFIN
from ..core.logging import get_logger
from .connection import open_warehouse

LOG = get_logger(__name__)

BENCHMARK_TABLE = "benchmark_daily"

# Vendor column -> canonical column, declared rather than positional so a
# vendor rename surfaces as an explicit error rather than a null column.
VENDOR_COLUMN_MAP: dict[str, str] = {
    "Ticker": "ticker",
    "Date": "date",
    "Close": "close",
    "Adj. Close": "adj_close",
    "Volume": "volume",
}


def build_benchmark(
    *,
    warehouse_path: str | Path,
    connector: SimfinPriceConnector | None = None,
    price_frame: pd.DataFrame | None = None,
    ticker: str = BENCHMARK_TICKER,
    pipeline_version: str = BENCHMARK_PIPELINE_VERSION,
) -> dict[str, object]:
    """Extract the benchmark series and (re)build `benchmark_daily`."""
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    frame = (
        price_frame
        if price_frame is not None
        else (connector or SimfinPriceConnector()).load()
    )
    missing = [c for c in VENDOR_COLUMN_MAP if c not in frame.columns]
    if missing:
        raise RuntimeError(
            f"Share-price file is missing expected column(s): {missing}. "
            "The vendor layout changed; update VENDOR_COLUMN_MAP."
        )

    rows = frame.loc[frame["Ticker"] == ticker, list(VENDOR_COLUMN_MAP)].rename(
        columns=VENDOR_COLUMN_MAP
    )
    if rows.empty:
        raise RuntimeError(
            f"No rows for benchmark {ticker!r} in the share-price file. "
            "Refusing to publish an empty benchmark: every comparison would "
            "silently have nothing to compare against."
        )

    rows = rows.assign(
        date=pd.to_datetime(rows["date"], errors="coerce").dt.date,
        close=pd.to_numeric(rows["close"], errors="coerce"),
        adj_close=pd.to_numeric(rows["adj_close"], errors="coerce"),
        volume=pd.to_numeric(rows["volume"], errors="coerce"),
        source=PRICE_SOURCE_SIMFIN,
        computed_at=datetime.now(UTC).replace(tzinfo=None),
        pipeline_version=pipeline_version,
    )
    rows = rows.dropna(subset=["date"]).sort_values("date")
    rows = rows[list(BENCHMARK_DAILY_COLUMNS)]

    with open_warehouse(path, read_only=False) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {BENCHMARK_TABLE}")
        conn.execute(create_benchmark_daily_ddl())
        conn.register("benchmark_frame", rows)
        conn.execute(f"INSERT INTO {BENCHMARK_TABLE} SELECT * FROM benchmark_frame")
        conn.unregister("benchmark_frame")

    first, last = rows["date"].iloc[0], rows["date"].iloc[-1]
    LOG.info(
        "Benchmark %s built: %d rows, %s to %s", ticker, len(rows), first, last
    )
    return {
        "benchmark_ticker": ticker,
        "benchmark_rows": len(rows),
        "first_date": str(first),
        "last_date": str(last),
        "null_closes": int(rows["close"].isna().sum()),
    }
