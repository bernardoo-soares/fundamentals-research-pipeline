"""Contract tests for the declared cross-era field semantics."""

from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.field_era_semantics import (
    DEFAULT_MIN_AGREEMENT_RATE,
    FIELD_ERA_SEMANTICS,
    Basis,
    EraSource,
    FamilyAgreementThreshold,
    FieldEraSemantics,
    Unit,
    declared_fields,
    semantics_for,
    validate_field_era_semantics,
)
from fundamentals_pipeline.contracts.source_families import (
    POOLED_FAMILY,
    SourceFamily,
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


def test_oiadpq_is_declared_non_equivalent_with_evidence():
    """oiadpq is a per-company classification boundary, not a remapping error.

    Declaring it equivalent produced a CONTRADICTION at 42.2% measured
    agreement. Recorded so a future reader does not retry the remapping.
    """
    declaration = semantics_for("oiadpq")
    assert declaration.eras_equivalent is False
    assert declaration.divergence_note, "non-equivalent requires a note"
    assert "0.474" in declaration.divergence_note, (
        "the note must record the candidate ceiling that rules out a remap"
    )


def _family_entry(*overrides, eras_equivalent=True):
    """A minimal declaration carrying the given per-family overrides."""
    return FieldEraSemantics(
        field="f",
        legacy=_source(),
        simfin=_source(),
        eras_equivalent=eras_equivalent,
        divergence_note="" if eras_equivalent else "declared divergent",
        family_thresholds=tuple(overrides),
    )


def test_pooled_family_resolves_to_the_field_level_rate():
    """The pooled row must be unaffected by any per-family override.

    Enforcement would otherwise change pooled verdicts as a side effect, which
    would make this slice's blast radius unmeasurable.
    """
    entry = _family_entry(
        FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.50, "measured")
    )
    assert entry.min_agreement_rate_for(POOLED_FAMILY) == entry.min_agreement_rate
    for declaration in FIELD_ERA_SEMANTICS:
        assert (
            declaration.min_agreement_rate_for(POOLED_FAMILY)
            == declaration.min_agreement_rate
        )


def test_override_applies_only_to_its_own_family():
    entry = _family_entry(
        FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.50, "measured")
    )
    assert entry.min_agreement_rate_for("insurance") == 0.50
    assert entry.min_agreement_rate_for("banks") == entry.min_agreement_rate
    assert entry.min_agreement_rate_for("general") == entry.min_agreement_rate


def test_family_override_requires_a_justification():
    """A per-family relaxation must carry its own measured evidence.

    Reusing the field-level threshold_justification is how the refuted pooled
    'median is exactly 0.0000' claim came to cover the banks family (S4.7).
    """
    entry = _family_entry(FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.50, ""))
    with pytest.raises(ValueError, match="justification"):
        entry.validate()


def test_duplicate_family_override_is_rejected():
    entry = _family_entry(
        FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.50, "a"),
        FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.60, "b"),
    )
    with pytest.raises(ValueError, match="duplicate"):
        entry.validate()


@pytest.mark.parametrize("rate", [0.0, -0.1, 1.5])
def test_out_of_range_family_override_is_rejected(rate):
    """A rate of 0 would pass unconditionally; above 1 could never pass."""
    entry = _family_entry(
        FamilyAgreementThreshold(SourceFamily.INSURANCE, rate, "measured")
    )
    with pytest.raises(ValueError, match="out of range"):
        entry.validate()


def test_override_for_the_pooled_aggregate_is_rejected():
    """`min_agreement_rate` is the control for the pooled row."""
    entry = _family_entry(FamilyAgreementThreshold(POOLED_FAMILY, 0.50, "measured"))
    with pytest.raises(ValueError, match=POOLED_FAMILY):
        entry.validate()


def test_override_on_a_non_equivalent_field_is_rejected_as_inert():
    """A non-equivalent field verdicts `divergent_declared` regardless of rate.

    An override there could never fire, so accepting it would leave a dead
    declaration that reads as a live guard.
    """
    entry = _family_entry(
        FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.50, "measured"),
        eras_equivalent=False,
    )
    with pytest.raises(ValueError, match="inert"):
        entry.validate()


def test_valid_family_override_passes():
    _family_entry(
        FamilyAgreementThreshold(SourceFamily.INSURANCE, 0.50, "measured")
    ).validate()


def test_saleq_insurance_threshold_is_declared_with_hand_verified_evidence():
    """The one declaration that enforceable per-family verdicts forced.

    Insurance measures 0.627 against the field-level 0.80. It is declared rather
    than nulled because SimFin holds the as-reported figure: AFL FY2023 SimFin
    revenue sums to 18,700 against Aflac's published $18.7B, while Compustat
    saleq sums to 17,729. The justification must carry that hand-verified
    evidence and the disclosed net_margin consequence, not merely a number.
    """
    entry = semantics_for("saleq")
    overrides = {str(o.family): o for o in entry.family_thresholds}
    assert set(overrides) == {"insurance"}
    insurance = overrides["insurance"]
    assert insurance.min_agreement_rate == 0.50
    assert entry.min_agreement_rate_for("insurance") == 0.50
    assert entry.min_agreement_rate_for("banks") == 0.80
    assert "18,700" in insurance.justification, "must pin the published figure"
    assert "17,729" in insurance.justification, "must pin the Compustat figure"
    assert "IRREDUCIBLE" in insurance.justification
    assert "net_margin" in insurance.justification, "level shift must be disclosed"


def test_saleq_field_justification_retracts_the_no_verdict_claim():
    """The field-level prose predates enforceable per-family verdicts.

    It asserted that a sub-threshold family 'raises nothing', which described
    the masking defect this slice closes. Leaving it uncorrected would document
    a guard as absent when it is now live (S4.7).
    """
    justification = semantics_for("saleq").threshold_justification
    assert "SUPERSEDED 2026-07-26" in justification
    assert "no longer true" in justification


def test_saleq_justification_does_not_make_the_refuted_pooled_claim():
    """The 'median relative difference is exactly 0.0000' claim is pooled.

    True for the general family, false for banks (0.5328). The per-family audit
    refuted it, so the justification must carry the correction rather than
    present the pooled figure as the whole picture (S4.7).
    """
    justification = semantics_for("saleq").threshold_justification
    assert "CORRECTED 2026-07-26" in justification
    assert "0.5328" in justification, "must record the measured banks median"
    assert "nulled for the banks family" in justification
