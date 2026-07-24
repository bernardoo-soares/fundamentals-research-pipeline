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
_ACTION = "nulled"


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
