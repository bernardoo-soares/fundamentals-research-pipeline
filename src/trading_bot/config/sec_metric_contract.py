from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


FETCH_ONLY_RAW_FIELDS: tuple[str, ...] = (
    "saleq",
    "niq",
    "oiadpq",
    "xintq",
    "txtq",
    "epspxq",
    "actq",
    "lctq",
    "ppentq",
    "gdwlq",
    "ivltq",
    "atq",
    "ceqq",
    "dlcq",
    "dlttq",
    "req",
    "tstkq",
    "oancfq",
    "prstkcq",
)

HELPER_FALLBACK_FIELDS: tuple[str, ...] = (
    "oancfy",
    "prstkcy",
    "cshopq",
)

REQUIRED_CANONICAL_FIELDS: frozenset[str] = frozenset(
    FETCH_ONLY_RAW_FIELDS + HELPER_FALLBACK_FIELDS
)

COMPUTE_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "Operating_Margin",
        "Net_Profit_Margin",
        "Current_Ratio",
        "ROA",
        "ROE",
        "Debt_to_Equity",
        "Short_Term_Debt",
        "Healthy_Long_Term_Debt",
        "Treasury_Adjusted_Debt_to_Equity",
        "Book_Value",
        "Retained_Earnings_Growth",
        "Share_Repurchases",
        "Revenue_Growth",
        "EPS_Growth",
        "Return_on_Shareholder_Equity",
        "P/E_Ratio",
        "Market_Cap",
        "P/B_Ratio",
        "Dividend_Yield",
        "Earnings_Yield",
    }
)

ALLOWED_FACT_TYPES: frozenset[str] = frozenset({"duration", "instant"})
ALLOWED_TRANSFORM_RULES: frozenset[str] = frozenset(
    {
        "direct",
        "q4_extract",
        "direct_with_annual_fallback",
        "direct_or_sum_components",
    }
)
ALLOWED_QUALITY_TIERS: frozenset[str] = frozenset({"primary", "fallback", "proxy"})
ALLOWED_FORMS: frozenset[str] = frozenset({"10-Q", "10-K"})


@dataclass(frozen=True)
class MetricMapping:
    canonical_name: str
    fact_type: str
    unit_priority: tuple[str, ...]
    form_priority: tuple[str, ...]
    tag_priority: tuple[str, ...]
    transform_rule: str
    quality_tier: str
    helper_fallbacks: tuple[str, ...] = ()
    component_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecMetricContract:
    version: str
    description: str
    metrics: dict[str, MetricMapping]


def _default_contract_path() -> Path:
    return Path(__file__).with_name("sec_metric_map.yml")


def _expect_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a mapping.")
    return value


def _expect_sequence(
    value: Any,
    *,
    context: str,
    min_length: int = 1,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list.")
    if len(value) < min_length:
        raise ValueError(f"{context} must include at least {min_length} item(s).")
    output = tuple(str(item).strip() for item in value if str(item).strip())
    if len(output) < min_length:
        raise ValueError(f"{context} must include non-empty values.")
    return output


def _parse_metric_mapping(name: str, payload: Any) -> MetricMapping:
    data = _expect_mapping(payload, context=f"metrics.{name}")

    required_keys = {
        "fact_type",
        "unit_priority",
        "form_priority",
        "tag_priority",
        "transform_rule",
        "quality_tier",
    }
    missing = sorted(required_keys.difference(data))
    if missing:
        raise ValueError(f"metrics.{name} is missing required key(s): {missing}")

    mapping = MetricMapping(
        canonical_name=name,
        fact_type=str(data["fact_type"]).strip(),
        unit_priority=_expect_sequence(
            data["unit_priority"],
            context=f"metrics.{name}.unit_priority",
        ),
        form_priority=_expect_sequence(
            data["form_priority"],
            context=f"metrics.{name}.form_priority",
        ),
        tag_priority=_expect_sequence(
            data["tag_priority"],
            context=f"metrics.{name}.tag_priority",
        ),
        transform_rule=str(data["transform_rule"]).strip(),
        quality_tier=str(data["quality_tier"]).strip(),
        helper_fallbacks=_expect_sequence(
            data.get("helper_fallbacks", []),
            context=f"metrics.{name}.helper_fallbacks",
            min_length=0,
        ),
        component_tags=_expect_sequence(
            data.get("component_tags", []),
            context=f"metrics.{name}.component_tags",
            min_length=0,
        ),
    )
    return mapping


def _validate_metric_mapping(mapping: MetricMapping) -> None:
    if mapping.fact_type not in ALLOWED_FACT_TYPES:
        raise ValueError(
            f"metrics.{mapping.canonical_name}.fact_type must be one of "
            f"{sorted(ALLOWED_FACT_TYPES)}."
        )
    if mapping.transform_rule not in ALLOWED_TRANSFORM_RULES:
        raise ValueError(
            f"metrics.{mapping.canonical_name}.transform_rule must be one of "
            f"{sorted(ALLOWED_TRANSFORM_RULES)}."
        )
    if mapping.quality_tier not in ALLOWED_QUALITY_TIERS:
        raise ValueError(
            f"metrics.{mapping.canonical_name}.quality_tier must be one of "
            f"{sorted(ALLOWED_QUALITY_TIERS)}."
        )
    unknown_forms = sorted(set(mapping.form_priority).difference(ALLOWED_FORMS))
    if unknown_forms:
        raise ValueError(
            f"metrics.{mapping.canonical_name}.form_priority contains unsupported "
            f"form(s): {unknown_forms}"
        )
    if (
        mapping.transform_rule == "direct_or_sum_components"
        and not mapping.component_tags
    ):
        raise ValueError(
            f"metrics.{mapping.canonical_name}.component_tags is required when "
            "transform_rule is direct_or_sum_components."
        )


def validate_contract(contract: SecMetricContract) -> None:
    names = frozenset(contract.metrics)
    missing = sorted(REQUIRED_CANONICAL_FIELDS.difference(names))
    extra = sorted(names.difference(REQUIRED_CANONICAL_FIELDS))
    if missing:
        raise ValueError(f"Contract is missing canonical field(s): {missing}")
    if extra:
        raise ValueError(f"Contract includes unsupported canonical field(s): {extra}")

    leaked_compute_fields = sorted(names.intersection(COMPUTE_ONLY_FIELDS))
    if leaked_compute_fields:
        raise ValueError(
            "Contract includes compute-only field(s), which is not allowed: "
            f"{leaked_compute_fields}"
        )

    for mapping in contract.metrics.values():
        _validate_metric_mapping(mapping)
        unknown_helpers = sorted(
            set(mapping.helper_fallbacks).difference(HELPER_FALLBACK_FIELDS)
        )
        if unknown_helpers:
            raise ValueError(
                f"metrics.{mapping.canonical_name}.helper_fallbacks has unknown "
                f"helper field(s): {unknown_helpers}"
            )
        missing_helpers = sorted(
            helper for helper in mapping.helper_fallbacks if helper not in names
        )
        if missing_helpers:
            raise ValueError(
                f"metrics.{mapping.canonical_name}.helper_fallbacks references missing "
                f"canonical field(s): {missing_helpers}"
            )


def load_sec_metric_contract(path: str | Path | None = None) -> SecMetricContract:
    mapping_path = Path(path) if path else _default_contract_path()
    raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    root = _expect_mapping(raw, context="root")

    version = str(root.get("version", "")).strip()
    if not version:
        raise ValueError("Contract must define a non-empty 'version'.")
    description = str(root.get("description", "")).strip()
    metrics_raw = _expect_mapping(root.get("metrics"), context="metrics")

    metrics = {
        name: _parse_metric_mapping(name, payload)
        for name, payload in metrics_raw.items()
    }
    contract = SecMetricContract(
        version=version,
        description=description,
        metrics=metrics,
    )
    validate_contract(contract)
    return contract


def get_metric_mapping(
    path: str | Path | None = None,
) -> dict[str, MetricMapping]:
    return load_sec_metric_contract(path=path).metrics

