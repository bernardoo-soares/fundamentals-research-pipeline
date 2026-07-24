from __future__ import annotations

import pandas as pd

from fundamentals_pipeline import __main__ as cli
from fundamentals_pipeline.contracts.stage1_fundamentals_schema import STAGE1_OUTPUT_COLUMNS
from fundamentals_pipeline.steps.legacy_processed_fundamentals_builder import (
    _prepare_legacy_frame,
    build_legacy_fundamentals,
    build_legacy_raw_stage1,
)
from fundamentals_pipeline.workflows.full_run import run_legacy_raw_stage1_window


def _legacy_row(
    ticker: str,
    datadate: str,
    fyearq: int,
    fqtr: int,
    *,
    saleq: float,
    niq: float,
    cshopq: float | None = None,
    prstkcy: float | None = None,
    cshoq: float | None = None,
    cshfdq: float | None = None,
) -> dict[str, object]:
    return {
        "tic": ticker,
        "datadate": datadate,
        "fyearq": fyearq,
        "fqtr": fqtr,
        "saleq": saleq,
        "niq": niq,
        "oiadpq": saleq * 0.15,
        "xintq": 1.0,
        "txtq": 2.0,
        "epspxq": 0.5,
        "actq": 50.0,
        "lctq": 25.0,
        "ppentq": 1000.0,
        "gdwlq": 100.0,
        "ivltq": 50.0,
        "atq": 500.0,
        "ceqq": 200.0,
        "dlcq": 40.0,
        "dlttq": 60.0,
        "req": 110.0,
        "tstkq": 5.0,
        "oancfq": 15.0,
        "oancfy": 60.0,
        "capxy": 24.0,
        "prstkcq": pd.NA,
        "prstkcy": prstkcy,
        "capxq": 6.0,
        "cheq": 20.0,
        "dvpq": 2.0,
        "cshfdq": cshfdq,
        "cshopq": cshopq,
        "cshoq": cshoq,
        "cogsq": 60.0,
        "xsgaq": 12.0,
        "xrdq": 8.0,
        "dpq": 11.0,
        "ltq": 300.0,
        "invtq": 30.0,
        "rectq": 22.0,
    }


def _write_legacy_file(path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_legacy_fundamentals_filters_and_writes_outputs(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)
    _write_legacy_file(
        raw_dir / "AAPL-001690.csv",
        [
            _legacy_row("AAPL", "2024-03-31", 2024, 1, saleq=100.0, niq=10.0, cshopq=4.0, cshoq=900.0),
            _legacy_row("AAPL", "2024-06-30", 2024, 2, saleq=110.0, niq=12.0, cshopq=5.0, cshoq=901.0),
            _legacy_row("AAPL", "2024-09-30", 2024, 3, saleq=120.0, niq=14.0, cshopq=6.0, cshoq=902.0),
            _legacy_row("AAPL", "2024-12-31", 2024, 4, saleq=130.0, niq=16.0, cshopq=7.0, cshoq=903.0),
        ],
    )
    _write_legacy_file(
        raw_dir / "MSFT-001111.csv",
        [_legacy_row("MSFT", "2024-03-31", 2024, 1, saleq=200.0, niq=20.0)],
    )

    canonical = build_legacy_fundamentals(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )

    assert canonical["ticker"].nunique() == 1
    assert canonical["ticker"].iloc[0] == "AAPL"
    assert len(canonical) == 4
    assert {"oancfy", "capxy", "prstkcy", "cshopq", "cshoq"}.issubset(canonical.columns)

    expected_files = [
        output_dir / "canonical_legacy_q.csv",
        output_dir / "fundamentals_q_2024.csv",
    ]
    for path in expected_files:
        assert path.exists()


def test_build_legacy_raw_stage1_writes_yearly_raw_only_outputs_and_reports(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["AAPL", "MSFT"]}).to_csv(universe_path, index=False)
    _write_legacy_file(
        raw_dir / "AAPL-001690.csv",
        [
            _legacy_row("AAPL", "2024-03-31", 2024, 1, saleq=100.0, niq=10.0, cshopq=4.0, cshoq=900.0),
            _legacy_row("AAPL", "2024-06-30", 2024, 2, saleq=110.0, niq=12.0, cshopq=5.0, cshoq=901.0),
            _legacy_row("AAPL", "2024-09-30", 2024, 3, saleq=120.0, niq=14.0, cshopq=6.0, cshoq=902.0),
            _legacy_row("AAPL", "2024-12-31", 2024, 4, saleq=130.0, niq=16.0, cshopq=7.0, cshoq=903.0),
        ],
    )

    artifacts = build_legacy_raw_stage1(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        reports_dir=reports_dir,
        start_year=2024,
        end_year=2024,
    )

    year_df = pd.read_csv(artifacts["processed_2024"])
    assert tuple(year_df.columns) == STAGE1_OUTPUT_COLUMNS
    assert len(year_df) == 4
    assert "Operating_Margin" not in year_df.columns

    first_row = year_df.iloc[0]
    assert first_row["cogsq"] == 60.0
    assert first_row["xsgaq"] == 12.0
    assert first_row["xrdq"] == 8.0
    assert first_row["dpq"] == 11.0
    assert first_row["ltq"] == 300.0
    assert first_row["invtq"] == 30.0
    assert first_row["rectq"] == 22.0

    coverage = pd.read_csv(artifacts["coverage_output"])
    assert coverage.loc[0, "rows_emitted"] == 4
    assert coverage.loc[0, "unique_tickers_emitted"] == 1

    missing = pd.read_csv(artifacts["missing_output"])
    assert missing.to_dict(orient="records") == [
        {"ticker": "MSFT", "reason": "missing_raw_file"}
    ]

    conflicts = pd.read_csv(artifacts["conflicts_output"])
    assert conflicts.empty


def test_stage1_year_filter_uses_fiscal_year_not_period_end(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)
    _write_legacy_file(
        raw_dir / "AAPL-001690.csv",
        [
            _legacy_row("AAPL", "2006-01-31", 2005, 4, saleq=80.0, niq=8.0),
            _legacy_row("AAPL", "2023-01-31", 2023, 1, saleq=90.0, niq=9.0),
            _legacy_row("AAPL", "2023-11-30", 2024, 1, saleq=100.0, niq=10.0),
        ],
    )

    artifacts = build_legacy_raw_stage1(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        reports_dir=reports_dir,
        start_year=2006,
        end_year=2023,
    )

    year_2023 = pd.read_csv(artifacts["processed_2023"])
    assert year_2023["year"].between(2006, 2023).all()
    assert year_2023["year"].tolist() == [2023]

    year_2006 = pd.read_csv(artifacts["processed_2006"])
    assert year_2006.empty


def test_build_legacy_raw_stage1_emits_conflict_report_and_dedupes(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)
    _write_legacy_file(
        raw_dir / "AAPL-001690.csv",
        [
            _legacy_row("AAPL", "2024-03-31", 2024, 1, saleq=100.0, niq=10.0),
            _legacy_row("AAPL", "2024-04-15", 2024, 1, saleq=125.0, niq=12.5),
        ],
    )

    artifacts = build_legacy_raw_stage1(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        reports_dir=reports_dir,
        start_year=2024,
        end_year=2024,
    )

    conflicts = pd.read_csv(artifacts["conflicts_output"])
    assert set(conflicts.columns) >= {"ticker", "year", "quarter", "conflict_reason"}
    assert len(conflicts) == 2

    year_df = pd.read_csv(artifacts["processed_2024"])
    assert not year_df.duplicated(subset=["ticker", "year", "quarter"]).any()
    assert year_df.loc[0, "saleq"] == 125.0


def test_build_legacy_raw_stage1_applies_current_universe_aliases(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["GOOG", "GOOGL", "FOX", "FOXA"]}).to_csv(
        universe_path,
        index=False,
    )
    _write_legacy_file(
        raw_dir / "GOOGL-160329.csv",
        [_legacy_row("GOOGL", "2024-03-31", 2024, 1, saleq=100.0, niq=10.0)],
    )
    _write_legacy_file(
        raw_dir / "FOXA-034636.csv",
        [_legacy_row("FOXA", "2024-03-31", 2024, 1, saleq=200.0, niq=20.0)],
    )

    artifacts = build_legacy_raw_stage1(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        reports_dir=reports_dir,
        start_year=2024,
        end_year=2024,
    )

    year_df = pd.read_csv(artifacts["processed_2024"])
    assert set(year_df["ticker"]) == {"GOOG", "GOOGL", "FOX", "FOXA"}
    assert year_df.loc[year_df["ticker"] == "GOOG", "saleq"].iloc[0] == 100.0
    assert year_df.loc[year_df["ticker"] == "GOOGL", "saleq"].iloc[0] == 100.0
    assert year_df.loc[year_df["ticker"] == "FOX", "saleq"].iloc[0] == 200.0
    assert year_df.loc[year_df["ticker"] == "FOXA", "saleq"].iloc[0] == 200.0


def test_build_legacy_raw_stage1_requires_explicit_fiscal_quarter_labels(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["TTWO"]}).to_csv(universe_path, index=False)
    _write_legacy_file(
        raw_dir / "TTWO-064630.csv",
        [
            {
                **_legacy_row("TTWO", "2010-01-31", 2010, 1, saleq=100.0, niq=10.0),
                "fqtr": pd.NA,
                "actq": 500.0,
            },
            _legacy_row("TTWO", "2010-06-30", 2010, 1, saleq=125.0, niq=12.5),
        ],
    )

    artifacts = build_legacy_raw_stage1(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        reports_dir=reports_dir,
        start_year=2010,
        end_year=2010,
    )

    year_df = pd.read_csv(artifacts["processed_2010"])
    assert len(year_df) == 1
    assert year_df.loc[0, "ticker"] == "TTWO"
    assert year_df.loc[0, "saleq"] == 125.0


def test_cli_legacy_raw_stage1_invokes_pipeline(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return {
            "processed_2023": "data/processed/raw_fundamentals_2023.csv",
            "coverage_output": "data/reports/legacy_raw_coverage_2023_2023.csv",
        }

    monkeypatch.setattr(cli, "build_legacy_raw_stage1", _fake_build)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fundamentals-pipeline",
            "legacy-raw-stage1",
            "--universe-path",
            "data/universe_current.csv",
            "--raw-dir",
            "data/raw/Processed-Fundamentals",
            "--output-dir",
            "data/processed",
            "--reports-dir",
            "data/reports",
            "--start-year",
            "2023",
            "--end-year",
            "2023",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "processed_2023=data/processed/raw_fundamentals_2023.csv" in out
    assert captured["start_year"] == 2023
    assert captured["end_year"] == 2023


def test_workflow_run_legacy_raw_stage1_window_invokes_step(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return {"processed_2023": "data/processed/raw_fundamentals_2023.csv"}

    monkeypatch.setattr("fundamentals_pipeline.workflows.full_run.build_legacy_raw_stage1", _fake_build)
    artifacts = run_legacy_raw_stage1_window(start_year=2023, end_year=2023)

    assert artifacts["processed_2023"] == "data/processed/raw_fundamentals_2023.csv"
    assert captured["start_year"] == 2023
    assert captured["end_year"] == 2023


def test_prstkcq_is_null_when_source_lacks_it() -> None:
    """Regression: prstkcq was filled from cshopq, a SHARE COUNT.

    Compustat publishes no quarterly purchase-of-stock column at all
    ("prstkcq" is absent from the extract), so the honest value is null.
    Real AAPL FY2019 Q1: cshopq 38.024 shares vs the actual 10114 dollars
    of YTD buyback. Pins the unit defect closed.
    """
    frame = pd.DataFrame(
        {"fyearq": [2019], "fqtr": [1], "cshopq": [38.024], "prstkcy": [10114.0]}
    )
    result = _prepare_legacy_frame(frame)
    assert pd.isna(result["prstkcq"].iloc[0])


def test_prstkcq_is_not_derived_from_quartered_prstkcy() -> None:
    """Regression: prstkcq was filled with prstkcy / 4 -- flat imputation."""
    frame = pd.DataFrame(
        {"fyearq": [2019], "fqtr": [1], "cshopq": [None], "prstkcy": [10114.0]}
    )
    result = _prepare_legacy_frame(frame)
    assert pd.isna(result["prstkcq"].iloc[0])


def test_cshfdq_is_null_when_source_lacks_it() -> None:
    """Regression: cshfdq was filled from cshoq.

    Compustat defines cshfdq as "Com Shares for Diluted EPS" and cshoq as
    "Common Shares Outstanding" -- different quantities, materially so for
    companies with significant options or convertibles.
    """
    frame = pd.DataFrame({"fyearq": [2019], "fqtr": [1], "cshoq": [4443.236]})
    result = _prepare_legacy_frame(frame)
    assert pd.isna(result["cshfdq"].iloc[0])


def test_present_source_values_are_preserved() -> None:
    """Removing fallbacks must not disturb genuinely present values."""
    frame = pd.DataFrame(
        {"fyearq": [2019], "fqtr": [1], "cshfdq": [4500.0], "saleq": [64040.0]}
    )
    result = _prepare_legacy_frame(frame)
    assert result["cshfdq"].iloc[0] == 4500.0
    assert result["saleq"].iloc[0] == 64040.0
