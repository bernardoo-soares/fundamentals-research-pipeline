"""Page 1 — ranking.

The page exists to answer one question honestly: *which companies score well
on evidence that was actually measured?* Measured 2026-07-29, the naive answer
puts COIN third at 92.1 on a coverage of 0.273 -- five criteria out of
twenty-two. So coverage is not a column here; it is built into the bar and
into a filter that is on by default.
"""

from __future__ import annotations

import html

import streamlit as st

from fundamentals_pipeline.warehouse import queries as Q

from .. import components as C
from ..theme import PAGE_SIZE

# Default minimum coverage. Chosen from the measured distribution: 0.70 keeps
# 310 of 384 FY2024 tickers while excluding the cases the ranking is least
# honest about (COIN 0.273, META 0.391). It is a floor the reader can lower --
# deliberately, and having seen where it sits -- not a hidden filter.
DEFAULT_MIN_COVERAGE = 0.70

# Badges rarer than half the universe, so worth the eye. See components.flags.
RARE_BADGES = frozenset({"low_confidence", "stale"})

SORT_EVIDENCE = "Evidence (score × coverage)"
SORT_COMPOSITE = "Composite score"
SORT_OPTIONS = (SORT_EVIDENCE, SORT_COMPOSITE)


def render(warehouse_path, as_of_year: int) -> None:
    """Draw the ranking page for one fiscal year."""
    frame = Q.ranking(warehouse_path, as_of_year=as_of_year)

    with st.sidebar:
        C.eyebrow("Filter")
        min_coverage = st.slider(
            "Minimum coverage",
            0.0,
            1.0,
            DEFAULT_MIN_COVERAGE,
            0.05,
            help=(
                "The share of scorecard criteria that were actually measured "
                "for a company. A high score computed from a handful of "
                "criteria is not the same claim as the same score computed "
                "from all of them."
            ),
        )
        min_score = st.slider("Minimum composite", 0.0, 100.0, 0.0, 1.0)
        sort_by = st.radio("Rank by", SORT_OPTIONS, index=0)
        search = st.text_input("Find ticker", placeholder="e.g. KO").strip().upper()

    shown = frame[frame["coverage_ratio"].fillna(0.0) >= min_coverage]
    shown = shown[shown["composite"].fillna(0.0) >= min_score]
    if search:
        shown = shown[shown["ticker"].str.contains(search, na=False)]
    shown = shown.sort_values(
        "evidence" if sort_by == SORT_EVIDENCE else "composite",
        ascending=False,
        kind="mergesort",
    )

    excluded = len(frame) - len(shown)
    C.eyebrow(
        f"{len(shown)} companies · FY{as_of_year} · "
        f"{excluded} held back by the filters"
    )

    if shown.empty:
        C.absent_block(
            "Nothing clears these filters",
            "Lower the minimum coverage or composite in the sidebar.",
        )
        return

    st.markdown(
        '<div class="rank-row rank-head">'
        "<div>#</div><div>Ticker</div><div>Score, and how much of it was "
        "measured</div><div class='rank-num'>Coverage</div>"
        "<div class='rank-num'>Checklist</div><div class='rank-num'>P/E</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    page = st.session_state.get("rank_page", 0)
    start = page * PAGE_SIZE
    window = shown.iloc[start : start + PAGE_SIZE]

    rows = []
    for offset, (_, row) in enumerate(window.iterrows(), start=start + 1):
        checklist = (
            f"{int(row['checklist_passed'])}/{int(row['checklist_applicable'])}"
            if row["checklist_applicable"] and row["checklist_applicable"] > 0
            else "—"
        )
        rows.append(
            '<div class="rank-row">'
            f'<div class="rank-n">{offset}</div>'
            f'<div class="rank-ticker">{html.escape(str(row["ticker"]))}</div>'
            f"<div>{C.evidence_bar(row['composite'], row['coverage_ratio'])}</div>"
            f'<div class="rank-num rank-thin">{C.num(row["coverage_ratio"], 2)}</div>'
            f'<div class="rank-num rank-thin">{checklist}</div>'
            f'<div class="rank-num rank-thin">{C.num(row["pe_ttm"], 1)}</div>'
            "</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)

    total_pages = max(1, -(-len(shown) // PAGE_SIZE))
    if total_pages > 1:
        left, mid, right = st.columns([1, 2, 1])
        with left:
            if st.button("Previous", disabled=page == 0, width="stretch"):
                st.session_state["rank_page"] = page - 1
                st.rerun()
        with mid:
            st.markdown(
                f'<div style="text-align:center" class="stat-note">'
                f"Page {page + 1} of {total_pages}</div>",
                unsafe_allow_html=True,
            )
        with right:
            if st.button(
                "Next", disabled=page + 1 >= total_pages, width="stretch"
            ):
                st.session_state["rank_page"] = page + 1
                st.rerun()

    C.eyebrow("Open a company")
    picked = st.selectbox(
        "Company", shown["ticker"].tolist(), label_visibility="collapsed"
    )
    if st.button("Show the full scorecard", type="primary"):
        st.session_state["ticker"] = picked
        st.session_state["view"] = "Company"
        st.rerun()

    st.download_button(
        "Download this view as CSV",
        shown.to_csv(index=False).encode("utf-8"),
        file_name=f"ranking_FY{as_of_year}.csv",
        mime="text/csv",
    )
