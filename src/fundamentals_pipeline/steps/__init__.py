"""Pipeline step exports.

Each step is a runnable unit that reads source artifacts and writes deterministic
outputs in the raw/processed/report layers.
"""

from .legacy_processed_fundamentals_builder import (
    build_legacy_fundamentals,
    build_legacy_raw_stage1,
    build_legacy_raw_stage1_compare_frame,
)
from .legacy_stage1_output_audit import run_legacy_stage1_audit
from .raw_fundamentals_unit_normalizer import (
    build_unit_normalization_report,
    normalize_raw_fundamentals_units,
)
from .sec_companyfacts_pipeline import (
    build_sec_cik_mapping,
    build_sec_processed_fundamentals,
    normalize_sec_facts_long,
    run_sec_raw_ingestion,
)
from .sec_submissions_pipeline import (
    build_sec_fiscal_calendar,
    run_sec_submissions_ingestion,
)
from .sp500_universe_builder import build_sp500_current_universe
from .stage1_extension_coverage_audit import run_stage1_extension_coverage_audit

# Re-export step entrypoints used by CLI and workflows.
__all__ = [
    "build_legacy_fundamentals",
    "build_legacy_raw_stage1",
    "build_legacy_raw_stage1_compare_frame",
    "build_unit_normalization_report",
    "build_sec_cik_mapping",
    "build_sec_processed_fundamentals",
    "build_sec_fiscal_calendar",
    "build_sp500_current_universe",
    "normalize_sec_facts_long",
    "normalize_raw_fundamentals_units",
    "run_legacy_stage1_audit",
    "run_sec_raw_ingestion",
    "run_sec_submissions_ingestion",
    "run_stage1_extension_coverage_audit",
]
