"""Contract tests for the declared SimFin statement-family vocabulary."""

from __future__ import annotations

from fundamentals_pipeline.contracts.source_families import (
    POOLED_FAMILY,
    SOURCE_FAMILY_COLUMN,
    SourceFamily,
    declared_families,
)
from fundamentals_pipeline.steps import cross_era_semantic_audit


def test_members_are_byte_identical_to_the_literals_they_replace() -> None:
    """Substituting the enum must not change any emitted family string.

    The builder writes `source_family` into the staged CSV and the audit groups
    on it. If a member did not compare equal to its literal, the migration
    would silently change published output.
    """
    assert SourceFamily.GENERAL == "general"
    assert SourceFamily.BANKS == "banks"
    assert SourceFamily.INSURANCE == "insurance"
    assert str(SourceFamily.INSURANCE) == "insurance"
    assert f"{SourceFamily.BANKS}" == "banks"


def test_declared_families_excludes_the_pooled_aggregate() -> None:
    """`POOLED_FAMILY` is an aggregate row, not a family."""
    assert declared_families() == {"general", "banks", "insurance"}
    assert POOLED_FAMILY not in declared_families()


def test_audit_consumes_the_declared_constants() -> None:
    """The audit must not define its own copy of the family constants."""
    assert cross_era_semantic_audit.POOLED_FAMILY is POOLED_FAMILY
    assert cross_era_semantic_audit.SOURCE_FAMILY_COLUMN is SOURCE_FAMILY_COLUMN
