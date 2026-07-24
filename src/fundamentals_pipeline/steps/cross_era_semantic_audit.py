"""Measure legacy-vs-SimFin agreement on the provider overlap window.

Verifies the declarations in `contracts/field_era_semantics.py` against real
data. A field declared equivalent whose measured agreement falls below its
declared threshold is a contradiction: the declaration and the data disagree,
and one of them is wrong.

The comparison is pure; only `run_cross_era_audit` touches the filesystem.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd

from ..contracts.field_era_semantics import Basis, declared_fields, semantics_for
from ..contracts.stage1_fundamentals_schema import STAGE1_KEY_COLUMNS
from ..core.exceptions import CrossEraContradictionError

RECONCILIATION_COLUMNS: tuple[str, ...] = (
    "field",
    "verdict",
    "n_compared",
    "agreement_rate",
    "median_rel_diff",
    "p90_rel_diff",
    "sign_flip_rate",
    "magnitude_ratio",
    "null_rate_legacy",
    "null_rate_simfin",
    "declared_equivalent",
    "note",
)

# Below this many jointly-present rows, a field's agreement is not measurable
# and is reported as insufficient_overlap rather than as agreement.
MIN_OVERLAP_ROWS = 20


class Verdict(StrEnum):
    """Closed set of reconciliation outcomes."""

    AGREE = "agree"
    DIVERGENT_DECLARED = "divergent_declared"
    CONTRADICTION = "CONTRADICTION"
    INSUFFICIENT_OVERLAP = "insufficient_overlap"


def _relative_difference(legacy: pd.Series, simfin: pd.Series) -> pd.Series:
    """Elementwise |a-b| / |b|, turning a zero denominator into NaN.

    Guarding rather than dividing keeps inf out of the report entirely.
    """
    denominator = simfin.abs().where(simfin.abs() > 0)
    return (legacy - simfin).abs() / denominator


def _comparable_rows(merged: pd.DataFrame, field: str) -> pd.DataFrame:
    """Restrict the merged frame to rows on which a field is comparable.

    Year-to-date fields are only comparable at Q4. Legacy states them
    cumulatively (KO dvy 2023: 101 / 2089 / 4078 / 7952) while SimFin
    broadcasts the annual total into all four quarters, so Q1-Q3 disagree by
    construction and would fabricate a contradiction. Q4 is the point where
    both conventions represent the same full-year quantity -- and it is the
    value annualization actually consumes.
    """
    declaration = semantics_for(field)
    bases = {
        source.basis
        for source in (declaration.legacy, declaration.simfin)
        if source is not None
    }
    if Basis.YEAR_TO_DATE in bases and "quarter" in merged.columns:
        return merged[merged["quarter"] == 4]
    return merged


def _empty_metrics() -> dict[str, object]:
    """Metric fields for a row that could not be measured."""
    return {
        "agreement_rate": None,
        "median_rel_diff": None,
        "p90_rel_diff": None,
        "sign_flip_rate": None,
        "magnitude_ratio": None,
    }


def _field_row(
    legacy: pd.Series,
    simfin: pd.Series,
    field: str,
) -> dict[str, object]:
    """Compute one field's reconciliation metrics against its declaration."""
    declaration = semantics_for(field)
    both = legacy.notna() & simfin.notna()
    n_compared = int(both.sum())

    row: dict[str, object] = {
        "field": field,
        "n_compared": n_compared,
        "null_rate_legacy": float(legacy.isna().mean()) if len(legacy) else 1.0,
        "null_rate_simfin": float(simfin.isna().mean()) if len(simfin) else 1.0,
        "declared_equivalent": declaration.eras_equivalent,
        "note": declaration.divergence_note,
        **_empty_metrics(),
    }

    if n_compared < MIN_OVERLAP_ROWS:
        row["verdict"] = Verdict.INSUFFICIENT_OVERLAP
        return row

    left, right = legacy[both], simfin[both]
    relative = _relative_difference(left, right).dropna()
    agreement_rate = (
        float((relative <= declaration.value_tolerance).mean())
        if len(relative)
        else 0.0
    )
    median_right = float(right.median())

    row["agreement_rate"] = agreement_rate
    row["median_rel_diff"] = float(relative.median()) if len(relative) else None
    row["p90_rel_diff"] = float(relative.quantile(0.90)) if len(relative) else None
    row["sign_flip_rate"] = float((np.sign(left) != np.sign(right)).mean())
    row["magnitude_ratio"] = (
        float(left.median()) / median_right if median_right != 0 else None
    )

    if not declaration.eras_equivalent:
        row["verdict"] = Verdict.DIVERGENT_DECLARED
    elif agreement_rate < declaration.min_agreement_rate:
        row["verdict"] = Verdict.CONTRADICTION
    else:
        row["verdict"] = Verdict.AGREE
    return row


def reconcile_frames(
    legacy_frame: pd.DataFrame,
    simfin_frame: pd.DataFrame,
    *,
    fields: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Compare two era frames on shared keys; one row per field.

    Pure: no I/O, no clock, no randomness. Field order is sorted so the
    output is deterministic regardless of declaration order.
    """
    target_fields = (
        tuple(fields) if fields is not None else tuple(sorted(declared_fields()))
    )
    keys = list(STAGE1_KEY_COLUMNS)
    merged = legacy_frame.merge(
        simfin_frame, on=keys, how="inner", suffixes=("_legacy", "_simfin")
    )

    rows: list[dict[str, object]] = []
    for field in target_fields:
        left_column = f"{field}_legacy"
        right_column = f"{field}_simfin"
        if left_column not in merged.columns or right_column not in merged.columns:
            empty = pd.Series(dtype="float64")
            rows.append(_field_row(empty, empty, field))
            continue
        comparable = _comparable_rows(merged, field)
        rows.append(
            _field_row(
                pd.to_numeric(comparable[left_column], errors="coerce"),
                pd.to_numeric(comparable[right_column], errors="coerce"),
                field,
            )
        )
    return pd.DataFrame(rows, columns=list(RECONCILIATION_COLUMNS))


def load_era_frame(staging_dir: str | Path, year: int) -> pd.DataFrame:
    """Read one provider's staged Stage 1 CSV for a fiscal year.

    Each builder writes into its own staging directory so the two eras stay
    separable; `steps/stage1_era_resolution.py` merges them into the single
    published CSV.
    """
    path = Path(staging_dir) / f"raw_fundamentals_{year}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Staged Stage 1 file not found: {path}")
    return pd.read_csv(path)


def run_cross_era_audit_from_dirs(
    *,
    legacy_dir: str | Path,
    simfin_dir: str | Path,
    reports_dir: str | Path,
    year: int,
) -> dict[str, object]:
    """Load both providers' staged frames for a year and reconcile them."""
    return run_cross_era_audit(
        legacy_frame=load_era_frame(legacy_dir, year),
        simfin_frame=load_era_frame(simfin_dir, year),
        reports_dir=reports_dir,
        year=year,
    )


def run_cross_era_audit(
    *,
    legacy_frame: pd.DataFrame,
    simfin_frame: pd.DataFrame,
    reports_dir: str | Path,
    year: int,
    fields: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Reconcile, write the report, then raise if an equivalence is contradicted.

    The report is written before the raise so a failing run still leaves its
    evidence on disk. Raises `CrossEraContradictionError` rather than exiting:
    mapping failures to exit codes belongs to the CLI.
    """
    report = reconcile_frames(legacy_frame, simfin_frame, fields=fields)

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / f"cross_era_reconciliation_{year}.csv"
    report.to_csv(report_path, index=False)

    contradictions = tuple(
        report.loc[report["verdict"] == Verdict.CONTRADICTION, "field"].tolist()
    )
    result: dict[str, object] = {
        "report_path": str(report_path),
        "fields_compared": int(len(report)),
        "contradiction_count": len(contradictions),
        "contradiction_fields": contradictions,
    }
    if contradictions:
        raise CrossEraContradictionError(
            "Declared era equivalence contradicted by data for: "
            f"{', '.join(contradictions)}. See {report_path}.",
            fields=contradictions,
            report_path=str(report_path),
        )
    return result
