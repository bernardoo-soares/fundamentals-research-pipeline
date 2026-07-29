"""Page 2 — company drilldown.

The platform spec's hard requirement: every number is a door. A score is only
useful here if the reader can get from it to the rule it came from, the value
that was measured, the formula that produced it, and the reason it is missing
when it is missing -- in under a minute, hand-verifiable against the published
CSVs.
"""

from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

from fundamentals_pipeline.metrics.quarterly_registry import (
    QUARTERLY_REGISTRY,
    operand_totals_for,
)
from fundamentals_pipeline.metrics.registry import REGISTRY
from fundamentals_pipeline.metrics.registry import (
    operand_totals_for as trend_totals_for,
)
from fundamentals_pipeline.warehouse import queries as Q

from .. import components as C
from ..theme import ASSAY, INK, PEWTER, RULE

# Formula strings come from the metric registries, which are the single source
# for both computation and display (platform spec section 6). The UI never
# writes its own description of what a metric does -- that is exactly how a
# docstring and an implementation drift apart.
FORMULAS: dict[str, str] = {
    **{m.metric_id: m.formula for m in REGISTRY},
    **{m.metric_id: m.formula for m in QUARTERLY_REGISTRY},
}
VERSIONS: dict[str, str] = {
    **{m.metric_id: m.version for m in REGISTRY},
    **{m.metric_id: m.version for m in QUARTERLY_REGISTRY},
}
# metric_id -> (grain, declared input columns, window length in years).
# The registries are the single source for both computation and display
# (platform spec section 6); the console never writes its own account of what
# a metric reads.
TREND_GRAIN = "trend"
QUARTERLY_GRAIN = "quarterly"
INPUTS: dict[str, tuple[str, tuple[str, ...], int]] = {
    **{m.metric_id: (TREND_GRAIN, m.inputs, m.window_length) for m in REGISTRY},
    **{
        m.metric_id: (QUARTERLY_GRAIN, m.inputs, 1)
        for m in QUARTERLY_REGISTRY
    },
}

# A TTM metric reads the four quarters ending at the fiscal year end.
TTM_QUARTERS = 4

ERA_MARK = {"legacy_compustat": "legacy", "simfin": "SimFin"}

QUARTERLY_BY_ID = {m.metric_id: m for m in QUARTERLY_REGISTRY}
TREND_BY_ID = {m.metric_id: m for m in REGISTRY}

# A derived intermediate with a one-year window is a per-year SERIES: only the
# whole series shows which years cleared a threshold, so it is drawn as a row
# in the operand grid rather than as a single figure.
SERIES_WINDOW_LENGTH = 1

# Money is stored in millions and reads fine at one decimal. A ratio does not:
# NVDA's net margin was 0.2411 in FY2016 and 0.1619 in FY2022, and at one
# decimal both print "0.2" -- destroying the >0.20 discrimination the row
# exists to make.
MONEY_DECIMALS = 1
RATIO_DECIMALS = 4

# How much of a long registry formula to show before the reader has to ask for
# the rest. Several carry multi-paragraph measurement records.
FORMULA_PREVIEW_CHARS = 260

CHART_HEIGHT = 190

# Vertical room per categorical bar. At 26px Altair silently drops every other
# axis label once there are five components, which reads as a broken chart.
CATEGORY_ROW_HEIGHT = 42


def _trend_chart(frame: pd.DataFrame, metric_id: str) -> alt.Chart:
    """A metric's history, with null years genuinely gapped.

    Altair breaks the line at a null rather than joining across it, which is
    the point: an interpolated segment would assert a measurement that was
    never taken (S4.2).
    """
    base = alt.Chart(frame).encode(
        x=alt.X(
            "as_of_year:O",
            title=None,
            axis=alt.Axis(labelAngle=0, labelColor=PEWTER, domainColor=RULE,
                          tickColor=RULE, labelFontSize=10),
        )
    )
    line = base.mark_line(color=ASSAY, strokeWidth=2, point=False).encode(
        y=alt.Y(
            "value:Q",
            title=None,
            axis=alt.Axis(labelColor=PEWTER, domainColor=RULE, tickColor=RULE,
                          gridColor=RULE, gridDash=[1, 3], labelFontSize=10),
        )
    )
    dots = base.mark_point(
        color=ASSAY, filled=True, size=32, opacity=1
    ).encode(
        y="value:Q",
        tooltip=[
            alt.Tooltip("as_of_year:O", title="Fiscal year"),
            alt.Tooltip("value:Q", title=metric_id, format=".4f"),
            alt.Tooltip("quality_flag:N", title="Flag"),
        ],
    )
    return (
        (line + dots)
        .properties(height=CHART_HEIGHT)
        .configure_view(strokeWidth=0)
        .configure(background="white")
    )


def _inputs_table(
    frame,
    period_column: str,
    label,
    *,
    ratio_fields: frozenset[str] = frozenset(),
    eras: dict | None = None,
) -> str:
    """Render operands as a field x period grid, with the provider era.

    `ratio_fields` are shown to four decimals; everything else to one. The era
    row is not decoration: it shows exactly where the provider boundary falls
    inside the window, which is what makes a value carry `mixed_era_window` or
    `cross_era_window`. Seeing the seam is how a reader checks that verdict.

    `eras` is passed in rather than read off `frame`, because derived series
    rows appended to the grid carry no provider of their own and would blank
    the row if they were allowed to overwrite it.
    """
    periods = list(dict.fromkeys(frame[period_column].tolist()))
    head = "".join(f"<th>{html.escape(label(p))}</th>" for p in periods)
    body = []
    for field, group in frame.groupby("field", sort=True):
        by_period = dict(zip(group[period_column], group["value"], strict=False))
        places = (
            RATIO_DECIMALS if str(field) in ratio_fields else MONEY_DECIMALS
        )
        cells = "".join(
            f"<td>{C.num(by_period.get(p), places)}</td>" for p in periods
        )
        derived = ' class="derived"' if str(field) in ratio_fields else ""
        body.append(
            f'<tr{derived}><th class="fld">{html.escape(str(field))}</th>'
            f"{cells}</tr>"
        )

    lookup = eras or {}
    era_cells = "".join(
        f"<td>{html.escape(ERA_MARK.get(str(lookup.get(p)), '—'))}</td>"
        for p in periods
    )
    body.append(f'<tr class="era"><th class="fld">provider</th>{era_cells}</tr>')

    return (
        f'<table class="inputs"><thead><tr><th class="fld"></th>{head}</tr>'
        f"</thead><tbody>{''.join(body)}</tbody></table>"
    )


def _render_inputs(warehouse_path, ticker: str, metric_id: str, as_of_year: int):
    """The operands behind one criterion, with their fiscal periods.

    For a quarterly metric this is followed by the TTM totals the metric used,
    read from `metrics_quarterly` -- never summed here. See
    `_render_operand_totals`.

    Trend metrics show operands only. Their window aggregates (the 10-year
    capex and earnings sums behind `capex_pct_net_income_avg10y`, for example)
    are not published by the engine, so there is nothing honest to display
    beside them yet; that is recorded as an open item rather than computed in
    a view.
    """
    declared = INPUTS.get(metric_id)
    if declared is None:
        C.absent_block(
            "No inputs registered",
            f"{metric_id} is not in a metric registry, so its operands are "
            "not declared.",
        )
        return
    grain, fields, window = declared

    if grain == TREND_GRAIN:
        frame = Q.annual_inputs(
            warehouse_path,
            ticker=ticker,
            fields=fields,
            start_year=as_of_year - window + 1,
            end_year=as_of_year,
        )
        period, label = "fiscal_year", lambda p: f"FY{int(p)}"
        caption = f"annual values across the {window}-year window"
        eras = dict(zip(frame["fiscal_year"], frame["source_era"], strict=False))
        frame, ratio_fields = _with_derived_series(
            warehouse_path, ticker, metric_id, as_of_year, window, frame
        )
    else:
        frame = Q.quarterly_inputs(
            warehouse_path,
            ticker=ticker,
            fields=fields,
            end_year=as_of_year,
            quarters=TTM_QUARTERS,
        )
        period, label = "quarter", None
        frame = frame.assign(
            period=frame["year"].astype(int).astype(str)
            + "Q"
            + frame["quarter"].astype(int).astype(str)
        )
        period, label = "period", str
        caption = f"the {TTM_QUARTERS} quarters ending at the fiscal year end"
        eras = dict(zip(frame["period"], frame["source_era"], strict=False))
        ratio_fields = frozenset()

    if frame.empty:
        C.absent_block(
            "No stored inputs for this window",
            "Stage 1 holds no rows for these periods.",
        )
        return

    st.markdown(
        f'<div class="stat-note">{html.escape(caption)}, exactly as Stage 1 '
        "stores them.</div>"
        + _inputs_table(
            frame, period, label, ratio_fields=ratio_fields, eras=eras
        ),
        unsafe_allow_html=True,
    )
    _render_operand_totals(warehouse_path, ticker, metric_id, grain, as_of_year)


def _with_derived_series(
    warehouse_path, ticker: str, metric_id: str, as_of_year: int, window: int, frame
):
    """Append per-year derived intermediates as extra rows in the operand grid.

    `net_margin_ge20_years_10y` counts years above 0.20; showing the ratio per
    year, aligned under the same year columns as its operands, is what makes
    that count checkable at a glance. The values are read from `metrics_trend`,
    not divided here.
    """
    metric = TREND_BY_ID.get(metric_id)
    if metric is None:
        return frame, frozenset()
    series_ids = tuple(
        total
        for total in trend_totals_for(metric)
        if TREND_BY_ID[total].window_length == SERIES_WINDOW_LENGTH
    )
    if not series_ids:
        return frame, frozenset()
    extra = Q.trend_metric_series(
        warehouse_path,
        ticker=ticker,
        metric_ids=series_ids,
        start_year=as_of_year - window + 1,
        end_year=as_of_year,
    )
    if extra.empty:
        return frame, frozenset()
    return pd.concat(
        [
            frame,
            extra.rename(
                columns={"metric_id": "field", "as_of_year": "fiscal_year"}
            ).assign(source_era=None)[
                ["fiscal_year", "source_era", "field", "value"]
            ],
        ],
        ignore_index=True,
    ), frozenset(series_ids)


def _render_operand_totals(
    warehouse_path, ticker: str, metric_id: str, grain: str, as_of_year: int
) -> None:
    """The derived figures the metric used, as the engine published them.

    Quarterly: the TTM totals. Trend: the per-year series a threshold metric
    tested, or the masked window sums behind a ratio of sums.

    Always read from the metrics tables, never computed here. Deriving them in
    a view would express the rule a second time (S2.6), and would produce a
    figure across the provider boundary where the engine nulls the window --
    so the console would show a total the engine had refused to compute. When
    that happens the reason code appears instead of a number.

    The masked window sums are the case that makes this load-bearing rather
    than convenient: `capex_pct_net_income_avg10y` sums only years where BOTH
    legs are present, so adding up the operand grid by hand gives a different
    number than the metric used.
    """
    if grain == QUARTERLY_GRAIN:
        metric = QUARTERLY_BY_ID.get(metric_id)
        wanted = operand_totals_for(metric) if metric else ()
        frame = (
            Q.quarterly_metric_values(
                warehouse_path, ticker=ticker, metric_ids=wanted, year=as_of_year
            )
            if wanted
            else None
        )
    else:
        metric = TREND_BY_ID.get(metric_id)
        wanted = (
            tuple(
                total
                for total in trend_totals_for(metric)
                if TREND_BY_ID[total].window_length != SERIES_WINDOW_LENGTH
            )
            if metric
            else ()
        )
        frame = (
            Q.trend_metric_values(
                warehouse_path, ticker=ticker, metric_ids=wanted, as_of_year=as_of_year
            )
            if wanted
            else None
        )
    if frame is None or frame.empty:
        return

    rows = []
    for _, row in frame.iterrows():
        name = str(row["metric_id"])
        if C._is_absent(row["value"]):
            shown = (
                f'<span class="verdict-na">not computed — '
                f'{html.escape(C.plain(row["reason_code"]))}</span>'
            )
        else:
            shown = f'<b>{C.num(row["value"], 1)}</b>'
        flag = (
            f' <span class="flag">{html.escape(str(row["quality_flag"]))}</span>'
            if not C._is_absent(row["quality_flag"])
            else ""
        )
        rows.append(
            f'<tr><th class="fld">{html.escape(name)} '
            f'<span class="rank-thin">v{html.escape(str(row["metric_version"]))}'
            f"</span></th><td>{shown}{flag}</td></tr>"
        )

    st.markdown(
        '<div class="stat-label" style="margin-top:.8rem">totals the metric '
        "used, as the engine published them</div>"
        f'<div class="stat-note">Read from '
        f'{"metrics_quarterly" if grain == QUARTERLY_GRAIN else "metrics_trend"}'
        ", not computed here: a figure derived in a view would express the "
        "rule a second time, and would aggregate across the provider boundary "
        "where the engine nulls the window.</div>"
        f'<table class="inputs totals"><tbody>{"".join(rows)}</tbody></table>',
        unsafe_allow_html=True,
    )


def _render_header(warehouse_path, ticker: str, as_of_year: int) -> bool:
    header = Q.score_header(
        warehouse_path, ticker=ticker, as_of_year=as_of_year
    )
    if header.empty:
        C.absent_block(
            f"{ticker} has no score for FY{as_of_year}",
            "Pick another year in the sidebar, or another company.",
        )
        return False
    row = header.iloc[0]

    profile = Q.company(warehouse_path, ticker=ticker)
    if profile.empty:
        # Left the index, so no current-membership row exists. Shown by ticker
        # alone rather than given an invented name.
        subtitle = "not a current S&P 500 constituent — no name or sector on file"
    else:
        p = profile.iloc[0]
        subtitle = " · ".join(
            str(x)
            for x in (p["company_name"], p["sector"], p["sub_industry"])
            if not C._is_absent(x)
        )
    st.markdown(
        f'<div class="assay-wordmark" style="font-size:34px">'
        f'{html.escape(ticker)}</div>'
        f'<div class="assay-tagline">{html.escape(subtitle)}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="ev-header">'
        f'{C.evidence_bar(row["composite"], row["coverage_ratio"])}</div>',
        unsafe_allow_html=True,
    )

    a, b, c, d = st.columns(4)
    with a:
        C.stat("Composite", C.num(row["composite"], 1), measured=True)
    with b:
        C.stat(
            "Coverage",
            C.num(row["coverage_ratio"], 2),
            note="share of criteria measured",
        )
    with c:
        applicable = row["checklist_applicable"]
        C.stat(
            "Checklist",
            f"{int(row['checklist_passed'])}/{int(applicable)}"
            if applicable
            else "—",
            note="rules passed",
        )
    with d:
        C.stat(
            "Staleness",
            f"{int(row['staleness_quarters'])} q",
            note="quarters behind the latest",
        )

    badges = C.flags(row["badges"], rare=frozenset({"low_confidence", "stale"}))
    if badges:
        st.markdown(badges, unsafe_allow_html=True)
        for badge in str(row["badges"]).split(","):
            name = badge.strip()
            if name:
                st.markdown(
                    f'<div class="stat-note">· <b>{html.escape(name)}</b> — '
                    f"{html.escape(C.plain(name))}</div>",
                    unsafe_allow_html=True,
                )
    st.session_state["_provenance"] = row
    return True


def _render_components(warehouse_path, ticker: str, as_of_year: int) -> None:
    C.eyebrow("Where the score came from")
    frame = Q.components(warehouse_path, ticker=ticker, as_of_year=as_of_year)
    if frame.empty:
        C.absent_block("No components", "This ticker-year produced no component rows.")
        return

    frame = frame.assign(contribution=frame["score"] * frame["weight"])
    chart = (
        alt.Chart(frame)
        .mark_bar(color=ASSAY)
        .encode(
            y=alt.Y("component_id:N", sort="-x", title=None,
                    axis=alt.Axis(labelColor=INK, labelFontSize=11,
                                  domainColor=RULE, tickColor=RULE)),
            x=alt.X("contribution:Q", title="points contributed to the composite",
                    axis=alt.Axis(labelColor=PEWTER, gridColor=RULE,
                                  gridDash=[1, 3], titleColor=PEWTER,
                                  titleFontSize=10)),
            tooltip=[
                alt.Tooltip("component_id:N", title="Component"),
                alt.Tooltip("score:Q", title="Score", format=".1f"),
                alt.Tooltip("weight:Q", title="Weight", format=".2f"),
                alt.Tooltip("contribution:Q", title="Contribution", format=".2f"),
                alt.Tooltip("applicable_criteria:Q", title="Criteria measured"),
                alt.Tooltip("total_criteria:Q", title="Criteria total"),
            ],
        )
        .properties(height=CATEGORY_ROW_HEIGHT * len(frame) + 50)
        .configure_view(strokeWidth=0)
        .configure(background="white")
    )
    st.altair_chart(chart, width="stretch")


def _render_criteria(warehouse_path, ticker: str, as_of_year: int) -> None:
    C.eyebrow("Every rule, and what it measured")
    frame = Q.criteria(warehouse_path, ticker=ticker, as_of_year=as_of_year)
    if frame.empty:
        C.absent_block("No criteria", "This ticker-year produced no criterion rows.")
        return

    for component_id, group in frame.groupby("component_id", sort=True):
        st.markdown(
            f'<div class="stat-label" style="margin-top:.9rem">'
            f"{html.escape(str(component_id))}</div>",
            unsafe_allow_html=True,
        )
        for _, row in group.iterrows():
            metric_id = str(row["metric_id"])
            if C._is_absent(row["value"]):
                right = (
                    f'<span class="verdict-na">not measured — '
                    f'{html.escape(C.plain(row["reason_code"]))}</span>'
                )
            else:
                right = (
                    f'<span class="led-val">{C.num(row["value"], 4)}</span>'
                    f'&nbsp;&nbsp;{C.num(row["points"], 1)} pts'
                    f'&nbsp;&times;&nbsp;{C.num(row["weight"], 2)}'
                    f"&nbsp;&nbsp;{C.verdict(row['checklist_verdict'])}"
                )
            flag = (
                C.flags(row["quality_flag"], rare=frozenset({"da_allocation_assumed"}))
                if not C._is_absent(row["quality_flag"])
                else ""
            )
            formula = FORMULAS.get(metric_id, "")
            preview = formula[:FORMULA_PREVIEW_CHARS]
            if len(formula) > FORMULA_PREVIEW_CHARS:
                preview += " …"
            version = VERSIONS.get(metric_id, "?")
            st.markdown(
                f'<div class="led">'
                f'<div class="led-top"><span class="led-name">'
                f"{html.escape(metric_id)} "
                f'<span class="rank-thin">v{html.escape(str(version))}</span>'
                f'</span><span class="led-right">{right}</span></div>'
                f'<div class="led-formula">{html.escape(preview)}</div>'
                f"{flag}</div>",
                unsafe_allow_html=True,
            )
            if flag:
                st.markdown(
                    f'<div class="stat-note" style="margin:-.3rem 0 .5rem">'
                    f'{html.escape(C.plain(row["quality_flag"]))}</div>',
                    unsafe_allow_html=True,
                )
            # The last door: the Stage 1 operands and their fiscal periods.
            # Collapsed, because 22 criteria of raw figures at once would bury
            # the scores they belong to.
            with st.expander(f"Inputs behind {metric_id}"):
                _render_inputs(warehouse_path, ticker, metric_id, as_of_year)
                st.markdown(
                    '<div class="stat-label" style="margin-top:.9rem">'
                    "full formula, from the metric registry</div>"
                    f'<div class="led-formula">'
                    f"{html.escape(FORMULAS.get(metric_id, '(none registered)'))}"
                    "</div>",
                    unsafe_allow_html=True,
                )


def _render_trends(warehouse_path, ticker: str) -> None:
    C.eyebrow("History")
    metric_ids = sorted(m.metric_id for m in REGISTRY)
    chosen = st.selectbox("Metric", metric_ids, key="trend_metric")
    frame = Q.trend_history(warehouse_path, ticker=ticker, metric_id=chosen)

    if frame.empty or frame["value"].notna().sum() == 0:
        reasons = (
            frame["reason_code"].dropna().value_counts()
            if not frame.empty
            else pd.Series(dtype=int)
        )
        why = C.plain(reasons.index[0]) if len(reasons) else "no rows were produced"
        C.absent_block(f"{chosen} has no values for {ticker}", why)
        return

    st.altair_chart(_trend_chart(frame, chosen), width="stretch")
    gaps = int(frame["value"].isna().sum())
    if gaps:
        reasons = frame["reason_code"].dropna().value_counts()
        detail = "; ".join(
            f"{count}× {C.plain(code)}" for code, count in reasons.items()
        )
        st.markdown(
            f'<div class="stat-note">{gaps} year(s) are gaps, never '
            f"interpolated — {html.escape(detail)}</div>",
            unsafe_allow_html=True,
        )


def _render_valuation(warehouse_path, ticker: str, as_of_year: int) -> None:
    C.eyebrow("Valuation at the fiscal year end")
    frame = Q.valuation(warehouse_path, ticker=ticker, as_of_year=as_of_year)
    if frame.empty:
        C.absent_block(
            "No valuation row",
            "This ticker-year has no price-linked valuation.",
        )
        return
    row = frame.iloc[0]

    a, b, c, d = st.columns(4)
    with a:
        C.stat(
            "Close",
            C.num(row["close"], 2),
            note=f"on {C.datestr(row['price_date'])}"
            if not C._is_absent(row["price_date"])
            else "",
            measured=True,
        )
    with b:
        cap = row["market_cap"]
        C.stat(
            "Market cap",
            "—" if C._is_absent(cap) else f"{float(cap) / 1e9:,.1f} B",
        )
    with c:
        C.stat(
            "P/E (TTM)",
            "n/m" if C._is_absent(row["pe_ttm"]) else C.num(row["pe_ttm"], 1),
            note=C.plain(row["reason_code"]) if C._is_absent(row["pe_ttm"]) else "",
        )
    with d:
        C.stat("Earnings yield", C.num(row["earnings_yield"], 4))

    lag = row["price_lag_days"]
    if not C._is_absent(lag):
        st.markdown(
            f'<div class="stat-note">Price taken {int(lag)} day(s) before the '
            f"fiscal period end {C.datestr(row['period_end_date'])}; results were "
            f"published {C.datestr(row['publish_date'])}. The price is what the "
            f"company was worth "
            f"when its year closed, not what the market could yet know.</div>",
            unsafe_allow_html=True,
        )


def _render_provenance() -> None:
    row = st.session_state.get("_provenance")
    if row is None:
        return
    C.eyebrow("Provenance")
    st.markdown(
        f'<div class="assay-panel"><div class="led-formula">'
        f"scorer&nbsp;&nbsp;{html.escape(str(row['scorer_name']))} "
        f"v{html.escape(str(row['scorer_version']))}<br>"
        f"config_hash&nbsp;&nbsp;{html.escape(str(row['config_hash']))}<br>"
        f"pipeline_version&nbsp;&nbsp;{html.escape(str(row['pipeline_version']))}<br>"
        f"computed_at&nbsp;&nbsp;{html.escape(str(row['computed_at']))}"
        f"</div></div>",
        unsafe_allow_html=True,
    )


def render(warehouse_path, as_of_year: int, tickers: list[str]) -> None:
    """Draw the drilldown for the selected company."""
    current = st.session_state.get("ticker") or (tickers[0] if tickers else None)
    with st.sidebar:
        C.eyebrow("Company")
        if current in tickers:
            index = tickers.index(current)
        else:
            index = 0
        picked = st.selectbox("Ticker", tickers, index=index)
        st.session_state["ticker"] = picked

    ticker = st.session_state["ticker"]
    if not _render_header(warehouse_path, ticker, as_of_year):
        return
    _render_components(warehouse_path, ticker, as_of_year)
    _render_valuation(warehouse_path, ticker, as_of_year)
    _render_criteria(warehouse_path, ticker, as_of_year)
    _render_trends(warehouse_path, ticker)
    _render_provenance()
