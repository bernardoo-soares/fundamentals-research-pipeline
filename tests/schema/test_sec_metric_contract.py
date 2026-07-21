from __future__ import annotations

from pathlib import Path

import pytest

from fundamentals_pipeline.contracts.sec_metric_mapping_schema import (
    ALLOWED_FORMS,
    COMPUTE_ONLY_FIELDS,
    FETCH_ONLY_RAW_FIELDS,
    HELPER_FALLBACK_FIELDS,
    REQUIRED_CANONICAL_FIELDS,
    load_sec_metric_contract,
)


def test_mapping_contract_file_exists() -> None:
    path = Path("src/fundamentals_pipeline/contracts/sec_metric_mapping.yml")
    assert path.exists(), "Expected sec metric mapping file to exist."


def test_contract_loads_and_has_version() -> None:
    contract = load_sec_metric_contract()
    assert contract.version
    assert contract.metrics


def test_contract_exactly_matches_required_fields() -> None:
    contract = load_sec_metric_contract()
    assert set(contract.metrics) == REQUIRED_CANONICAL_FIELDS


def test_contract_has_all_fetch_and_helper_fields() -> None:
    contract = load_sec_metric_contract()
    for field in FETCH_ONLY_RAW_FIELDS + HELPER_FALLBACK_FIELDS:
        assert field in contract.metrics


def test_contract_does_not_include_compute_only_fields() -> None:
    contract = load_sec_metric_contract()
    leaked = set(contract.metrics).intersection(COMPUTE_ONLY_FIELDS)
    assert not leaked


def test_all_mappings_use_supported_forms() -> None:
    contract = load_sec_metric_contract()
    for name, mapping in contract.metrics.items():
        invalid = set(mapping.form_priority).difference(ALLOWED_FORMS)
        assert not invalid, f"{name} has invalid forms: {sorted(invalid)}"


def test_ivltq_has_component_fallback() -> None:
    contract = load_sec_metric_contract()
    mapping = contract.metrics["ivltq"]
    assert mapping.transform_rule == "direct_or_sum_components"
    assert mapping.component_tags


def test_helper_fallbacks_reference_existing_helper_fields() -> None:
    contract = load_sec_metric_contract()
    available = set(contract.metrics)
    helper_allowed = set(HELPER_FALLBACK_FIELDS)
    for name, mapping in contract.metrics.items():
        for helper in mapping.helper_fallbacks:
            assert helper in helper_allowed, (
                f"{name} has non-helper fallback field {helper!r}"
            )
            assert helper in available, (
                f"{name} references missing helper fallback {helper!r}"
            )


def test_extended_fallback_tags_present() -> None:
    contract = load_sec_metric_contract()
    assert (
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
        in contract.metrics["oiadpq"].tag_priority
    )
    assert "us-gaap:InterestExpenseNonoperating" in contract.metrics["xintq"].tag_priority
    assert "us-gaap:CommercialPaper" in contract.metrics["dlcq"].tag_priority
    assert "us-gaap:SeniorNotes" in contract.metrics["dlttq"].tag_priority
    assert "us-gaap:TreasuryStockCommonValue" in contract.metrics["tstkq"].tag_priority
    assert "us-gaap:StockRepurchasedDuringPeriodValue" in contract.metrics["prstkcq"].tag_priority
    assert "us-gaap:DividendsCommonStockCash" in contract.metrics["dvpq"].tag_priority


def test_failing_when_required_field_missing(tmp_path: Path) -> None:
    bad_contract = tmp_path / "sec_metric_mapping.yml"
    bad_contract.write_text(
        "version: '1.0.0'\n"
        "description: 'bad'\n"
        "metrics:\n"
        "  saleq:\n"
        "    fact_type: duration\n"
        "    unit_priority: ['USD']\n"
        "    form_priority: ['10-Q', '10-K']\n"
        "    tag_priority: ['us-gaap:Revenues']\n"
        "    transform_rule: q4_extract\n"
        "    quality_tier: primary\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing canonical field"):
        load_sec_metric_contract(path=bad_contract)
