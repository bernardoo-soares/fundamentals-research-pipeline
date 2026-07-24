"""Audit runner for published legacy Stage 1 raw fundamentals artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..contracts.legacy_stage1_audit_schema import (
    AUDIT_SUMMARY_COLUMNS,
    FIELD_NULLS_COLUMNS,
    KEY_ISSUES_COLUMNS,
    RECONCILIATION_COLUMNS,
    RECONCILIATION_SUMMARY_COLUMNS,
    REVIEW_SAMPLE_COLUMNS,
    SCHEMA_ISSUES_COLUMNS,
    SUSPICIOUS_VALUES_COLUMNS,
    validate_report_columns,
)
from ..contracts.stage1_fundamentals_schema import (
    STAGE1_KEY_COLUMNS,
    STAGE1_RAW_COLUMNS,
)
from .legacy_processed_fundamentals_builder import build_legacy_raw_stage1_compare_frame

NEGATIVE_BALANCE_FIELDS: tuple[str, ...] = ("actq", "atq", "cheq", "cshfdq", "cshoq")


def _summary_row(
    *,
    year: int,
    check_name: str,
    status: str,
    observed_value: Any,
    expected_value: Any,
    detail: str,
) -> dict[str, Any]:
    return {
        "year": year,
        "check_name": check_name,
        "status": status,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "detail": detail,
    }


def _empty_frame(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _coerce_stage1_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in STAGE1_RAW_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    out = out[list(STAGE1_RAW_COLUMNS)].copy()
    return out.reset_index(drop=True)


def _coerce_quarter_value(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _values_match(left: Any, right: Any) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True

    left_num = pd.to_numeric(pd.Series([left]), errors="coerce").iloc[0]
    right_num = pd.to_numeric(pd.Series([right]), errors="coerce").iloc[0]
    if pd.notna(left_num) and pd.notna(right_num):
        return bool(left_num == right_num)

    return str(left) == str(right)


def _write_report(frame: pd.DataFrame, path: Path, report_name: str) -> None:
    validate_report_columns(report_name, frame.columns.tolist())
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def load_stage1_year(path: Path) -> pd.DataFrame:
    """Load one published Stage 1 yearly CSV."""
    return pd.read_csv(path)


def check_stage1_columns(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    """Report column-order mismatches against the frozen Stage 1 contract."""
    if tuple(frame.columns) == STAGE1_RAW_COLUMNS:
        return _empty_frame(SCHEMA_ISSUES_COLUMNS)

    return pd.DataFrame(
        [
            {
                "year": year,
                "issue_type": "column_mismatch",
                "expected_columns": "|".join(STAGE1_RAW_COLUMNS),
                "observed_columns": "|".join(map(str, frame.columns.tolist())),
                "detail": "processed file columns differ from Stage 1 contract",
            }
        ],
        columns=SCHEMA_ISSUES_COLUMNS,
    )


def check_stage1_key_uniqueness(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    """Report duplicate quarterly keys in a processed Stage 1 frame."""
    required = set(STAGE1_KEY_COLUMNS)
    if not required.issubset(frame.columns):
        missing = sorted(required.difference(frame.columns))
        return pd.DataFrame(
            [
                {
                    "year": year,
                    "ticker": "",
                    "quarter": pd.NA,
                    "issue_type": "missing_key_columns",
                    "row_count": 0,
                    "detail": f"missing key columns: {missing}",
                }
            ],
            columns=KEY_ISSUES_COLUMNS,
        )

    counts = (
        frame.groupby(list(STAGE1_KEY_COLUMNS), dropna=False)
        .size()
        .reset_index(name="row_count")
    )
    dupes = counts[counts["row_count"] > 1].copy()
    if dupes.empty:
        return _empty_frame(KEY_ISSUES_COLUMNS)

    dupes["issue_type"] = "duplicate_key"
    dupes["detail"] = "multiple processed rows share the same quarterly key"
    return dupes[
        ["year", "ticker", "quarter", "issue_type", "row_count", "detail"]
    ].reset_index(drop=True)


def check_stage1_sort_order(frame: pd.DataFrame) -> bool:
    """Return whether rows are sorted by deterministic Stage 1 key order."""
    if frame.empty:
        return True
    sorted_frame = frame.sort_values(
        list(STAGE1_KEY_COLUMNS),
        kind="mergesort",
    ).reset_index(drop=True)
    return sorted_frame.equals(frame.reset_index(drop=True))


def build_field_nulls_report(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    """Build per-field null counts for one processed Stage 1 year."""
    rows: list[dict[str, Any]] = []
    total_rows = int(len(frame))
    for field_name in STAGE1_RAW_COLUMNS[len(STAGE1_KEY_COLUMNS) :]:
        null_rows = int(frame[field_name].isna().sum()) if total_rows else 0
        null_pct = round((null_rows / total_rows) * 100.0, 6) if total_rows else 0.0
        rows.append(
            {
                "year": year,
                "field_name": field_name,
                "null_rows": null_rows,
                "total_rows": total_rows,
                "null_pct": null_pct,
            }
        )
    return pd.DataFrame(rows, columns=FIELD_NULLS_COLUMNS)


def build_expected_stage1_frame(
    *,
    universe_path: str | Path,
    raw_dir: str | Path,
    year: int,
) -> pd.DataFrame:
    """Rebuild expected Stage 1 rows from legacy source files for one year."""
    return build_legacy_raw_stage1_compare_frame(
        universe_path=universe_path,
        raw_dir=raw_dir,
        start_year=year,
        end_year=year,
    )


def reconcile_processed_vs_expected(
    processed: pd.DataFrame,
    expected: pd.DataFrame,
    year: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare processed Stage 1 values against reconstructed expected values."""
    compare_fields = list(STAGE1_RAW_COLUMNS[len(STAGE1_KEY_COLUMNS) :])
    merged = processed.merge(
        expected,
        on=list(STAGE1_KEY_COLUMNS),
        how="outer",
        suffixes=("_processed", "_expected"),
        indicator=True,
    )

    detail_rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        for field_name in compare_fields:
            processed_value = row.get(f"{field_name}_processed", pd.NA)
            expected_value = row.get(f"{field_name}_expected", pd.NA)
            if row["_merge"] == "left_only":
                status = "expected_missing"
            elif row["_merge"] == "right_only":
                status = "processed_missing"
            elif _values_match(processed_value, expected_value):
                status = "match"
            else:
                status = "mismatch"

            detail_rows.append(
                {
                    "year": year,
                    "ticker": str(row.get("ticker", "")),
                    "quarter": _coerce_quarter_value(row.get("quarter")),
                    "field_name": field_name,
                    "processed_value": processed_value,
                    "expected_value": expected_value,
                    "match_status": status,
                    "source_file": row.get("source_file", ""),
                }
            )

    detail = pd.DataFrame(detail_rows, columns=RECONCILIATION_COLUMNS)
    mismatch_count = int((detail["match_status"] != "match").sum()) if not detail.empty else 0
    summary = pd.DataFrame(
        [
            {
                "year": year,
                "compared_rows": int(merged.shape[0]),
                "compared_fields": int(len(detail)),
                "exact_matches": int((detail["match_status"] == "match").sum()) if not detail.empty else 0,
                "mismatches": mismatch_count,
                "mismatch_pct": round((mismatch_count / len(detail)) * 100.0, 6)
                if len(detail)
                else 0.0,
            }
        ],
        columns=RECONCILIATION_SUMMARY_COLUMNS,
    )
    return detail, summary


def build_suspicious_values_report(
    frame: pd.DataFrame,
    field_nulls: pd.DataFrame,
    reconciliation: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    """Build a compact anomaly report to drive human review."""
    rows: list[dict[str, Any]] = []

    for _, null_row in field_nulls[field_nulls["null_pct"] == 100.0].iterrows():
        rows.append(
            {
                "year": year,
                "ticker": "",
                "quarter": pd.NA,
                "field_name": null_row["field_name"],
                "value": pd.NA,
                "anomaly_type": "systemic_null_field",
                "detail": "field is null for every emitted row in the year",
            }
        )

    if not frame.empty:
        for field_name in NEGATIVE_BALANCE_FIELDS:
            if field_name not in frame.columns:
                continue
            negatives = frame[pd.to_numeric(frame[field_name], errors="coerce") < 0].copy()
            for _, row in negatives.iterrows():
                rows.append(
                    {
                        "year": year,
                        "ticker": str(row["ticker"]),
                        "quarter": _coerce_quarter_value(row["quarter"]),
                        "field_name": field_name,
                        "value": row[field_name],
                        "anomaly_type": "negative_balance_like_value",
                        "detail": "negative value in a usually non-negative balance-like field",
                    }
                )

        quarter_counts = frame.groupby("ticker")["quarter"].nunique().reset_index(name="quarter_count")
        low_coverage = quarter_counts[quarter_counts["quarter_count"] < 4]
        for _, row in low_coverage.iterrows():
            rows.append(
                {
                    "year": year,
                    "ticker": str(row["ticker"]),
                    "quarter": pd.NA,
                    "field_name": "",
                    "value": row["quarter_count"],
                    "anomaly_type": "low_coverage_ticker",
                    "detail": "ticker has fewer than four emitted quarters in the year",
                }
            )

    mismatches = reconciliation[reconciliation["match_status"] != "match"].copy()
    mismatches = mismatches.sort_values(
        ["ticker", "quarter", "field_name"],
        kind="mergesort",
    ).drop_duplicates(subset=["ticker", "quarter"], keep="first")
    for _, row in mismatches.iterrows():
        rows.append(
            {
                "year": year,
                "ticker": str(row["ticker"]),
                "quarter": _coerce_quarter_value(row["quarter"]),
                "field_name": str(row["field_name"]),
                "value": row["processed_value"],
                "anomaly_type": "source_reconciliation_mismatch",
                "detail": str(row["match_status"]),
            }
        )

    suspicious = pd.DataFrame(rows, columns=SUSPICIOUS_VALUES_COLUMNS)
    if suspicious.empty:
        return suspicious
    return suspicious.sort_values(
        ["anomaly_type", "ticker", "quarter", "field_name"],
        kind="mergesort",
    ).reset_index(drop=True)


def build_review_sample(
    suspicious: pd.DataFrame,
    *,
    per_reason: int = 10,
) -> pd.DataFrame:
    """Build a deterministic review shortlist grouped by anomaly reason."""
    if suspicious.empty:
        return _empty_frame(REVIEW_SAMPLE_COLUMNS)

    samples: list[pd.DataFrame] = []
    grouped = suspicious[suspicious["ticker"].astype(str) != ""].copy()
    for reason, subset in grouped.groupby("anomaly_type", dropna=False):
        picked = subset.sort_values(
            ["ticker", "quarter", "field_name"],
            kind="mergesort",
        ).head(per_reason)
        sample = picked.loc[:, ["year", "ticker", "quarter"]].copy()
        sample["sample_reason"] = reason
        samples.append(sample)

    if not samples:
        return _empty_frame(REVIEW_SAMPLE_COLUMNS)

    return pd.concat(samples, ignore_index=True)[list(REVIEW_SAMPLE_COLUMNS)]


def run_legacy_stage1_audit(
    *,
    universe_path: str | Path = "data/universe_current.csv",
    raw_dir: str | Path = "data/raw/Processed-Fundamentals",
    processed_dir: str | Path = "data/processed",
    reports_dir: str | Path = "data/reports",
    start_year: int = 2006,
    end_year: int = 2023,
) -> dict[str, str]:
    """Run the full published-vs-source audit for legacy Stage 1 outputs."""
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")

    processed_dir = Path(processed_dir)
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_frames: list[pd.DataFrame] = []
    schema_issue_frames: list[pd.DataFrame] = []
    key_issue_frames: list[pd.DataFrame] = []
    field_null_frames: list[pd.DataFrame] = []
    reconciliation_frames: list[pd.DataFrame] = []
    reconciliation_summary_frames: list[pd.DataFrame] = []
    suspicious_frames: list[pd.DataFrame] = []
    review_sample_frames: list[pd.DataFrame] = []

    for year in range(start_year, end_year + 1):
        summary_rows: list[dict[str, Any]] = []
        processed_path = processed_dir / f"raw_fundamentals_{year}.csv"

        if processed_path.exists():
            raw_processed = load_stage1_year(processed_path)
            summary_rows.append(
                _summary_row(
                    year=year,
                    check_name="processed_file_exists",
                    status="pass",
                    observed_value=str(processed_path),
                    expected_value="exists",
                    detail="published Stage 1 file found",
                )
            )
        else:
            raw_processed = pd.DataFrame(columns=STAGE1_RAW_COLUMNS)
            schema_issue_frames.append(
                pd.DataFrame(
                    [
                        {
                            "year": year,
                            "issue_type": "missing_processed_file",
                            "expected_columns": "|".join(STAGE1_RAW_COLUMNS),
                            "observed_columns": "",
                            "detail": f"missing processed file: {processed_path}",
                        }
                    ],
                    columns=SCHEMA_ISSUES_COLUMNS,
                )
            )
            summary_rows.append(
                _summary_row(
                    year=year,
                    check_name="processed_file_exists",
                    status="fail",
                    observed_value="missing",
                    expected_value=str(processed_path),
                    detail="published Stage 1 file not found",
                )
            )

        schema_issues = check_stage1_columns(raw_processed, year)
        schema_issue_frames.append(schema_issues)
        summary_rows.append(
            _summary_row(
                year=year,
                check_name="columns_match_contract",
                status="pass" if schema_issues.empty else "fail",
                observed_value=0 if schema_issues.empty else len(schema_issues),
                expected_value=0,
                detail="column-order validation against Stage 1 contract",
            )
        )

        processed = _coerce_stage1_frame(raw_processed)
        key_issues = check_stage1_key_uniqueness(processed, year)
        key_issue_frames.append(key_issues)
        summary_rows.append(
            _summary_row(
                year=year,
                check_name="duplicate_quarter_keys",
                status="pass" if key_issues.empty else "fail",
                observed_value=int(key_issues["row_count"].sum()) if not key_issues.empty else 0,
                expected_value=0,
                detail="duplicate ticker/year/quarter keys in published file",
            )
        )

        sorted_ok = check_stage1_sort_order(processed)
        summary_rows.append(
            _summary_row(
                year=year,
                check_name="sorted_by_key",
                status="pass" if sorted_ok else "fail",
                observed_value=sorted_ok,
                expected_value=True,
                detail="rows should be sorted by ticker, year, quarter",
            )
        )

        field_nulls = build_field_nulls_report(processed, year)
        field_null_frames.append(field_nulls)

        quarter_counts = (
            processed.groupby("ticker")["quarter"].nunique()
            if not processed.empty
            else pd.Series(dtype="int64")
        )
        summary_rows.extend(
            [
                _summary_row(
                    year=year,
                    check_name="rows_emitted",
                    status="info",
                    observed_value=int(len(processed)),
                    expected_value=">= 0",
                    detail="published Stage 1 row count",
                ),
                _summary_row(
                    year=year,
                    check_name="unique_tickers_emitted",
                    status="info",
                    observed_value=int(processed["ticker"].nunique()) if not processed.empty else 0,
                    expected_value=">= 0",
                    detail="distinct tickers in published Stage 1 file",
                ),
                _summary_row(
                    year=year,
                    check_name="tickers_with_full_coverage",
                    status="info",
                    observed_value=int((quarter_counts == 4).sum()) if not quarter_counts.empty else 0,
                    expected_value="informational",
                    detail="tickers with four emitted quarters",
                ),
            ]
        )

        expected = build_expected_stage1_frame(
            universe_path=universe_path,
            raw_dir=raw_dir,
            year=year,
        )
        reconciliation, reconciliation_summary = reconcile_processed_vs_expected(
            processed,
            expected,
            year,
        )
        reconciliation_frames.append(reconciliation)
        reconciliation_summary_frames.append(reconciliation_summary)
        mismatch_count = int(reconciliation_summary.loc[0, "mismatches"])
        summary_rows.append(
            _summary_row(
                year=year,
                check_name="source_reconciliation_mismatches",
                status="pass" if mismatch_count == 0 else "fail",
                observed_value=mismatch_count,
                expected_value=0,
                detail="field-level differences between published and reconstructed Stage 1 rows",
            )
        )

        suspicious = build_suspicious_values_report(
            processed,
            field_nulls,
            reconciliation,
            year,
        )
        suspicious_frames.append(suspicious)
        review_sample_frames.append(build_review_sample(suspicious))
        summary_frames.append(pd.DataFrame(summary_rows, columns=AUDIT_SUMMARY_COLUMNS))

    summary_output = reports_dir / f"legacy_stage1_audit_summary_{start_year}_{end_year}.csv"
    schema_output = reports_dir / f"legacy_stage1_schema_issues_{start_year}_{end_year}.csv"
    key_output = reports_dir / f"legacy_stage1_key_issues_{start_year}_{end_year}.csv"
    field_nulls_output = reports_dir / f"legacy_stage1_field_nulls_{start_year}_{end_year}.csv"
    reconciliation_output = reports_dir / f"legacy_stage1_reconciliation_{start_year}_{end_year}.csv"
    reconciliation_summary_output = (
        reports_dir / f"legacy_stage1_reconciliation_summary_{start_year}_{end_year}.csv"
    )
    suspicious_output = reports_dir / f"legacy_stage1_suspicious_values_{start_year}_{end_year}.csv"
    review_sample_output = reports_dir / f"legacy_stage1_review_sample_{start_year}_{end_year}.csv"

    _write_report(pd.concat(summary_frames, ignore_index=True), summary_output, "summary")
    _write_report(
        pd.concat(schema_issue_frames, ignore_index=True)
        if schema_issue_frames
        else _empty_frame(SCHEMA_ISSUES_COLUMNS),
        schema_output,
        "schema_issues",
    )
    _write_report(
        pd.concat(key_issue_frames, ignore_index=True) if key_issue_frames else _empty_frame(KEY_ISSUES_COLUMNS),
        key_output,
        "key_issues",
    )
    _write_report(
        pd.concat(field_null_frames, ignore_index=True),
        field_nulls_output,
        "field_nulls",
    )
    _write_report(
        pd.concat(reconciliation_frames, ignore_index=True),
        reconciliation_output,
        "reconciliation",
    )
    _write_report(
        pd.concat(reconciliation_summary_frames, ignore_index=True),
        reconciliation_summary_output,
        "reconciliation_summary",
    )
    _write_report(
        pd.concat(suspicious_frames, ignore_index=True)
        if suspicious_frames
        else _empty_frame(SUSPICIOUS_VALUES_COLUMNS),
        suspicious_output,
        "suspicious_values",
    )
    _write_report(
        pd.concat(review_sample_frames, ignore_index=True)
        if review_sample_frames
        else _empty_frame(REVIEW_SAMPLE_COLUMNS),
        review_sample_output,
        "review_sample",
    )

    return {
        "summary_output": str(summary_output),
        "schema_output": str(schema_output),
        "key_output": str(key_output),
        "field_nulls_output": str(field_nulls_output),
        "reconciliation_output": str(reconciliation_output),
        "reconciliation_summary_output": str(reconciliation_summary_output),
        "suspicious_output": str(suspicious_output),
        "review_sample_output": str(review_sample_output),
    }
