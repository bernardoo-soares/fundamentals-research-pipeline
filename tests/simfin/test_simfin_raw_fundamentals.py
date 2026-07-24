from __future__ import annotations

import pandas as pd

from fundamentals_pipeline import __main__ as cli
from fundamentals_pipeline.connectors.simfin_dataset_loader import SimfinConnector
from fundamentals_pipeline.steps.simfin_raw_fundamentals_builder import (
    build_simfin_raw_fundamentals,
)


def _write_simfin_csv(path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, sep=";", index=False)


def _build_cache(cache_dir) -> None:
    _write_simfin_csv(
        cache_dir / "us-income-quarterly.csv",
        [
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-05-01",
                "Restated Date": "2023-05-01",
                "Shares (Basic)": 10.0,
                "Shares (Diluted)": 11.0,
                "Revenue": 100.0,
                "Operating Income (Loss)": 30.0,
                "Interest Expense, Net": 5.0,
                "Income Tax (Expense) Benefit, Net": 4.0,
                "Net Income": 20.0,
                "Net Income (Common)": 20.0,
                "Cost of Revenue": -60.0,
                "Gross Profit": 40.0,
                "Selling, General & Administrative": -12.0,
                "Research & Development": -8.0,
                "Depreciation & Amortization": 999.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Revenue",
            "Operating Income (Loss)",
            "Interest Expense, Net",
            "Income Tax (Expense) Benefit, Net",
            "Net Income",
            "Net Income (Common)",
            "Cost of Revenue",
            "Gross Profit",
            "Selling, General & Administrative",
            "Research & Development",
            "Depreciation & Amortization",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-balance-quarterly.csv",
        [
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-05-01",
                "Restated Date": "2023-05-01",
                "Shares (Basic)": 10.0,
                "Shares (Diluted)": 11.0,
                "Cash, Cash Equivalents & Short Term Investments": 50.0,
                "Total Current Assets": 80.0,
                "Property, Plant & Equipment, Net": 300.0,
                "Long Term Investments & Receivables": 60.0,
                "Total Assets": 500.0,
                "Short Term Debt": 15.0,
                "Total Current Liabilities": 40.0,
                "Long Term Debt": 100.0,
                "Treasury Stock": 8.0,
                "Retained Earnings": 90.0,
                "Total Equity": 200.0,
                "Goodwill": 12.0,
                "Inventories": 30.0,
                "Accounts & Notes Receivable": 22.0,
                "Total Liabilities": 300.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Cash, Cash Equivalents & Short Term Investments",
            "Total Current Assets",
            "Property, Plant & Equipment, Net",
            "Long Term Investments & Receivables",
            "Total Assets",
            "Short Term Debt",
            "Total Current Liabilities",
            "Long Term Debt",
            "Treasury Stock",
            "Retained Earnings",
            "Total Equity",
            "Goodwill",
            "Inventories",
            "Accounts & Notes Receivable",
            "Total Liabilities",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-quarterly.csv",
        [
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-05-01",
                "Restated Date": "2023-05-01",
                "Shares (Basic)": 10.0,
                "Shares (Diluted)": 11.0,
                "Net Cash from Operating Activities": 25.0,
                "Change in Fixed Assets & Intangibles": -9.0,
                "Dividends Paid": -3.0,
                "Cash from (Repurchase of) Equity": -7.0,
                "Depreciation & Amortization": 11.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Dividends Paid",
            "Cash from (Repurchase of) Equity",
            "Depreciation & Amortization",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-annual.csv",
        [
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Report Date": "2023-09-30",
                "Publish Date": "2023-11-01",
                "Restated Date": "2023-11-01",
                "Net Cash from Operating Activities": 120.0,
                "Change in Fixed Assets & Intangibles": -36.0,
                "Cash from (Repurchase of) Equity": -28.0,
                "Dividends Paid": -12.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Cash from (Repurchase of) Equity",
            "Dividends Paid",
        ],
    )

    _write_simfin_csv(
        cache_dir / "us-income-banks-quarterly.csv",
        [
            {
                "Ticker": "ABCB",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-04-28",
                "Restated Date": "2023-04-28",
                "Shares (Basic)": 20.0,
                "Shares (Diluted)": 21.0,
                "Revenue": 200.0,
                "Operating Income (Loss)": 40.0,
                "Income Tax (Expense) Benefit, Net": 6.0,
                "Net Income": 30.0,
                "Net Income (Common)": 30.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Revenue",
            "Operating Income (Loss)",
            "Income Tax (Expense) Benefit, Net",
            "Net Income",
            "Net Income (Common)",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-balance-banks-quarterly.csv",
        [
            {
                "Ticker": "ABCB",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-04-28",
                "Restated Date": "2023-04-28",
                "Shares (Basic)": 20.0,
                "Shares (Diluted)": 21.0,
                "Cash, Cash Equivalents & Short Term Investments": 70.0,
                "Short & Long Term Investments": 600.0,
                "Net Fixed Assets": 500.0,
                "Total Assets": 900.0,
                "Short Term Debt": 25.0,
                "Long Term Debt": 35.0,
                "Treasury Stock": 2.0,
                "Retained Earnings": 110.0,
                "Total Equity": 300.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Cash, Cash Equivalents & Short Term Investments",
            "Short & Long Term Investments",
            "Net Fixed Assets",
            "Total Assets",
            "Short Term Debt",
            "Long Term Debt",
            "Treasury Stock",
            "Retained Earnings",
            "Total Equity",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-banks-quarterly.csv",
        [
            {
                "Ticker": "ABCB",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-04-28",
                "Restated Date": "2023-04-28",
                "Shares (Basic)": 20.0,
                "Shares (Diluted)": 21.0,
                "Net Cash from Operating Activities": 45.0,
                "Change in Fixed Assets & Intangibles": -5.0,
                "Dividends Paid": -4.0,
                "Cash from (Repurchase of) Equity": -9.0,
                "Depreciation & Amortization": 7.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Dividends Paid",
            "Cash from (Repurchase of) Equity",
            "Depreciation & Amortization",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-banks-annual.csv",
        [],
        [
            "Ticker",
            "Fiscal Year",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Cash from (Repurchase of) Equity",
        ],
    )

    _write_simfin_csv(
        cache_dir / "us-income-insurance-quarterly.csv",
        [],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Revenue",
            "Operating Income (Loss)",
            "Income Tax (Expense) Benefit, Net",
            "Net Income",
            "Net Income (Common)",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-balance-insurance-quarterly.csv",
        [],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Total Investments",
            "Cash, Cash Equivalents & Short Term Investments",
            "Property, Plant & Equipment, Net",
            "Total Assets",
            "Short Term Debt",
            "Long Term Debt",
            "Treasury Stock",
            "Retained Earnings",
            "Total Equity",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-insurance-quarterly.csv",
        [],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Dividends Paid",
            "Cash from (Repurchase of) Equity",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-insurance-annual.csv",
        [],
        [
            "Ticker",
            "Fiscal Year",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Cash from (Repurchase of) Equity",
        ],
    )


def test_build_simfin_raw_fundamentals_writes_yearly_outputs_and_reports(tmp_path) -> None:
    cache_dir = tmp_path / "simfin_cache"
    _build_cache(cache_dir)

    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["AAPL", "ABCB", "MISS"]}).to_csv(universe_path, index=False)

    artifacts = build_simfin_raw_fundamentals(
        universe_path=universe_path,
        output_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
        start_year=2023,
        end_year=2023,
        connector=SimfinConnector(data_dir=cache_dir),
    )

    year_df = pd.read_csv(artifacts["processed_2023"])
    assert list(year_df.columns[:3]) == ["ticker", "year", "quarter"]
    assert set(year_df["ticker"]) == {"AAPL", "ABCB"}

    aapl = year_df[year_df["ticker"] == "AAPL"].iloc[0]
    assert aapl["saleq"] == 0.0001
    assert aapl["xintq"] == 0.000005
    assert aapl["actq"] == 0.00008
    assert aapl["lctq"] == 0.00004
    assert aapl["prstkcq"] == 0.000007
    assert aapl["capxq"] == 0.000009
    # dvpq is preferred dividends; SimFin has no such column, so it is null.
    # Total dividends live in dvy (annual "Dividends Paid" -12.0 -> 1.2e-5).
    assert pd.isna(aapl["dvpq"])
    assert aapl["dvy"] == 0.000012
    assert aapl["epspxq"] == 2.0
    assert aapl["oancfy"] == 0.00012
    assert aapl["capxy"] == 0.000036
    assert aapl["prstkcy"] == 0.000028
    assert pd.isna(aapl["cshopq"])
    assert aapl["cogsq"] == 0.00006
    assert aapl["xsgaq"] == 0.000012
    assert aapl["xrdq"] == 0.000008
    assert aapl["ltq"] == 0.0003
    assert aapl["invtq"] == 0.00003
    assert aapl["rectq"] == 0.000022
    assert aapl["dpq"] == 0.000011  # cashflow D&A 11.0, NOT income decoy 999.0

    abcb = year_df[year_df["ticker"] == "ABCB"].iloc[0]
    assert pd.isna(abcb["xintq"])
    assert pd.isna(abcb["actq"])
    assert pd.isna(abcb["lctq"])
    assert abcb["ppentq"] == 0.0005
    assert abcb["ivltq"] == 0.0006
    assert abcb["prstkcq"] == 0.000009
    assert pd.isna(abcb["cogsq"])
    assert pd.isna(abcb["xsgaq"])
    assert pd.isna(abcb["xrdq"])
    assert pd.isna(abcb["invtq"])
    assert abcb["dpq"] == 0.000007

    coverage = pd.read_csv(artifacts["coverage_output"])
    assert coverage.loc[0, "rows_emitted"] == 2
    assert coverage.loc[0, "unique_tickers_emitted"] == 2

    unit_report = pd.read_csv(artifacts["unit_normalization_output"])
    saleq_report = unit_report[unit_report["field_name"] == "saleq"].iloc[0]
    assert saleq_report["scale_divisor_applied"] == 1_000_000.0
    assert saleq_report["source_system"] == "simfin"

    missing_universe = pd.read_csv(artifacts["missing_universe_output"])
    assert missing_universe.to_dict(orient="records") == [
        {"ticker": "MISS", "reason": "no_rows_in_year_window"}
    ]

    missing_rows = pd.read_csv(artifacts["missing_rows_output"])
    assert (
        missing_rows[
            (missing_rows["ticker"] == "MISS")
            & (missing_rows["year"] == 2023)
            & (missing_rows["quarter"] == 1)
        ]["reason"].iloc[0]
        == "missing_simfin_quarter"
    )

    missing_fields = pd.read_csv(artifacts["missing_fields_output"])
    assert not (
        (missing_fields["ticker"] == "AAPL")
        & (missing_fields["field_name"] == "capxy")
    ).any()
    assert (
        missing_fields[
            (missing_fields["ticker"] == "AAPL")
            & (missing_fields["field_name"] == "cshopq")
        ]["reason"].iloc[0]
        == "null_simfin_field"
    )


def test_build_simfin_raw_fundamentals_expands_validated_alias_tickers(tmp_path) -> None:
    cache_dir = tmp_path / "simfin_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _write_simfin_csv(
        cache_dir / "us-income-quarterly.csv",
        [
            {
                "Ticker": "GOOG",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-04-30",
                "Restated Date": "2023-04-30",
                "Shares (Basic)": 10.0,
                "Shares (Diluted)": 11.0,
                "Revenue": 100.0,
                "Operating Income (Loss)": 30.0,
                "Interest Expense, Net": 1.0,
                "Income Tax (Expense) Benefit, Net": 4.0,
                "Net Income": 20.0,
                "Net Income (Common)": 20.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Shares (Basic)",
            "Shares (Diluted)",
            "Revenue",
            "Operating Income (Loss)",
            "Interest Expense, Net",
            "Income Tax (Expense) Benefit, Net",
            "Net Income",
            "Net Income (Common)",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-balance-quarterly.csv",
        [
            {
                "Ticker": "GOOG",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-04-30",
                "Restated Date": "2023-04-30",
                "Cash, Cash Equivalents & Short Term Investments": 50.0,
                "Total Current Assets": 80.0,
                "Property, Plant & Equipment, Net": 300.0,
                "Long Term Investments & Receivables": 60.0,
                "Total Assets": 500.0,
                "Short Term Debt": 15.0,
                "Total Current Liabilities": 40.0,
                "Long Term Debt": 100.0,
                "Treasury Stock": 8.0,
                "Retained Earnings": 90.0,
                "Total Equity": 200.0,
                "Goodwill": 12.0,
                "Shares (Basic)": 10.0,
                "Shares (Diluted)": 11.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Cash, Cash Equivalents & Short Term Investments",
            "Total Current Assets",
            "Property, Plant & Equipment, Net",
            "Long Term Investments & Receivables",
            "Total Assets",
            "Short Term Debt",
            "Total Current Liabilities",
            "Long Term Debt",
            "Treasury Stock",
            "Retained Earnings",
            "Total Equity",
            "Goodwill",
            "Shares (Basic)",
            "Shares (Diluted)",
        ],
    )
    _write_simfin_csv(
        cache_dir / "us-cashflow-quarterly.csv",
        [
            {
                "Ticker": "GOOG",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Report Date": "2023-03-31",
                "Publish Date": "2023-04-30",
                "Restated Date": "2023-04-30",
                "Net Cash from Operating Activities": 25.0,
                "Change in Fixed Assets & Intangibles": -9.0,
                "Dividends Paid": -3.0,
                "Cash from (Repurchase of) Equity": -7.0,
                "Shares (Basic)": 10.0,
                "Shares (Diluted)": 11.0,
            }
        ],
        [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Publish Date",
            "Restated Date",
            "Net Cash from Operating Activities",
            "Change in Fixed Assets & Intangibles",
            "Dividends Paid",
            "Cash from (Repurchase of) Equity",
            "Shares (Basic)",
            "Shares (Diluted)",
        ],
    )
    _write_simfin_csv(cache_dir / "us-income-banks-quarterly.csv", [], ["Ticker", "Fiscal Year", "Fiscal Period"])
    _write_simfin_csv(cache_dir / "us-balance-banks-quarterly.csv", [], ["Ticker", "Fiscal Year", "Fiscal Period"])
    _write_simfin_csv(cache_dir / "us-cashflow-banks-quarterly.csv", [], ["Ticker", "Fiscal Year", "Fiscal Period"])
    _write_simfin_csv(cache_dir / "us-income-insurance-quarterly.csv", [], ["Ticker", "Fiscal Year", "Fiscal Period"])
    _write_simfin_csv(cache_dir / "us-balance-insurance-quarterly.csv", [], ["Ticker", "Fiscal Year", "Fiscal Period"])
    _write_simfin_csv(cache_dir / "us-cashflow-insurance-quarterly.csv", [], ["Ticker", "Fiscal Year", "Fiscal Period"])
    _write_simfin_csv(cache_dir / "us-cashflow-annual.csv", [], ["Ticker", "Fiscal Year"])
    _write_simfin_csv(cache_dir / "us-cashflow-banks-annual.csv", [], ["Ticker", "Fiscal Year"])
    _write_simfin_csv(cache_dir / "us-cashflow-insurance-annual.csv", [], ["Ticker", "Fiscal Year"])

    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["GOOG", "GOOGL"]}).to_csv(universe_path, index=False)

    artifacts = build_simfin_raw_fundamentals(
        universe_path=universe_path,
        output_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
        start_year=2023,
        end_year=2023,
        connector=SimfinConnector(data_dir=cache_dir),
    )

    year_df = pd.read_csv(artifacts["processed_2023"])
    assert set(year_df["ticker"]) == {"GOOG", "GOOGL"}

    alias_report = pd.read_csv(artifacts["alias_output"])
    googl = alias_report[alias_report["requested_ticker"] == "GOOGL"].iloc[0]
    assert bool(googl["alias_applied"]) is True
    assert googl["provider_ticker"] == "GOOG"
    assert googl["rows_emitted"] == 1


def test_simfin_cogs_falls_back_to_revenue_minus_gross_profit(tmp_path) -> None:
    cache_dir = tmp_path / "simfin_cache"
    _build_cache(cache_dir)

    income_path = cache_dir / "us-income-quarterly.csv"
    income = pd.read_csv(income_path, sep=";")
    income.loc[income["Ticker"] == "AAPL", "Cost of Revenue"] = None
    income.to_csv(income_path, sep=";", index=False)

    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)

    artifacts = build_simfin_raw_fundamentals(
        universe_path=universe_path,
        output_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
        start_year=2023,
        end_year=2023,
        connector=SimfinConnector(data_dir=cache_dir),
    )

    year_df = pd.read_csv(artifacts["processed_2023"])
    aapl = year_df[year_df["ticker"] == "AAPL"].iloc[0]
    # Revenue 100.0 − Gross Profit 40.0 = 60.0 → published 0.00006
    assert aapl["cogsq"] == 0.00006


def test_cli_simfin_raw_fundamentals_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return {
            "processed_2023": "data/processed/raw_fundamentals_2023.csv",
            "coverage_output": "data/reports/simfin_raw_coverage_2023_2023.csv",
        }

    monkeypatch.setattr(cli, "build_simfin_raw_fundamentals", _fake_build)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fundamentals-pipeline",
            "simfin-raw-fundamentals",
            "--universe-path",
            "data/universe_current.csv",
            "--output-dir",
            "data/processed",
            "--reports-dir",
            "data/reports",
            "--start-year",
            "2023",
            "--end-year",
            "2025",
            "--refresh-quarterly-cache",
            "--quarterly-refresh-days",
            "0",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "processed_2023=data/processed/raw_fundamentals_2023.csv" in out
    assert captured["start_year"] == 2023
    assert captured["end_year"] == 2025
    assert captured["refresh_quarterly"] is True
    assert captured["quarterly_refresh_days"] == 0


def test_simfin_dvpq_is_null_and_dvy_carries_total_dividends(tmp_path) -> None:
    """dvpq means PREFERRED dividends (Compustat definition).

    SimFin publishes no preferred-dividend column, so the honest value is
    null. Total dividends now live in `dvy`, sourced from the annual cashflow
    "Dividends Paid". Previously dvpq was mapped to the total, which made
    dividend_payer_years_10y read ~0 for genuine payers before 2023.
    """
    cache_dir = tmp_path / "simfin_cache"
    _build_cache(cache_dir)

    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)

    artifacts = build_simfin_raw_fundamentals(
        universe_path=universe_path,
        output_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
        start_year=2023,
        end_year=2023,
        connector=SimfinConnector(data_dir=cache_dir),
    )

    year_df = pd.read_csv(artifacts["processed_2023"])
    aapl = year_df[year_df["ticker"] == "AAPL"].iloc[0]
    assert pd.isna(aapl["dvpq"])
    # annual "Dividends Paid" -12.0 -> positive spend 12.0 -> published 1.2e-5
    assert aapl["dvy"] == 0.000012
