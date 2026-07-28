"""Reject values that are impossible under any accounting treatment.

Providers occasionally publish a negative figure for a quantity that cannot be
negative -- SimFin derives some Q4 values as a residual, and a fiscal-calendar
mismatch turns that residual negative. Measured on the FY2023 corpus: eight
tickers carried negative Q4 revenue, including Marriott at -11,318 and Dollar
Tree at -5,183, and for every one of them the four quarters no longer summed
to the true annual -- Dollar Tree's revenue read 16,781 against 30,604.

A halved revenue figure is far worse than a missing one, so such values are
nulled and recorded rather than propagated. Annualization already requires all
four quarters, so nulling one quarter correctly nulls that fiscal year instead
of publishing a wrong total.

Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..contracts.stage1_fundamentals_schema import NON_NEGATIVE_FIELDS

VIOLATION_COLUMNS: tuple[str, ...] = (
    "ticker",
    "year",
    "quarter",
    "field_name",
    "observed_value",
    "rule",
    "action",
)

_NEGATIVE_RULE = "non_negative"
_SHARE_SCALE_RULE = "share_count_scale"
_ACTION = "nulled"

# Basic and diluted share counts describe the same company in the same unit, so
# their ratio is bounded by ordinary dilution -- a few percent, never an order
# of magnitude. Below this ratio the pair cannot both be right.
#
# Measured 2026-07-28: SimFin publishes MCD FY2024 Q3/Q4 `Shares (Basic)` as
# 718 against a diluted 722,000,000 -- six orders of magnitude out, while Q1/Q2
# of the same year read 722,000,000. The vendor dropped the scale on two
# quarters. Carried through, it made derived EPS 2,809,192 per share and a
# trailing P/E of 0.0, which put McDonald's at the top of a cheapest-stock
# screen. That is the exact failure the Prime Directive exists to prevent, and
# it reached a headline table before this gate existed.
#
# 0.5 is far looser than any real dilution (the largest legitimate basic/diluted
# gaps in the corpus are a few percent) and far tighter than the 1e-6 defect, so
# it separates the two without sitting near either.
MIN_BASIC_TO_DILUTED_SHARE_RATIO = 0.5

_BASIC_SHARES_FIELD = "cshoq"
_DILUTED_SHARES_FIELD = "cshfdq"

# In the SimFin era `epspxq` has no as-reported source and is DERIVED as
# Net Income (Common) / Shares (Basic) -- the very field the scale rule
# rejects. So a bad basic share count poisons the derived EPS too, and nulling
# only the share count would leave the corrupted per-share figure in place.
# Nulled together, and only in that era: legacy `epspxq` is as-reported and is
# not a function of `cshoq`, so it must not be touched here.
_DERIVED_EPS_FIELD = "epspxq"
_DERIVED_EPS_ERA = "simfin"
_SOURCE_ERA_FIELD = "source_era"


@dataclass(frozen=True)
class PlausibilityResult:
    """A frame with impossible values removed, plus what was removed."""

    frame: pd.DataFrame
    violations: pd.DataFrame
    nulled_count: int = field(default=0)


def apply_non_negative_gate(
    frame: pd.DataFrame,
    *,
    fields: tuple[str, ...] = NON_NEGATIVE_FIELDS,
) -> PlausibilityResult:
    """Null negative values in fields that cannot be negative.

    Returns the cleaned frame alongside one violation row per nulled value, so
    the rejection is auditable rather than silent.
    """
    cleaned = frame.copy()
    records: list[dict[str, object]] = []

    for name in fields:
        if name not in cleaned.columns:
            continue
        values = pd.to_numeric(cleaned[name], errors="coerce")
        offending = values < 0
        if not bool(offending.any()):
            continue
        for row in cleaned.loc[offending].itertuples():
            records.append(
                {
                    "ticker": getattr(row, "ticker", None),
                    "year": getattr(row, "year", None),
                    "quarter": getattr(row, "quarter", None),
                    "field_name": name,
                    "observed_value": float(values.loc[row.Index]),
                    "rule": _NEGATIVE_RULE,
                    "action": _ACTION,
                }
            )
        cleaned.loc[offending, name] = pd.NA

    violations = pd.DataFrame(records, columns=list(VIOLATION_COLUMNS))
    if not violations.empty:
        violations = violations.sort_values(
            ["ticker", "year", "quarter", "field_name"]
        ).reset_index(drop=True)
    return PlausibilityResult(
        frame=cleaned, violations=violations, nulled_count=len(violations)
    )


def apply_share_scale_gate(
    frame: pd.DataFrame,
    *,
    min_ratio: float = MIN_BASIC_TO_DILUTED_SHARE_RATIO,
) -> PlausibilityResult:
    """Null a basic share count that cannot share a unit with its diluted pair.

    Only the basic count is nulled: the diluted figure is the one that stayed
    correct in every observed case, and nulling both would discard a good value
    to punish a bad one. A null `cshoq` yields a reasoned-null downstream, which
    is the honest outcome -- unlike the alternative, which was a per-share
    figure six orders of magnitude wrong reaching a valuation screen.
    """
    cleaned = frame.copy()
    records: list[dict[str, object]] = []

    if {_BASIC_SHARES_FIELD, _DILUTED_SHARES_FIELD} <= set(cleaned.columns):
        basic = pd.to_numeric(cleaned[_BASIC_SHARES_FIELD], errors="coerce")
        diluted = pd.to_numeric(cleaned[_DILUTED_SHARES_FIELD], errors="coerce")
        # Both must be present and positive for the ratio to mean anything; a
        # missing counterpart is a coverage gap, not a scale defect.
        comparable = basic.notna() & diluted.notna() & (basic > 0) & (diluted > 0)
        offending = comparable & ((basic / diluted) < min_ratio)
        for row in cleaned.loc[offending].itertuples():
            records.append(
                {
                    "ticker": getattr(row, "ticker", None),
                    "year": getattr(row, "year", None),
                    "quarter": getattr(row, "quarter", None),
                    "field_name": _BASIC_SHARES_FIELD,
                    "observed_value": float(basic.loc[row.Index]),
                    "rule": _SHARE_SCALE_RULE,
                    "action": _ACTION,
                }
            )
        cleaned.loc[offending, _BASIC_SHARES_FIELD] = pd.NA

        # The derived per-share figure computed from that same share count.
        if {_DERIVED_EPS_FIELD, _SOURCE_ERA_FIELD} <= set(cleaned.columns):
            derived = offending & (cleaned[_SOURCE_ERA_FIELD] == _DERIVED_EPS_ERA)
            eps_values = pd.to_numeric(cleaned[_DERIVED_EPS_FIELD], errors="coerce")
            derived = derived & eps_values.notna()
            for row in cleaned.loc[derived].itertuples():
                records.append(
                    {
                        "ticker": getattr(row, "ticker", None),
                        "year": getattr(row, "year", None),
                        "quarter": getattr(row, "quarter", None),
                        "field_name": _DERIVED_EPS_FIELD,
                        "observed_value": float(eps_values.loc[row.Index]),
                        "rule": _SHARE_SCALE_RULE,
                        "action": _ACTION,
                    }
                )
            cleaned.loc[derived, _DERIVED_EPS_FIELD] = pd.NA

    violations = pd.DataFrame(records, columns=list(VIOLATION_COLUMNS))
    if not violations.empty:
        violations = violations.sort_values(
            ["ticker", "year", "quarter", "field_name"]
        ).reset_index(drop=True)
    return PlausibilityResult(
        frame=cleaned, violations=violations, nulled_count=len(violations)
    )
