"""Tests for the BuffettHeuristicScorer: assembly, null policy, special cases."""

from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.scorecard_schema import (
    ChecklistVerdict,
    MetricReading,
    ScoreBadge,
    ScoreReasonCode,
    ScorerInput,
)
from fundamentals_pipeline.scoring.buffett_scorer import BuffettHeuristicScorer
from fundamentals_pipeline.scoring.config import load_scorecard_config

CONFIG = load_scorecard_config()
SCORER = BuffettHeuristicScorer(CONFIG)


def _readings(**values) -> dict[str, MetricReading]:
    """Metric readings from metric_id=value; None means a reasoned null."""
    out = {}
    for metric_id, value in values.items():
        out[metric_id] = (
            MetricReading(metric_id, None, "missing_input")
            if value is None
            else MetricReading(metric_id, float(value), None)
        )
    return out


def _input(readings, **kwargs) -> ScorerInput:
    return ScorerInput(
        ticker=kwargs.pop("ticker", "TEST"),
        as_of_year=kwargs.pop("as_of_year", 2022),
        readings=readings,
        **kwargs,
    )


def _all_metrics(value_by_metric: dict[str, float | None]) -> dict:
    """Readings for every declared criterion, defaulting to a reasoned null."""
    full = {c.metric_id: None for c in CONFIG.criteria()}
    full.update(value_by_metric)
    return _readings(**full)


def test_composite_is_null_with_a_reason_when_nothing_is_measurable():
    """A null composite must never be published as 0.

    Zero would rank an unmeasured company as the worst one; the truth is that
    nothing is known about it (spec 7.4, S4.5).
    """
    result = SCORER.score(_input(_all_metrics({})))
    assert result.composite is None
    assert result.reason_code == ScoreReasonCode.NO_APPLICABLE_COMPONENT
    assert result.coverage_ratio == 0.0
    assert ScoreBadge.LOW_CONFIDENCE in result.badges


def test_a_perfect_company_scores_100():
    """Every criterion at or beyond its top anchor gives a composite of 100."""
    perfect = {
        "gross_margin": 0.70, "gross_margin_ge40_years_10y": 1.0,
        "net_margin_ge20_years_10y": 1.0, "sga_pct_gross_profit": 0.10,
        "rd_pct_gross_profit": 0.0, "dep_pct_gross_profit": 0.05,
        "eps_up_year_fraction_10y": 1.0, "net_income_up_year_fraction_10y": 1.0,
        "net_margin": 0.40, "roe": 0.40,
        "lt_debt_payback_years": 0.5, "debt_to_equity_adj": 0.20,
        "interest_pct_operating_income": 0.0, "st_lt_debt_ratio": 0.05,
        "current_ratio": 3.0,
        "capex_pct_net_income_avg10y": 0.10, "buyback_years_10y": 10.0,
        "retained_earnings_cagr_10y": 0.25, "treasury_stock_present": 1.0,
        "revenue_cagr_4y": 0.20, "revenue_cagr_10y": 0.20,
        "receivables_pct_sales_trend_10y": -0.02,
        "inventory_earnings_correspondence_10y": 1.0,
    }
    result = SCORER.score(_input(_all_metrics(perfect)))
    assert result.composite == pytest.approx(100.0)
    assert result.coverage_ratio == pytest.approx(1.0)
    assert result.checklist_applicable == 23
    assert result.checklist_passed == 23
    assert result.badges == ()


def test_a_worst_case_company_scores_zero_but_is_not_null():
    """0 is a real answer when everything was measured and everything is bad."""
    worst = {
        "gross_margin": 0.05, "gross_margin_ge40_years_10y": 0.0,
        "net_margin_ge20_years_10y": 0.0, "sga_pct_gross_profit": 2.0,
        "rd_pct_gross_profit": 0.90, "dep_pct_gross_profit": 0.60,
        "eps_up_year_fraction_10y": 0.0, "net_income_up_year_fraction_10y": 0.0,
        "net_margin": -0.20, "roe": -0.50,
        "lt_debt_payback_years": 30.0, "debt_to_equity_adj": 8.0,
        "interest_pct_operating_income": 0.90, "st_lt_debt_ratio": 4.0,
        "current_ratio": 0.10,
        "capex_pct_net_income_avg10y": 5.0, "buyback_years_10y": 0.0,
        "retained_earnings_cagr_10y": -0.20, "treasury_stock_present": 0.0,
        "revenue_cagr_4y": -0.10, "revenue_cagr_10y": -0.10,
        "receivables_pct_sales_trend_10y": 0.05,
        "inventory_earnings_correspondence_10y": 0.0,
    }
    result = SCORER.score(_input(_all_metrics(worst)))
    # current_ratio floors at 30 (the book's sub-1.0 franchises), so the
    # composite is small but not exactly zero.
    assert result.composite is not None
    assert 0.0 <= result.composite < 5.0
    assert result.reason_code is None
    assert result.checklist_passed == 0


def test_null_criterion_is_excluded_and_the_component_renormalizes():
    """Spec 7.4.1: a null criterion contributes no points and no weight.

    Two of four earnings criteria present, both at full points, must give the
    component 100 -- not 50, which is what including the nulls as zeros would.
    """
    readings = _all_metrics(
        {
            "eps_up_year_fraction_10y": 1.0,
            "net_income_up_year_fraction_10y": 1.0,
        }
    )
    result = SCORER.score(_input(readings))
    earnings = next(
        c for c in result.components if c.component_id == "earnings_consistency"
    )
    assert earnings.applicable_criteria == 2
    assert earnings.total_criteria == 4
    assert earnings.coverage_ratio == pytest.approx(0.5)
    assert earnings.score == pytest.approx(100.0)
    # Each applicable criterion carries half the component after renormalization.
    weights = [
        c.weight
        for c in result.criteria
        if c.component_id == "earnings_consistency" and c.applicable
    ]
    assert weights == [pytest.approx(0.5), pytest.approx(0.5)]


def test_component_below_the_coverage_floor_is_excluded():
    """The FY2024 profitability collapse: 1 of 6 criteria must not carry 30%.

    Renormalizing a 30%-weight component onto one criterion is not the same
    component measured with less data (spec 2026-07-26_SP4 section 1.1).
    """
    readings = _all_metrics(
        {
            "net_margin_ge20_years_10y": 1.0,  # 1 of 6 profitability criteria
            "eps_up_year_fraction_10y": 1.0,
            "net_income_up_year_fraction_10y": 1.0,
            "net_margin": 0.30,
            "roe": 0.30,
        }
    )
    result = SCORER.score(_input(readings))
    profitability = next(
        c for c in result.components if c.component_id == "profitability_moat"
    )
    assert profitability.coverage_ratio == pytest.approx(1 / 6)
    assert profitability.score is None
    assert profitability.reason_code == ScoreReasonCode.COMPONENT_COVERAGE_BELOW_FLOOR
    assert profitability.weight is None, "an excluded component carries no weight"


def test_surviving_component_weights_renormalize_to_one():
    """Top-level weights must always sum to 1.0 over the surviving components."""
    readings = _all_metrics(
        {
            "eps_up_year_fraction_10y": 1.0,
            "net_income_up_year_fraction_10y": 1.0,
            "net_margin": 0.30,
            "roe": 0.30,
        }
    )
    result = SCORER.score(_input(readings))
    weights = [c.weight for c in result.components if c.weight is not None]
    assert weights == [pytest.approx(1.0)], "only earnings_consistency survives"
    assert result.composite == pytest.approx(100.0)


def test_negative_equity_special_case_replaces_roe_with_full_points():
    """Spec 7.4.3: the book's durable-advantage case, not a defect.

    ROE is null with `negative_base` in exactly this situation, so without the
    override the criterion would drop out and the company would be judged on
    three criteria instead of four -- silently penalising the very pattern the
    book calls a strength.
    """
    readings = _all_metrics(
        {
            "eps_up_year_fraction_10y": 1.0,
            "net_income_up_year_fraction_10y": 1.0,
            "net_margin": 0.30,
            "negative_equity_strong_earnings": 1.0,
        }
    )
    readings["roe"] = MetricReading("roe", None, "negative_base")
    result = SCORER.score(_input(readings))
    roe = next(c for c in result.criteria if c.criterion_id == "return_on_equity")
    assert roe.points == pytest.approx(100.0)
    assert roe.checklist_verdict == ChecklistVerdict.PASS
    assert "special case" in roe.annotation
    earnings = next(
        c for c in result.components if c.component_id == "earnings_consistency"
    )
    assert earnings.applicable_criteria == 4


def test_roe_stays_null_when_the_special_case_does_not_fire():
    """Negative equity WITHOUT the profit record must not get free points."""
    readings = _all_metrics(
        {
            "eps_up_year_fraction_10y": 1.0,
            "negative_equity_strong_earnings": 0.0,
        }
    )
    readings["roe"] = MetricReading("roe", None, "negative_base")
    result = SCORER.score(_input(readings))
    roe = next(c for c in result.criteria if c.criterion_id == "return_on_equity")
    assert roe.points is None
    assert roe.checklist_verdict == ChecklistVerdict.NOT_APPLICABLE
    assert roe.reason_code == "negative_base"


def test_criterion_reason_code_is_carried_through_for_the_ui():
    """A blank cell is not an explanation; the UI must be able to say why."""
    readings = _all_metrics({"gross_margin": None})
    readings["gross_margin"] = MetricReading("gross_margin", None, "era_not_supported")
    result = SCORER.score(_input(readings))
    criterion = next(c for c in result.criteria if c.criterion_id == "gross_margin")
    assert criterion.reason_code == "era_not_supported"
    assert criterion.checklist_verdict == ChecklistVerdict.NOT_APPLICABLE


def test_stale_data_badge_fires_on_staleness():
    readings = _all_metrics({m.metric_id: 1.0 for m in CONFIG.criteria()})
    fresh = SCORER.score(_input(readings, staleness_quarters=2))
    stale = SCORER.score(_input(readings, staleness_quarters=9))
    assert ScoreBadge.STALE_DATA not in fresh.badges
    assert ScoreBadge.STALE_DATA in stale.badges


def test_scoring_is_deterministic():
    """Same input, same output -- no clock, randomness or ordering dependence."""
    readings = _all_metrics({"eps_up_year_fraction_10y": 1.0, "net_margin": 0.25})
    first = SCORER.score(_input(readings))
    second = SCORER.score(_input(readings))
    assert first == second


def test_points_never_leave_the_declared_scale():
    """Property: every criterion's points lie within [0, 100]."""
    extreme = _all_metrics({c.metric_id: 1e9 for c in CONFIG.criteria()})
    result = SCORER.score(_input(extreme))
    for criterion in result.criteria:
        if criterion.points is not None:
            assert 0.0 <= criterion.points <= 100.0
    assert result.composite is not None
    assert 0.0 <= result.composite <= 100.0


# --- Golden: a fully hand-computed scorecard ---


def test_golden_hand_computed_single_component_scorecard():
    """One component, every number derived by hand in this docstring.

    Only earnings_consistency is populated, so it is the sole surviving
    component and its weight renormalizes 0.20 -> 1.0.

      eps_up_year_fraction_10y  = 0.90
        ramp [[0,0],[1,100]]  -> 0.90 * 100                    =  90.0 pts
      net_income_up_year_fraction_10y = 0.80 -> 80.0 pts
      net_margin = 0.25
        ramp [[0,0],[0.10,50],[0.20,80],[0.30,100]]
        segment 0.20->0.30 spans 20 pts over 0.10;
        (0.25-0.20)/0.10 = 0.5 -> 80 + 0.5*20                  =  90.0 pts
      roe = 0.175
        ramp [...[0.15,70],[0.20,90]...]
        (0.175-0.15)/0.05 = 0.5 -> 70 + 0.5*20                 =  80.0 pts

      4 of 4 applicable -> each weighs 1/4
      component = (90 + 80 + 90 + 80) / 4                      =  85.0
      composite = 85.0 * (0.20 / 0.20)                         =  85.0

      checklist: eps 0.90 >= 0.80 PASS; net_income 0.80 >= 0.80 PASS;
                 net_margin 0.25 > 0.20 PASS; roe 0.175 > 0.15 PASS -> 4 of 4
    """
    readings = _all_metrics(
        {
            "eps_up_year_fraction_10y": 0.90,
            "net_income_up_year_fraction_10y": 0.80,
            "net_margin": 0.25,
            "roe": 0.175,
        }
    )
    result = SCORER.score(_input(readings))

    points = {c.criterion_id: c.points for c in result.criteria if c.applicable}
    assert points == {
        "eps_uptrend": pytest.approx(90.0),
        "net_income_uptrend": pytest.approx(80.0),
        "net_margin_level": pytest.approx(90.0),
        "return_on_equity": pytest.approx(80.0),
    }
    earnings = next(
        c for c in result.components if c.component_id == "earnings_consistency"
    )
    assert earnings.score == pytest.approx(85.0)
    assert earnings.weight == pytest.approx(1.0)
    assert result.composite == pytest.approx(85.0)
    assert result.checklist_passed == 4
    assert result.checklist_applicable == 4
    assert result.coverage_ratio == pytest.approx(4 / 23)
    assert ScoreBadge.LOW_CONFIDENCE in result.badges
