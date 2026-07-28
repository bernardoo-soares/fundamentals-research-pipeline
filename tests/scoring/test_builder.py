"""Tests for the scores builder -- the I/O edge of the scoring layer.

Synthetic fixtures here test mechanics only (S4.4): the golden scorecard whose
every number is hand-derived lives in `test_buffett_scorer.py`, and the
real-corpus verification is recorded in the SP4 spec.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fundamentals_pipeline.contracts.scorecard_schema import (
    SCORE_COMPONENTS_COLUMNS,
    SCORE_CRITERIA_COLUMNS,
    SCORES_COLUMNS,
    SCORES_PIPELINE_VERSION,
    ScoreBadge,
    ScoreReasonCode,
)
from fundamentals_pipeline.scoring.builder import (
    build_scores,
    quarter_ordinal,
)
from fundamentals_pipeline.scoring.config import load_scorecard_config

# Values chosen to land on ramp anchors so a mechanical regression is obvious,
# not to represent any real company.
_TREND_VALUES = {
    "gross_margin_ge40_years_10y": 1.0,
    "net_margin_ge20_years_10y": 1.0,
    "eps_up_year_fraction_10y": 1.0,
    "net_income_up_year_fraction_10y": 1.0,
    "capex_pct_net_income_avg10y": 0.25,
    "buyback_years_10y": 8.0,
    "retained_earnings_cagr_10y": 0.15,
    "revenue_cagr_4y": 0.15,
    "revenue_cagr_10y": 0.15,
    "receivables_pct_sales_trend_10y": -0.005,
    "inventory_earnings_correspondence_10y": 1.0,
    "negative_equity_strong_earnings": 0.0,
}
_QUARTERLY_VALUES = {
    "gross_margin": 0.60,
    # Just inside the strict `< 0.30` checklist. The ramp already awards full
    # points at 0.30 itself, where the checklist fails -- see
    # `test_ramp_and_checklist_can_disagree_at_a_shared_boundary`.
    "sga_pct_gross_profit": 0.29,
    "rd_pct_gross_profit": 0.0,
    "dep_pct_gross_profit": 0.06,
    "net_margin": 0.30,
    "roe": 0.30,
    "lt_debt_payback_years": 1.0,
    "debt_to_equity_adj": 0.50,
    "interest_pct_operating_income": 0.05,
    "st_lt_debt_ratio": 0.10,
    "current_ratio": 2.0,
    "treasury_stock_present": 1.0,
}


def _seed(
    path,
    *,
    trend: dict[str, float | None],
    quarterly: dict[str, float | None],
    ticker: str = "TEST",
    year: int = 2022,
    latest_quarter: tuple[int, int] = (2022, 4),
) -> None:
    """Write metrics_trend and metrics_quarterly rows for one ticker-year."""
    trend_rows = [
        {
            "ticker": ticker,
            "as_of_year": year,
            "metric_id": metric_id,
            "value": value,
            "reason_code": None if value is not None else "insufficient_history",
        }
        for metric_id, value in trend.items()
    ]
    quarterly_rows = [
        {
            "ticker": ticker,
            "year": year,
            "quarter": 4,
            "metric_id": metric_id,
            "value": value,
            "reason_code": None if value is not None else "missing_input",
            "quality_flag": None,
        }
        for metric_id, value in quarterly.items()
    ]
    # A later quarter drives the staleness measurement. Skipped when it is the
    # scored quarter itself, which the real table's primary key would reject.
    if latest_quarter != (year, 4):
        quarterly_rows.append(
            {
                "ticker": ticker,
                "year": latest_quarter[0],
                "quarter": latest_quarter[1],
                "metric_id": "net_margin",
                "value": None,
                "reason_code": "missing_input",
                "quality_flag": None,
            }
        )

    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE metrics_trend "
        "(ticker VARCHAR, as_of_year INTEGER, metric_id VARCHAR, "
        "value DOUBLE, reason_code VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE metrics_quarterly "
        "(ticker VARCHAR, year INTEGER, quarter INTEGER, metric_id VARCHAR, "
        "value DOUBLE, reason_code VARCHAR, quality_flag VARCHAR)"
    )
    for table, rows in (("metrics_trend", trend_rows), ("metrics_quarterly", quarterly_rows)):
        if not rows:
            continue
        conn.register("seed", pd.DataFrame(rows))
        conn.execute(f"INSERT INTO {table} SELECT * FROM seed")
        conn.unregister("seed")
    conn.close()


def _fetch(path, sql: str):
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_quarter_ordinal_is_monotonic_across_the_year_boundary() -> None:
    assert quarter_ordinal(2025, 1) == quarter_ordinal(2024, 4) + 1
    assert quarter_ordinal(2024, 4) - quarter_ordinal(2023, 4) == 4


def test_build_writes_all_three_tables(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES)
    config = load_scorecard_config()

    result = build_scores(warehouse_path=db)

    assert result["scores_rows"] == 1
    assert result["score_components_rows"] == len(config.components)
    assert result["score_criteria_rows"] == len(config.criteria())
    assert result["config_hash"] == config.config_hash
    assert result["null_composites"] == 0


def test_every_criterion_on_its_best_anchor_scores_one_hundred(tmp_path) -> None:
    """All 23 criteria pinned to their top-scoring anchor must compose to 100.

    Verifies the builder wires readings to the criteria it thinks it does: a
    metric_id typo or a grain mix-up would leave that criterion unscored and
    drag the composite below 100 without failing anything else.
    """
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES)

    build_scores(warehouse_path=db)

    composite, coverage, passed, applicable = _fetch(
        db,
        "SELECT composite, coverage_ratio, checklist_passed, checklist_applicable "
        "FROM scores",
    )[0]
    assert composite == pytest.approx(100.0)
    assert coverage == pytest.approx(1.0)
    assert passed == applicable == len(load_scorecard_config().criteria())


def test_ramp_and_checklist_can_disagree_at_a_shared_boundary(tmp_path) -> None:
    """Full ramp points with a failing checklist is correct, not a defect.

    `sga_discipline` awards 100 points from 0.30 downward while its checklist
    demands strictly `< 0.30`, so exactly 0.30 scores 100 and fails. The two are
    independent judgements by design (spec 7.3): the graded score ranks, the
    checklist grounds. Pinned so a future "fix" that quietly aligns them has to
    be a deliberate config change.
    """
    db = tmp_path / "research.duckdb"
    boundary = dict(_QUARTERLY_VALUES, sga_pct_gross_profit=0.30)
    _seed(db, trend=_TREND_VALUES, quarterly=boundary)

    build_scores(warehouse_path=db)

    points, verdict = _fetch(
        db,
        "SELECT points, checklist_verdict FROM score_criteria "
        "WHERE criterion_id='sga_discipline'",
    )[0]
    assert points == pytest.approx(100.0)
    assert verdict == "fail"


def test_absent_quarterly_grain_excludes_its_components(tmp_path) -> None:
    """With no fiscal-year-end readings, three components fall below the floor."""
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly={})

    build_scores(warehouse_path=db)

    excluded = {
        row[0]
        for row in _fetch(db, "SELECT component_id FROM score_components WHERE score IS NULL")
    }
    assert "debt_discipline" in excluded  # all 5 criteria are quarterly
    reasons = {
        row[0]
        for row in _fetch(
            db, "SELECT reason_code FROM score_components WHERE score IS NULL"
        )
    }
    assert reasons <= {
        ScoreReasonCode.NO_APPLICABLE_CRITERION.value,
        ScoreReasonCode.COMPONENT_COVERAGE_BELOW_FLOOR.value,
    }


def test_unscorable_ticker_year_publishes_a_reason_never_a_zero(tmp_path) -> None:
    """The invariant the whole layer exists to protect (spec 7.4.3, S4.5)."""
    db = tmp_path / "research.duckdb"
    _seed(
        db,
        trend=dict.fromkeys(_TREND_VALUES),
        quarterly=dict.fromkeys(_QUARTERLY_VALUES),
    )

    result = build_scores(warehouse_path=db)

    assert result["null_composites"] == 1
    composite, reason = _fetch(db, "SELECT composite, reason_code FROM scores")[0]
    assert composite is None
    assert reason == ScoreReasonCode.NO_APPLICABLE_COMPONENT.value


def test_value_xor_reason_holds_on_every_published_row(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    # A partial scorecard exercises both branches on one build.
    partial = dict(_QUARTERLY_VALUES)
    partial["gross_margin"] = None
    partial["roe"] = None
    _seed(db, trend=_TREND_VALUES, quarterly=partial)

    build_scores(warehouse_path=db)

    assert _fetch(
        db,
        "SELECT COUNT(*) FROM scores "
        "WHERE (composite IS NULL) = (reason_code IS NULL)",
    )[0][0] == 0
    assert _fetch(
        db,
        "SELECT COUNT(*) FROM score_components "
        "WHERE (score IS NULL) = (reason_code IS NULL)",
    )[0][0] == 0
    # A criterion carries points exactly when it is applicable; the annotated
    # negative-equity override is the one case where a null metric value still
    # earns points, so points -- not value -- is the invariant's subject.
    assert _fetch(
        db,
        "SELECT COUNT(*) FROM score_criteria "
        "WHERE (points IS NULL) = (reason_code IS NULL)",
    )[0][0] == 0


def test_no_nan_reaches_a_stored_column(tmp_path) -> None:
    """S4.5: NaN in a DOUBLE column is a value, not a null, and must never ship."""
    db = tmp_path / "research.duckdb"
    partial = dict(_QUARTERLY_VALUES)
    partial["gross_margin"] = None
    _seed(db, trend=_TREND_VALUES, quarterly=partial)

    build_scores(warehouse_path=db)

    for table, column in (
        ("scores", "composite"),
        ("scores", "coverage_ratio"),
        ("score_components", "score"),
        ("score_criteria", "points"),
        ("score_criteria", "value"),
    ):
        count = _fetch(
            db,
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {column} IS NOT NULL AND (isnan({column}) OR isinf({column}))",
        )[0][0]
        assert count == 0, f"{table}.{column} carries a non-finite value"


def test_staleness_badge_fires_on_a_ticker_that_stopped_reporting(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed(
        db,
        trend=_TREND_VALUES,
        quarterly=_QUARTERLY_VALUES,
        year=2022,
        latest_quarter=(2024, 4),
    )

    result = build_scores(warehouse_path=db)

    staleness, badges = _fetch(db, "SELECT staleness_quarters, badges FROM scores")[0]
    # Only one ticker exists, so it defines the global latest quarter and is not
    # stale relative to it -- staleness measures reporting lag, not score age.
    assert staleness == 0
    assert ScoreBadge.STALE_DATA.value not in badges
    assert result["badge_counts"].get(ScoreBadge.STALE_DATA.value) is None


def test_staleness_is_measured_against_the_global_latest_quarter(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES, latest_quarter=(2022, 4))
    # A second ticker reporting two years later moves the warehouse's frontier.
    conn = duckdb.connect(str(db))
    conn.execute(
        "INSERT INTO metrics_quarterly VALUES "
        "('FRESH', 2024, 4, 'net_margin', 0.2, NULL, NULL)"
    )
    conn.close()

    build_scores(warehouse_path=db)

    rows = dict(
        _fetch(db, "SELECT ticker, staleness_quarters FROM scores ORDER BY ticker")
    )
    assert rows["TEST"] == 8  # 2022Q4 -> 2024Q4
    assert rows["FRESH"] == 0
    badges = dict(_fetch(db, "SELECT ticker, badges FROM scores"))
    assert ScoreBadge.STALE_DATA.value in badges["TEST"]


def test_quarterly_only_ticker_year_is_published_not_dropped(tmp_path) -> None:
    """987 real ticker-years have no trend window; omitting them would hide them."""
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES, year=2022)
    conn = duckdb.connect(str(db))
    conn.execute(
        "INSERT INTO metrics_quarterly VALUES "
        "('TEST', 2006, 4, 'current_ratio', 2.0, NULL, NULL)"
    )
    conn.close()

    build_scores(warehouse_path=db)

    years = {row[0] for row in _fetch(db, "SELECT as_of_year FROM scores")}
    assert years == {2006, 2022}


def test_readings_are_taken_at_fiscal_year_end_only(tmp_path) -> None:
    """A Q3 reading must not stand in for an absent Q4 one (S4.2: no imputation)."""
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly={})
    conn = duckdb.connect(str(db))
    conn.execute(
        "INSERT INTO metrics_quarterly VALUES "
        "('TEST', 2022, 3, 'current_ratio', 2.0, NULL, NULL)"
    )
    conn.close()

    build_scores(warehouse_path=db)

    liquidity = _fetch(
        db, "SELECT value, points FROM score_criteria WHERE criterion_id='liquidity'"
    )[0]
    assert liquidity == (None, None)


def test_a_metric_id_at_both_grains_is_rejected(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES)
    conn = duckdb.connect(str(db))
    conn.execute(
        "INSERT INTO metrics_quarterly VALUES "
        "('TEST', 2022, 4, 'revenue_cagr_10y', 0.9, NULL, NULL)"
    )
    conn.close()

    with pytest.raises(ValueError, match="both the trend and quarterly grains"):
        build_scores(warehouse_path=db)


def test_build_is_idempotent_and_deterministic(tmp_path) -> None:
    """S3.1: same input, byte-identical output apart from metadata."""
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES)

    first = build_scores(warehouse_path=db)
    payload_columns = ", ".join(
        column for column in SCORES_COLUMNS if column != "computed_at"
    )
    before = _fetch(db, f"SELECT {payload_columns} FROM scores ORDER BY ticker")

    second = build_scores(warehouse_path=db)
    after = _fetch(db, f"SELECT {payload_columns} FROM scores ORDER BY ticker")

    assert first == second
    assert before == after
    for columns, table in (
        (SCORE_COMPONENTS_COLUMNS, "score_components"),
        (SCORE_CRITERIA_COLUMNS, "score_criteria"),
    ):
        payload = ", ".join(c for c in columns if c != "computed_at")
        assert len(_fetch(db, f"SELECT {payload} FROM {table}")) == len(
            set(_fetch(db, f"SELECT {payload} FROM {table}"))
        )


def test_rows_carry_provenance(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES)

    build_scores(warehouse_path=db)

    version = _fetch(db, "SELECT DISTINCT pipeline_version FROM scores")
    assert version == [(SCORES_PIPELINE_VERSION,)]


def test_missing_metrics_tables_are_rejected(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    duckdb.connect(str(db)).close()

    with pytest.raises(FileNotFoundError, match="metrics_quarterly, metrics_trend"):
        build_scores(warehouse_path=db)


def test_missing_warehouse_is_rejected(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="Warehouse database not found"):
        build_scores(warehouse_path=tmp_path / "absent.duckdb")


def test_scorer_and_config_path_together_are_rejected(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed(db, trend=_TREND_VALUES, quarterly=_QUARTERLY_VALUES)
    from fundamentals_pipeline.scoring.buffett_scorer import BuffettHeuristicScorer

    with pytest.raises(ValueError, match="not both"):
        build_scores(
            warehouse_path=db,
            scorer=BuffettHeuristicScorer(load_scorecard_config()),
            config_path="anything.yml",
        )


def test_era_guarded_criterion_leaves_the_coverage_denominator(tmp_path) -> None:
    """A criterion absent for EVERY company must not read as a company gap.

    `mixed_era_window` and `era_not_supported` mean the measurement does not
    exist in this provider era. Counting them as per-company gaps blames the
    company for a provider limitation and can push a component below the
    coverage floor for a reason that has nothing to do with it.
    """
    db = tmp_path / "research.duckdb"
    # capex is era-guarded; the other three capital_allocation criteria are fine.
    trend = dict(_TREND_VALUES)
    trend["capex_pct_net_income_avg10y"] = None
    _seed(db, trend=trend, quarterly=_QUARTERLY_VALUES)
    conn = duckdb.connect(str(db))
    conn.execute(
        "UPDATE metrics_trend SET reason_code='mixed_era_window' "
        "WHERE metric_id='capex_pct_net_income_avg10y'"
    )
    conn.close()

    build_scores(warehouse_path=db)

    row = _fetch(
        db,
        "SELECT coverage_ratio, applicable_criteria, total_criteria, "
        "era_unavailable_criteria FROM score_components "
        "WHERE component_id='capital_allocation'",
    )[0]
    coverage, applicable, total, era_out = row
    assert (total, era_out, applicable) == (4, 1, 3)
    # 3 of 3 measurable, not 3 of 4.
    assert coverage == pytest.approx(1.0)


def test_era_guarded_criterion_raises_the_era_limited_badge(tmp_path) -> None:
    """Removing it from the denominator must not make the limit invisible."""
    db = tmp_path / "research.duckdb"
    trend = dict(_TREND_VALUES)
    trend["capex_pct_net_income_avg10y"] = None
    _seed(db, trend=trend, quarterly=_QUARTERLY_VALUES)
    conn = duckdb.connect(str(db))
    conn.execute(
        "UPDATE metrics_trend SET reason_code='mixed_era_window' "
        "WHERE metric_id='capex_pct_net_income_avg10y'"
    )
    conn.close()

    result = build_scores(warehouse_path=db)

    badges = _fetch(db, "SELECT badges FROM scores")[0][0]
    assert ScoreBadge.ERA_LIMITED.value in badges
    assert result["badge_counts"].get(ScoreBadge.ERA_LIMITED.value) == 1


def test_a_company_specific_gap_still_counts_against_coverage(tmp_path) -> None:
    """The control: an ordinary missing input must still lower coverage."""
    db = tmp_path / "research.duckdb"
    trend = dict(_TREND_VALUES)
    trend["capex_pct_net_income_avg10y"] = None  # reason defaults to insufficient_history
    _seed(db, trend=trend, quarterly=_QUARTERLY_VALUES)

    build_scores(warehouse_path=db)

    coverage, era_out = _fetch(
        db,
        "SELECT coverage_ratio, era_unavailable_criteria FROM score_components "
        "WHERE component_id='capital_allocation'",
    )[0]
    assert era_out == 0
    assert coverage == pytest.approx(0.75)
    badges = _fetch(db, "SELECT badges FROM scores")[0][0]
    assert ScoreBadge.ERA_LIMITED.value not in badges
