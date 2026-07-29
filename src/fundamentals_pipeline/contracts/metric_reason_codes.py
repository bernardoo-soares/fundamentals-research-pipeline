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
    # A window whose inputs straddle the provider boundary, for a field whose
    # cross-era divergence was MEASURED as mild enough to publish rather than
    # null. Distinct from MIXED_ERA_WINDOW, which is a reason code and carries
    # no value: this one accompanies a real value that is known to be slightly
    # less trustworthy. The distinction matters downstream -- a nulled row
    # cannot be ranked, a flagged row can be ranked and captioned.
    CROSS_ERA_WINDOW = "cross_era_window"
    # A per-share window that reaches into the SimFin era, where no split
    # adjustment factor exists. The legacy era is normalised by `ajexq`; SimFin
    # publishes no equivalent and restates share counts inconsistently
    # (measured 2026-07-29: 15 of 20 boundary splitters agree with the
    # ajexq-adjusted basis, 5 do not). The value is usually right and cannot be
    # verified to be.
    EPS_BASIS_UNVERIFIED = "eps_basis_unverified"


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
        ReasonCode.CROSS_ERA_WINDOW,
        ReasonCode.EPS_BASIS_UNVERIFIED,
    }
)


# Advisory flags that co-exist with a PRESENT value. Distinct from reason
# codes, which explain a null: a flagged row still carries a real number, it is
# simply one whose known limitation must travel with it to the UI.
#
# Shared by both Stage 2 grains. Declared here rather than in either grain's
# schema so the vocabulary cannot drift between them (AGENTS.md S2.6).
QUALITY_FLAGS: frozenset[str] = frozenset(
    {
        ReasonCode.TSTK_UNAVAILABLE,
        ReasonCode.DA_ALLOCATION_ASSUMED,
        ReasonCode.CROSS_ERA_WINDOW,
        ReasonCode.EPS_BASIS_UNVERIFIED,
    }
)


def validate_quality_flag(value: float | None, quality_flag: str | None) -> None:
    """Enforce that a quality flag accompanies a value and is a known flag.

    A flag on a null row would be meaningless -- the reason code already
    explains the absence -- and an unknown flag would reach the UI as an
    uninterpretable string.
    """
    if quality_flag is None:
        return
    if value is None:
        raise ValueError("quality_flag requires a non-null value.")
    if quality_flag not in QUALITY_FLAGS:
        raise ValueError(f"Unknown quality_flag: {quality_flag!r}")


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


# Reason codes that mean "this measurement does not exist in this provider era",
# as opposed to "this company is missing data". The distinction matters at the
# score grain: an era-guarded criterion is absent for EVERY company in the era,
# so counting it as a per-company gap blames the company for a provider gap.
ERA_STRUCTURAL_REASON_CODES: frozenset[str] = frozenset(
    {ReasonCode.ERA_NOT_SUPPORTED, ReasonCode.MIXED_ERA_WINDOW}
)
