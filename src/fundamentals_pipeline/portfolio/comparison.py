"""Equal-weight buy-and-hold comparison against a market benchmark.

Pure: frames in, frames out. No I/O, no clock, no randomness (AGENTS.md S2.4).

WHY THE ARITHMETIC LIVES HERE AND NOT IN THE VIEW
-------------------------------------------------
Every other console number is SELECTed from a table, because every other number
is precomputed. A portfolio is chosen at runtime from an arbitrary subset of
tickers, so there is no table to precompute it into. That does not license
arithmetic in a Streamlit page: the computation lives in this module, pure and
tested, and the view calls it. The rule "the console computes nothing" is
narrowed by exactly this much and no further, and the narrowing is written down
here so it cannot spread.

WHAT IS AND IS NOT CLAIMED
--------------------------
This is a **descriptive look-back**, not a backtest, and the distinction is not
pedantic. The selection is made with today's fundamentals (look-ahead) from
today's index membership (survivorship). Both biases push the result in the
same flattering direction. `contracts/benchmark_schema.LOOKBACK_CAVEAT` states
this on the chart itself.

Price return on both sides, dividends excluded on both sides. Symmetric by
construction rather than by adjustment, which is why `close` is used and
`adj_close` is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

# Every holding starts at the same value, so a comparison is not decided by
# which member happens to have the highest share price.
INDEX_BASE = 100.0

# How far before the window start to accept a price, in calendar days. Markets
# close for weekends and holidays, so an exact-date requirement would drop
# roughly three windows in ten for no reason. Beyond this the position did not
# exist at the start and the ticker is excluded rather than back-dated.
MAX_START_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class Holding:
    """One member's contribution to the comparison."""

    ticker: str
    start_date: date
    start_close: float
    end_date: date
    end_close: float
    total_return: float
    start_weight: float
    end_weight: float


@dataclass(frozen=True)
class Comparison:
    """The result of comparing an equal-weight basket against the benchmark.

    `series` is long-form `(date, series_name, index_value)`, indexed to 100 at
    the window start, ready to chart without further shaping.

    `excluded` names the tickers that had no price at the window start, with
    the reason. They are listed rather than quietly dropped: a basket that
    silently loses its late arrivals reports the survivors' return as the
    basket's.
    """

    series: pd.DataFrame
    holdings: tuple[Holding, ...]
    excluded: tuple[tuple[str, str], ...]
    start_date: date | None
    end_date: date | None
    portfolio_return: float | None
    benchmark_return: float | None

    @property
    def is_empty(self) -> bool:
        return not self.holdings


PORTFOLIO_SERIES = "Selection (equal weight)"


def _to_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise a `date` column to plain `datetime.date`.

    DuckDB returns DATE columns as `datetime64`, while a caller building a
    frame by hand supplies `date`. Comparing the two raises rather than
    silently mis-filtering, so the conversion happens once, here, at the pure
    module's boundary.
    """
    if frame.empty:
        return frame
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    return out.dropna(subset=["date"])


def _as_of_start(frame: pd.DataFrame, start: date) -> tuple[date, float] | None:
    """Last close at or before `start`, within the bounded look-back.

    Backward-only, deliberately: taking the first price AFTER the window start
    would silently begin the position late, and for a stock that IPO'd
    mid-window that is the difference between an exclusion and a fabricated
    holding.
    """
    eligible = frame[frame["date"] <= start]
    if eligible.empty:
        return None
    row = eligible.iloc[-1]
    if (start - row["date"]).days > MAX_START_LOOKBACK_DAYS:
        return None
    return row["date"], float(row["close"])


def compare(
    *,
    prices: pd.DataFrame,
    benchmark: pd.DataFrame,
    start: date,
    end: date,
    benchmark_label: str,
) -> Comparison:
    """Compare an equal-weight buy-and-hold basket against the benchmark.

    `prices` is long-form `(ticker, date, close)` for the selection; `benchmark`
    is `(date, close)`. Both are filtered to the window here, so the caller
    cannot change the window by passing a different slice.

    Contract:
    - A ticker with no close at or before `start` (within the look-back) is
      **excluded and named**, never begun late.
    - A ticker with a non-positive start price is excluded: a return relative
      to zero is undefined, not infinite.
    - The portfolio index on a given date averages the price relatives of the
      holdings that have a price on that date. A holding that stops trading
      stops contributing rather than being carried forward at its last value.
    - An empty selection yields an empty `Comparison`, never a flat line at
      100, which would read as "no movement" instead of "nothing selected".
    """
    empty = Comparison(
        pd.DataFrame(columns=["date", "series_name", "index_value"]),
        (),
        (),
        None,
        None,
        None,
        None,
    )
    if prices.empty or benchmark.empty:
        return empty

    # Two filters, not one. The opening price may legitimately sit a few days
    # BEFORE the window start (a weekend or holiday), so the frame used to find
    # it reaches back by the look-back; the frame that becomes the chart starts
    # at the window. Applying only the narrow filter first -- as a first draft
    # did -- silently disabled the look-back, and dense real prices hid it.
    reach = start - timedelta(days=MAX_START_LOOKBACK_DAYS)
    prices = _to_dates(prices)
    benchmark = _to_dates(benchmark)
    openable = prices[(prices["date"] >= reach) & (prices["date"] <= end)]
    prices = prices[(prices["date"] >= start) & (prices["date"] <= end)]
    bench_openable = benchmark[
        (benchmark["date"] >= reach) & (benchmark["date"] <= end)
    ].sort_values("date")
    benchmark = benchmark[
        (benchmark["date"] >= start) & (benchmark["date"] <= end)
    ].sort_values("date")
    if bench_openable.empty:
        return empty

    bench_start = _as_of_start(bench_openable, start)
    if bench_start is None:
        return empty

    holdings: list[Holding] = []
    excluded: list[tuple[str, str]] = []
    relatives: dict[str, pd.Series] = {}

    openings = {
        str(ticker): _as_of_start(group.sort_values("date"), start)
        for ticker, group in openable.groupby("ticker", sort=True)
    }
    for ticker, group in openable.groupby("ticker", sort=True):
        group = group.sort_values("date")
        opening = openings.get(str(ticker))
        if opening is None:
            excluded.append(
                (str(ticker), "no price at the window start (listed later)")
            )
            continue
        start_date, start_close = opening
        if start_close <= 0:
            excluded.append((str(ticker), "start price is zero or negative"))
            continue
        in_window = prices[prices["ticker"] == ticker].sort_values("date")
        priced = in_window[
            in_window["close"].notna() & (in_window["close"] > 0)
        ]
        if priced.empty:
            excluded.append((str(ticker), "no usable prices in the window"))
            continue
        relatives[str(ticker)] = pd.Series(
            (priced["close"] / start_close).values, index=priced["date"].values
        )
        last = priced.iloc[-1]
        holdings.append(
            Holding(
                ticker=str(ticker),
                start_date=start_date,
                start_close=start_close,
                end_date=last["date"],
                end_close=float(last["close"]),
                total_return=float(last["close"]) / start_close - 1.0,
                start_weight=0.0,  # filled once the member count is known
                end_weight=0.0,
            )
        )

    if not holdings:
        return Comparison(empty.series, (), tuple(excluded), None, None, None, None)

    # Equal dollars at the start; weights drift with performance thereafter.
    n = len(holdings)
    ending = {h.ticker: h.end_close / h.start_close for h in holdings}
    total_ending = sum(ending.values())
    holdings = [
        Holding(
            h.ticker,
            h.start_date,
            h.start_close,
            h.end_date,
            h.end_close,
            h.total_return,
            1.0 / n,
            ending[h.ticker] / total_ending,
        )
        for h in holdings
    ]

    basket = pd.DataFrame(relatives).sort_index()
    portfolio = basket.mean(axis=1) * INDEX_BASE

    bench_start_close = bench_start[1]
    bench = benchmark.set_index("date")["close"] / bench_start_close * INDEX_BASE

    series = pd.concat(
        [
            pd.DataFrame(
                {
                    "date": portfolio.index,
                    "series_name": PORTFOLIO_SERIES,
                    "index_value": portfolio.values,
                }
            ),
            pd.DataFrame(
                {
                    "date": bench.index,
                    "series_name": benchmark_label,
                    "index_value": bench.values,
                }
            ),
        ],
        ignore_index=True,
    )

    return Comparison(
        series=series,
        holdings=tuple(sorted(holdings, key=lambda h: -h.total_return)),
        excluded=tuple(sorted(excluded)),
        start_date=min(h.start_date for h in holdings),
        end_date=max(h.end_date for h in holdings),
        portfolio_return=float(portfolio.iloc[-1]) / INDEX_BASE - 1.0,
        benchmark_return=float(bench.iloc[-1]) / INDEX_BASE - 1.0,
    )
