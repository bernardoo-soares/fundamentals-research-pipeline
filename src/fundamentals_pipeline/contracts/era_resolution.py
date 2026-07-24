"""Declarative provider-precedence rule for the Stage 1 publish boundary.

Replaces the hardcoded `_LEGACY_MAX_YEAR = 2022` cutoff that routed every
2023+ row to SimFin and discarded usable legacy data for 112 universe tickers
in FY2023.

Resolution is whole-ticker-year: a fiscal year is served entirely by one
provider. Annualization sums four quarters, so a year stitched from two
providers would corrupt every flow field.
"""

from __future__ import annotations

from enum import StrEnum

MIN_QUARTERS_FOR_COMPLETE_YEAR = 4

# Provider staging directories, relative to the processed-data root. Each
# builder writes here; only `steps/stage1_era_resolution.py` writes the
# published CSVs alongside them. Declared once so the builders' output
# defaults and the resolver's input defaults cannot drift apart.
LEGACY_STAGING_DIRNAME = "_staging_legacy"
SIMFIN_STAGING_DIRNAME = "_staging_simfin"


class SourceEra(StrEnum):
    """Provider that served a given ticker-year."""

    LEGACY = "legacy_compustat"
    SIMFIN = "simfin"


def resolve_ticker_year_provider(
    *,
    legacy_quarters: int,
    simfin_quarters: int,
) -> SourceEra | None:
    """Choose the provider for one ticker-year, or None if neither is complete.

    SimFin is preferred wherever it has a complete year, which minimises how
    often a ticker changes provider: legacy fills only the ticker-years SimFin
    does not cover completely.

    This reduces mid-series switches but does not eliminate them. A ticker with
    complete legacy FY2023, incomplete SimFin FY2023, and complete SimFin
    FY2024 still resolves LEGACY then SIMFIN. Each ticker therefore has its own
    boundary year, which is why `metrics.windows.require_single_era` checks the
    per-row `source_era` values rather than assuming a single global cutover.

    The rejected alternative -- preferring legacy wherever available -- would
    have produced that switch for the majority of tickers rather than a
    minority, since legacy covers FY2023 well (463 tickers) but FY2024 barely
    (33).

    Args:
        legacy_quarters: Distinct quarters the legacy extract covers.
        simfin_quarters: Distinct quarters SimFin covers.

    Returns:
        The chosen provider, or None when neither offers a complete year.
    """
    if simfin_quarters >= MIN_QUARTERS_FOR_COMPLETE_YEAR:
        return SourceEra.SIMFIN
    if legacy_quarters >= MIN_QUARTERS_FOR_COMPLETE_YEAR:
        return SourceEra.LEGACY
    return None
