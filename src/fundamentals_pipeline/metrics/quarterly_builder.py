"""Build the metrics_quarterly table from fundamentals_quarterly (callable core).

The only module boundary that reads fundamentals_quarterly and writes
metrics_quarterly. Compute stays pure in metrics/quarterly.py; this function is
the I/O edge. Rebuild is idempotent: the table is dropped and recreated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..contracts.metrics_quarterly_schema import (
    METRICS_QUARTERLY_COLUMNS,
    METRICS_QUARTERLY_PIPELINE_VERSION,
    create_metrics_quarterly_ddl,
)
from ..warehouse.connection import open_warehouse
from .quarterly import apply_era_restriction
from .quarterly_registry import QUARTERLY_REGISTRY

_SOURCE_TABLE = "fundamentals_quarterly"
_TARGET_TABLE = "metrics_quarterly"
_STAGING_VIEW = "staging_metrics_quarterly"


def _compute_rows(
    quarterly: pd.DataFrame, registry, pipeline_version: str
) -> list[dict]:
    computed_at = datetime.now(UTC).replace(tzinfo=None)
    rows: list[dict] = []
    for ticker, group in quarterly.groupby("ticker"):
        for metric in registry:
            points = apply_era_restriction(
                metric.compute(group), metric.supported_eras
            )
            for point in points:
                rows.append(
                    {
                        "ticker": ticker,
                        "year": point.year,
                        "quarter": point.quarter,
                        "metric_id": metric.metric_id,
                        "value": point.value,
                        "reason_code": point.reason_code,
                        "quality_flag": point.quality_flag,
                        "source_era": point.source_era,
                        "metric_version": metric.version,
                        "computed_at": computed_at,
                        "pipeline_version": pipeline_version,
                    }
                )
    return rows


def build_metrics_quarterly(
    *,
    warehouse_path: str | Path,
    registry=QUARTERLY_REGISTRY,
    pipeline_version: str = METRICS_QUARTERLY_PIPELINE_VERSION,
) -> dict[str, object]:
    """Read fundamentals_quarterly, compute quarterly metrics, (re)build the table."""
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    with open_warehouse(path, read_only=False) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        if _SOURCE_TABLE not in tables:
            raise FileNotFoundError(
                f"{_SOURCE_TABLE} not found; run warehouse-rebuild first."
            )
        quarterly = conn.execute(f"SELECT * FROM {_SOURCE_TABLE}").df()
        rows = _compute_rows(quarterly, registry, pipeline_version)
        frame = pd.DataFrame(rows, columns=list(METRICS_QUARTERLY_COLUMNS))

        conn.execute(f"DROP TABLE IF EXISTS {_TARGET_TABLE}")
        conn.execute(create_metrics_quarterly_ddl())
        if not frame.empty:
            conn.register(_STAGING_VIEW, frame)
            try:
                columns = ", ".join(METRICS_QUARTERLY_COLUMNS)
                conn.execute(
                    f"INSERT INTO {_TARGET_TABLE} ({columns}) "
                    f"SELECT {columns} FROM {_STAGING_VIEW}"
                )
            finally:
                conn.unregister(_STAGING_VIEW)

    per_metric = (
        frame.groupby("metric_id").size().astype(int).to_dict()
        if not frame.empty
        else {}
    )
    reason_counts = (
        frame[frame["reason_code"].notna()]
        .groupby("reason_code")
        .size()
        .astype(int)
        .to_dict()
        if not frame.empty
        else {}
    )
    return {
        "metrics_quarterly_rows": int(len(frame)),
        "metric_count": len(registry),
        "per_metric_counts": per_metric,
        "reason_code_counts": reason_counts,
    }
