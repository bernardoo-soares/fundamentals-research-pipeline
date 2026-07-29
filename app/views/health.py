"""Page 3 — data health.

Answers the question the ranking cannot: *how much of this can be trusted, and
where does it run out?* Every figure here is a count from the warehouse, so the
page is also the honest counterweight to a leaderboard that necessarily shows
its best rows first.
"""

from __future__ import annotations

import altair as alt
import streamlit as st

from fundamentals_pipeline.warehouse import queries as Q

from .. import components as C
from ..theme import ASSAY, INK, PEWTER, RULE


def _coverage_chart(frame):
    return (
        alt.Chart(frame)
        .mark_bar(color=ASSAY)
        .encode(
            x=alt.X("threshold:O", title="minimum coverage",
                    axis=alt.Axis(labelAngle=0, labelColor=PEWTER,
                                  titleColor=PEWTER, titleFontSize=10,
                                  domainColor=RULE, tickColor=RULE)),
            y=alt.Y("tickers:Q", title="companies clearing it",
                    axis=alt.Axis(labelColor=PEWTER, titleColor=PEWTER,
                                  titleFontSize=10, gridColor=RULE,
                                  gridDash=[1, 3], domainColor=RULE)),
            tooltip=["threshold", "tickers"],
        )
        .properties(height=220)
        .configure_view(strokeWidth=0)
        .configure(background="white")
    )


def render(warehouse_path, as_of_year: int) -> None:
    """Draw the data-health page for one fiscal year."""
    C.eyebrow(f"How big is the trustworthy universe · FY{as_of_year}")
    coverage = Q.coverage_distribution(warehouse_path, as_of_year=as_of_year)
    st.altair_chart(_coverage_chart(coverage), width="stretch")
    st.markdown(
        '<div class="stat-note">Coverage is the share of scorecard criteria '
        "that were actually measured for a company. The curve is steep on "
        "purpose: a ranking taken from the left-hand bars is ranking companies "
        "against each other on different sets of rules.</div>",
        unsafe_allow_html=True,
    )

    C.eyebrow("Metrics that have stopped being measurable")
    metrics = Q.metric_coverage(warehouse_path, as_of_year=as_of_year)
    absent = metrics[metrics["structurally_absent"]]
    live = metrics[~metrics["structurally_absent"]]

    if absent.empty:
        C.absent_block("None", "Every metric clears the structural-absence floor.")
    else:
        # The reason is identical for all of them, so it is stated once. Four
        # copies of the same sentence is noise, and noise is what stops a
        # caveat being read.
        st.markdown(
            '<div class="stat-note">These are not charted anywhere in the '
            "console. The data source stopped providing their inputs, so a "
            "chart would be an empty frame rather than a finding. They still "
            "count against a company&#39;s coverage, which is why coverage "
            "falls after the provider changeover.</div>",
            unsafe_allow_html=True,
        )
        for _, row in absent.iterrows():
            st.markdown(
                f'<div class="led"><div class="led-top">'
                f'<span class="led-name">{row["metric_id"]}</span>'
                f'<span class="led-val verdict-na">'
                f'{int(row["present"])} of {int(row["total"])} companies</span>'
                "</div></div>",
                unsafe_allow_html=True,
            )

    C.eyebrow("Metrics still being measured")
    st.dataframe(
        live[["metric_id", "present", "total", "coverage"]],
        width="stretch",
        hide_index=True,
        column_config={
            "metric_id": st.column_config.TextColumn("Metric"),
            "present": st.column_config.NumberColumn("Measured"),
            "total": st.column_config.NumberColumn("Companies"),
            "coverage": st.column_config.ProgressColumn(
                "Coverage", min_value=0.0, max_value=1.0, format="%.3f"
            ),
        },
    )

    C.eyebrow("Known limitations attached to real values")
    st.markdown(
        '<div class="stat-note">These are not missing numbers. Each is a value '
        "that was computed and carries a measured caveat, which travels with "
        "the row rather than living in a document.</div>",
        unsafe_allow_html=True,
    )
    flags = Q.quality_flag_tally(warehouse_path, as_of_year=as_of_year)
    if flags.empty:
        C.absent_block("None recorded", "No criterion carries a quality flag.")
    else:
        for _, row in flags.iterrows():
            st.markdown(
                f'<div class="led"><div class="led-top">'
                f'<span class="led-name">{row["quality_flag"]}</span>'
                f'<span class="led-val rank-thin">{int(row["rows"])} rows · '
                f'{int(row["tickers"])} companies</span></div>'
                f'<div class="led-formula">{C.plain(row["quality_flag"])}</div>'
                "</div>",
                unsafe_allow_html=True,
            )

    C.eyebrow("Why values are absent")
    reasons = Q.reason_code_tally(warehouse_path, as_of_year=as_of_year)
    if reasons.empty:
        C.absent_block("Nothing absent", "Every trend metric produced a value.")
        return
    chart = (
        alt.Chart(reasons)
        .mark_bar(color=PEWTER)
        .encode(
            y=alt.Y("reason_code:N", sort="-x", title=None,
                    axis=alt.Axis(labelColor=INK, labelFontSize=11,
                                  domainColor=RULE, tickColor=RULE)),
            x=alt.X("rows:Q", title="rows",
                    axis=alt.Axis(labelColor=PEWTER, titleColor=PEWTER,
                                  titleFontSize=10, gridColor=RULE,
                                  gridDash=[1, 3])),
            tooltip=["reason_code", "rows"],
        )
        .properties(height=26 * len(reasons) + 40)
        .configure_view(strokeWidth=0)
        .configure(background="white")
    )
    st.altair_chart(chart, width="stretch")
    for _, row in reasons.iterrows():
        st.markdown(
            f'<div class="stat-note">· <b>{row["reason_code"]}</b> — '
            f'{C.plain(row["reason_code"])}</div>',
            unsafe_allow_html=True,
        )
