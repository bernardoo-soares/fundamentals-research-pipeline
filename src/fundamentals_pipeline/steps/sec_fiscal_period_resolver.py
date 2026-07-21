"""Fiscal quarter resolution helpers for SEC period-end observations.

This module maps SEC fact `period_end` dates onto fiscal year / quarter values
using each company's fiscal year-end anchor (`MMDD`) from SEC submissions.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FiscalResolution:
    """Resolved fiscal period assignment for one period-end timestamp."""

    fyearq: int
    fqtr: int
    fiscal_anchor_end: pd.Timestamp
    day_delta: int


def normalize_fiscal_year_end_mmdd(value: str | None) -> str | None:
    """Validate and normalize SEC fiscal year-end string to 4-digit `MMDD`.

    Returns:
        Normalized `MMDD` when valid; otherwise `None`.
    """
    text = str(value or "").strip()
    if len(text) != 4 or not text.isdigit():
        return None

    month = int(text[:2])
    day = int(text[2:])
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return f"{month:02d}{day:02d}"


def _safe_date(year: int, month: int, day: int) -> pd.Timestamp:
    """Construct a calendar-valid date for year/month/day.

    SEC fiscal anchors can include `MMDD` that are invalid in leap-sensitive
    years (for example `0229`). This helper clamps day to month-end.
    """
    last_day = calendar.monthrange(year, month)[1]
    return pd.Timestamp(year=year, month=month, day=min(day, last_day))


def quarter_end_anchors(
    *,
    fyearq: int,
    fiscal_year_end_mmdd: str,
) -> dict[int, pd.Timestamp]:
    """Build theoretical fiscal quarter-end anchors for one fiscal year.

    Args:
        fyearq: Fiscal year label for Q4 anchor.
        fiscal_year_end_mmdd: Fiscal year-end in `MMDD`.

    Returns:
        Mapping `{1..4 -> quarter_end_timestamp}`.
    """
    month = int(fiscal_year_end_mmdd[:2])
    day = int(fiscal_year_end_mmdd[2:])
    q4 = _safe_date(fyearq, month, day).normalize()
    return {
        1: (q4 - pd.DateOffset(months=9)).normalize(),
        2: (q4 - pd.DateOffset(months=6)).normalize(),
        3: (q4 - pd.DateOffset(months=3)).normalize(),
        4: q4,
    }


def resolve_fiscal_quarter(
    *,
    period_end: pd.Timestamp,
    fiscal_year_end_mmdd: str,
    start_year: int,
    end_year: int,
    max_day_delta: int = 30,
) -> FiscalResolution | None:
    """Resolve fiscal year/quarter from period end and fiscal-year anchor.

    Resolution scans quarter-end anchors for fiscal years in `[start_year, end_year]`
    and picks the nearest anchor. If nearest anchor is farther than
    `max_day_delta` days, resolution is rejected.
    """
    if pd.isna(period_end):
        return None

    mmdd = normalize_fiscal_year_end_mmdd(fiscal_year_end_mmdd)
    if mmdd is None:
        return None

    normalized_period_end = period_end.normalize()
    best: tuple[int, int, int, pd.Timestamp] | None = None
    for fyearq in range(start_year, end_year + 1):
        for fqtr, anchor in quarter_end_anchors(
            fyearq=fyearq,
            fiscal_year_end_mmdd=mmdd,
        ).items():
            delta = abs((normalized_period_end - anchor).days)
            candidate = (delta, fyearq, fqtr, anchor)
            if best is None or candidate < best:
                best = candidate

    if best is None:
        return None

    day_delta, fyearq, fqtr, anchor = best
    if day_delta > max_day_delta:
        return None

    return FiscalResolution(
        fyearq=int(fyearq),
        fqtr=int(fqtr),
        fiscal_anchor_end=anchor,
        day_delta=int(day_delta),
    )

