from __future__ import annotations

import pandas as pd

from fundamentals_pipeline.contracts.stage1_fundamentals_schema import STAGE1_RAW_COLUMNS
from fundamentals_pipeline.steps.legacy_stage1_output_audit import (
    build_field_nulls_report,
    build_review_sample,
    check_stage1_columns,
    reconcile_processed_vs_expected,
    run_legacy_stage1_audit,
)


def _legacy_row(
    ticker: str,
    datadate: str,
    fyearq: int,
    fqtr: int,
    *,
    saleq: float,
    niq: float,
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
        "prstkcq": 3.0,
        "prstkcy": 12.0,
        "capxq": 6.0,
        "cheq": 20.0,
        "dvpq": 2.0,
        "cshfdq": 100.0,
        "cshopq": 3.0,
        "cshoq": 99.0,
    }


def _stage1_row(ticker: str, year: int, quarter: int, saleq: float) -> dict[str, object]:
    row = {column: pd.NA for column in STAGE1_RAW_COLUMNS}
    row["ticker"] = ticker
    row["year"] = year
    row["quarter"] = quarter
    row["saleq"] = saleq
    row["niq"] = 10.0
    row["oiadpq"] = 15.0
    row["xintq"] = 1.0
    row["txtq"] = 2.0
    row["epspxq"] = 0.5
    row["actq"] = 50.0
    row["lctq"] = 25.0
    row["ppentq"] = 1000.0
    row["gdwlq"] = 100.0
    row["ivltq"] = 50.0
    row["atq"] = 500.0
    row["ceqq"] = 200.0
    row["dlcq"] = 40.0
    row["dlttq"] = 60.0
    row["req"] = 110.0
    row["tstkq"] = 5.0
    row["oancfq"] = 15.0
    row["prstkcq"] = 3.0
    row["capxq"] = 6.0
    row["cheq"] = 20.0
    row["dvpq"] = 2.0
    row["cshfdq"] = 100.0
    row["oancfy"] = 60.0
    row["capxy"] = 24.0
    row["prstkcy"] = 12.0
    row["cshopq"] = 3.0
    row["cshoq"] = 99.0
    return row


def test_check_stage1_columns_reports_mismatch() -> None:
    frame = pd.DataFrame(columns=["ticker", "year", "quarter", "saleq"])
    issues = check_stage1_columns(frame, 2024)
    assert len(issues) == 1
    assert issues.iloc[0]["issue_type"] == "column_mismatch"


def test_build_field_nulls_report_counts_nulls_by_field() -> None:
    rows = [_stage1_row("AAPL", 2024, 1, 100.0), _stage1_row("AAPL", 2024, 2, 110.0)]
    frame = pd.DataFrame(rows)
    frame.loc[1, "saleq"] = pd.NA
    report = build_field_nulls_report(frame, 2024)
    saleq = report.loc[report["field_name"] == "saleq"].iloc[0]
    assert saleq["null_rows"] == 1
    assert saleq["total_rows"] == 2


def test_reconciliation_reports_field_level_mismatch() -> None:
    processed = pd.DataFrame([_stage1_row("AAPL", 2024, 1, 100.0)])
    expected = processed.copy()
    expected.loc[0, "saleq"] = 125.0
    expected["source_file"] = "AAPL-001690.csv"

    detail, summary = reconcile_processed_vs_expected(processed, expected, 2024)

    mismatch = detail[detail["field_name"] == "saleq"].iloc[0]
    assert mismatch["match_status"] == "mismatch"
    assert summary.iloc[0]["mismatches"] >= 1


def test_build_review_sample_is_deterministic_by_reason() -> None:
    suspicious = pd.DataFrame(
        [
            {
                "year": 2024,
                "ticker": "MSFT",
                "quarter": 2,
                "field_name": "saleq",
                "value": 1.0,
                "anomaly_type": "source_reconciliation_mismatch",
                "detail": "mismatch",
            },
            {
                "year": 2024,
                "ticker": "AAPL",
                "quarter": 1,
                "field_name": "saleq",
                "value": 1.0,
                "anomaly_type": "source_reconciliation_mismatch",
                "detail": "mismatch",
            },
        ]
    )

    out = build_review_sample(suspicious, per_reason=1)
    assert out.iloc[0]["ticker"] == "AAPL"


def test_run_legacy_stage1_audit_writes_reports_and_flags_mismatch(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    reports_dir = tmp_path / "reports"
    universe_path = tmp_path / "universe.csv"
    raw_dir.mkdir()
    processed_dir.mkdir()
    reports_dir.mkdir()

    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)
    pd.DataFrame(
        [
            _legacy_row("AAPL", "2024-03-31", 2024, 1, saleq=100.0, niq=10.0),
            _legacy_row("AAPL", "2024-06-30", 2024, 2, saleq=110.0, niq=11.0),
        ]
    ).to_csv(raw_dir / "AAPL-001690.csv", index=False)

    processed = pd.DataFrame(
        [
            _stage1_row("AAPL", 2024, 1, 999.0),
            _stage1_row("AAPL", 2024, 2, 110.0),
        ],
        columns=STAGE1_RAW_COLUMNS,
    )
    processed.to_csv(processed_dir / "raw_fundamentals_2024.csv", index=False)

    artifacts = run_legacy_stage1_audit(
        universe_path=universe_path,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        reports_dir=reports_dir,
        start_year=2024,
        end_year=2024,
    )

    for path in artifacts.values():
        assert pd.notna(path)

    summary = pd.read_csv(artifacts["summary_output"])
    reconciliation = pd.read_csv(artifacts["reconciliation_output"])
    review_sample = pd.read_csv(artifacts["review_sample_output"])

    mismatch_summary = summary[summary["check_name"] == "source_reconciliation_mismatches"].iloc[0]
    assert mismatch_summary["status"] == "fail"
    assert (reconciliation["match_status"] == "mismatch").any()
    assert (review_sample["ticker"] == "AAPL").any()


def test_published_columns_with_provenance_are_not_a_mismatch() -> None:
    """Regression: the audit reads PUBLISHED files, which carry source_era.
    Comparing them to the builder-only column set flagged every correct file."""
    from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
        STAGE1_OUTPUT_COLUMNS,
        STAGE1_RAW_COLUMNS,
    )
    from fundamentals_pipeline.steps.legacy_stage1_output_audit import (
        check_stage1_columns,
    )

    published = pd.DataFrame(columns=list(STAGE1_OUTPUT_COLUMNS))
    staged = pd.DataFrame(columns=list(STAGE1_RAW_COLUMNS))
    assert check_stage1_columns(published, 2023).empty
    assert check_stage1_columns(staged, 2023).empty
    wrong = pd.DataFrame(columns=["ticker", "year", "quarter"])
    assert not check_stage1_columns(wrong, 2023).empty
