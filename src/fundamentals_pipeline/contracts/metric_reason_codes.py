"""Shared closed set of metric reason codes and the value/reason invariant.

Used by both Stage 2 grains (metrics_trend and metrics_quarterly). Extracted so
the value-XOR-reason rule and the reason-code vocabulary live in exactly one
place (AGENTS.md S2.6).
"""

from __future__ import annotations


class ReasonCode:
    """Closed set of reason codes (Buffett platform spec section 6.3)."""

    MISSING_INPUT = "missing_input"
    INCOMPLETE_YEAR = "incomplete_year"
    NEGATIVE_BASE = "negative_base"
    ZERO_DENOMINATOR = "zero_denominator"
    NOT_APPLICABLE_SECTOR = "not_applicable_sector"
    INSUFFICIENT_HISTORY = "insufficient_history"
    TSTK_UNAVAILABLE = "tstk_unavailable"
    MIXED_ERA_WINDOW = "mixed_era_window"
    ERA_NOT_SUPPORTED = "era_not_supported"
    # Legacy-era gross profit assumes the filer placed ALL depreciation inside
    # cost of revenue. Measured 2026-07-28: true for ~34% of filers, while ~26%
    # present D&A outside it and are understated by a median 13.46pp. Compustat
    # normalises the distinction away, so it is unrecoverable in that era -- the
    # value is real but carries a known one-directional bias, which is a quality
    # flag rather than a reason code.
    DA_ALLOCATION_ASSUMED = "da_allocation_assumed"


REASON_CODES: frozenset[str] = frozenset(
    {
        ReasonCode.MISSING_INPUT,
        ReasonCode.INCOMPLETE_YEAR,
        ReasonCode.NEGATIVE_BASE,
        ReasonCode.ZERO_DENOMINATOR,
        ReasonCode.NOT_APPLICABLE_SECTOR,
        ReasonCode.INSUFFICIENT_HISTORY,
        ReasonCode.TSTK_UNAVAILABLE,
        ReasonCode.MIXED_ERA_WINDOW,
        ReasonCode.ERA_NOT_SUPPORTED,
        ReasonCode.DA_ALLOCATION_ASSUMED,
    }
)


def validate_value_xor_reason(
    value: float | None, reason_code: str | None
) -> None:
    """Enforce exactly one of value / reason_code, and a known reason_code.

    This is the S4.5 invariant expressed once. A row carries either a value or
    a reason for its absence, never both and never neither.
    """
    if (value is None) == (reason_code is None):
        raise ValueError("Exactly one of value / reason_code must be set.")
    if reason_code is not None and reason_code not in REASON_CODES:
        raise ValueError(f"Unknown reason_code: {reason_code!r}")
