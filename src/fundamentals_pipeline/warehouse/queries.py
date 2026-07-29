"""Read-only query API for the research console (platform spec section 7.1).

The **only** module the UI reads the database through. Two rules make the
spec's "the UI computes nothing" guarantee structural rather than a convention
someone could forget:

1. Every connection here is opened read-only. The app cannot write even by
   accident.
2. Every function returns a frame of values already in the warehouse. Nothing
   here derives a number that a metric or scorer did not already publish and
   version. Formatting is the app's job; arithmetic is nobody's job at this
   layer.

Kept free of Streamlit so it is testable without a browser.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .connection import open_warehouse

# Tables the console reads. Named once so a rename is a one-line change and a
# typo is not spread across a dozen f-strings (AGENTS.md S1.1).
SCORES_TABLE = "scores"
SCORE_COMPONENTS_TABLE = "score_components"
SCORE_CRITERIA_TABLE = "score_criteria"
METRICS_TREND_TABLE = "metrics_trend"
METRICS_QUARTERLY_TABLE = "metrics_quarterly"
FUNDAMENTALS_ANNUAL_TABLE = "fundamentals_annual"
VALUATION_HISTORY_TABLE = "valuation_history"

REQUIRED_TABLES: tuple[str, ...] = (
    SCORES_TABLE,
    SCORE_COMPONENTS_TABLE,
    SCORE_CRITERIA_TABLE,
    METRICS_TREND_TABLE,
    VALUATION_HISTORY_TABLE,
)

# A metric present for fewer than this share of the scored universe is reported
# as structurally unavailable rather than charted. Measured 2026-07-29: the
# four era-casualty metrics sit at 4-6 of 344 (~1.7%), while the next-lowest
# live metric is retained_earnings_cagr_10y at 250 of 343 (72.9%). Any cut in
# that gap separates them; 0.10 is placed well clear of both.
STRUCTURALLY_ABSENT_MAX_COVERAGE = 0.10


class WarehouseUnavailable(RuntimeError):
    """The warehouse is missing, or missing a table the console requires.

    Raised instead of returning an empty frame: an empty ranking and a
    not-yet-built warehouse look identical on screen, and only one of them
    means the numbers are trustworthy.
    """


def _connect(warehouse_path: str | Path):
    path = Path(warehouse_path)
    if not path.exists():
        raise WarehouseUnavailable(
            f"Warehouse not found at {path}. Run the pipeline first: "
            "warehouse-rebuild, metrics-build, metrics-quarterly-build, "
            "scores-build, prices-build, valuation-build."
        )
    return open_warehouse(path, read_only=True)


def check_ready(warehouse_path: str | Path) -> None:
    """Raise `WarehouseUnavailable` unless every required table exists."""
    with _connect(warehouse_path) as conn:
        present = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    missing = [name for name in REQUIRED_TABLES if name not in present]
    if missing:
        raise WarehouseUnavailable(
            f"Warehouse at {warehouse_path} is missing {', '.join(missing)}. "
            "Run scores-build and valuation-build."
        )


def available_years(warehouse_path: str | Path) -> list[int]:
    """Scored fiscal years, newest first."""
    with _connect(warehouse_path) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT as_of_year FROM {SCORES_TABLE} ORDER BY as_of_year DESC"
        ).fetchall()
    return [int(row[0]) for row in rows]


def ranking(warehouse_path: str | Path, *, as_of_year: int) -> pd.DataFrame:
    """One row per scored ticker for a single fiscal year, ranked.

    Deliberately single-year: composites are not comparable across years
    (spec section 3, C1), so the API offers no shape that would let a caller
    build a cross-year comparison by accident.

    `evidence` is `coverage_ratio * composite` -- the portion of the score
    backed by measured criteria. It is the one derived column here, and it
    exists because it is the sort key the ranking is honest under; it is
    computed in SQL so the app still computes nothing.
    """
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT
              s.ticker,
              s.composite,
              s.coverage_ratio,
              s.coverage_ratio * s.composite AS evidence,
              s.checklist_passed,
              s.checklist_applicable,
              s.badges,
              s.reason_code,
              s.staleness_quarters,
              v.pe_ttm,
              v.market_cap,
              v.close,
              v.price_date
            FROM {SCORES_TABLE} s
            LEFT JOIN {VALUATION_HISTORY_TABLE} v
              ON v.ticker = s.ticker AND v.fiscal_year = s.as_of_year
            WHERE s.as_of_year = ?
            ORDER BY s.composite DESC, s.ticker
            """,
            [as_of_year],
        ).fetchdf()


def components(
    warehouse_path: str | Path, *, ticker: str, as_of_year: int
) -> pd.DataFrame:
    """Component scores and weights for one ticker-year, heaviest first."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT component_id, score, weight, coverage_ratio,
                   applicable_criteria, total_criteria,
                   era_unavailable_criteria, reason_code
            FROM {SCORE_COMPONENTS_TABLE}
            WHERE ticker = ? AND as_of_year = ?
            ORDER BY weight DESC, component_id
            """,
            [ticker, as_of_year],
        ).fetchdf()


def criteria(
    warehouse_path: str | Path, *, ticker: str, as_of_year: int
) -> pd.DataFrame:
    """Every criterion for one ticker-year: value, points, verdict, flag."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT component_id, criterion_id, metric_id, value, points,
                   weight, checklist_verdict, reason_code, quality_flag,
                   annotation
            FROM {SCORE_CRITERIA_TABLE}
            WHERE ticker = ? AND as_of_year = ?
            ORDER BY component_id, criterion_id
            """,
            [ticker, as_of_year],
        ).fetchdf()


def score_header(
    warehouse_path: str | Path, *, ticker: str, as_of_year: int
) -> pd.DataFrame:
    """The score row plus its provenance, for the drilldown header."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT ticker, as_of_year, composite, coverage_ratio,
                   checklist_passed, checklist_applicable, badges,
                   reason_code, staleness_quarters, scorer_name,
                   scorer_version, config_hash, pipeline_version, computed_at
            FROM {SCORES_TABLE}
            WHERE ticker = ? AND as_of_year = ?
            """,
            [ticker, as_of_year],
        ).fetchdf()


def trend_history(
    warehouse_path: str | Path, *, ticker: str, metric_id: str
) -> pd.DataFrame:
    """A metric's full history for one ticker, oldest first.

    Null years are returned as null rows, never dropped and never filled: a
    gap in the chart is the honest rendering of a gap in the data (C4).
    """
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT as_of_year, value, reason_code, quality_flag,
                   window_years_present, metric_version
            FROM {METRICS_TREND_TABLE}
            WHERE ticker = ? AND metric_id = ?
            ORDER BY as_of_year
            """,
            [ticker, metric_id],
        ).fetchdf()


def annual_fundamentals(
    warehouse_path: str | Path, *, ticker: str
) -> pd.DataFrame:
    """Raw annual inputs behind the metrics, for the drilldown's inputs row."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT fiscal_year, source_era, quarters_present, has_q4,
                   saleq_annual, niq_annual, epspxq_annual, ceqq_q4, atq_q4,
                   dlttq_q4, req_q4
            FROM {FUNDAMENTALS_ANNUAL_TABLE}
            WHERE ticker = ?
            ORDER BY fiscal_year
            """,
            [ticker],
        ).fetchdf()


def valuation(
    warehouse_path: str | Path, *, ticker: str, as_of_year: int
) -> pd.DataFrame:
    """The valuation strip for one ticker-year."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT ticker, fiscal_year, period_end_date, publish_date,
                   price_date, price_lag_days, close, shares_outstanding,
                   market_cap, net_income_ttm, pe_ttm, earnings_yield,
                   reason_code, quality_flag
            FROM {VALUATION_HISTORY_TABLE}
            WHERE ticker = ? AND fiscal_year = ?
            """,
            [ticker, as_of_year],
        ).fetchdf()


def metric_coverage(
    warehouse_path: str | Path, *, as_of_year: int
) -> pd.DataFrame:
    """Per-metric coverage for the data-health page, least covered first.

    `structurally_absent` marks a metric whose coverage sits below
    `STRUCTURALLY_ABSENT_MAX_COVERAGE`. The health page states those as an
    absence with a reason instead of charting them (C6).
    """
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT
              metric_id,
              COUNT(*) FILTER (WHERE value IS NOT NULL) AS present,
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE value IS NOT NULL) * 1.0 / COUNT(*)
                AS coverage,
              COUNT(*) FILTER (WHERE value IS NOT NULL) * 1.0 / COUNT(*)
                <= {STRUCTURALLY_ABSENT_MAX_COVERAGE} AS structurally_absent
            FROM {METRICS_TREND_TABLE}
            WHERE as_of_year = ?
            GROUP BY metric_id
            ORDER BY coverage, metric_id
            """,
            [as_of_year],
        ).fetchdf()


def reason_code_tally(
    warehouse_path: str | Path, *, as_of_year: int
) -> pd.DataFrame:
    """Why values are absent, most common first (data-health page)."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT reason_code, COUNT(*) AS rows
            FROM {METRICS_TREND_TABLE}
            WHERE as_of_year = ? AND reason_code IS NOT NULL
            GROUP BY reason_code
            ORDER BY rows DESC
            """,
            [as_of_year],
        ).fetchdf()


def quality_flag_tally(
    warehouse_path: str | Path, *, as_of_year: int
) -> pd.DataFrame:
    """Which known limitations are attached to real values, and how widely."""
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT quality_flag, COUNT(*) AS rows,
                   COUNT(DISTINCT ticker) AS tickers
            FROM {SCORE_CRITERIA_TABLE}
            WHERE as_of_year = ? AND quality_flag IS NOT NULL
            GROUP BY quality_flag
            ORDER BY rows DESC
            """,
            [as_of_year],
        ).fetchdf()


def coverage_distribution(
    warehouse_path: str | Path, *, as_of_year: int
) -> pd.DataFrame:
    """How many tickers clear each coverage threshold.

    The data-health page's answer to "how big is the trustworthy universe?",
    which measured 135 of 384 at 0.90 and 28 at 1.00 on FY2024.
    """
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT t.threshold,
                   COUNT(s.ticker) FILTER (
                     WHERE s.coverage_ratio >= t.threshold
                   ) AS tickers
            FROM (SELECT UNNEST([0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0])
                    AS threshold) t
            CROSS JOIN {SCORES_TABLE} s
            WHERE s.as_of_year = ?
            GROUP BY t.threshold
            ORDER BY t.threshold
            """,
            [as_of_year],
        ).fetchdf()
