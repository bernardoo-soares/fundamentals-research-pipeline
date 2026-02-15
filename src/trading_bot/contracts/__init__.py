"""SEC contract package exports.

This package defines and validates the canonical mapping contract that links SEC
XBRL tags to raw quarterly fundamentals fields.
"""

from .sec_metric_contract import (
    COMPUTE_ONLY_FIELDS,
    FETCH_ONLY_RAW_FIELDS,
    HELPER_FALLBACK_FIELDS,
    REQUIRED_CANONICAL_FIELDS,
    MetricMapping,
    SecMetricContract,
    get_metric_mapping,
    load_sec_metric_contract,
    validate_contract,
)

# Re-export contract primitives for steps/tests.
__all__ = [
    "COMPUTE_ONLY_FIELDS",
    "FETCH_ONLY_RAW_FIELDS",
    "HELPER_FALLBACK_FIELDS",
    "MetricMapping",
    "REQUIRED_CANONICAL_FIELDS",
    "SecMetricContract",
    "get_metric_mapping",
    "load_sec_metric_contract",
    "validate_contract",
]
