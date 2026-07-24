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

    SimFin is preferred wherever it has a complete year. That keeps the SimFin
    era contiguous for the tickers it covers, so legacy fills only the tickers
    SimFin lacks and no ticker's series switches provider mid-window.

    The rejected alternative -- preferring legacy wherever available -- would
    have given a ticker legacy FY2023 and SimFin FY2024, relocating the
    provider discontinuity into the middle of that ticker's series.

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
