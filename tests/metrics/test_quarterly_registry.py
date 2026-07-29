from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.era_resolution import SourceEra
from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.metrics.quarterly import apply_era_restriction
from fundamentals_pipeline.metrics.quarterly_registry import (
    QUARTERLY_REGISTRY,
    operand_totals_for,
    validate_quarterly_registry,
)

METRICS = {m.metric_id: m for m in QUARTERLY_REGISTRY}


def test_registry_has_every_declared_quarterly_metric() -> None:
    assert set(METRICS) == {
        "net_margin",
        "roa",
        "roe",
        "debt_to_equity_adj",
        "current_ratio",
        "st_lt_debt_ratio",
        "lt_debt_payback_years",
        "interest_pct_operating_income",
        "treasury_stock_present",
        "eps_ttm",  # per-share trend use
        "net_income_ttm",  # drives valuation; split-adjustment invariant
        # gross-profit family; era-dispatched arithmetic, both eras
        "gross_margin",
        "sga_pct_gross_profit",
        "rd_pct_gross_profit",
        "dep_pct_gross_profit",
        # Operand totals: published so the console can show the derived figure
        # a ratio used, without re-deriving the TTM rule in a view (S2.6).
        "revenue_ttm",
        "cost_of_revenue_ttm",
        "depreciation_ttm",
        "sga_ttm",
        "rd_ttm",
        "interest_expense_ttm",
        "operating_income_ttm",
        "gross_profit_ttm",
    }


def test_operand_totals_are_marked_and_read_one_concept_each() -> None:
    """A total that read several unrelated fields would attach to nothing."""
    totals = [m for m in QUARTERLY_REGISTRY if m.is_operand_total]
    # 7 new plain TTM sums, the 2 that already existed (eps_ttm,
    # net_income_ttm), and the era-dispatched gross_profit_ttm.
    assert len(totals) == 10
    for metric in totals:
        assert metric.inputs, f"{metric.metric_id} declares no inputs"


def test_operand_totals_attach_by_subset_not_by_lookup_table() -> None:
    """The subset rule must pick up gross_profit_ttm without a special case."""
    by_id = {m.metric_id: m for m in QUARTERLY_REGISTRY}
    assert set(operand_totals_for(by_id["net_margin"])) == {
        "net_income_ttm",
        "revenue_ttm",
    }
    assert "gross_profit_ttm" in operand_totals_for(by_id["sga_pct_gross_profit"])
    # A stock-only metric has no TTM behind it, and must not be given one.
    assert operand_totals_for(by_id["current_ratio"]) == ()


def test_an_operand_total_never_lists_itself() -> None:
    by_id = {m.metric_id: m for m in QUARTERLY_REGISTRY}
    assert "revenue_ttm" not in operand_totals_for(by_id["revenue_ttm"])


def test_validate_rejects_duplicate_ids() -> None:
    dup = QUARTERLY_REGISTRY + (QUARTERLY_REGISTRY[0],)
    with pytest.raises(ValueError):
        validate_quarterly_registry(dup)


def _replace_metric(metric_id: str, **overrides) -> tuple:
    """Build a registry with one metric's fields overridden, for validator tests."""
    updated = []
    for metric in QUARTERLY_REGISTRY:
        if metric.metric_id == metric_id:
            metric = replace(metric, **overrides)
        updated.append(metric)
    return tuple(updated)


def test_validate_accepts_a_valid_era_restriction() -> None:
    registry = _replace_metric(
        "treasury_stock_present", supported_eras=frozenset({SourceEra.LEGACY})
    )
    validate_quarterly_registry(registry)  # must not raise


def test_validate_rejects_unknown_era_value() -> None:
    """A typo'd era (e.g. a bare string instead of SourceEra.LEGACY) must not
    pass silently -- it would null every row of the metric with
    era_not_supported and raise nothing, a silent total coverage wipe."""
    registry = _replace_metric(
        "treasury_stock_present", supported_eras=frozenset({"legacy"})
    )
    with pytest.raises(ValueError, match="treasury_stock_present"):
        validate_quarterly_registry(registry)


def test_validate_rejects_empty_supported_eras() -> None:
    """An empty frozenset would null every row of the metric; None (every
    era) is the correct spelling of 'no restriction', not an empty set."""
    registry = _replace_metric("treasury_stock_present", supported_eras=frozenset())
    with pytest.raises(ValueError, match="treasury_stock_present"):
        validate_quarterly_registry(registry)


def test_validate_accepts_supported_eras_none() -> None:
    registry = _replace_metric("treasury_stock_present", supported_eras=None)
    validate_quarterly_registry(registry)  # must not raise


# --- Real AAPL FY2023 corpus (warehouse; matches Apple's 10-K to the $M) ---
# 2023Q1..Q4 sum to revenue 383,285 and net income 96,995 (Apple FY2023).
_AAPL = [
    # year, quarter, saleq, niq, atq, ceqq, ltq, tstkq, era
    (2022, 4, 90146.0, 20721.0, 352755.0, 50672.0, 302083.0, 0.0, "legacy_compustat"),
    (2023, 1, 117154.0, 29998.0, 346747.0, 56727.0, 290020.0, None, "simfin"),
    (2023, 2, 94836.0, 24160.0, 332160.0, 62158.0, 270002.0, None, "simfin"),
    (2023, 3, 81797.0, 19881.0, 335038.0, 60274.0, 274764.0, None, "simfin"),
    (2023, 4, 89498.0, 22956.0, 352583.0, 62146.0, 290437.0, None, "simfin"),
]


def _aapl_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAPL", "year": y, "quarter": q, "saleq": s, "niq": n,
                "atq": a, "ceqq": c, "ltq": lt, "tstkq": t, "source_era": e,
            }
            for (y, q, s, n, a, c, lt, t, e) in _AAPL
        ]
    )


def _value_at(metric_id, frame, year, quarter):
    return next(
        p
        for p in METRICS[metric_id].compute(frame)
        if p.year == year and p.quarter == quarter
    )


def test_golden_net_margin_aapl_fy2023() -> None:
    # niq_ttm 96,995 / saleq_ttm 383,285 = 0.25307 (Apple FY2023 net margin ~25.3%)
    p = _value_at("net_margin", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(96995.0 / 383285.0)
    assert p.value == pytest.approx(0.25307, abs=1e-5)


def test_golden_roa_aapl_fy2023() -> None:
    # 96,995 / total assets 352,583 = 0.27510
    p = _value_at("roa", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(96995.0 / 352583.0)


def test_golden_roe_aapl_fy2023() -> None:
    # 96,995 / total equity 62,146 = 1.56076 (Apple's famously high ROE)
    p = _value_at("roe", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(96995.0 / 62146.0)


def test_golden_debt_to_equity_adj_aapl_tstk_null_flagged() -> None:
    # 2023 simfin: tstkq null -> ltq 290,437 / ceqq 62,146, flagged tstk_unavailable
    p = _value_at("debt_to_equity_adj", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(290437.0 / 62146.0)
    assert p.quality_flag == ReasonCode.TSTK_UNAVAILABLE


def test_golden_debt_to_equity_adj_aapl_tstk_present_no_flag() -> None:
    # 2022 legacy: tstkq 0 present -> ltq 302,083 / ceqq 50,672, no flag
    p = _value_at("debt_to_equity_adj", _aapl_frame(), 2022, 4)
    assert p.value == pytest.approx(302083.0 / 50672.0)
    assert p.quality_flag is None


def test_golden_roe_negative_equity_azo() -> None:
    # AutoZone (AZO) FY2023Q4: ceqq -4,349.894 < 0 -> roe null (negative_base)
    frame = pd.DataFrame(
        [
            {"ticker": "AZO", "year": 2023, "quarter": q, "niq": 500.0,
             "ceqq": -4349.894, "source_era": "simfin"}
            for q in (1, 2, 3, 4)
        ]
    )
    p = _value_at("roe", frame, 2023, 4)
    assert p.value is None
    assert p.reason_code == ReasonCode.NEGATIVE_BASE


def test_interest_pct_is_restricted_to_the_legacy_era():
    """Both legs diverge across the boundary, so the metric is legacy-only."""
    metric = next(
        m for m in QUARTERLY_REGISTRY
        if m.metric_id == "interest_pct_operating_income"
    )
    assert metric.supported_eras == frozenset({SourceEra.LEGACY})
    assert metric.version == "2", "restricting the computation bumps the version"


# Every metric whose computation is era-specific, and why. A metric absent from
# this set must apply in both eras; adding one here is a deliberate act that
# costs SimFin-era coverage, so the set is asserted exhaustively.
# The gross-profit family left this set on 2026-07-28: its arithmetic is
# era-DISPATCHED rather than era-restricted, so both eras compute (the legacy
# one flagged `da_allocation_assumed`). `interest_pct` stays: no remapping of
# either leg rose above 0.474 agreement, so there is no SimFin arithmetic to
# dispatch to.
_LEGACY_RESTRICTED = {
    "interest_pct_operating_income",  # both legs diverge across the boundary
}


def test_only_the_declared_metrics_are_era_restricted():
    for metric in QUARTERLY_REGISTRY:
        expected = (
            frozenset({SourceEra.LEGACY})
            if metric.metric_id in _LEGACY_RESTRICTED
            else None
        )
        assert metric.supported_eras == expected, metric.metric_id


def test_compute_layer_interest_pct_mixed_era_abbv() -> None:
    """Pure compute-layer outcome only -- not what production publishes.

    AbbVie (ABBV) at 2023Q1: xintq window 2022Q2-Q4 legacy gross (556/560/566)
    + 2023Q1 simfin net (-454). xintq non-equivalent -> mixed_era_window when
    `metric.compute` is called directly, which is what this assertion proves:
    the TTM era guard fires on a non-equivalent field spanning two eras.

    `interest_pct_operating_income` is also restricted to the legacy era
    (see test_interest_pct_is_restricted_to_the_legacy_era), and this row's
    source_era is "simfin". The builder calls `apply_era_restriction` after
    `metric.compute`, but that helper relabels only points that still carry a
    value -- an already-reasoned null keeps its more specific diagnosis. So
    production publishes MIXED_ERA_WINDOW here, not ERA_NOT_SUPPORTED: the
    era-contamination signal survives the restriction. Asserted below.
    """
    frame = pd.DataFrame(
        [
            {"ticker": "ABBV", "year": 2022, "quarter": 2, "xintq": 556.0,
             "oiadpq": 5000.0, "source_era": "legacy_compustat"},
            {"ticker": "ABBV", "year": 2022, "quarter": 3, "xintq": 560.0,
             "oiadpq": 5000.0, "source_era": "legacy_compustat"},
            {"ticker": "ABBV", "year": 2022, "quarter": 4, "xintq": 566.0,
             "oiadpq": 5000.0, "source_era": "legacy_compustat"},
            {"ticker": "ABBV", "year": 2023, "quarter": 1, "xintq": -454.0,
             "oiadpq": 2918.0, "source_era": "simfin"},
        ]
    )
    p = _value_at("interest_pct_operating_income", frame, 2023, 1)
    assert p.value is None
    assert p.reason_code == ReasonCode.MIXED_ERA_WINDOW

    # What the builder actually publishes for this row. The metric is
    # restricted to the legacy era, but the row is already a reasoned null, so
    # the specific mixed_era_window diagnosis is preserved rather than being
    # flattened to era_not_supported.
    metric = next(
        m for m in QUARTERLY_REGISTRY
        if m.metric_id == "interest_pct_operating_income"
    )
    published = apply_era_restriction(metric.compute(frame), metric.supported_eras)
    row = next(pt for pt in published if pt.year == 2023 and pt.quarter == 1)
    assert row.value is None
    assert row.reason_code == ReasonCode.MIXED_ERA_WINDOW


# --- Real KO FY2021 corpus (warehouse; matches Coca-Cola's 10-K to the $M) ---
# Compustat states cogsq and xsgaq BEFORE depreciation, so published gross
# profit is saleq - cogsq - dpq. Sums: saleq 38,655 (KO's published net
# operating revenues), cogsq 13,905, dpq 1,452, xsgaq 11,964.
# 13,905 + 1,452 = 15,357 = KO's published cost of goods sold, exactly.
_KO_2021 = [
    # year, quarter, saleq, cogsq, dpq, xsgaq
    (2021, 1, 9020.0, 3139.0, 366.0, 2659.0),
    (2021, 2, 10129.0, 3404.0, 383.0, 3012.0),
    (2021, 3, 10042.0, 3615.0, 362.0, 2847.0),
    (2021, 4, 9464.0, 3747.0, 341.0, 3446.0),
]

_KO_SALEQ_TTM = 38655.0
_KO_COGSQ_TTM = 13905.0
_KO_DPQ_TTM = 1452.0
_KO_XSGAQ_TTM = 11964.0
_KO_GROSS_PROFIT = 23298.0  # KO's published FY2021 gross profit


def _ko_frame(era: str = "legacy_compustat") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "KO", "year": y, "quarter": q, "saleq": s, "cogsq": c,
                "dpq": d, "xsgaq": g, "xrdq": None, "source_era": era,
            }
            for (y, q, s, c, d, g) in _KO_2021
        ]
    )


def _restricted_value_at(metric_id, frame, year, quarter):
    """Compute a metric the way the builder does: compute then apply era restriction."""
    metric = METRICS[metric_id]
    points = apply_era_restriction(metric.compute(frame), metric.supported_eras)
    return next(p for p in points if p.year == year and p.quarter == quarter)


def test_golden_gross_profit_ko_fy2021_matches_published() -> None:
    """The corrected denominator reproduces KO's published gross profit exactly.

    38,655 - 13,905 - 1,452 = 23,298. The catalog's uncorrected
    (saleq - cogsq) gives 24,750, which is gross profit BEFORE depreciation and
    is not the line Coca-Cola reports.
    """
    assert _KO_SALEQ_TTM - _KO_COGSQ_TTM - _KO_DPQ_TTM == _KO_GROSS_PROFIT
    assert _KO_COGSQ_TTM + _KO_DPQ_TTM == 15357.0  # published COGS


def test_golden_gross_margin_ko_fy2021() -> None:
    # 23,298 / 38,655 = 0.602716 -- Coca-Cola's published FY2021 gross margin.
    p = _restricted_value_at("gross_margin", _ko_frame(), 2021, 4)
    assert p.value == pytest.approx(_KO_GROSS_PROFIT / _KO_SALEQ_TTM)
    assert p.value == pytest.approx(0.602716, abs=1e-6)


def test_golden_gross_margin_rejects_the_uncorrected_formula() -> None:
    """Guards the defect directly: the pre-depreciation form must not ship.

    (38,655 - 13,905) / 38,655 = 0.640279 overstates the published margin by
    3.76pp. Measured across 9,003 legacy quarters the median overstatement is
    4.09pp against a book threshold of >40%.
    """
    p = _restricted_value_at("gross_margin", _ko_frame(), 2021, 4)
    uncorrected = (_KO_SALEQ_TTM - _KO_COGSQ_TTM) / _KO_SALEQ_TTM
    assert uncorrected == pytest.approx(0.640279, abs=1e-6)
    assert p.value != pytest.approx(uncorrected, abs=1e-4)


def test_golden_dep_pct_gross_profit_ko_reproduces_the_book_anchor() -> None:
    """1,452 / 23,298 = 0.0623, matching the spec's book anchor 'KO approx 6%'.

    The anchor is NOT reproducible with the catalog's uncorrected denominator
    (1,452 / 24,750 = 0.0587), so the catalog's anchor and its own formula
    disagreed. This test pins the anchor, not the formula.
    """
    p = _restricted_value_at("dep_pct_gross_profit", _ko_frame(), 2021, 4)
    assert p.value == pytest.approx(_KO_DPQ_TTM / _KO_GROSS_PROFIT)
    assert p.value == pytest.approx(0.062323, abs=1e-6)


def test_golden_sga_pct_gross_profit_ko_fy2021() -> None:
    # 11,964 / 23,298 = 0.513520
    p = _restricted_value_at("sga_pct_gross_profit", _ko_frame(), 2021, 4)
    assert p.value == pytest.approx(_KO_XSGAQ_TTM / _KO_GROSS_PROFIT)
    assert p.value == pytest.approx(0.513520, abs=1e-6)


@pytest.mark.parametrize(
    "metric_id",
    ["gross_margin", "sga_pct_gross_profit", "rd_pct_gross_profit", "dep_pct_gross_profit"],
)
def test_gross_profit_family_computes_in_both_eras(metric_id: str) -> None:
    """SimFin rows are COMPUTED, not nulled -- reversed 2026-07-28.

    The family used to be legacy-only on the belief that "SimFin's Cost of
    Revenue already includes D&A". Measured: that holds for only 34.4% of
    filers. SimFin preserves each filer's own presentation, so
    `Revenue - Cost of Revenue` is the as-reported gross profit for ALL of them
    and needs no depreciation term. `dpq` is deliberately absent from this frame
    to prove the SimFin path does not require it.

    `xrdq` is supplied here (KO reports none) so every metric in the family can
    produce a value.
    """
    frame = _ko_frame(era="simfin")
    frame["xrdq"] = 100.0
    assert METRICS[metric_id].supported_eras is None
    p = _restricted_value_at(metric_id, frame, 2021, 4)
    assert p.value is not None, p.reason_code
    assert p.reason_code is None
    # As-reported arithmetic carries no assumption, so no caveat.
    assert p.quality_flag is None


def test_simfin_gross_profit_does_not_require_depreciation() -> None:
    """The SimFin denominator needs no `dpq`, unlike the legacy one.

    Proves the era dispatch really happened rather than the legacy branch
    quietly succeeding: with `dpq` absent the legacy arithmetic cannot produce
    a gross profit at all, so a value here can only have come from
    `saleq - cogsq`.

    `dep_pct_gross_profit` is excluded because `dpq` is its NUMERATOR -- it
    needs the field regardless of which era supplies the denominator.
    """
    frame = _ko_frame(era="simfin")
    frame["dpq"] = None
    point = _restricted_value_at("gross_margin", frame, 2021, 4)
    assert point.value is not None, point.reason_code
    assert point.quality_flag is None


def test_legacy_gross_profit_is_flagged_as_assuming_the_da_split() -> None:
    """Every legacy gross-profit row must carry the caveat to the UI.

    Compustat normalises the filer's own D&A allocation away, so `a = 1` is
    assumed -- exact for 34.4% of filers, understating by a median 13.46pp for
    the 26.4% who present D&A outside cost of revenue. The value is real, so it
    is a quality flag rather than a reason code, but it must never be silent.
    """
    point = _restricted_value_at("gross_margin", _ko_frame(era="legacy"), 2021, 4)
    assert point.value is not None
    assert point.quality_flag == ReasonCode.DA_ALLOCATION_ASSUMED


@pytest.mark.parametrize(
    "metric_id",
    ["gross_margin", "sga_pct_gross_profit", "rd_pct_gross_profit", "dep_pct_gross_profit"],
)
def test_gross_profit_family_computes_on_legacy_rows(metric_id: str) -> None:
    """The counterpart: the restriction must not null the era it supports."""
    frame = _ko_frame()
    frame["xrdq"] = 100.0
    p = _restricted_value_at(metric_id, frame, 2021, 4)
    assert p.value is not None
    assert p.reason_code is None


def test_rd_pct_gross_profit_is_missing_input_when_xrdq_absent() -> None:
    """KO reports no R&D line: null with a reason, never zero (S4.2)."""
    p = _restricted_value_at("rd_pct_gross_profit", _ko_frame(), 2021, 4)
    assert p.value is None
    assert p.reason_code == ReasonCode.MISSING_INPUT


def test_negative_gross_profit_is_reasoned_null() -> None:
    """Selling below cost is real but makes the ratio meaningless."""
    frame = pd.DataFrame(
        [
            {"ticker": "X", "year": 2021, "quarter": q, "saleq": 100.0,
             "cogsq": 90.0, "dpq": 30.0, "xsgaq": 10.0, "xrdq": None,
             "source_era": "legacy_compustat"}
            for q in (1, 2, 3, 4)
        ]
    )
    p = _restricted_value_at("sga_pct_gross_profit", frame, 2021, 4)
    assert p.value is None
    assert p.reason_code == ReasonCode.NEGATIVE_BASE


# --- SimFin-era gross-margin golden: Apple FY2023, from the 10-K ------------
# Total net sales 383,285 and total cost of sales 214,137 give the published
# gross margin of 169,148 / 383,285 = 44.13%. SimFin's Cost of Revenue IS that
# 214,137, which is the whole reason the SimFin era needs no depreciation term.
_AAPL_FY2023_COST_OF_SALES = [66822.0, 52860.0, 45384.0, 49071.0]
_AAPL_FY2023_REVENUE = [117154.0, 94836.0, 81797.0, 89498.0]


def _aapl_gross_profit_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "year": 2023,
                "quarter": quarter,
                "saleq": revenue,
                "cogsq": cost,
                # Present but irrelevant: the SimFin arithmetic must not touch
                # it. If it did, gross margin would come out 41.13%, not the published 44.13%.
                "dpq": 2879.75,
                "xsgaq": None,
                "xrdq": None,
                "source_era": "simfin",
            }
            for quarter, (revenue, cost) in enumerate(
                zip(_AAPL_FY2023_REVENUE, _AAPL_FY2023_COST_OF_SALES, strict=True),
                start=1,
            )
        ]
    )


def test_golden_gross_margin_aapl_fy2023_simfin_era() -> None:
    """The published figure, not a derived one (S4.4).

    383,285 - 214,137 = 169,148, and 169,148 / 383,285 = 0.441261 -- Apple's
    reported FY2023 gross margin of 44.13%. Subtracting `dpq` as the legacy
    arithmetic does would give 0.411258, understating it by 3.01pp.
    """
    point = _value_at("gross_margin", _aapl_gross_profit_frame(), 2023, 4)
    assert sum(_AAPL_FY2023_REVENUE) == 383285.0
    assert sum(_AAPL_FY2023_COST_OF_SALES) == 214137.0
    assert point.value == pytest.approx(169148.0 / 383285.0)
    assert point.value == pytest.approx(0.441311, abs=1e-6)
    assert point.quality_flag is None
    assert point.source_era == "simfin"
