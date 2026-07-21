"""Workflow helpers for repeatable pipeline runs."""

from __future__ import annotations

from ..steps.legacy_processed_fundamentals_builder import build_legacy_raw_stage1


def run_legacy_raw_stage1_window(
    start_year: int = 2006,
    end_year: int = 2023,
) -> dict[str, str]:
    """Run the local legacy Stage 1 raw-yearly publisher for a year window."""
    return build_legacy_raw_stage1(
        start_year=start_year,
        end_year=end_year,
    )
