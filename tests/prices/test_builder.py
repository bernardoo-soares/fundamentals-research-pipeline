"""Tests for the price and valuation builders -- the I/O edge of `prices/`."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fundamentals_pipeline.contracts.prices_schema import (
    PRICE_SOURCE_SIMFIN,
    ValuationReasonCode,
)
from fundamentals_pipeline.prices.builder import (
    build_prices_daily,
    build_valuation_current,
)

_DATES = ["2025-07-30", "2025-07-31", "2025-08-01"]


def _price_frame(tickers=("AAPL", "KO"), extra=()):
    rows = [
        {
            "Ticker": ticker,
            "Date": date,
            "Close": 100.0 + index,
            "Adj. Close": 99.0 + index,
            "Volume": 1_000_000.0,
            "Dividend": None,
            "Shares Outstanding": 2_000_000.0,
        }
        for ticker in tickers
        for index, date in enumerate(_DATES)
    ]
    rows.extend(extra)
    return pd.DataFrame(rows)


def _seed_warehouse(path, tickers=("AAPL", "KO"), eps=None) -> None:
    conn = duckdb.connect(str(path))
    fundamentals = pd.DataFrame(
        [{"ticker": t, "year": 2024, "quarter": q} for t in tickers for q in (1, 2, 3, 4)]
    )
    conn.register("f", fundamentals)
    conn.execute("CREATE TABLE fundamentals_quarterly AS SELECT * FROM f")
    conn.unregister("f")
    metrics = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "year": year,
                "quarter": 4,
                "metric_id": "net_income_ttm",
                "value": val,
                "reason_code": None if val is not None else "missing_input",
                "quality_flag": None,
            }
            for ticker, per_year in (eps or {}).items()
            for year, val in per_year.items()
        ]
    )
    if metrics.empty:
        conn.execute(
            "CREATE TABLE metrics_quarterly (ticker VARCHAR, year INTEGER, "
            "quarter INTEGER, metric_id VARCHAR, value DOUBLE, "
            "reason_code VARCHAR, quality_flag VARCHAR)"
        )
    else:
        conn.register("m", metrics)
        conn.execute("CREATE TABLE metrics_quarterly AS SELECT * FROM m")
        conn.unregister("m")
    conn.close()


def _fetch(path, sql):
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_prices_build_writes_rows_and_stamps_the_source(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db)

    result = build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    assert result["prices_daily_rows"] == 6
    assert result["tickers_priced"] == 2
    assert result["tickers_unpriced"] == 0
    assert _fetch(db, "SELECT DISTINCT source FROM prices_daily") == [
        (PRICE_SOURCE_SIMFIN,)
    ]


def test_prices_build_restricts_to_the_warehouse_universe(tmp_path) -> None:
    """SimFin covers ~5,890 tickers; storing the ~5,400 we never query is waste."""
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, tickers=("AAPL",))

    result = build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    assert result["tickers_priced"] == 1
    assert {row[0] for row in _fetch(db, "SELECT DISTINCT ticker FROM prices_daily")} == {
        "AAPL"
    }


def test_prices_build_reports_unpriced_universe_tickers(tmp_path) -> None:
    """The 12 real unpriced tickers must be visible, not silently absent."""
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, tickers=("AAPL", "KO", "BRK.B"))

    result = build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    assert result["tickers_unpriced"] == 1
    assert "BRK.B" in result["unpriced_sample"]


def test_prices_build_rejects_a_vendor_schema_change(tmp_path) -> None:
    """A renamed vendor column must fail loudly, not become a null column."""
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db)
    frame = _price_frame().rename(columns={"Shares Outstanding": "SharesOutstanding"})

    with pytest.raises(ValueError, match="missing expected columns"):
        build_prices_daily(warehouse_path=db, price_frame=frame)


def test_prices_build_is_idempotent(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db)
    first = build_prices_daily(warehouse_path=db, price_frame=_price_frame())
    second = build_prices_daily(warehouse_path=db, price_frame=_price_frame())
    assert first == second


def test_valuation_pins_the_price_date_to_the_data_not_the_clock(tmp_path) -> None:
    """S3.1/S3.4: same input, identical rows, whenever it is run."""
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, eps={"AAPL": {2024: 5.0}, "KO": {2024: 2.0}})
    build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    result = build_valuation_current(warehouse_path=db)

    assert result["price_date"] == "2025-08-01"
    assert _fetch(db, "SELECT DISTINCT price_date FROM valuation_current") == [
        (pd.Timestamp("2025-08-01").date(),)
    ]


def test_valuation_computes_the_three_figures(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, eps={"AAPL": {2024: 5.0}})
    build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    build_valuation_current(warehouse_path=db)

    close, shares, cap, earnings, pe, ey = _fetch(
        db,
        "SELECT close, shares_outstanding, market_cap, net_income_ttm, pe_ttm, "
        "earnings_yield FROM valuation_current WHERE ticker='AAPL'",
    )[0]
    assert (close, shares) == (102.0, 2_000_000.0)
    assert cap == pytest.approx(204_000_000.0)
    # 5.0 million of earnings against a 204 million market cap.
    assert (earnings, pe) == (5.0, pytest.approx(204_000_000.0 / 5_000_000.0))
    assert ey == pytest.approx(5_000_000.0 / 204_000_000.0)


def test_valuation_uses_the_latest_earnings_not_an_arbitrary_one(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, eps={"AAPL": {2022: 1.0, 2024: 5.0, 2023: 3.0}})
    build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    build_valuation_current(warehouse_path=db)

    assert _fetch(
        db, "SELECT net_income_ttm FROM valuation_current WHERE ticker='AAPL'"
    ) == [(5.0,)]


def test_unpriced_ticker_is_published_with_a_reason_not_omitted(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, tickers=("AAPL", "BRK.B"), eps={"AAPL": {2024: 5.0}})
    build_prices_daily(warehouse_path=db, price_frame=_price_frame(tickers=("AAPL",)))

    build_valuation_current(warehouse_path=db)

    cap, reason = _fetch(
        db, "SELECT market_cap, reason_code FROM valuation_current WHERE ticker='BRK.B'"
    )[0]
    assert cap is None
    assert reason == ValuationReasonCode.PRICE_UNAVAILABLE


def test_no_nan_or_inf_reaches_a_stored_valuation_column(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, eps={"AAPL": {2024: 0.0}, "KO": {2024: -1.0}})
    build_prices_daily(warehouse_path=db, price_frame=_price_frame())

    build_valuation_current(warehouse_path=db)

    for column in ("market_cap", "pe_ttm", "earnings_yield", "net_income_ttm"):
        bad = _fetch(
            db,
            f"SELECT COUNT(*) FROM valuation_current WHERE {column} IS NOT NULL "
            f"AND (isnan({column}) OR isinf({column}))",
        )[0][0]
        assert bad == 0, column


def test_valuation_is_idempotent(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_warehouse(db, eps={"AAPL": {2024: 5.0}})
    build_prices_daily(warehouse_path=db, price_frame=_price_frame())
    first = build_valuation_current(warehouse_path=db)
    second = build_valuation_current(warehouse_path=db)
    assert first == second


def test_valuation_never_reaches_the_scoring_layer(tmp_path) -> None:
    """Spec 7.1: scorers read only metrics_* -- never prices.

    Structural, not conventional: `valuation_current` is deliberately outside
    the `metrics_*` namespace and the score builder names its two source tables
    explicitly. This asserts the guarantee rather than trusting it.
    """
    from fundamentals_pipeline.scoring import builder as score_builder

    source = (
        score_builder._TREND_TABLE,
        score_builder._QUARTERLY_TABLE,
    )
    assert "valuation_current" not in source
    assert "prices_daily" not in source
    assert all(not name.startswith("valuation") for name in source)
