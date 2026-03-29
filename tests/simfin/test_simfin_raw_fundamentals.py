from __future__ import annotations

import pandas as pd

from trading_bot import __main__ as cli
from trading_bot.connectors.simfin_dataset_loader import SimfinConnector
from trading_bot.steps.simfin_raw_fundamentals_builder import (
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
    assert aapl["saleq"] == 100.0
    assert aapl["xintq"] == 5.0
    assert aapl["actq"] == 80.0
    assert aapl["lctq"] == 40.0
    assert aapl["prstkcq"] == 7.0
    assert aapl["capxq"] == 9.0
    assert aapl["dvpq"] == 3.0
    assert aapl["epspxq"] == 2.0
    assert aapl["oancfy"] == 120.0
    assert aapl["capxy"] == 36.0
    assert aapl["prstkcy"] == 28.0
    assert pd.isna(aapl["cshopq"])

    abcb = year_df[year_df["ticker"] == "ABCB"].iloc[0]
    assert pd.isna(abcb["xintq"])
    assert pd.isna(abcb["actq"])
    assert pd.isna(abcb["lctq"])
    assert abcb["ppentq"] == 500.0
    assert abcb["ivltq"] == 600.0
    assert abcb["prstkcq"] == 9.0

    coverage = pd.read_csv(artifacts["coverage_output"])
    assert coverage.loc[0, "rows_emitted"] == 2
    assert coverage.loc[0, "unique_tickers_emitted"] == 2

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
            "trading-bot",
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
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "processed_2023=data/processed/raw_fundamentals_2023.csv" in out
    assert captured["start_year"] == 2023
    assert captured["end_year"] == 2025
