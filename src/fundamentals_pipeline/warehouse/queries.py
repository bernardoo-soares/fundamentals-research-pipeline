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

from ..contracts.fundamentals_annual_schema import ANNUAL_VALUE_COLUMNS
from ..contracts.scorecard_schema import FISCAL_YEAR_END_QUARTER, QUARTERS_PER_YEAR
from ..contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
    SUPPORT_RAW_FIELDS,
)
from .connection import open_warehouse

# The column names a metric may declare as an input, taken from the schema
# contracts rather than restated, so the allow-list cannot drift from the
# tables (AGENTS.md S2.6).
ANNUAL_INPUT_COLUMNS: tuple[str, ...] = ANNUAL_VALUE_COLUMNS
QUARTERLY_INPUT_FIELDS: tuple[str, ...] = (
    *CORE_RAW_FIELDS,
    *SUPPORT_RAW_FIELDS,
    *EXTENDED_RAW_FIELDS,
)

# Tables the console reads. Named once so a rename is a one-line change and a
# typo is not spread across a dozen f-strings (AGENTS.md S1.1).
SCORES_TABLE = "scores"
SCORE_COMPONENTS_TABLE = "score_components"
SCORE_CRITERIA_TABLE = "score_criteria"
METRICS_TREND_TABLE = "metrics_trend"
METRICS_QUARTERLY_TABLE = "metrics_quarterly"
FUNDAMENTALS_ANNUAL_TABLE = "fundamentals_annual"
FUNDAMENTALS_QUARTERLY_TABLE = "fundamentals_quarterly"
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


def _validate_fields(fields: tuple[str, ...], allowed: frozenset[str]) -> None:
    """Reject any column name not in the declared contract.

    These names reach a SQL string, so an unvalidated one is an injection
    seam. They come from the metric registries rather than from a user, but
    checking is one line and the alternative is trusting an f-string.
    """
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"Not warehouse columns: {unknown}")


def annual_inputs(
    warehouse_path: str | Path,
    *,
    ticker: str,
    fields: tuple[str, ...],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Raw annual operands behind a trend metric, one row per year.

    NO DERIVED TOTAL IS RETURNED, DELIBERATELY
    ------------------------------------------
    The obvious thing to return alongside these is the window sum or the TTM
    the metric used. That would be the same rule -- annualisation, TTM, the
    null policy -- expressed a second time, which AGENTS.md S2.6 calls a
    defect, and the two would eventually disagree. Worse, the metric engine
    nulls a window that crosses the provider boundary while a naive SQL sum
    would happily add across it, so the console would display a total the
    engine had refused to compute.

    So the audit trail is the operands and their fiscal periods; the derived
    figure is the metric's own published value, shown beside them.
    """
    if not fields:
        return pd.DataFrame(columns=["fiscal_year", "source_era", "field", "value"])
    _validate_fields(fields, frozenset(ANNUAL_INPUT_COLUMNS))
    selected = ", ".join(fields)
    names = ", ".join(f"'{field}'" for field in fields)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT fiscal_year, source_era, field, value
            FROM (
              SELECT fiscal_year, source_era, {selected}
              FROM {FUNDAMENTALS_ANNUAL_TABLE}
              WHERE ticker = ? AND fiscal_year BETWEEN ? AND ?
            )
            UNPIVOT INCLUDE NULLS (value FOR field IN ({names}))
            ORDER BY field, fiscal_year
            """,
            [ticker, start_year, end_year],
        ).fetchdf()


def quarterly_inputs(
    warehouse_path: str | Path,
    *,
    ticker: str,
    fields: tuple[str, ...],
    end_year: int,
    quarters: int,
) -> pd.DataFrame:
    """Raw quarterly operands behind a point-in-time metric, newest last.

    Returns the `quarters` most recent quarters up to and including the fiscal
    year end, which is the window a TTM metric reads. As with `annual_inputs`,
    no TTM total is derived here.
    """
    if not fields:
        return pd.DataFrame(
            columns=["year", "quarter", "source_era", "field", "value"]
        )
    _validate_fields(fields, frozenset(QUARTERLY_INPUT_FIELDS))
    selected = ", ".join(fields)
    names = ", ".join(f"'{field}'" for field in fields)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT year, quarter, source_era, field, value
            FROM (
              SELECT year, quarter, source_era, {selected}
              FROM {FUNDAMENTALS_QUARTERLY_TABLE}
              WHERE ticker = ?
                AND (year * {QUARTERS_PER_YEAR} + quarter)
                    <= (? * {QUARTERS_PER_YEAR} + {FISCAL_YEAR_END_QUARTER})
                AND (year * {QUARTERS_PER_YEAR} + quarter)
                    >  (? * {QUARTERS_PER_YEAR} + {FISCAL_YEAR_END_QUARTER} - ?)
            )
            UNPIVOT INCLUDE NULLS (value FOR field IN ({names}))
            ORDER BY field, year, quarter
            """,
            [ticker, end_year, end_year, quarters],
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
