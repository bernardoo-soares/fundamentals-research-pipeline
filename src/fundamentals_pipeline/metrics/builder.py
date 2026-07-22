"""Build the metrics_trend table from fundamentals_annual (callable core)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..contracts.stage2_metrics_schema import (
    METRICS_PIPELINE_VERSION,
    METRICS_TREND_COLUMNS,
    create_metrics_trend_ddl,
)
from ..warehouse.connection import open_warehouse
from .registry import REGISTRY


def _compute_rows(annual: pd.DataFrame, registry, pipeline_version: str) -> list[dict]:
    computed_at = datetime.now(UTC).replace(tzinfo=None)
    rows: list[dict] = []
    for ticker, group in annual.groupby("ticker"):
        frame = group.sort_values("fiscal_year")
        for metric in registry:
            for point in metric.compute(frame):
                rows.append(
                    {
                        "ticker": ticker,
                        "as_of_year": point.as_of_year,
                        "metric_id": metric.metric_id,
                        "value": point.value,
                        "reason_code": point.reason_code,
                        "window_length": metric.window_length,
                        "window_years_present": point.window_years_present,
                        "metric_version": metric.version,
                        "computed_at": computed_at,
                        "pipeline_version": pipeline_version,
                    }
                )
    return rows


def build_metrics_trend(
    *,
    warehouse_path: str | Path,
    registry=REGISTRY,
    pipeline_version: str = METRICS_PIPELINE_VERSION,
) -> dict[str, object]:
    """Read fundamentals_annual, compute trend metrics, (re)build metrics_trend."""
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    with open_warehouse(path, read_only=False) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        if "fundamentals_annual" not in tables:
            raise FileNotFoundError(
                "fundamentals_annual not found; run warehouse-rebuild first."
            )
        annual = conn.execute("SELECT * FROM fundamentals_annual").df()
        rows = _compute_rows(annual, registry, pipeline_version)
        frame = pd.DataFrame(rows, columns=list(METRICS_TREND_COLUMNS))

        conn.execute("DROP TABLE IF EXISTS metrics_trend")
        conn.execute(create_metrics_trend_ddl())
        if not frame.empty:
            conn.register("staging_metrics", frame)
            try:
                columns = ", ".join(METRICS_TREND_COLUMNS)
                conn.execute(
                    f"INSERT INTO metrics_trend ({columns}) "
                    f"SELECT {columns} FROM staging_metrics"
                )
            finally:
                conn.unregister("staging_metrics")

    per_metric = (
        frame.groupby("metric_id").size().astype(int).to_dict()
        if not frame.empty
        else {}
    )
    return {
        "metrics_trend_rows": int(len(frame)),
        "metric_count": len(registry),
        "per_metric_counts": per_metric,
    }
