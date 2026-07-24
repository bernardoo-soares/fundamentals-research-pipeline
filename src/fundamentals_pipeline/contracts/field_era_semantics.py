"""Declared per-era semantics for every published Stage 1 field.

Compute-free. This module records what each provider actually means by each
column, per era, so that a semantic change across the provider boundary is a
declared fact -- checked against real data by
`steps/cross_era_semantic_audit.py` -- rather than an assumption. The `dvpq`
and `prstkcq` defects both existed because this declaration did not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .stage1_fundamentals_schema import STAGE1_KEY_COLUMNS, STAGE1_OUTPUT_COLUMNS

DEFAULT_VALUE_TOLERANCE = 0.01
DEFAULT_MIN_AGREEMENT_RATE = 0.90


class Basis(StrEnum):
    """How a number is stated across time."""

    DISCRETE_QUARTER = "discrete_quarter"
    YEAR_TO_DATE = "year_to_date"
    POINT_IN_TIME = "point_in_time"


class Unit(StrEnum):
    """The dimension a number is measured in."""

    USD_MILLIONS = "usd_millions"
    SHARES_MILLIONS = "shares_millions"
    USD_PER_SHARE = "usd_per_share"


@dataclass(frozen=True)
class EraSource:
    """One provider's source for a canonical field, in that provider's terms."""

    column: str
    meaning: str
    unit: Unit
    basis: Basis
    derived: bool = False


@dataclass(frozen=True)
class FieldEraSemantics:
    """Declared cross-era semantics for one canonical field.

    `value_tolerance` is per-row (a row agrees when its relative difference is
    within it); `min_agreement_rate` is per-field (the fraction of rows that
    must agree). Keeping them distinct matters: conflating them was a defect
    in the first draft of the design spec.
    """

    field: str
    legacy: EraSource | None
    simfin: EraSource | None
    eras_equivalent: bool
    divergence_note: str = ""
    value_tolerance: float = DEFAULT_VALUE_TOLERANCE
    min_agreement_rate: float = DEFAULT_MIN_AGREEMENT_RATE
    threshold_justification: str = ""

    def validate(self) -> None:
        """Raise ValueError when the declaration is internally inconsistent."""
        if self.eras_equivalent:
            if self.legacy is None or self.simfin is None:
                raise ValueError(
                    f"{self.field}: eras_equivalent=True requires both eras present."
                )
            if self.legacy.unit != self.simfin.unit:
                raise ValueError(
                    f"{self.field}: eras_equivalent=True but unit differs "
                    f"({self.legacy.unit} vs {self.simfin.unit})."
                )
            if self.legacy.basis != self.simfin.basis:
                raise ValueError(
                    f"{self.field}: eras_equivalent=True but basis differs "
                    f"({self.legacy.basis} vs {self.simfin.basis})."
                )
        elif not self.divergence_note:
            raise ValueError(
                f"{self.field}: eras_equivalent=False requires a divergence_note."
            )
        if (
            self.min_agreement_rate < DEFAULT_MIN_AGREEMENT_RATE
            and not self.threshold_justification
        ):
            raise ValueError(
                f"{self.field}: min_agreement_rate below "
                f"{DEFAULT_MIN_AGREEMENT_RATE} requires a threshold_justification."
            )


def _usd(
    column: str,
    meaning: str,
    basis: Basis = Basis.DISCRETE_QUARTER,
    *,
    derived: bool = False,
) -> EraSource:
    """Shorthand for a currency-denominated source."""
    return EraSource(column, meaning, Unit.USD_MILLIONS, basis, derived)


def _shares(column: str, meaning: str) -> EraSource:
    """Shorthand for a share-count source."""
    return EraSource(column, meaning, Unit.SHARES_MILLIONS, Basis.POINT_IN_TIME)


def _equivalent_usd(
    field: str,
    legacy_column: str,
    simfin_column: str,
    meaning: str,
    basis: Basis,
) -> FieldEraSemantics:
    """Declare a currency field the two providers state the same way."""
    return FieldEraSemantics(
        field=field,
        legacy=_usd(legacy_column, meaning, basis),
        simfin=_usd(simfin_column, meaning, basis),
        eras_equivalent=True,
    )


_FLOW = Basis.DISCRETE_QUARTER
_STOCK = Basis.POINT_IN_TIME

FIELD_ERA_SEMANTICS: tuple[FieldEraSemantics, ...] = (
    # --- Income statement (discrete quarterly flows) ---
    _equivalent_usd("saleq", "saleq", "Revenue", "total revenue", _FLOW),
    _equivalent_usd("niq", "niq", "Net Income", "net income", _FLOW),
    _equivalent_usd(
        "oiadpq", "oiadpq", "Operating Income (Loss)", "operating income", _FLOW
    ),
    FieldEraSemantics(
        field="xintq",
        legacy=_usd("xintq", "Interest Expense - Total", _FLOW),
        simfin=_usd("Interest Expense, Net", "interest expense net of income", _FLOW),
        eras_equivalent=False,
        divergence_note=(
            "Legacy is gross interest expense; SimFin is net of interest "
            "income, and states it with the opposite sign. Measured FY2023: "
            "89.8% sign-flip rate, magnitude ratio -1.22 (KO legacy 413 vs "
            "SimFin -146). Not a pure sign fix -- the two are different "
            "quantities, so interest_pct_operating_income (spec 6.2) must "
            "carry this caveat when it is built."
        ),
    ),
    _equivalent_usd(
        "txtq", "txtq", "Income Tax (Expense) Benefit, Net", "income tax", _FLOW
    ),
    _equivalent_usd(
        "cogsq", "cogsq", "Cost of Revenue", "cost of goods sold", _FLOW
    ),
    _equivalent_usd(
        "xsgaq",
        "xsgaq",
        "Selling, General & Administrative",
        "SG&A expense",
        _FLOW,
    ),
    _equivalent_usd(
        "xrdq", "xrdq", "Research & Development", "R&D expense", _FLOW
    ),
    _equivalent_usd(
        "dpq",
        "dpq",
        "Depreciation & Amortization (cashflow)",
        "depreciation and amortization",
        _FLOW,
    ),
    FieldEraSemantics(
        field="epspxq",
        legacy=EraSource(
            "epspxq",
            "Earnings Per Share (Basic) - Excluding Extraordinary Items",
            Unit.USD_PER_SHARE,
            _FLOW,
        ),
        simfin=EraSource(
            "Net Income (Common) / Shares (Basic)",
            "derived basic EPS",
            Unit.USD_PER_SHARE,
            _FLOW,
            derived=True,
        ),
        eras_equivalent=False,
        divergence_note=(
            "SimFin publishes no EPS column at all, so the SimFin-era value is "
            "derived rather than as-reported. Irreducible: disclosed, not fixed."
        ),
    ),
    # --- Balance sheet (point-in-time stocks) ---
    _equivalent_usd(
        "actq", "actq", "Total Current Assets", "current assets", _STOCK
    ),
    _equivalent_usd(
        "lctq", "lctq", "Total Current Liabilities", "current liabilities", _STOCK
    ),
    _equivalent_usd(
        "ppentq",
        "ppentq",
        "Property, Plant & Equipment, Net",
        "net PP&E",
        _STOCK,
    ),
    _equivalent_usd("gdwlq", "gdwlq", "Goodwill", "goodwill", _STOCK),
    _equivalent_usd(
        "ivltq",
        "ivltq",
        "Long Term Investments & Receivables",
        "long-term investments",
        _STOCK,
    ),
    _equivalent_usd("atq", "atq", "Total Assets", "total assets", _STOCK),
    _equivalent_usd("ceqq", "ceqq", "Total Equity", "common equity", _STOCK),
    _equivalent_usd(
        "dlcq", "dlcq", "Short Term Debt", "short-term debt", _STOCK
    ),
    _equivalent_usd("dlttq", "dlttq", "Long Term Debt", "long-term debt", _STOCK),
    _equivalent_usd(
        "req", "req", "Retained Earnings", "retained earnings", _STOCK
    ),
    _equivalent_usd(
        "tstkq", "tstkq", "Treasury Stock", "treasury stock", _STOCK
    ),
    _equivalent_usd(
        "cheq",
        "cheq",
        "Cash, Cash Equivalents & Short Term Investments",
        "cash and equivalents",
        _STOCK,
    ),
    _equivalent_usd(
        "ltq", "ltq", "Total Liabilities", "total liabilities", _STOCK
    ),
    _equivalent_usd("invtq", "invtq", "Inventories", "inventories", _STOCK),
    _equivalent_usd(
        "rectq",
        "rectq",
        "Accounts & Notes Receivable",
        "receivables",
        _STOCK,
    ),
    # --- Share counts ---
    FieldEraSemantics(
        field="cshfdq",
        legacy=_shares("cshfdq", "Com Shares for Diluted EPS"),
        simfin=_shares("Shares (Diluted)", "diluted share count"),
        eras_equivalent=True,
    ),
    FieldEraSemantics(
        field="cshoq",
        legacy=_shares("cshoq", "Common Shares Outstanding"),
        simfin=_shares("Shares (Basic)", "basic share count"),
        eras_equivalent=True,
    ),
    FieldEraSemantics(
        field="cshopq",
        legacy=_shares("cshopq", "Total Shares Repurchased - Quarter"),
        simfin=None,
        eras_equivalent=False,
        divergence_note=(
            "SimFin publishes no shares-repurchased count; null in that era. "
            "This field was previously substituted into the currency field "
            "prstkcq, producing a unit error."
        ),
    ),
    # --- Cash flow ---
    _equivalent_usd(
        "oancfq",
        "oancfq",
        "Net Cash from Operating Activities",
        "operating cash flow",
        _FLOW,
    ),
    _equivalent_usd(
        "capxq",
        "capxq",
        "Change in Fixed Assets & Intangibles",
        "capital expenditure",
        _FLOW,
    ),
    _equivalent_usd(
        "oancfy",
        "oancfy",
        "Net Cash from Operating Activities (annual)",
        "operating cash flow",
        Basis.YEAR_TO_DATE,
    ),
    _equivalent_usd(
        "capxy",
        "capxy",
        "Change in Fixed Assets & Intangibles (annual)",
        "capital expenditure",
        Basis.YEAR_TO_DATE,
    ),
    FieldEraSemantics(
        field="dvy",
        legacy=_usd("dvy", "Cash Dividends", Basis.YEAR_TO_DATE),
        simfin=_usd(
            "Dividends Paid (annual)", "Dividends Paid", Basis.YEAR_TO_DATE
        ),
        eras_equivalent=True,
        min_agreement_rate=0.90,
        threshold_justification=(
            "Measured 2026-07-24 on 274 FY2023 overlap tickers: 92.9% agree "
            "within 1% (median relative difference 0.0000). Residual ~7% is an "
            "open item in design spec section 10.5, suspected fiscal-calendar "
            "alignment, not a mapping error."
        ),
    ),
    FieldEraSemantics(
        field="dvpq",
        legacy=_usd("dvpq", "Dividends - Preferred/Preference", _FLOW),
        simfin=None,
        eras_equivalent=False,
        divergence_note=(
            "dvpq is preferred dividends by the Compustat definition. SimFin "
            "publishes no preferred-dividend field, so it is null in that era. "
            "It was previously mis-mapped to total 'Dividends Paid', which now "
            "lives in dvy."
        ),
    ),
    FieldEraSemantics(
        field="prstkcq",
        legacy=None,
        simfin=_usd(
            "Cash from (Repurchase of) Equity",
            "net equity issuance/repurchase",
            _FLOW,
        ),
        eras_equivalent=False,
        divergence_note=(
            "Compustat publishes no quarterly purchase-of-stock column, so this "
            "is null in the legacy era. It was previously filled from cshopq, "
            "a share count, producing a unit error."
        ),
    ),
    FieldEraSemantics(
        field="prstkcy",
        legacy=_usd(
            "prstkcy",
            "Purchase of Common and Preferred Stock",
            Basis.YEAR_TO_DATE,
        ),
        simfin=_usd(
            "Cash from (Repurchase of) Equity (annual)",
            "net equity issuance/repurchase",
            Basis.YEAR_TO_DATE,
        ),
        eras_equivalent=False,
        divergence_note=(
            "Legacy is gross repurchase; SimFin is net equity flow (488 of 3548 "
            "SimFin quarters negative against 1 of 30187 legacy). Magnitudes "
            "align, so buyback_years_10y is usable with a stated era bias."
        ),
    ),
)


def semantics_for(field: str) -> FieldEraSemantics:
    """Return the declared semantics for one field."""
    for entry in FIELD_ERA_SEMANTICS:
        if entry.field == field:
            return entry
    raise KeyError(f"No declared era semantics for field: {field!r}")


def declared_fields() -> frozenset[str]:
    """Return the set of fields carrying a declaration."""
    return frozenset(entry.field for entry in FIELD_ERA_SEMANTICS)


def validate_field_era_semantics() -> None:
    """Validate every declaration and reject duplicates or undeclared names."""
    seen: set[str] = set()
    for entry in FIELD_ERA_SEMANTICS:
        if entry.field in seen:
            raise ValueError(f"Duplicate era-semantics entry: {entry.field}")
        seen.add(entry.field)
        entry.validate()
        if entry.field in STAGE1_KEY_COLUMNS:
            raise ValueError(f"Key column must not be declared: {entry.field}")
        if entry.field not in STAGE1_OUTPUT_COLUMNS:
            raise ValueError(f"Declared field is not published: {entry.field}")
