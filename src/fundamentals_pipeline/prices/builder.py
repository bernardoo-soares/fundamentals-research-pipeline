"""Build `prices_daily` and `valuation_current` (callable core).

The only module in `prices/` that touches the warehouse or the price cache;
`prices/valuation.py` stays pure. Both rebuilds are idempotent: the table is
dropped and recreated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..contracts.prices_schema import (
    MAX_PRICE_LOOKBACK_DAYS,
    PRICE_SOURCE_SIMFIN,
    PRICES_DAILY_COLUMNS,
    PRICES_PIPELINE_VERSION,
    VALUATION_CURRENT_COLUMNS,
    VALUATION_HISTORY_COLUMNS,
    ValuationReasonCode,
    create_prices_daily_ddl,
    create_valuation_current_ddl,
    create_valuation_history_ddl,
)
from ..contracts.scorecard_schema import FISCAL_YEAR_END_QUARTER
from ..warehouse.connection import open_warehouse
from .valuation import ValuationInputs, value

_PRICES_TABLE = "prices_daily"
_VALUATION_TABLE = "valuation_current"
_VALUATION_HISTORY_TABLE = "valuation_history"
_QUARTERLY_METRICS_TABLE = "metrics_quarterly"
_EARNINGS_METRIC_ID = "net_income_ttm"
_STAGING_PREFIX = "staging_"

# SimFin's column names -> our contract's. Declared once (S1.1) so a vendor
# rename is a one-line change here rather than a hunt through the builder.
_SIMFIN_COLUMNS: dict[str, str] = {
    "Ticker": "ticker",
    "Date": "date",
    "Close": "close",
    "Adj. Close": "adj_close",
    "Volume": "volume",
    "Dividend": "dividend",
    "Shares Outstanding": "shares_outstanding",
}


def _replace_table(conn, table: str, ddl: str, columns: tuple[str, ...], frame) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(ddl)
    if frame.empty:
        return
    staging = f"{_STAGING_PREFIX}{table}"
    conn.register(staging, frame)
    try:
        column_list = ", ".join(columns)
        conn.execute(
            f"INSERT INTO {table} ({column_list}) "
            f"SELECT {column_list} FROM {staging}"
        )
    finally:
        conn.unregister(staging)


def build_prices_daily(
    *,
    warehouse_path: str | Path,
    price_frame: pd.DataFrame,
    pipeline_version: str = PRICES_PIPELINE_VERSION,
) -> dict[str, object]:
    """Load a SimFin daily share-price frame into `prices_daily`.

    Takes the frame rather than fetching it, so the transform is testable
    without network or cache (the connector is the only fetcher).

    Rows are restricted to tickers the warehouse actually holds fundamentals
    for: SimFin covers ~5,890 US tickers against our ~500-name universe, and
    storing the rest would be six million rows of data no query wants.
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    missing = sorted(set(_SIMFIN_COLUMNS) - set(price_frame.columns))
    if missing:
        raise ValueError(
            f"SimFin price frame is missing expected columns: {missing}. "
            "The vendor schema changed; update _SIMFIN_COLUMNS deliberately "
            "rather than letting the column silently become null."
        )

    computed_at = datetime.now(UTC).replace(tzinfo=None)
    frame = price_frame[list(_SIMFIN_COLUMNS)].rename(columns=_SIMFIN_COLUMNS).copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date

    with open_warehouse(path, read_only=False) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        if "fundamentals_quarterly" not in tables:
            raise FileNotFoundError(
                "fundamentals_quarterly not found; run warehouse-rebuild first."
            )
        universe = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT ticker FROM fundamentals_quarterly"
            ).fetchall()
        }
        frame = frame[frame["ticker"].isin(universe)].copy()
        frame["source"] = PRICE_SOURCE_SIMFIN
        frame["computed_at"] = computed_at
        frame["pipeline_version"] = pipeline_version
        # Deterministic order (S3.3), and the primary key rejects duplicates.
        frame = frame.sort_values(["ticker", "date"]).drop_duplicates(
            subset=["ticker", "date"], keep="last"
        )
        _replace_table(
            conn, _PRICES_TABLE, create_prices_daily_ddl(), PRICES_DAILY_COLUMNS, frame
        )

    priced = set(frame["ticker"].unique())
    return {
        "prices_daily_rows": int(len(frame)),
        "tickers_priced": len(priced),
        "universe_tickers": len(universe),
        "tickers_unpriced": len(universe - priced),
        "unpriced_sample": sorted(universe - priced)[:20],
        "first_date": str(frame["date"].min()) if not frame.empty else None,
        "last_date": str(frame["date"].max()) if not frame.empty else None,
    }


def build_valuation_current(
    *,
    warehouse_path: str | Path,
    pipeline_version: str = PRICES_PIPELINE_VERSION,
) -> dict[str, object]:
    """Value every universe ticker at the latest price date in the warehouse.

    The price date is pinned to the maximum date present in `prices_daily`, not
    to the wall clock, so the same ingested data always yields identical rows
    (S3.1/S3.4). A ticker with no row on that date is published with a null
    valuation and `price_unavailable` -- never omitted, so the UI can show the
    gap rather than a blank.
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    computed_at = datetime.now(UTC).replace(tzinfo=None)
    with open_warehouse(path, read_only=False) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        for required in (_PRICES_TABLE, _QUARTERLY_METRICS_TABLE):
            if required not in tables:
                raise FileNotFoundError(
                    f"{required} not found; run prices-build and "
                    "metrics-quarterly-build first."
                )

        price_date = conn.execute(f"SELECT MAX(date) FROM {_PRICES_TABLE}").fetchone()[0]
        if price_date is None:
            raise ValueError(f"{_PRICES_TABLE} is empty; run prices-build first.")

        universe = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT ticker FROM fundamentals_quarterly ORDER BY ticker"
            ).fetchall()
        ]
        prices = dict(
            (row[0], (row[1], row[2]))
            for row in conn.execute(
                f"SELECT ticker, close, shares_outstanding FROM {_PRICES_TABLE} "
                "WHERE date = ?",
                [price_date],
            ).fetchall()
        )
        # Latest EPS TTM per ticker, by (year, quarter). Ordering is explicit so
        # the pick never depends on row order (S3.3).
        earnings = dict(
            (row[0], row[1])
            for row in conn.execute(
                f"SELECT ticker, value FROM (SELECT ticker, value, "
                f"ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY year DESC, "
                f"quarter DESC) AS rn FROM {_QUARTERLY_METRICS_TABLE} "
                f"WHERE metric_id = '{_EARNINGS_METRIC_ID}' AND value IS NOT NULL) "
                "WHERE rn = 1"
            ).fetchall()
        )

        rows: list[dict] = []
        for ticker in universe:
            close, shares = prices.get(ticker, (None, None))
            result = value(
                ValuationInputs(
                    close=close,
                    shares_outstanding=shares,
                    net_income_ttm=earnings.get(ticker),
                )
            )
            rows.append(
                {
                    "ticker": ticker,
                    "price_date": price_date,
                    "close": close,
                    "shares_outstanding": shares,
                    "market_cap": result.market_cap,
                    "net_income_ttm": result.net_income_ttm,
                    "pe_ttm": result.pe_ttm,
                    "earnings_yield": result.earnings_yield,
                    "reason_code": result.reason_code,
                    "quality_flag": result.pe_reason_code,
                    "computed_at": computed_at,
                    "pipeline_version": pipeline_version,
                }
            )

        frame = pd.DataFrame(rows, columns=list(VALUATION_CURRENT_COLUMNS))
        _replace_table(
            conn,
            _VALUATION_TABLE,
            create_valuation_current_ddl(),
            VALUATION_CURRENT_COLUMNS,
            frame,
        )

    # str() on the keys: reason codes are StrEnum members, and a bare dict would
    # print its repr rather than the value that is actually stored.
    reason_counts = (
        {
            str(reason): int(count)
            for reason, count in frame[frame["reason_code"].notna()]
            .groupby("reason_code")
            .size()
            .to_dict()
            .items()
        }
        if not frame.empty
        else {}
    )
    return {
        "valuation_rows": int(len(frame)),
        "price_date": str(price_date),
        "market_cap_present": int(frame["market_cap"].notna().sum()),
        "pe_ttm_present": int(frame["pe_ttm"].notna().sum()),
        "earnings_yield_present": int(frame["earnings_yield"].notna().sum()),
        "reason_code_counts": reason_counts,
        "non_positive_eps": int(
            (frame["quality_flag"] == ValuationReasonCode.NON_POSITIVE_EPS).sum()
        ),
    }


def build_valuation_history(
    *,
    warehouse_path: str | Path,
    pipeline_version: str = PRICES_PIPELINE_VERSION,
) -> dict[str, object]:
    """Value every ticker at each fiscal year end its period-end date allows.

    Unlocked by Stage 1 carrying `period_end_date`: the fiscal year end cannot
    be derived from `(year, quarter)` -- measured, the fiscal quarter differs
    from the calendar quarter of the period end for 21.5% of rows -- so before
    this column existed the price could only be aligned by guessing, which
    would have been wrong for roughly one company in five and silently off by
    up to a quarter.

    The price is the last close at or before the period end, within
    `MAX_PRICE_LOOKBACK_DAYS`. Looking BACKWARD only is deliberate: a close
    from after the period end is information from the future. The realised gap
    is stored as `price_lag_days` so a stretched match is visible rather than
    implied, and a period end with no trading day inside the window is nulled
    with `price_unavailable` rather than reaching further.

    `publish_date` is carried but NOT used as the anchor. The two are a median
    28-33 days apart, and that gap is exactly the difference between "what the
    company was worth when its year closed" (this table) and "what the market
    could have known" (a tradeable signal, which spec D8 explicitly says this
    platform does not claim to produce).
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    computed_at = datetime.now(UTC).replace(tzinfo=None)
    with open_warehouse(path, read_only=False) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        for required in (_PRICES_TABLE, _QUARTERLY_METRICS_TABLE):
            if required not in tables:
                raise FileNotFoundError(
                    f"{required} not found; run prices-build and "
                    "metrics-quarterly-build first."
                )

        # One as-of join, done in SQL so the "latest close at or before the
        # period end" rule is expressed once and cannot drift between rows.
        rows = conn.execute(
            f"""
            WITH year_end AS (
              SELECT ticker, year AS fiscal_year, period_end_date, publish_date
              FROM fundamentals_quarterly
              WHERE quarter = {FISCAL_YEAR_END_QUARTER}
                AND period_end_date IS NOT NULL
            ),
            eps AS (
              SELECT ticker, year AS fiscal_year, value AS net_income_ttm
              FROM {_QUARTERLY_METRICS_TABLE}
              WHERE metric_id = '{_EARNINGS_METRIC_ID}'
                AND quarter = {FISCAL_YEAR_END_QUARTER}
            ),
            anchored AS (
              SELECT
                y.ticker, y.fiscal_year, y.period_end_date, y.publish_date,
                (SELECT p.date FROM {_PRICES_TABLE} p
                  WHERE p.ticker = y.ticker AND p.date <= y.period_end_date
                    AND p.date >= y.period_end_date - {MAX_PRICE_LOOKBACK_DAYS}
                  ORDER BY p.date DESC LIMIT 1) AS price_date
              FROM year_end y
            )
            SELECT
              a.ticker, a.fiscal_year, a.period_end_date, a.publish_date,
              a.price_date,
              date_diff('day', a.price_date, a.period_end_date) AS price_lag_days,
              p.close, p.shares_outstanding, e.net_income_ttm
            FROM anchored a
            LEFT JOIN {_PRICES_TABLE} p
              ON p.ticker = a.ticker AND p.date = a.price_date
            LEFT JOIN eps e
              ON e.ticker = a.ticker AND e.fiscal_year = a.fiscal_year
            ORDER BY a.ticker, a.fiscal_year
            """
        ).fetchall()

        built: list[dict] = []
        for (
            ticker,
            fiscal_year,
            period_end_date,
            publish_date,
            price_date,
            price_lag_days,
            close,
            shares,
            net_income_ttm,
        ) in rows:
            result = value(
                ValuationInputs(
                    close=close, shares_outstanding=shares, net_income_ttm=net_income_ttm
                )
            )
            built.append(
                {
                    "ticker": ticker,
                    "fiscal_year": fiscal_year,
                    "period_end_date": period_end_date,
                    "publish_date": publish_date,
                    "price_date": price_date,
                    "price_lag_days": price_lag_days,
                    "close": close,
                    "shares_outstanding": shares,
                    "market_cap": result.market_cap,
                    "net_income_ttm": result.net_income_ttm,
                    "pe_ttm": result.pe_ttm,
                    "earnings_yield": result.earnings_yield,
                    "reason_code": result.reason_code,
                    "quality_flag": result.pe_reason_code,
                    "computed_at": computed_at,
                    "pipeline_version": pipeline_version,
                }
            )

        frame = pd.DataFrame(built, columns=list(VALUATION_HISTORY_COLUMNS))
        _replace_table(
            conn,
            _VALUATION_HISTORY_TABLE,
            create_valuation_history_ddl(),
            VALUATION_HISTORY_COLUMNS,
            frame,
        )

    priced = frame[frame["market_cap"].notna()] if not frame.empty else frame
    return {
        "valuation_history_rows": int(len(frame)),
        "with_market_cap": int(len(priced)),
        "with_pe_ttm": int(frame["pe_ttm"].notna().sum()) if not frame.empty else 0,
        "fiscal_years": sorted(frame["fiscal_year"].unique().tolist())
        if not frame.empty
        else [],
        "median_price_lag_days": float(priced["price_lag_days"].median())
        if not priced.empty
        else None,
        "max_price_lag_days": int(priced["price_lag_days"].max())
        if not priced.empty
        else None,
    }
