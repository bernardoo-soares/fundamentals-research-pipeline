"""Contract tests for the declared cross-era field semantics."""

from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.field_era_semantics import (
    DEFAULT_MIN_AGREEMENT_RATE,
    FIELD_ERA_SEMANTICS,
    Basis,
    EraSource,
    FieldEraSemantics,
    Unit,
    declared_fields,
    semantics_for,
    validate_field_era_semantics,
)


def _source(unit=Unit.USD_MILLIONS, basis=Basis.DISCRETE_QUARTER):
    return EraSource(column="x", meaning="m", unit=unit, basis=basis)


def test_equivalent_requires_matching_unit():
    """A unit mismatch under eras_equivalent=True is the prstkcq defect shape."""
    entry = FieldEraSemantics(
        field="f",
        legacy=_source(unit=Unit.SHARES_MILLIONS),
        simfin=_source(unit=Unit.USD_MILLIONS),
        eras_equivalent=True,
    )
    with pytest.raises(ValueError, match="unit"):
        entry.validate()


def test_equivalent_requires_matching_basis():
    entry = FieldEraSemantics(
        field="f",
        legacy=_source(basis=Basis.YEAR_TO_DATE),
        simfin=_source(basis=Basis.DISCRETE_QUARTER),
        eras_equivalent=True,
    )
    with pytest.raises(ValueError, match="basis"):
        entry.validate()


def test_equivalent_requires_both_eras_present():
    entry = FieldEraSemantics(
        field="f", legacy=_source(), simfin=None, eras_equivalent=True
    )
    with pytest.raises(ValueError, match="both eras"):
        entry.validate()


def test_divergent_requires_note():
    entry = FieldEraSemantics(
        field="f", legacy=_source(), simfin=_source(), eras_equivalent=False
    )
    with pytest.raises(ValueError, match="divergence_note"):
        entry.validate()


def test_lowered_threshold_requires_justification():
    """Thresholds may never be loosened silently to pass a failing audit."""
    entry = FieldEraSemantics(
        field="f",
        legacy=_source(),
        simfin=_source(),
        eras_equivalent=True,
        min_agreement_rate=0.5,
    )
    with pytest.raises(ValueError, match="threshold_justification"):
        entry.validate()


def test_valid_entry_passes():
    entry = FieldEraSemantics(
        field="f", legacy=_source(), simfin=_source(), eras_equivalent=True
    )
    entry.validate()


def test_registry_is_internally_valid():
    validate_field_era_semantics()


def test_dvy_declares_equivalence_with_measured_justification():
    """dvy's 0.90 threshold is chosen from measurement, not convenience."""
    entry = semantics_for("dvy")
    assert entry.eras_equivalent is True
    assert entry.min_agreement_rate == 0.90
    assert "92.9%" in entry.threshold_justification


def test_dvpq_is_declared_legacy_only():
    entry = semantics_for("dvpq")
    assert entry.simfin is None
    assert entry.eras_equivalent is False
    assert "preferred" in entry.divergence_note.lower()


def test_prstkcq_is_declared_simfin_only():
    entry = semantics_for("prstkcq")
    assert entry.legacy is None
    assert "cshopq" in entry.divergence_note


def test_unknown_field_raises():
    with pytest.raises(KeyError):
        semantics_for("not_a_field")


def test_declared_fields_returns_names():
    assert "dvy" in declared_fields()


def test_taxonomy_boundary_fields_are_declared_not_comparable():
    """ppentq and ivltq cannot be reconciled by remapping.

    ppentq: SimFin's condensed balance sheet draws the PP&E / Other-Long-Term
    boundary differently per company. The aggregate reconciles (ppentq+aoq vs
    SimFin PP&E+OtherLT, 65.7% at median 0.0000) but the split is dispersed
    (ratio p90/p10 = 2.17), so no alternative column fixes it.

    ivltq: SimFin maps three different concepts by family and leaves the
    general-family value null or zero for 67.8% of companies.
    """
    for field in ("ppentq", "ivltq"):
        entry = semantics_for(field)
        assert entry.eras_equivalent is False
        assert "NOT cross-era comparable" in entry.divergence_note


def test_declared_divergences_never_lower_the_threshold():
    """Divergence is recorded, never hidden by loosening a bound."""
    for entry in FIELD_ERA_SEMANTICS:
        if not entry.eras_equivalent:
            assert entry.min_agreement_rate == DEFAULT_MIN_AGREEMENT_RATE


def test_cogsq_divergence_warns_about_the_gross_margin_threshold():
    """cogsq feeds five planned metrics, one with a hard >40% threshold.

    13.6% of companies flip across that line by provider alone (27.7% of
    those between 30% and 50%), so the declaration must carry the scoring
    consequence, not just the measurement.
    """
    entry = semantics_for("cogsq")
    assert entry.eras_equivalent is False
    assert "single era" in entry.divergence_note
    assert "40%" in entry.divergence_note
