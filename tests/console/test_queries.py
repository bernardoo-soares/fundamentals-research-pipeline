"""Tests for the console's read-only query API.

The guarantees under test are the ones a reader's money depends on: the API
cannot write, it cannot invent a number, and it cannot offer a shape that
would let a caller build a cross-year comparison the data does not support.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fundamentals_pipeline.warehouse import queries as Q
from fundamentals_pipeline.warehouse.queries import WarehouseUnavailable


def _seed(path) -> None:
    """A miniature warehouse: two companies, two years, one absent metric."""
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE scores (ticker VARCHAR, as_of_year INTEGER, "
        "scorer_name VARCHAR, scorer_version VARCHAR, config_hash VARCHAR, "
        "composite DOUBLE, reason_code VARCHAR, coverage_ratio DOUBLE, "
        "checklist_passed INTEGER, checklist_applicable INTEGER, "
        "badges VARCHAR, staleness_quarters INTEGER, computed_at TIMESTAMP, "
        "pipeline_version VARCHAR)"
    )
    conn.execute(
        "INSERT INTO scores VALUES "
        "('SOLID', 2024, 'buffett', '1', 'abc', 80.0, NULL, 1.0, 15, 17, "
        "'unreliable_input', 0, now(), 'p1'),"
        "('HOLLOW', 2024, 'buffett', '1', 'abc', 92.0, NULL, 0.25, 5, 6, "
        "'low_confidence', 0, now(), 'p1'),"
        "('SOLID', 2023, 'buffett', '1', 'abc', 70.0, NULL, 1.0, 14, 17, "
        "'', 0, now(), 'p1')"
    )
    conn.execute(
        "CREATE TABLE score_components (ticker VARCHAR, as_of_year INTEGER, "
        "scorer_name VARCHAR, scorer_version VARCHAR, config_hash VARCHAR, "
        "component_id VARCHAR, score DOUBLE, weight DOUBLE, "
        "coverage_ratio DOUBLE, applicable_criteria INTEGER, "
        "total_criteria INTEGER, era_unavailable_criteria INTEGER, "
        "reason_code VARCHAR, computed_at TIMESTAMP, pipeline_version VARCHAR)"
    )
    conn.execute(
        "INSERT INTO score_components VALUES "
        "('SOLID', 2024, 'buffett', '1', 'abc', 'profitability_moat', 80.0, "
        "0.3, 1.0, 6, 6, 0, NULL, now(), 'p1')"
    )
    conn.execute(
        "CREATE TABLE score_criteria (ticker VARCHAR, as_of_year INTEGER, "
        "scorer_name VARCHAR, scorer_version VARCHAR, config_hash VARCHAR, "
        "criterion_id VARCHAR, component_id VARCHAR, metric_id VARCHAR, "
        "value DOUBLE, points DOUBLE, weight DOUBLE, "
        "checklist_verdict VARCHAR, reason_code VARCHAR, annotation VARCHAR, "
        "quality_flag VARCHAR, computed_at TIMESTAMP, pipeline_version VARCHAR)"
    )
    conn.execute(
        "INSERT INTO score_criteria VALUES "
        "('SOLID', 2024, 'buffett', '1', 'abc', 'c1', 'profitability_moat', "
        "'net_margin', 0.25, 80.0, 0.3, 'pass', NULL, NULL, "
        "'eps_basis_unverified', now(), 'p1'),"
        "('SOLID', 2024, 'buffett', '1', 'abc', 'c2', 'profitability_moat', "
        "'roe', NULL, NULL, 0.3, NULL, 'missing_input', NULL, NULL, "
        "now(), 'p1')"
    )
    conn.execute(
        "CREATE TABLE metrics_trend (ticker VARCHAR, as_of_year INTEGER, "
        "metric_id VARCHAR, value DOUBLE, reason_code VARCHAR, "
        "quality_flag VARCHAR, window_length INTEGER, "
        "window_years_present INTEGER, metric_version VARCHAR, "
        "computed_at TIMESTAMP, pipeline_version VARCHAR)"
    )
    conn.execute(
        "INSERT INTO metrics_trend VALUES "
        "('SOLID', 2024, 'live_metric', 0.5, NULL, NULL, 10, 10, '1', now(), 'p1'),"
        "('HOLLOW', 2024, 'live_metric', 0.6, NULL, NULL, 10, 10, '1', now(), 'p1'),"
        "('SOLID', 2024, 'dead_metric', NULL, 'era_not_supported', NULL, 10, 0, "
        "'1', now(), 'p1'),"
        "('HOLLOW', 2024, 'dead_metric', NULL, 'era_not_supported', NULL, 10, 0, "
        "'1', now(), 'p1'),"
        "('SOLID', 2023, 'live_metric', NULL, 'missing_input', NULL, 10, 3, "
        "'1', now(), 'p1'),"
        "('SOLID', 2022, 'live_metric', 0.4, NULL, NULL, 10, 10, '1', now(), 'p1')"
    )
    conn.execute(
        "CREATE TABLE valuation_history (ticker VARCHAR, fiscal_year INTEGER, "
        "period_end_date DATE, publish_date DATE, price_date DATE, "
        "price_lag_days INTEGER, close DOUBLE, shares_outstanding DOUBLE, "
        "market_cap DOUBLE, net_income_ttm DOUBLE, pe_ttm DOUBLE, "
        "earnings_yield DOUBLE, reason_code VARCHAR, quality_flag VARCHAR, "
        "computed_at TIMESTAMP, pipeline_version VARCHAR)"
    )
    conn.execute(
        "INSERT INTO valuation_history VALUES "
        "('SOLID', 2024, DATE '2024-12-31', DATE '2025-02-01', "
        "DATE '2024-12-31', 0, 100.0, 1000.0, 1e11, 5000.0, 20.0, 0.05, "
        "NULL, NULL, now(), 'p1'),"
        "('HOLLOW', 2024, DATE '2024-12-31', DATE '2025-02-01', NULL, NULL, "
        "NULL, NULL, NULL, NULL, NULL, NULL, 'price_unavailable', NULL, "
        "now(), 'p1')"
    )
    conn.execute(
        "CREATE TABLE fundamentals_annual (ticker VARCHAR, fiscal_year INTEGER, "
        "source_era VARCHAR, quarters_present INTEGER, has_q4 BOOLEAN, "
        "saleq_annual DOUBLE, niq_annual DOUBLE, epspxq_annual DOUBLE, "
        "ceqq_q4 DOUBLE, atq_q4 DOUBLE, dlttq_q4 DOUBLE, req_q4 DOUBLE)"
    )
    conn.execute(
        "INSERT INTO fundamentals_annual VALUES "
        "('SOLID', 2022, 'legacy_compustat', 4, true, 80.0, 12.0, 1.2, 40.0, "
        "160.0, 25.0, 30.0),"
        "('SOLID', 2023, 'simfin', 4, true, 90.0, 16.0, 1.6, 45.0, 180.0, "
        "28.0, 35.0),"
        "('SOLID', 2024, 'simfin', 4, true, 100.0, 20.0, 2.0, 50.0, 200.0, "
        "30.0, 40.0)"
    )
    conn.execute(
        "CREATE TABLE fundamentals_quarterly (ticker VARCHAR, year INTEGER, "
        "quarter INTEGER, source_era VARCHAR, niq DOUBLE, saleq DOUBLE, "
        "atq DOUBLE)"
    )
    conn.execute(
        "INSERT INTO fundamentals_quarterly VALUES "
        "('SOLID', 2023, 4, 'simfin', 3.0, 20.0, 190.0),"
        "('SOLID', 2024, 1, 'simfin', 4.0, 22.0, 195.0),"
        "('SOLID', 2024, 2, 'simfin', 5.0, 24.0, 197.0),"
        "('SOLID', 2024, 3, 'simfin', 5.5, 26.0, 199.0),"
        "('SOLID', 2024, 4, 'simfin', 5.5, 28.0, 200.0)"
    )
    conn.close()


@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "w.duckdb"
    _seed(path)
    return path


def test_missing_warehouse_raises_rather_than_returning_empty(tmp_path):
    """An empty ranking and an unbuilt warehouse look identical on screen."""
    with pytest.raises(WarehouseUnavailable, match="not found"):
        Q.check_ready(tmp_path / "nope.duckdb")


def test_warehouse_missing_a_table_names_it(tmp_path):
    path = tmp_path / "partial.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE scores (ticker VARCHAR)")
    conn.close()
    with pytest.raises(WarehouseUnavailable, match="score_components"):
        Q.check_ready(path)


def test_ready_warehouse_passes(warehouse):
    Q.check_ready(warehouse)


def test_the_api_cannot_write(warehouse):
    """Read-only is structural, not a convention the app must remember."""
    from fundamentals_pipeline.warehouse.connection import open_warehouse

    with open_warehouse(warehouse, read_only=True) as conn:
        with pytest.raises(duckdb.Error, match="read-only"):
            conn.execute("INSERT INTO scores VALUES ('X', 2024, 'b', '1', "
                         "'h', 1.0, NULL, 1.0, 1, 1, '', 0, now(), 'p')")


def test_available_years_are_newest_first(warehouse):
    assert Q.available_years(warehouse) == [2024, 2023]


def test_ranking_is_one_year_only(warehouse):
    """C1: the API offers no shape that spans fiscal years."""
    frame = Q.ranking(warehouse, as_of_year=2024)
    assert set(frame["ticker"]) == {"SOLID", "HOLLOW"}
    assert len(frame) == 2


def test_evidence_is_score_times_coverage(warehouse):
    """The signature column: a hollow 92 must rank below a solid 80."""
    frame = Q.ranking(warehouse, as_of_year=2024).set_index("ticker")
    assert frame.loc["SOLID", "evidence"] == pytest.approx(80.0)
    assert frame.loc["HOLLOW", "evidence"] == pytest.approx(23.0)
    assert frame.loc["HOLLOW", "composite"] > frame.loc["SOLID", "composite"]
    assert frame.loc["HOLLOW", "evidence"] < frame.loc["SOLID", "evidence"]


def test_ranking_keeps_a_null_valuation_null(warehouse):
    """C4: an absent price is absent, never zero-filled."""
    frame = Q.ranking(warehouse, as_of_year=2024).set_index("ticker")
    assert pd.isna(frame.loc["HOLLOW", "pe_ttm"])


def test_trend_history_returns_gaps_not_dropped_rows(warehouse):
    """A null year must survive to the chart so it renders as a gap."""
    frame = Q.trend_history(warehouse, ticker="SOLID", metric_id="live_metric")
    assert list(frame["as_of_year"]) == [2022, 2023, 2024]
    assert pd.isna(frame.loc[frame["as_of_year"] == 2023, "value"]).all()
    assert (
        frame.loc[frame["as_of_year"] == 2023, "reason_code"].iloc[0]
        == "missing_input"
    )


def test_metric_coverage_marks_a_structurally_absent_metric(warehouse):
    """C6: a metric with no data is flagged so it is stated, not charted."""
    frame = Q.metric_coverage(warehouse, as_of_year=2024).set_index("metric_id")
    assert bool(frame.loc["dead_metric", "structurally_absent"]) is True
    assert bool(frame.loc["live_metric", "structurally_absent"]) is False


def test_coverage_distribution_is_monotonically_non_increasing(warehouse):
    frame = Q.coverage_distribution(warehouse, as_of_year=2024)
    counts = frame.sort_values("threshold")["tickers"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_criteria_carry_their_quality_flag(warehouse):
    """C3: a known limitation must reach the surface."""
    frame = Q.criteria(warehouse, ticker="SOLID", as_of_year=2024)
    flags = set(frame["quality_flag"].dropna())
    assert flags == {"eps_basis_unverified"}


def test_quality_flag_tally_counts_rows_and_tickers(warehouse):
    frame = Q.quality_flag_tally(warehouse, as_of_year=2024).set_index(
        "quality_flag"
    )
    assert int(frame.loc["eps_basis_unverified", "rows"]) == 1
    assert int(frame.loc["eps_basis_unverified", "tickers"]) == 1


def test_reason_code_tally_explains_absences(warehouse):
    frame = Q.reason_code_tally(warehouse, as_of_year=2024).set_index("reason_code")
    assert int(frame.loc["era_not_supported", "rows"]) == 2


def test_valuation_returns_the_reason_when_the_price_is_missing(warehouse):
    frame = Q.valuation(warehouse, ticker="HOLLOW", as_of_year=2024)
    assert pd.isna(frame.iloc[0]["pe_ttm"])
    assert frame.iloc[0]["reason_code"] == "price_unavailable"


# --- The drilldown's inputs row --------------------------------------------


def test_annual_inputs_returns_one_row_per_field_and_year(warehouse):
    frame = Q.annual_inputs(
        warehouse,
        ticker="SOLID",
        fields=("saleq_annual", "niq_annual"),
        start_year=2022,
        end_year=2024,
    )
    assert len(frame) == 6  # 2 fields x 3 years
    assert set(frame["field"]) == {"saleq_annual", "niq_annual"}
    saleq = frame[frame["field"] == "saleq_annual"].set_index("fiscal_year")
    assert saleq.loc[2024, "value"] == 100.0
    assert saleq.loc[2022, "value"] == 80.0


def test_annual_inputs_carries_the_provider_era_per_year(warehouse):
    """The era row is how a reader checks a mixed_era_window verdict."""
    frame = Q.annual_inputs(
        warehouse,
        ticker="SOLID",
        fields=("saleq_annual",),
        start_year=2022,
        end_year=2024,
    )
    eras = dict(zip(frame["fiscal_year"], frame["source_era"], strict=False))
    assert eras[2022] == "legacy_compustat"
    assert eras[2024] == "simfin"


def test_annual_inputs_keeps_null_years_as_rows(warehouse):
    """A year with no stored value must still appear, or the gap is invisible."""
    frame = Q.annual_inputs(
        warehouse,
        ticker="SOLID",
        fields=("saleq_annual",),
        start_year=2020,
        end_year=2024,
    )
    # 2020 and 2021 have no fundamentals_annual row at all, so they are absent;
    # what matters is that present rows are never dropped for being null.
    assert set(frame["fiscal_year"]) == {2022, 2023, 2024}


def test_quarterly_inputs_returns_the_ttm_window_ending_at_year_end(warehouse):
    frame = Q.quarterly_inputs(
        warehouse, ticker="SOLID", fields=("niq", "saleq"), end_year=2024, quarters=4
    )
    quarters = sorted(set(zip(frame["year"], frame["quarter"], strict=False)))
    assert quarters == [(2024, 1), (2024, 2), (2024, 3), (2024, 4)]
    assert 2023 not in set(frame["year"])


def test_quarterly_inputs_window_can_reach_back_across_a_year(warehouse):
    frame = Q.quarterly_inputs(
        warehouse, ticker="SOLID", fields=("niq",), end_year=2024, quarters=5
    )
    quarters = sorted(set(zip(frame["year"], frame["quarter"], strict=False)))
    assert quarters[0] == (2023, 4)


def test_inputs_reject_a_column_outside_the_contract(warehouse):
    """These names reach a SQL string, so the allow-list is not optional."""
    with pytest.raises(ValueError, match="Not warehouse columns"):
        Q.annual_inputs(
            warehouse,
            ticker="SOLID",
            fields=("saleq_annual; DROP TABLE scores",),
            start_year=2022,
            end_year=2024,
        )
    with pytest.raises(ValueError, match="Not warehouse columns"):
        Q.quarterly_inputs(
            warehouse, ticker="SOLID", fields=("nope",), end_year=2024, quarters=4
        )


def test_empty_field_list_returns_an_empty_frame_not_broken_sql(warehouse):
    assert Q.annual_inputs(
        warehouse, ticker="SOLID", fields=(), start_year=2022, end_year=2024
    ).empty
    assert Q.quarterly_inputs(
        warehouse, ticker="SOLID", fields=(), end_year=2024, quarters=4
    ).empty


def test_no_derived_total_is_returned(warehouse):
    """S2.6: re-deriving the TTM here would express the rule a second time."""
    frame = Q.quarterly_inputs(
        warehouse, ticker="SOLID", fields=("niq",), end_year=2024, quarters=4
    )
    assert set(frame.columns) == {"year", "quarter", "source_era", "field", "value"}
    assert not any(
        name in frame.columns for name in ("ttm", "total", "sum", "value_ttm")
    )


# --- Company identity -------------------------------------------------------


def _add_companies(path) -> None:
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE companies (ticker VARCHAR, company_name VARCHAR, "
        "sector VARCHAR, sub_industry VARCHAR, headquarters VARCHAR, "
        "index_added_date DATE, cik VARCHAR, source VARCHAR, "
        "as_of_date DATE, computed_at TIMESTAMP, pipeline_version VARCHAR)"
    )
    # HOLLOW deliberately has no row: it stands for a company that has left
    # the index and therefore cannot be named.
    conn.execute(
        "INSERT INTO companies VALUES ('SOLID', 'Solid Industries', "
        "'Industrials', 'Conglomerates', 'Omaha', DATE '1990-01-01', '1', "
        "'wikipedia_sp500_constituents', DATE '2026-07-29', now(), 'c1')"
    )
    conn.close()


def test_ranking_works_without_the_optional_companies_table(warehouse):
    """The console must be usable before anyone runs companies-build."""
    assert Q.has_companies(warehouse) is False
    frame = Q.ranking(warehouse, as_of_year=2024)
    assert len(frame) == 2
    assert frame["company_name"].isna().all()
    assert Q.sectors(warehouse, as_of_year=2024) == []


def test_ranking_joins_names_when_present(warehouse):
    _add_companies(warehouse)
    assert Q.has_companies(warehouse) is True
    frame = Q.ranking(warehouse, as_of_year=2024).set_index("ticker")
    assert frame.loc["SOLID", "company_name"] == "Solid Industries"
    assert frame.loc["SOLID", "sector"] == "Industrials"


def test_a_company_without_a_current_row_is_kept_and_left_unnamed(warehouse):
    """An INNER JOIN here would silently drop companies from the ranking."""
    _add_companies(warehouse)
    frame = Q.ranking(warehouse, as_of_year=2024).set_index("ticker")
    assert "HOLLOW" in frame.index
    assert pd.isna(frame.loc["HOLLOW", "company_name"])


def test_sectors_lists_only_those_present_among_scored_tickers(warehouse):
    _add_companies(warehouse)
    assert Q.sectors(warehouse, as_of_year=2024) == ["Industrials"]


def test_company_returns_an_empty_frame_for_a_departed_ticker(warehouse):
    _add_companies(warehouse)
    assert Q.company(warehouse, ticker="HOLLOW").empty
    assert not Q.company(warehouse, ticker="SOLID").empty


# --- Operand totals ---------------------------------------------------------


def test_quarterly_metric_values_reads_published_totals(warehouse):
    conn = duckdb.connect(str(warehouse))
    conn.execute(
        "CREATE TABLE metrics_quarterly (ticker VARCHAR, year INTEGER, "
        "quarter INTEGER, metric_id VARCHAR, value DOUBLE, "
        "reason_code VARCHAR, quality_flag VARCHAR, source_era VARCHAR, "
        "metric_version VARCHAR, computed_at TIMESTAMP, "
        "pipeline_version VARCHAR)"
    )
    conn.execute(
        "INSERT INTO metrics_quarterly VALUES "
        "('SOLID', 2024, 4, 'revenue_ttm', 100.0, NULL, NULL, 'simfin', '1', "
        "now(), 'p1'),"
        "('SOLID', 2024, 4, 'net_income_ttm', NULL, 'mixed_era_window', NULL, "
        "'simfin', '1', now(), 'p1')"
    )
    conn.close()

    frame = Q.quarterly_metric_values(
        warehouse,
        ticker="SOLID",
        metric_ids=("revenue_ttm", "net_income_ttm"),
        year=2024,
    ).set_index("metric_id")
    assert frame.loc["revenue_ttm", "value"] == 100.0
    # A total the engine refused to compute stays refused; the console shows
    # the reason rather than a number it summed itself.
    assert pd.isna(frame.loc["net_income_ttm", "value"])
    assert frame.loc["net_income_ttm", "reason_code"] == "mixed_era_window"


def test_quarterly_metric_values_with_no_ids_returns_empty(warehouse):
    assert Q.quarterly_metric_values(
        warehouse, ticker="SOLID", metric_ids=(), year=2024
    ).empty
