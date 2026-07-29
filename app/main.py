"""The research console: a thin router over the read-only query API.

Run it with:

    python -m streamlit run app/main.py

No business logic lives here or in any view. Every number is SELECTed from the
warehouse by `warehouse/queries.py`, which opens the database read-only, so
"the console computes nothing" is structural rather than a convention
(platform spec section 7.2).

ONE FISCAL YEAR AT A TIME, DELIBERATELY
---------------------------------------
There is no cross-year composite view and no "vs last year" delta, because
composites are not comparable across years. Measured 2026-07-29: the mean
FY2020 composite is 56.8 and the mean FY2024 composite is 64.6, while mean
coverage falls from 0.87 to 0.81. Companies did not improve by eight points --
the criteria that were hardest to satisfy stopped being measurable. Offering
the comparison would be offering a false number.
"""

from __future__ import annotations

# Imports below the sys.path bootstrap are deliberate and cannot be hoisted:
# the repo root has to be importable before `app` and `fundamentals_pipeline`
# resolve when this file is launched directly by `streamlit run`.
# ruff: noqa: E402
import sys
from pathlib import Path

import streamlit as st

# Support `streamlit run app/main.py` from the repo root without an install
# step, which is how a local research tool is actually launched.
_REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "src"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from app import components as C  # noqa: E402
from app.theme import stylesheet  # noqa: E402
from app.views import (  # noqa: E402
    company,
    health,
    portfolio,
    ranking,
    watchlist,
)
from fundamentals_pipeline.core.settings import get_settings  # noqa: E402
from fundamentals_pipeline.warehouse import queries as Q  # noqa: E402
from fundamentals_pipeline.warehouse.queries import (  # noqa: E402
    WarehouseUnavailable,
)

VIEWS = ("Ranking", "Company", "Vs market", "Watchlist", "Data health")

# The universe the S&P 500 is drawn from, for the horizon banner's denominator.
UNIVERSE_SIZE = 502


def _masthead() -> None:
    st.markdown(
        '<div class="assay-masthead">'
        '<div class="assay-wordmark">ASSAY<span class="mark">.</span></div>'
        '<div class="assay-tagline">Durable-business research on S&amp;P 500 '
        "fundamentals. Gold marks what was measured.</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _horizon(as_of_year: int, scored: int, latest_year: int) -> None:
    st.markdown(
        f'<div class="assay-horizon">'
        f"Fundamentals through <b>FY{latest_year}</b> (SimFin free tier, "
        f"roughly a 12-month delay). Viewing <b>FY{as_of_year}</b> · "
        f"<b>{scored}</b> of {UNIVERSE_SIZE} universe tickers scored. "
        f"Scores from different fiscal years are not comparable and are never "
        f"shown side by side."
        "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    """Render the console."""
    st.set_page_config(
        page_title="Assay — fundamentals research",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(stylesheet(), unsafe_allow_html=True)
    _masthead()

    warehouse_path = get_settings().warehouse_path
    try:
        Q.check_ready(warehouse_path)
    except WarehouseUnavailable as error:
        C.absent_block("The warehouse is not ready", str(error))
        return

    years = Q.available_years(warehouse_path)
    if not years:
        C.absent_block(
            "No scores yet",
            "Run `python -m fundamentals_pipeline scores-build` and reload.",
        )
        return

    with st.sidebar:
        C.eyebrow("View")
        view = st.radio(
            "View",
            VIEWS,
            index=VIEWS.index(st.session_state.get("view", VIEWS[0])),
            label_visibility="collapsed",
        )
        st.session_state["view"] = view
        C.eyebrow("Fiscal year")
        as_of_year = st.selectbox(
            "Fiscal year", years, index=0, label_visibility="collapsed"
        )

    frame = Q.ranking(warehouse_path, as_of_year=as_of_year)
    _horizon(as_of_year, len(frame), years[0])

    if view == "Ranking":
        ranking.render(warehouse_path, as_of_year)
    elif view == "Company":
        company.render(warehouse_path, as_of_year, frame["ticker"].tolist())
    elif view == "Vs market":
        portfolio.render(warehouse_path, as_of_year, frame)
    elif view == "Watchlist":
        watchlist.render(warehouse_path, frame)
    else:
        health.render(warehouse_path, as_of_year)


main()
