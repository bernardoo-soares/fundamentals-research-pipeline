"""Tests for the equal-weight buy-and-hold comparison.

Pure module, so these are deterministic and need no warehouse.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from fundamentals_pipeline.portfolio.comparison import (
    INDEX_BASE,
    MAX_START_LOOKBACK_DAYS,
    PORTFOLIO_SERIES,
    compare,
)

START = date(2022, 1, 3)
END = date(2022, 1, 7)
DAYS = [START + timedelta(days=n) for n in range(5)]
BENCH_LABEL = "SPY (S&P 500 ETF)"


def _prices(series: dict[str, list[float | None]], days=None) -> pd.DataFrame:
    days = days or DAYS
    rows = []
    for ticker, closes in series.items():
        for day, close in zip(days, closes, strict=False):
            rows.append({"ticker": ticker, "date": day, "close": close})
    return pd.DataFrame(rows)


def _benchmark(closes: list[float], days=None) -> pd.DataFrame:
    days = days or DAYS
    return pd.DataFrame(
        {"date": days[: len(closes)], "close": closes}
    )


def _run(prices, benchmark, start=START, end=END):
    return compare(
        prices=prices,
        benchmark=benchmark,
        start=start,
        end=end,
        benchmark_label=BENCH_LABEL,
    )


def test_a_single_holding_tracks_its_own_price_relative():
    result = _run(
        _prices({"AAA": [10.0, 11.0, 12.0, 13.0, 20.0]}),
        _benchmark([100.0] * 5),
    )
    assert result.portfolio_return == pytest.approx(1.0)  # 10 -> 20
    assert result.benchmark_return == pytest.approx(0.0)


def test_equal_weight_is_not_decided_by_share_price():
    """A $1000 stock and a $1 stock must contribute equally."""
    result = _run(
        _prices(
            {
                "RICH": [1000.0, 1000.0, 1000.0, 1000.0, 1100.0],  # +10%
                "CHEAP": [1.0, 1.0, 1.0, 1.0, 1.3],  # +30%
            }
        ),
        _benchmark([100.0] * 5),
    )
    assert result.portfolio_return == pytest.approx(0.20)  # mean of 10% and 30%


def test_weights_drift_with_performance_and_start_equal():
    result = _run(
        _prices({"UP": [10.0] * 4 + [30.0], "FLAT": [10.0] * 5}),
        _benchmark([100.0] * 5),
    )
    by_ticker = {h.ticker: h for h in result.holdings}
    assert by_ticker["UP"].start_weight == pytest.approx(0.5)
    assert by_ticker["FLAT"].start_weight == pytest.approx(0.5)
    assert by_ticker["UP"].end_weight == pytest.approx(0.75)
    assert by_ticker["FLAT"].end_weight == pytest.approx(0.25)


def test_series_is_indexed_to_100_at_the_window_start():
    result = _run(
        _prices({"AAA": [50.0, 60.0, 70.0, 80.0, 90.0]}),
        _benchmark([200.0, 210.0, 220.0, 230.0, 240.0]),
    )
    first = result.series.sort_values("date").groupby("series_name").first()
    assert first.loc[PORTFOLIO_SERIES, "index_value"] == pytest.approx(INDEX_BASE)
    assert first.loc[BENCH_LABEL, "index_value"] == pytest.approx(INDEX_BASE)


# --- The insufficient-history policy (platform spec 8.3) --------------------


def test_a_ticker_listed_after_the_window_start_is_excluded_and_named():
    """Never begun late: that would report a partial holding as a full one."""
    late = _prices({"LATE": [None, None, None, 10.0, 12.0]})
    late = late.dropna(subset=["close"])
    result = _run(
        pd.concat([_prices({"AAA": [10.0] * 5}), late], ignore_index=True),
        _benchmark([100.0] * 5),
    )
    assert [t for t, _ in result.excluded] == ["LATE"]
    assert "listed later" in dict(result.excluded)["LATE"]
    assert {h.ticker for h in result.holdings} == {"AAA"}


def test_an_exclusion_does_not_silently_shrink_the_basket_return():
    """The survivors' return must not be reported as the basket's silently."""
    late = _prices({"LATE": [None, None, None, 10.0, 100.0]}).dropna(
        subset=["close"]
    )
    result = _run(
        pd.concat([_prices({"AAA": [10.0] * 5}), late], ignore_index=True),
        _benchmark([100.0] * 5),
    )
    # LATE's +900% is absent from the return AND its exclusion is reported.
    assert result.portfolio_return == pytest.approx(0.0)
    assert result.excluded


def test_a_price_within_the_lookback_still_opens_the_position():
    """Weekends and holidays must not drop a holding."""
    days = [START - timedelta(days=MAX_START_LOOKBACK_DAYS), *DAYS[1:]]
    result = _run(_prices({"AAA": [10.0] * 5}, days=days), _benchmark([100.0] * 5))
    assert {h.ticker for h in result.holdings} == {"AAA"}


def test_a_price_older_than_the_lookback_does_not():
    days = [START - timedelta(days=MAX_START_LOOKBACK_DAYS + 1), *DAYS[1:]]
    prices = _prices({"AAA": [10.0, None, None, None, None]}, days=days).dropna(
        subset=["close"]
    )
    result = _run(prices, _benchmark([100.0] * 5))
    assert result.is_empty


def test_a_non_positive_start_price_is_excluded_not_infinite():
    result = _run(
        _prices({"ZERO": [0.0, 1.0, 2.0, 3.0, 4.0], "AAA": [10.0] * 5}),
        _benchmark([100.0] * 5),
    )
    assert "ZERO" in dict(result.excluded)


# --- Empty and degenerate cases --------------------------------------------


def test_an_empty_selection_is_empty_not_a_flat_line_at_100():
    """A flat 100 would read as 'no movement' instead of 'nothing selected'."""
    result = _run(pd.DataFrame(columns=["ticker", "date", "close"]),
                  _benchmark([100.0] * 5))
    assert result.is_empty
    assert result.series.empty
    assert result.portfolio_return is None


def test_a_missing_benchmark_yields_an_empty_comparison():
    result = _run(_prices({"AAA": [10.0] * 5}),
                  pd.DataFrame(columns=["date", "close"]))
    assert result.is_empty


def test_dates_from_duckdb_and_from_python_both_work():
    """DuckDB returns datetime64; a hand-built frame supplies date."""
    frame = _prices({"AAA": [10.0, 11.0, 12.0, 13.0, 14.0]})
    frame["date"] = pd.to_datetime(frame["date"])
    bench = _benchmark([100.0] * 5)
    bench["date"] = pd.to_datetime(bench["date"])
    result = _run(frame, bench)
    assert result.portfolio_return == pytest.approx(0.4)


def test_a_holding_that_stops_trading_stops_contributing():
    """Carrying a dead price forward would invent a return it did not earn."""
    stops = _prices({"STOP": [10.0, 10.0, None, None, None]}).dropna(
        subset=["close"]
    )
    result = _run(
        pd.concat([_prices({"AAA": [10.0, 10.0, 10.0, 10.0, 20.0]}), stops],
                  ignore_index=True),
        _benchmark([100.0] * 5),
    )
    # On the final day only AAA has a price, so the index is AAA's alone.
    final = result.series[
        (result.series["series_name"] == PORTFOLIO_SERIES)
    ].sort_values("date").iloc[-1]
    assert final["index_value"] == pytest.approx(200.0)


def test_the_window_is_enforced_here_not_by_the_caller():
    """Passing a wider frame must not widen the window."""
    wide_days = [START - timedelta(days=30), *DAYS]
    prices = _prices({"AAA": [1.0, 10.0, 11.0, 12.0, 13.0, 14.0]}, days=wide_days)
    bench = _benchmark([50.0, 100.0, 100.0, 100.0, 100.0, 100.0], days=wide_days)
    result = _run(prices, bench)
    # The 30-days-early price is outside the look-back and must not become the
    # opening price; the window opens at 10.0, not 1.0.
    assert result.holdings[0].start_close == pytest.approx(10.0)
