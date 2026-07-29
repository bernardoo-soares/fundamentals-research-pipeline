"""Page 4 — selection against the market (platform spec section 8.3).

The most dangerous page in the console, because a line above the benchmark
looks like evidence and is not. Everything here is arranged around saying so:
the caveat is printed with the chart rather than tucked in a tooltip, the
excluded tickers are named, and the page never uses the word backtest.
"""

from __future__ import annotations

import html
from datetime import timedelta

import altair as alt
import streamlit as st

from fundamentals_pipeline.contracts.benchmark_schema import (
    AVAILABLE_WINDOW_YEARS,
    BENCHMARK_LABEL,
    LOOKBACK_CAVEAT,
    RETURN_BASIS_NOTE,
    WINDOW_LIMIT_REASON,
)
from fundamentals_pipeline.portfolio.comparison import (
    PORTFOLIO_SERIES,
    compare,
)
from fundamentals_pipeline.warehouse import queries as Q

from .. import components as C
from ..theme import ASSAY, INK, PEWTER, RULE

DAYS_PER_YEAR = 365.25
CHART_HEIGHT = 380

# How many companies to preselect, so the page shows something on arrival
# rather than an empty frame. Deliberately small: a default of "the top 20"
# would look like a recommendation.
DEFAULT_SELECTION_SIZE = 5


def _chart(frame) -> alt.Chart:
    return (
        alt.Chart(frame)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("date:T", title=None,
                    axis=alt.Axis(labelColor=PEWTER, domainColor=RULE,
                                  tickColor=RULE, labelFontSize=10)),
            y=alt.Y("index_value:Q", title="indexed to 100 at window start",
                    scale=alt.Scale(zero=False),
                    axis=alt.Axis(labelColor=PEWTER, titleColor=PEWTER,
                                  titleFontSize=10, gridColor=RULE,
                                  gridDash=[1, 3], domainColor=RULE,
                                  labelFontSize=10)),
            color=alt.Color(
                "series_name:N",
                title=None,
                # Gold is the selection because gold means measured; the
                # benchmark is the neutral reference it is measured against.
                scale=alt.Scale(
                    domain=[PORTFOLIO_SERIES, BENCHMARK_LABEL],
                    range=[ASSAY, INK],
                ),
                legend=alt.Legend(orient="top-left", labelFontSize=11),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("series_name:N", title="Series"),
                alt.Tooltip("index_value:Q", title="Index", format=".1f"),
            ],
        )
        .properties(height=CHART_HEIGHT)
        .configure_view(strokeWidth=0)
        .configure(background="white")
    )


def render(warehouse_path, as_of_year: int, ranked) -> None:
    """Draw the comparison page for a chosen selection and window."""
    if not Q.has_benchmark(warehouse_path):
        C.absent_block(
            "No benchmark series",
            "Run `python -m fundamentals_pipeline benchmark-build` to load it.",
        )
        return

    coverage = Q.price_coverage(warehouse_path)
    if coverage is None:
        C.absent_block("No price history", "Run prices-build and benchmark-build.")
        return
    first_priced, last_priced = coverage

    tickers = ranked["ticker"].tolist()
    with st.sidebar:
        C.eyebrow("Selection")
        chosen = st.multiselect(
            "Companies",
            tickers,
            default=tickers[:DEFAULT_SELECTION_SIZE],
            help=(
                "Equal dollars into each at the window start, then held. No "
                "rebalancing."
            ),
        )
        years = st.radio(
            "Window",
            AVAILABLE_WINDOW_YEARS,
            index=len(AVAILABLE_WINDOW_YEARS) - 1,
            format_func=lambda y: f"{y} year" + ("s" if y > 1 else ""),
            horizontal=True,
        )
        st.markdown(
            f'<div class="stat-note">{html.escape(WINDOW_LIMIT_REASON)}</div>',
            unsafe_allow_html=True,
        )

    end = last_priced
    start = end - timedelta(days=int(DAYS_PER_YEAR * years))

    if not chosen:
        C.absent_block(
            "Nothing selected",
            "Pick one or more companies in the sidebar to compare.",
        )
        return

    result = compare(
        prices=Q.price_history(
            warehouse_path, tickers=tuple(chosen), start=start, end=end
        ),
        benchmark=Q.benchmark_history(warehouse_path, start=start, end=end),
        start=start,
        end=end,
        benchmark_label=BENCHMARK_LABEL,
    )

    if result.is_empty:
        C.absent_block(
            "Nothing in this selection has a price at the window start",
            f"The window begins {start}. Price history starts {first_priced}.",
        )
        return

    C.eyebrow(
        f"{len(result.holdings)} companies · {years}-year window · "
        f"{result.start_date} to {result.end_date}"
    )

    # The caveat sits ABOVE the chart, not below it: a reader who stops at the
    # picture must still have read it.
    st.markdown(
        f'<div class="assay-caveat">{html.escape(LOOKBACK_CAVEAT)}</div>',
        unsafe_allow_html=True,
    )
    st.altair_chart(_chart(result.series), width="stretch")
    st.markdown(
        f'<div class="stat-note">{html.escape(RETURN_BASIS_NOTE)}</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)
    with left:
        C.stat(
            "Selection",
            f"{result.portfolio_return:+.1%}",
            note="equal weight, buy and hold",
            measured=True,
        )
    with right:
        C.stat(
            BENCHMARK_LABEL,
            f"{result.benchmark_return:+.1%}",
            note="price return, dividends excluded",
        )

    if result.excluded:
        C.eyebrow(f"Excluded from this window ({len(result.excluded)})")
        st.markdown(
            '<div class="stat-note">Named rather than dropped: a basket that '
            "silently loses its late arrivals reports the survivors' return as "
            "the basket's.</div>",
            unsafe_allow_html=True,
        )
        for ticker, reason in result.excluded:
            st.markdown(
                f'<div class="led"><div class="led-top">'
                f'<span class="led-name">{html.escape(ticker)}</span>'
                f'<span class="led-right verdict-na">{html.escape(reason)}'
                "</span></div></div>",
                unsafe_allow_html=True,
            )

    C.eyebrow("Per-company contribution")
    rows = []
    for holding in result.holdings:
        rows.append(
            '<tr>'
            f'<th class="fld">{html.escape(holding.ticker)}</th>'
            f"<td>{C.num(holding.start_close, 2)}</td>"
            f"<td>{C.num(holding.end_close, 2)}</td>"
            f"<td>{holding.total_return:+.2%}</td>"
            f"<td>{holding.start_weight:.3f}</td>"
            f"<td>{holding.end_weight:.3f}</td>"
            "</tr>"
        )
    st.markdown(
        '<table class="inputs"><thead><tr><th class="fld"></th>'
        "<th>Start</th><th>End</th><th>Return</th>"
        "<th>Weight at start</th><th>Weight at end</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>",
        unsafe_allow_html=True,
    )
