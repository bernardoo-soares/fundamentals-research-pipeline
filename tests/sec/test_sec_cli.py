from __future__ import annotations

import pandas as pd

from trading_bot import __main__ as cli


def test_cli_sec_normalize_long_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_normalize(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame([{"ticker": "AAPL"}])

    monkeypatch.setattr(cli, "normalize_sec_facts_long", _fake_normalize)
    monkeypatch.setattr(
        "sys.argv",
        [
            "trading-bot",
            "sec-normalize-long",
            "--raw-dir",
            "data/raw/sec/companyfacts",
            "--mapping-path",
            "src/trading_bot/contracts/sec_metric_map.yml",
            "--output-path",
            "data/processed/sec_facts_long_2023_2025.csv",
            "--start-year",
            "2023",
            "--end-year",
            "2025",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "normalized_rows=1" in out
    assert captured["start_year"] == 2023
    assert captured["end_year"] == 2025


def test_cli_sec_map_cik_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_map(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame([{"ticker": "AAPL"}, {"ticker": "MSFT"}])

    monkeypatch.setattr(cli, "build_sec_cik_mapping", _fake_map)
    monkeypatch.setattr(
        "sys.argv",
        [
            "trading-bot",
            "sec-map-cik",
            "--universe-path",
            "data/universe_current.csv",
            "--output-path",
            "data/reports/sec_cik_mapping.csv",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "mapping_rows=2" in out
    assert captured["universe_path"] == "data/universe_current.csv"


def test_cli_sec_ingest_submissions_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_ingest(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame([{"ticker": "AAPL"}, {"ticker": "MSFT"}])

    monkeypatch.setattr(cli, "run_sec_submissions_ingestion", _fake_ingest)
    monkeypatch.setattr(
        "sys.argv",
        [
            "trading-bot",
            "sec-ingest-submissions",
            "--mapping-path",
            "data/reports/sec_cik_mapping.csv",
            "--raw-dir",
            "data/raw/sec/submissions",
            "--log-path",
            "data/reports/sec_submissions_ingestion_log.csv",
            "--run-id",
            "run-123",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "submissions_ingestion_rows=2" in out
    assert captured["mapping_path"] == "data/reports/sec_cik_mapping.csv"
    assert captured["raw_dir"] == "data/raw/sec/submissions"
    assert captured["log_path"] == "data/reports/sec_submissions_ingestion_log.csv"
    assert captured["run_id"] == "run-123"


def test_cli_sec_build_fiscal_calendar_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_calendar(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame([{"ticker": "AAPL"}])

    monkeypatch.setattr(cli, "build_sec_fiscal_calendar", _fake_calendar)
    monkeypatch.setattr(
        "sys.argv",
        [
            "trading-bot",
            "sec-build-fiscal-calendar",
            "--submissions-dir",
            "data/raw/sec/submissions",
            "--mapping-path",
            "data/reports/sec_cik_mapping.csv",
            "--output-path",
            "data/reports/sec_fiscal_calendar.csv",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "fiscal_calendar_rows=1" in out
    assert captured["submissions_dir"] == "data/raw/sec/submissions"
    assert captured["mapping_path"] == "data/reports/sec_cik_mapping.csv"
    assert captured["output_path"] == "data/reports/sec_fiscal_calendar.csv"


def test_cli_sec_build_processed_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_processed(**kwargs):
        captured.update(kwargs)
        return {
            "processed_2023": "data/processed/processed_fundamentals_2023.csv",
            "coverage_output": "data/reports/sec_processed_coverage_2023_2025.csv",
        }

    monkeypatch.setattr(cli, "build_sec_processed_fundamentals", _fake_processed)
    monkeypatch.setattr(
        "sys.argv",
        [
            "trading-bot",
            "sec-build-processed",
            "--raw-dir",
            "data/raw/sec/companyfacts",
            "--mapping-path",
            "src/trading_bot/contracts/sec_metric_map.yml",
            "--fiscal-calendar-path",
            "data/reports/sec_fiscal_calendar.csv",
            "--sec-cik-mapping-path",
            "data/reports/sec_cik_mapping.csv",
            "--output-dir",
            "data/processed",
            "--reports-dir",
            "data/reports",
            "--start-year",
            "2023",
            "--end-year",
            "2025",
            "--max-day-delta",
            "30",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "processed_2023=data/processed/processed_fundamentals_2023.csv" in out
    assert captured["fiscal_calendar_path"] == "data/reports/sec_fiscal_calendar.csv"
    assert captured["sec_cik_mapping_path"] == "data/reports/sec_cik_mapping.csv"
