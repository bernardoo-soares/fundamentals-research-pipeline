"""Reusable render helpers for the console.

Pure string builders plus thin Streamlit wrappers. Nothing here computes a
financial quantity: every number arrives already derived, versioned and
reason-coded from the warehouse (platform spec section 7.2). The only
arithmetic is turning a ratio into a CSS percentage.
"""

from __future__ import annotations

import html
import math
from typing import Any

import streamlit as st

# The composite scale, so a bar's width is a share of the possible maximum
# rather than of whatever the current page happens to top out at.
COMPOSITE_MAX = 100.0

# Flags rare enough to be worth the eye's attention. Measured 2026-07-29 on
# FY2024: `unreliable_input` fires on 96.6% of rows and `era_limited` on 96.1%,
# so those two are shown plainly; anything below this share is emphasised.
RARE_FLAG_MAX_SHARE = 0.50

# Plain-language readings of the closed reason-code and flag vocabularies. The
# UI never invents wording for a code it does not know -- an unrecognised code
# is shown verbatim, which is honest and makes the omission obvious.
PLAIN_WORDS: dict[str, str] = {
    "missing_input": "an input was not reported",
    "incomplete_year": "the fiscal year is missing quarters",
    "negative_base": "the starting value is zero or negative, so growth is undefined",
    "zero_denominator": "the denominator is zero",
    "not_applicable_sector": "the rule does not apply to this kind of business",
    "insufficient_history": "not enough years of history in the window",
    "tstk_unavailable": "computed without the treasury-stock add-back",
    "mixed_era_window": "the window crosses the data-provider boundary, "
    "where the two providers do not measure this the same way",
    "era_not_supported": "not defined in this row's data provider era",
    "da_allocation_assumed": "assumes all depreciation sits inside cost of "
    "revenue; true for ~34% of filers, understated for ~26%",
    "cross_era_window": "the window crosses the provider boundary; the "
    "divergence was measured as mild enough to publish",
    "eps_basis_unverified": "reaches into the SimFin era, which publishes no "
    "split adjustment factor, so the share basis cannot be verified",
    "price_unavailable": "no price for this ticker",
    "shares_unavailable": "share count not reported",
    "eps_unavailable": "earnings not available",
    "non_positive_eps": "earnings are zero or negative, so a P/E is not "
    "meaningful",
    "all_criteria_era_unavailable": "every criterion is undefined in this "
    "row's provider era",
    "low_confidence": "scored on a small share of the criteria",
    "unreliable_input": "at least one input carries a known limitation",
    "era_limited": "at least one criterion is unavailable in this provider era",
    "stale": "this ticker stopped reporting before the latest quarter",
}


def plain(code: str | None) -> str:
    """Return a plain-language reading of a reason code or flag."""
    if not code:
        return ""
    return PLAIN_WORDS.get(code, code)


def _is_absent(value: Any) -> bool:
    """True when a value is null in any of the shapes DuckDB/pandas return."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def num(value: Any, places: int = 2, *, absent: str = "—") -> str:
    """Format a number for display, or the absence mark when it is null.

    `absent` is an em dash rather than 0 or "n/a": a dash cannot be mistaken
    for a measurement, which is the whole point (S4.5).
    """
    if _is_absent(value):
        return absent
    return f"{float(value):,.{places}f}"


def datestr(value: Any) -> str:
    """Format a date without a midnight timestamp.

    `2025-01-31 00:00:00` implies a time that was never measured; these are
    fiscal dates, not instants.
    """
    if _is_absent(value):
        return "—"
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def evidence_bar(composite: Any, coverage: Any) -> str:
    """The signature element: score as length, measured share as solid gold.

    The pewter hatch is the part of the score inferred from an incomplete
    scorecard. A high score on thin evidence looks hollow beside a lower score
    that is solid, so the eye ranks by gold length -- which is the honest
    ordering -- without being told to.
    """
    if _is_absent(composite):
        return (
            '<div class="ev-wrap"><div class="ev-track"></div>'
            '<span class="ev-score">—</span></div>'
        )
    total = max(0.0, min(float(composite), COMPOSITE_MAX))
    ratio = 0.0 if _is_absent(coverage) else max(0.0, min(float(coverage), 1.0))
    total_pct = total / COMPOSITE_MAX * 100.0
    solid_pct = total_pct * ratio
    seam = (
        f'<div class="ev-seam" style="left:{solid_pct:.2f}%"></div>'
        if ratio < 1.0
        else ""
    )
    return (
        '<div class="ev-wrap">'
        '<div class="ev-track">'
        f'<div class="ev-total" style="width:{total_pct:.2f}%"></div>'
        f'<div class="ev-solid" style="width:{solid_pct:.2f}%"></div>'
        f"{seam}"
        "</div>"
        f'<span class="ev-score">{total:.1f}</span>'
        "</div>"
    )


def flags(badge_string: Any, *, rare: frozenset[str] = frozenset()) -> str:
    """Render a comma-separated badge string as quiet mono annotations.

    Not coloured chips. A warning that fires on 96% of rows is read as
    decoration, so emphasis is reserved for the codes in `rare`.
    """
    if _is_absent(badge_string) or not str(badge_string).strip():
        return ""
    out = []
    for badge in str(badge_string).split(","):
        name = badge.strip()
        if not name:
            continue
        css = "flag rare" if name in rare else "flag"
        out.append(
            f'<span class="{css}" title="{html.escape(plain(name))}">'
            f"{html.escape(name)}</span>"
        )
    return "".join(out)


def verdict(value: Any) -> str:
    """Render a checklist verdict in the palette's semantics."""
    if _is_absent(value):
        return '<span class="verdict-na">n/a</span>'
    text = str(value).lower()
    if text == "pass":
        return '<span class="verdict-pass">pass</span>'
    if text == "fail":
        return '<span class="verdict-fail">fail</span>'
    return f'<span class="verdict-na">{html.escape(text)}</span>'


def eyebrow(text: str) -> None:
    """A section label: the only titling device in the console."""
    st.markdown(
        f'<div class="assay-eyebrow">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def stat(label: str, value: str, *, note: str = "", measured: bool = False) -> None:
    """One headline figure. `measured` grants it the gold, per the palette rule."""
    absent = value.strip() in {"—", ""}
    cls = "stat-value absent" if absent else (
        "stat-value measured" if measured else "stat-value"
    )
    note_html = (
        f'<div class="stat-note">{html.escape(note)}</div>' if note else ""
    )
    st.markdown(
        f'<div class="assay-panel">'
        f'<div class="stat-label">{html.escape(label)}</div>'
        f'<div class="{cls}">{html.escape(value)}</div>'
        f"{note_html}</div>",
        unsafe_allow_html=True,
    )


def absent_block(title: str, reason: str) -> None:
    """State an absence instead of drawing an empty chart (design C6)."""
    st.markdown(
        f'<div class="assay-absent"><b>{html.escape(title)}</b><br>'
        f"{html.escape(reason)}</div>",
        unsafe_allow_html=True,
    )
