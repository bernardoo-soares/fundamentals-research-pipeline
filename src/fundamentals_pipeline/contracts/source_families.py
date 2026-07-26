"""Declared SimFin statement-family vocabulary.

Compute-free. SimFin publishes a separate statement set per business family, and
a canonical field can mean a structurally different thing in each: `saleq` is
total revenue for the general family but a narrower construction for banks, and
`oiadpq` is drawn after a different cost line for insurance. Two remediation
slices (PRs #9 and #10) were spent on fields that published one family's
aggregate as if it were another's.

These names are therefore logic-bearing values, not incidental strings, and are
declared once here (AGENTS.md S1.1) rather than repeated as literals in the
builder that emits them and the audit that groups by them.

`SourceFamily` is a `StrEnum`, so a member compares and serialises identically
to the bare literal it replaces; substituting it changes no published value.
"""

from __future__ import annotations

from enum import StrEnum


class SourceFamily(StrEnum):
    """The SimFin statement family that served a row."""

    GENERAL = "general"
    BANKS = "banks"
    INSURANCE = "insurance"


# Value of `source_family` on the reconciliation row that spans every family.
# Deliberately outside `SourceFamily`: it is an aggregate, not a family, and
# admitting it as a member would let it be declared as one (for example as the
# target of a per-family threshold override, where the field-level rate is the
# correct control).
POOLED_FAMILY = "all"

# Column carrying the family on staged Stage 1 frames and reconciliation reports.
SOURCE_FAMILY_COLUMN = "source_family"


def declared_families() -> frozenset[str]:
    """Return the set of declared family names, excluding `POOLED_FAMILY`."""
    return frozenset(str(family) for family in SourceFamily)
