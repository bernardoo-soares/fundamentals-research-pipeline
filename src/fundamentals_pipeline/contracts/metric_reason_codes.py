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
