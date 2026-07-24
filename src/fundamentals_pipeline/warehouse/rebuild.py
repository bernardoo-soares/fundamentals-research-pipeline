"""Atomic warehouse rebuild: build to temp, validate, swap over the live DB."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .annualize import build_fundamentals_annual
from .connection import open_warehouse
from .fundamentals_loader import load_fundamentals_quarterly
from .schema import WAREHOUSE_PIPELINE_VERSION, create_all_tables
from .validation import build_health_report, write_plausibility_violations


def rebuild_warehouse(
    *,
    processed_dir: str | Path,
    warehouse_path: str | Path,
    reports_dir: str | Path,
    start_year: int,
    end_year: int,
    pipeline_version: str = WAREHOUSE_PIPELINE_VERSION,
) -> dict[str, str]:
    """Rebuild the warehouse from the Stage 1 CSVs, atomically."""
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year.")

    warehouse = Path(warehouse_path)
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = warehouse.with_suffix(warehouse.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    run_id = str(uuid.uuid4())
    started = datetime.now(UTC).replace(tzinfo=None)
    health_path = ""
    try:
        with open_warehouse(tmp_path, read_only=False) as conn:
            create_all_tables(conn)
            quarterly_rows, violations = load_fundamentals_quarterly(
                conn,
                processed_dir=processed_dir,
                start_year=start_year,
                end_year=end_year,
                pipeline_version=pipeline_version,
            )
            annual_rows = build_fundamentals_annual(
                conn, pipeline_version=pipeline_version
            )
            health_path = build_health_report(
                conn,
                reports_dir=reports_dir,
                start_year=start_year,
                end_year=end_year,
            )
            violations_path = write_plausibility_violations(
                violations,
                reports_dir=reports_dir,
                start_year=start_year,
                end_year=end_year,
            )
            finished = datetime.now(UTC).replace(tzinfo=None)
            # build_log records successful rebuilds only: a failed rebuild raises
            # (see the except block below) and discards the temp DB, so this
            # atomic no-op never reaches this INSERT. The schema's 'failed'
            # gate_status is intentionally never written in v1.
            conn.execute(
                "INSERT INTO build_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id,
                    started,
                    finished,
                    start_year,
                    end_year,
                    quarterly_rows,
                    annual_rows,
                    "passed",
                    health_path,
                    pipeline_version,
                ],
            )
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    os.replace(tmp_path, warehouse)
    return {
        "warehouse_path": str(warehouse),
        "health_report_path": health_path,
        "plausibility_violations_path": violations_path,
        "plausibility_nulled_count": str(len(violations)),
    }
