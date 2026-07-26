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

from .source_families import POOLED_FAMILY, SourceFamily
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
class FamilyAgreementThreshold:
    """A per-family override of a field's `min_agreement_rate`.

    SimFin publishes a separate statement set per business family, so one
    canonical field can agree with the legacy era in one family and diverge in
    another. A pooled rate averages those together: `saleq` measured 0.869
    pooled -- clearing its declared 0.80 -- while every bank row disagreed at
    0.000. Declaring the threshold per family is what lets the audit judge each
    family on its own terms instead of on the corpus average.

    `justification` is mandatory and must state measured evidence. It is
    deliberately separate from the field-level `threshold_justification`: a
    per-family relaxation must not inherit prose written about the pooled rate,
    which is exactly how the refuted "median relative difference is exactly
    0.0000" claim came to appear to cover the banks family (AGENTS.md S4.7).
    """

    family: SourceFamily
    min_agreement_rate: float
    justification: str


@dataclass(frozen=True)
class FieldEraSemantics:
    """Declared cross-era semantics for one canonical field.

    `value_tolerance` is per-row (a row agrees when its relative difference is
    within it); `min_agreement_rate` is per-field (the fraction of rows that
    must agree). Keeping them distinct matters: conflating them was a defect
    in the first draft of the design spec.

    `family_thresholds` optionally overrides `min_agreement_rate` for individual
    SimFin statement families; see `min_agreement_rate_for`.
    """

    field: str
    legacy: EraSource | None
    simfin: EraSource | None
    eras_equivalent: bool
    divergence_note: str = ""
    value_tolerance: float = DEFAULT_VALUE_TOLERANCE
    min_agreement_rate: float = DEFAULT_MIN_AGREEMENT_RATE
    threshold_justification: str = ""
    family_thresholds: tuple[FamilyAgreementThreshold, ...] = ()

    def min_agreement_rate_for(self, source_family: str) -> float:
        """Return the agreement threshold that applies to one family.

        Resolves to the family's declared override when one exists, else to the
        field-level `min_agreement_rate`. `POOLED_FAMILY` never carries an
        override (`validate` rejects it), so the pooled row always resolves to
        the field-level rate and its verdict is unaffected by any override.
        """
        for override in self.family_thresholds:
            if str(override.family) == source_family:
                return override.min_agreement_rate
        return self.min_agreement_rate

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
        self._validate_family_thresholds()

    def _validate_family_thresholds(self) -> None:
        """Reject per-family overrides that are unjustified or structurally inert.

        Each rejection guards a way an override could read as a live guard while
        being incapable of firing, or could relax a bound without evidence.
        """
        seen: set[str] = set()
        for override in self.family_thresholds:
            name = str(override.family)
            if not self.eras_equivalent:
                raise ValueError(
                    f"{self.field}: family_thresholds on a non-equivalent field "
                    "are inert -- the verdict is divergent_declared regardless "
                    "of the agreement rate."
                )
            if name == POOLED_FAMILY:
                raise ValueError(
                    f"{self.field}: {POOLED_FAMILY!r} is the pooled aggregate; "
                    "use min_agreement_rate to control it."
                )
            if name in seen:
                raise ValueError(
                    f"{self.field}: duplicate family threshold for {name!r}."
                )
            if not 0.0 < override.min_agreement_rate <= 1.0:
                raise ValueError(
                    f"{self.field}: family threshold for {name!r} is out of "
                    "range; must be within (0, 1]."
                )
            if not override.justification:
                raise ValueError(
                    f"{self.field}: family threshold for {name!r} requires a "
                    "justification stating the measured evidence."
                )
            seen.add(name)


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
    FieldEraSemantics(
        field="saleq",
        legacy=_usd("saleq", "Sales/Turnover (Net)", _FLOW),
        simfin=_usd("Revenue", "total revenue", _FLOW),
        eras_equivalent=True,
        min_agreement_rate=0.80,
        family_thresholds=(
            FamilyAgreementThreshold(
                family=SourceFamily.INSURANCE,
                min_agreement_rate=0.50,
                justification=(
                    "Insurance measures 0.627 against the field-level 0.80. "
                    "Investigated 2026-07-26 (spec "
                    "2026-07-26_PER_FAMILY_AUDIT_VERDICTS_DESIGN section 3) and "
                    "declared rather than nulled, because SimFin holds the "
                    "AS-REPORTED figure here and Compustat does not. "
                    "HAND-VERIFIED on AFL FY2023: SimFin Revenue sums to 18,700 "
                    "against Aflac's published total revenues of $18.7B, while "
                    "Compustat saleq sums to 17,729 -- 971 (5.2%) lower. The two "
                    "providers agree EXACTLY on AFL net income quarter by "
                    "quarter (1188/1634/1569/268, both summing to 4,659 against "
                    "a published $4.66B), which isolates the divergence to the "
                    "revenue line: a fiscal-calendar, unit or restatement cause "
                    "would have moved net income too. "
                    "NOT a tolerance problem, which is why value_tolerance is "
                    "left at 1%: the distribution is not a smooth tail (median "
                    "0.0046, p90 0.0257, p95 0.1336, max 0.3924) but 6 tickers "
                    "agreeing exactly (TRV, WRB, HUM, CI, CINF, MET), 5 within "
                    "2.6% (L, ACGL, CB, ERIE, HIG) and 2 genuinely divergent "
                    "(AIG max 39.2%, AFL median 13.4% with 0/4 quarters within "
                    "1%). Raising tolerance to 3% would clear a 0.90 rate while "
                    "AIG and AFL kept publishing divergent revenue, and would "
                    "assert agreement within 3% -- false for AFL. "
                    "IRREDUCIBLE: SimFin's insurance income statement publishes "
                    "a single Revenue column with no premiums / investment-income "
                    "decomposition, and on the Compustat side AFL has saleq == "
                    "revtq exactly with tiiq and finrevq null, so no candidate "
                    "column exists on either side. Special items are rejected as "
                    "the cause (spiq sums to 38 against a 971 gap). Quarterly "
                    "gaps swing both directions (Q2 -1135, Q4 +679), which is "
                    "CONSISTENT WITH but does not confirm realized investment "
                    "gains/losses -- large for AFL and AIG relative to premiums, "
                    "small for the six exact tickers. "
                    "0.50 is the weakest statement that still does real work -- a "
                    "majority of rows must agree exactly -- and keeps 0.13 "
                    "headroom below the measured 0.627 so it is not fitted to "
                    "it. It still fails a banks-style concept mismatch (0.000) "
                    "and a material degradation on refresh. "
                    "DISCLOSED CONSEQUENCE: net_margin for insurers with "
                    "material realized investment gains carries a level shift "
                    "across the 2022/2023 boundary (AFL 5.2% of revenue at the "
                    "FY2023 annual grain, AIG 16.7%). Each era's value is "
                    "internally consistent and defensible in its own era, but "
                    "they are not the same quantity. revenue_cagr_* is already "
                    "protected: windows.require_single_era nulls any multi-year "
                    "window spanning the boundary as mixed_era_window."
                ),
            ),
        ),
        threshold_justification=(
            "CORRECTED 2026-07-26: the claim below that 'the median relative "
            "difference is exactly 0.0000' is a POOLED figure, true for the "
            "general family and FALSE for banks (median 0.5328, agreement "
            "0.000, ratio 1.533). The per-family audit added 2026-07-25 "
            "refuted it: SimFin's bank Revenue is a narrower construction no "
            "Compustat column reproduces, and the pooled rate cleared this "
            "0.80 threshold as `agree` while every bank row disagreed. "
            "`saleq` is therefore nulled for the banks family from 2026-07-26 "
            "(spec 2026-07-26_FAMILY_PROXY_REMEDIATION_DESIGN). Insurance "
            "(0.627, median 0.0046, ratio 0.999) remains mapped. "
            "SUPERSEDED 2026-07-26 on two counts by spec "
            "2026-07-26_PER_FAMILY_AUDIT_VERDICTS_DESIGN. (1) The claim that "
            "insurance 'sits below this 0.80 threshold while the pooled rate "
            "clears it, and per-family rows carry no verdict, so nothing "
            "raises' described the masking defect and is no longer true: "
            "per-family rows now carry enforceable verdicts, and insurance "
            "carries an explicit declared threshold of 0.50 -- see "
            "family_thresholds above. (2) Calling insurance a 'tail problem' "
            "was refuted by measurement: the distribution is 6 exact tickers, "
            "5 within 2.6% and 2 genuinely divergent (AIG max 39.2%, AFL "
            "median 13.4%), not a smooth tail, and SimFin rather than Compustat "
            "holds the as-reported figure. The "
            "general-family median relative difference of 0.0000 below was "
            "re-confirmed per family; the `revtq` 84.7% vs `saleq` 83.5% "
            "comparison was a POOLED 2026-07-24 figure and has NOT been "
            "re-measured per family, so it should not be read as "
            "general-family evidence.\n"
            "Investigated 2026-07-24. The concepts DO match -- the median "
            "relative difference is exactly 0.0000 and `revtq` scores the same "
            "as `saleq` (84.7% vs 83.5%), so this is not a definitional "
            "mismatch. The residual is provider data quality: SimFin derives "
            "some Q4 figures as a residual and publishes IMPOSSIBLE values when "
            "the fiscal calendars disagree -- eight FY2023 tickers carried "
            "negative Q4 revenue (Marriott -11318, Dollar Tree -5183, Hilton "
            "-3218), and for all of them the four quarters no longer summed to "
            "the true annual (Dollar Tree 16781 against 30604). "
            "`warehouse/plausibility.py` now nulls impossible values so they "
            "cannot propagate. The threshold is 0.80 to accept the residual "
            "tail rather than to hide it; the tail is enumerated in the "
            "reconciliation report and remains an open item."
        ),
    ),
    _equivalent_usd("niq", "niq", "Net Income", "net income", _FLOW),
    FieldEraSemantics(
        field="oiadpq",
        legacy=_usd("oiadpq", "Operating Income (Loss)", _FLOW),
        simfin=_usd("Operating Income (Loss)", "operating income", _FLOW),
        eras_equivalent=False,
        divergence_note=(
            "The providers draw the operating/non-operating line per company. "
            "Investigated 2026-07-25 on the FY2023 overlap, general family "
            "(1,319 rows): oiadpq agrees 44.6% (median 1.58%). No remapping "
            "of the 663 available Compustat columns clears it -- oiadpq+spiq "
            "0.474, piq-nopiq+xintq 0.474, revtq-xoprq-dpq 0.453, oibdpq-dpq "
            "0.448, oibdpq 0.003, saleq-cogsq-xsgaq 0.008. The ceiling is "
            "0.474 against a 0.90 threshold, where the successful Stage 1 "
            "remediations reached 0.958 (reunaq) and 0.940 (seqq+mibtq). "
            "DECISIVE: 73.9% of rows agree under at least ONE candidate "
            "definition while no single definition exceeds 0.474, so which "
            "definition reconciles varies per company -- a judgement about "
            "what sits above the operating line (restructuring, impairments, "
            "gains on sale, litigation), not a formula that can be chosen "
            "once. Three hypotheses rejected by measurement: special/abnormal "
            "items (subtracting SimFin Abnormal Gains worsens it to 0.307), "
            "shared cause with cogsq (Spearman 0.210), and fiscal-calendar "
            "misalignment (the annual grain is worse at 0.374). The ratio is "
            "symmetric about 1.000 (p25 1.000, p50 1.000, legacy higher on "
            "50.5%) with dispersion p90/p10 = 1.21, so unlike cogsq there is "
            "no systematic bias to correct and unlike ppentq (2.17) it is not "
            "a gross definitional offset. Banks and insurance are a separate "
            "defect, fixed at the builder: SimFin's family statements define "
            "operating income differently (banks 0.000 agreement), so oiadpq "
            "is null for them from 2026-07-25. NOT cross-era comparable: a "
            "TTM sum crossing a ticker's era-switch year is nulled "
            "mixed_era_window, and interest_pct_operating_income is "
            "restricted to the legacy era (spec "
            "2026-07-25_OIADPQ_ERA_REMEDIATION_DESIGN section 3.3)."
        ),
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
    FieldEraSemantics(
        field="cogsq",
        legacy=_usd("cogsq", "Cost of Goods Sold", _FLOW),
        simfin=_usd("Cost of Revenue", "cost of revenue", _FLOW),
        eras_equivalent=False,
        divergence_note=(
            "The two providers place different operating costs above the "
            "gross-profit line. Investigated 2026-07-24 on the FY2023 overlap, "
            "restricted to the 273 companies whose revenue agrees within 1% so "
            "that COGS composition is the only variable: legacy gross margin is "
            "systematically HIGHER by a median +2.45pp (80.6% of companies), "
            "median absolute gap 3.51pp, p90 18.76pp, only 17.6% within 1pp. "
            "Candidate remappings do not close it: cogsq 12.6% agreement, "
            "cogsq+dpq 36.6%, cogsq-dpq 2.7%, xoprq-xsgaq 13.7%. The usual "
            "explanation (Compustat COGS excludes depreciation, reported "
            "separately in dpq) was PLAUSIBLE BUT UNCONFIRMED here because "
            "SimFin's income-statement D&A column is only ~40% populated, so "
            "that test had n=89 and was inconclusive. "
            "CONFIRMED 2026-07-26 from the COMPUSTAT side instead, which "
            "sidesteps the sparse SimFin column entirely (spec "
            "2026-07-26_SP3_METRIC_CATALOG_COMPLETION_DESIGN section 2): "
            "Compustat's own identity saleq - (cogsq + xsgaq) = oibdpq "
            "(operating income BEFORE D&A) holds for 99.69% of 9,035 legacy "
            "quarters across 176 tickers, with oibdpq - dpq = oiadpq. So cogsq "
            "AND xsgaq are both stated pre-depreciation, and cogsq is not the "
            "cost-of-goods line a filing reports. Verified against published "
            "filings: cogsq + dpq recovers reported COGS EXACTLY for AAPL "
            "FY2022 (212,442 + 11,104 = 223,546) and KO FY2021 (13,905 + 1,452 "
            "= 15,357), and to within 0.14-0.44% of revenue for PG, MMM and "
            "JNJ. This explains the direction of the divergence recorded above "
            "-- legacy gross margin reads HIGHER because legacy COGS omits D&A "
            "while SimFin's Cost of Revenue includes it. Correcting the "
            "arithmetic to saleq - cogsq - dpq raises cross-era gross-margin "
            "agreement from 0.100 to 0.386 at 1% tolerance and halves the "
            "median step (0.0350 to 0.0138), so the D&A treatment is the "
            "SUBSTANTIAL but not the ONLY cause; the residual is consistent "
            "with dpq including D&A allocated to SG&A. Every shipped "
            "gross-profit metric therefore uses the corrected arithmetic and is "
            "restricted to the legacy era, since the correct formula differs by "
            "era (S4.3). "
            "CONSEQUENCE FOR SCORING: gross margin carries a >40% threshold "
            "(platform spec 6.2), and 13.6% of companies -- 27.7% of those with "
            "gross margin between 30% and 50% -- flip across that line purely by "
            "which provider served the row. Any gross-margin metric must be "
            "restricted to a single era or dropped; it must NOT be computed "
            "across the 2022/2023 boundary."
        ),
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
            "derived rather than as-reported. Irreducible: disclosed, not fixed. "
            "Measured impact on eps_up_year_fraction_10y at the 2022->2023 "
            "transition (n=353): the direction flips for 5.7% of tickers, with "
            "a median relative difference of only 0.23%, affecting at most 1 of "
            "~9 pairs in a 10-year window. Materially milder than the cogsq "
            "divergence, which is why this metric is not era-restricted."
        ),
    ),
    # --- Balance sheet (point-in-time stocks) ---
    _equivalent_usd(
        "actq", "actq", "Total Current Assets", "current assets", _STOCK
    ),
    _equivalent_usd(
        "lctq", "lctq", "Total Current Liabilities", "current liabilities", _STOCK
    ),
    FieldEraSemantics(
        field="ppentq",
        legacy=_usd("ppentq", "Property Plant and Equipment - Total (Net)", _STOCK),
        simfin=_usd("Property, Plant & Equipment, Net", "net PP&E", _STOCK),
        eras_equivalent=False,
        divergence_note=(
            "Both sides say 'net PP&E', but SimFin uses a condensed five-bucket "
            "balance sheet and draws the PP&E / Other-Long-Term-Assets boundary "
            "differently from Compustat, per company. Investigated 2026-07-24 on "
            "the FY2023 overlap: ppentq agrees 7.4% (median 0.197); gross ppegtq "
            "0.0%; ppegtq-dpactq 8.8%. The AGGREGATE reconciles -- "
            "ppentq+aoq vs SimFin PP&E+OtherLT agrees 65.7% at median 0.0000 -- "
            "so the total is conserved and only the split differs. The ratio is "
            "dispersed (p10 1.009, p50 1.167, p90 2.194; p90/p10 = 2.17), which "
            "rules out a constant definitional offset and therefore any fix by "
            "remapping. NOT cross-era comparable: a metric using ppentq must "
            "stay inside one era."
        ),
    ),
    _equivalent_usd("gdwlq", "gdwlq", "Goodwill", "goodwill", _STOCK),
    FieldEraSemantics(
        field="ivltq",
        legacy=_usd("ivltq", "Total Long-term Investments", _STOCK),
        simfin=_usd(
            "Long Term Investments & Receivables (general) / Short & Long Term "
            "Investments (banks) / Total Investments (insurance)",
            "family-dependent investment aggregate",
            _STOCK,
        ),
        eras_equivalent=False,
        divergence_note=(
            "SimFin maps three different concepts by family, none of which is "
            "Compustat's 'Total Long-term Investments': general includes "
            "RECEIVABLES, banks includes SHORT-term, insurance is TOTAL "
            "investments. SIMFIN_STAGE1_MAPPING.md already records the bank and "
            "insurance mappings as proxies. Investigated 2026-07-24 on the "
            "FY2023 overlap: SimFin's general-family value is null or zero for "
            "67.8% of companies against 18.4% for Compustat, and where both "
            "exist (n=93) agreement is 40.9%. No candidate column improves it "
            "(ivaeqq+ivaoq n=6; +ivstq 13.6%; +rectq 0.9%). NOT cross-era "
            "comparable: a metric using ivltq must stay inside one era."
        ),
    ),
    _equivalent_usd("atq", "atq", "Total Assets", "total assets", _STOCK),
    FieldEraSemantics(
        field="ceqq",
        legacy=_usd("seqq + mibtq", "stockholders equity + noncontrolling", _STOCK),
        simfin=_usd("Total Equity", "total equity incl. noncontrolling", _STOCK),
        eras_equivalent=True,
        threshold_justification=(
            "Sourced from Compustat `seqq + mibtq`, NOT `ceqq`. SimFin "
            "publishes one equity line that includes noncontrolling interests; "
            "Compustat `ceqq` is Common/Ordinary Equity and excludes them. "
            "Measured on the FY2023 overlap: ceqq 64.7%, teqq 86.3%, "
            "seqq+mibtq 94.0% (median relative difference 0.0000). "
            "CONSEQUENCE FOR ROE: the numerator is parent-only income in both "
            "eras (legacy niq agrees 92.0% with SimFin Net Income, whereas "
            "pre-noncontrolling ibmiiq agrees only 67.6%), so pairing it with "
            "total equity slightly understates ROE for companies with material "
            "noncontrolling interests. The effect is small -- mibtq is exactly "
            "zero for 45.6% of rows and the ceqq-vs-total median gap is 0.12% "
            "-- and SimFin offers no common-equity line, so this is the only "
            "cross-era-comparable choice. Document it wherever ROE is shown."
        ),
    ),
    FieldEraSemantics(
        field="dlcq",
        legacy=_usd("dlcq", "Debt in Current Liabilities", _STOCK),
        simfin=_usd("Short Term Debt", "short-term debt", _STOCK),
        eras_equivalent=False,
        divergence_note=(
            "Investigated 2026-07-24 on the FY2023 overlap: dlcq agrees 8.7% "
            "(median 0.183), dd1q 3.9%, dlcq-dd1q 6.6%. Coverage also diverges "
            "sharply -- SimFin leaves this null for 28.2% of companies against "
            "0.9% for Compustat -- so the providers disagree on both the value "
            "and on whether the concept applies. NOT cross-era comparable: a "
            "windowed (trend-grain) metric using it must stay inside a single "
            "era. The point-in-time metrics_quarterly grain is unaffected: each "
            "quarterly st_lt_debt_ratio value uses one quarter, hence one era "
            "(spec 2026-07-25_METRICS_QUARTERLY_TTM_ENGINE_DESIGN section 4)."
        ),
    ),
    FieldEraSemantics(
        field="dlttq",
        legacy=_usd("dlttq", "Long-Term Debt - Total", _STOCK),
        simfin=_usd("Long Term Debt", "long-term debt", _STOCK),
        eras_equivalent=False,
        divergence_note=(
            "The providers draw the long-term-debt boundary differently, most "
            "likely over lease obligations and the current portion. "
            "Investigated 2026-07-24 on the FY2023 overlap: dlttq agrees 9.8% "
            "(median 0.064), dlttq+dd1q 1.7%, lltq 0.0%. No Compustat column "
            "matches, so this is a classification boundary rather than a "
            "remapping error -- the same shape as ppentq. NOT cross-era "
            "comparable: a windowed (trend-grain) metric using it must stay "
            "inside a single era, and a TTM sum crossing a ticker's era-switch "
            "year is nulled mixed_era_window. The point-in-time "
            "metrics_quarterly values of lt_debt_payback_years and "
            "st_lt_debt_ratio are unaffected: each uses one quarter's balance "
            "sheet, hence one era (spec "
            "2026-07-25_METRICS_QUARTERLY_TTM_ENGINE_DESIGN section 4)."
        ),
    ),
    FieldEraSemantics(
        field="req",
        legacy=_usd("reunaq", "Unadjusted Retained Earnings", _STOCK),
        simfin=_usd("Retained Earnings", "as-reported retained earnings", _STOCK),
        eras_equivalent=True,
        threshold_justification=(
            "Sourced from Compustat `reunaq`, NOT `req`. Compustat `req` is "
            "ADJUSTED retained earnings; the identity req = reunaq + acomincq "
            "holds within 0.1% for 98.4% of 19,982 legacy ticker-years, and "
            "AOCI is negative in 66.9% of them, so `req` read ~11% low against "
            "SimFin's as-reported line. SimFin has no AOCI column, so matching "
            "on the unadjusted basis is the only option. Measured on the FY2023 "
            "overlap: `req` 23.3% agreement, `reunaq` 95.8% (median relative "
            "difference 0.0000)."
        ),
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
            "Legacy is GROSS repurchase; SimFin is NET equity flow (488 of 3548 "
            "SimFin quarters negative against 1 of 30187 legacy). SimFin "
            "publishes no separate issuance/repurchase legs -- only the net "
            "line -- so this is irreducible, not a remapping error. "
            "Measured impact on buyback_years_10y at FY2023 (n=308): the "
            "'> 0' verdict flips for 13.0% of tickers, asymmetrically -- 39 "
            "cases where legacy sees a buyback and SimFin does not, against 1 "
            "the other way, because 18.2% of SimFin rows are net issuance. The "
            "count is therefore biased DOWNWARD by up to 2 of 10 years for "
            "SimFin-served tickers. Post-2022 the metric answers 'was the "
            "company a net returner of equity capital?' rather than 'did it "
            "repurchase?'."
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
