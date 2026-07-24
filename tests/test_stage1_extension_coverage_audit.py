from __future__ import annotations

import pandas as pd

from fundamentals_pipeline.contracts.stage1_fundamentals_schema import STAGE1_RAW_COLUMNS
from fundamentals_pipeline.steps.stage1_extension_coverage_audit import (
    run_stage1_extension_coverage_audit,
)


def _publish_year(processed_dir, year: int, rows: list[dict[str, object]]) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    for column in STAGE1_RAW_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[list(STAGE1_RAW_COLUMNS)]
    frame.to_csv(processed_dir / f"raw_fundamentals_{year}.csv", index=False)


def test_audit_reports_extension_field_coverage_per_year(tmp_path) -> None:
    processed_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    _publish_year(
        processed_dir,
        2023,
        [
            {"ticker": "AAPL", "year": 2023, "quarter": 1, "cogsq": 60.0, "ltq": 300.0},
            {"ticker": "AAPL", "year": 2023, "quarter": 2, "cogsq": None, "ltq": 310.0},
        ],
    )

    artifacts = run_stage1_extension_coverage_audit(
        processed_dir=processed_dir,
        reports_dir=reports_dir,
        start_year=2023,
        end_year=2023,
    )

    report = pd.read_csv(artifacts["extension_coverage_output"])
    cogs = report[(report["year"] == 2023) & (report["field_name"] == "cogsq")].iloc[0]
    assert cogs["total_rows"] == 2
    assert cogs["non_null_rows"] == 1
    assert cogs["non_null_pct"] == 50.0
    ltq = report[(report["year"] == 2023) & (report["field_name"] == "ltq")].iloc[0]
    assert ltq["non_null_rows"] == 2
    # 7 extension fields per year
    assert len(report) == 7


def test_audit_counts_cogs_fallback_rows_from_simfin_cache(tmp_path) -> None:
    processed_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _publish_year(
        processed_dir,
        2023,
        [{"ticker": "AAPL", "year": 2023, "quarter": 1, "cogsq": 60.0}],
    )
    pd.DataFrame(
        [
            # fallback row: no Cost of Revenue, Revenue+Gross Profit present
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Revenue": 100.0,
                "Cost of Revenue": None,
                "Gross Profit": 40.0,
            },
            # direct row: Cost of Revenue present -> not a fallback
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Revenue": 100.0,
                "Cost of Revenue": -60.0,
                "Gross Profit": 40.0,
            },
            # ticker not in published year output -> ignored
            {
                "Ticker": "ZZZZ",
                "Fiscal Year": 2023,
                "Revenue": 10.0,
                "Cost of Revenue": None,
                "Gross Profit": 4.0,
            },
        ]
    ).to_csv(cache_dir / "us-income-quarterly.csv", sep=";", index=False)

    artifacts = run_stage1_extension_coverage_audit(
        processed_dir=processed_dir,
        reports_dir=reports_dir,
        start_year=2023,
        end_year=2023,
        simfin_cache_dir=cache_dir,
    )

    report = pd.read_csv(artifacts["extension_coverage_output"])
    cogs = report[(report["year"] == 2023) & (report["field_name"] == "cogsq")].iloc[0]
    assert cogs["cogsq_fallback_rows"] == 1


def test_cli_stage1_extension_audit_invokes_step(monkeypatch, capsys) -> None:
    from fundamentals_pipeline import __main__ as cli

    captured: dict[str, object] = {}

    def _fake_audit(**kwargs):
        captured.update(kwargs)
        return {"extension_coverage_output": "data/reports/stage1_extension_coverage_2006_2025.csv"}

    monkeypatch.setattr(cli, "run_stage1_extension_coverage_audit", _fake_audit)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fundamentals-pipeline",
            "stage1-extension-audit",
            "--processed-dir",
            "data/processed",
            "--reports-dir",
            "data/reports",
            "--start-year",
            "2006",
            "--end-year",
            "2025",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "extension_coverage_output=" in out
    assert captured["start_year"] == 2006
    assert captured["end_year"] == 2025
