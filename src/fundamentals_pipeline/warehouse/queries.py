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

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..contracts.company_profile_schema import COMPANIES_COLUMNS
from ..contracts.fundamentals_annual_schema import ANNUAL_VALUE_COLUMNS
from ..contracts.scorecard_schema import FISCAL_YEAR_END_QUARTER, QUARTERS_PER_YEAR
from ..contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
    SUPPORT_RAW_FIELDS,
)
from ..portfolio.comparison import MAX_START_LOOKBACK_DAYS
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
# Optional: names and GICS sectors. See `has_companies`.
COMPANIES_TABLE = "companies"
PRICES_DAILY_TABLE = "prices_daily"
BENCHMARK_TABLE = "benchmark_daily"

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
    # LEFT JOIN, always: a ticker that has left the index has no
    # current-membership row, and it must still be ranked and shown, by ticker
    # alone. An INNER JOIN here would silently drop 10 of 494 companies.
    profile = (
        f"LEFT JOIN {COMPANIES_TABLE} c ON c.ticker = s.ticker"
        if has_companies(warehouse_path)
        else ""
    )
    name_columns = (
        "c.company_name, c.sector" if profile else "NULL AS company_name, NULL AS sector"
    )
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT
              s.ticker,
              {name_columns},
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
            {profile}
            WHERE s.as_of_year = ?
            ORDER BY s.composite DESC, s.ticker
            """,
            [as_of_year],
        ).fetchdf()


def has_companies(warehouse_path: str | Path) -> bool:
    """Whether the optional `companies` table has been built.

    Optional rather than required: the console is fully usable without names,
    and blocking it behind a network fetch would be a worse failure than
    showing tickers. When it is absent the ranking says so, rather than
    quietly rendering a blank column.
    """
    with _connect(warehouse_path) as conn:
        return bool(
            conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = ?",
                [COMPANIES_TABLE],
            ).fetchone()[0]
        )


def sectors(warehouse_path: str | Path, *, as_of_year: int) -> list[str]:
    """GICS sectors present among scored tickers, alphabetical.

    Current classification, not the classification as of `as_of_year`; see
    `contracts/company_profile_schema.py`.
    """
    if not has_companies(warehouse_path):
        return []
    with _connect(warehouse_path) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT c.sector
            FROM {SCORES_TABLE} s
            JOIN {COMPANIES_TABLE} c ON c.ticker = s.ticker
            WHERE s.as_of_year = ? AND c.sector IS NOT NULL
            ORDER BY c.sector
            """,
            [as_of_year],
        ).fetchall()
    return [row[0] for row in rows]


def company(warehouse_path: str | Path, *, ticker: str) -> pd.DataFrame:
    """One company's identity row, or an empty frame if it has no current one."""
    if not has_companies(warehouse_path):
        return pd.DataFrame(columns=list(COMPANIES_COLUMNS))
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"SELECT * FROM {COMPANIES_TABLE} WHERE ticker = ?", [ticker]
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


def quarterly_metric_values(
    warehouse_path: str | Path,
    *,
    ticker: str,
    metric_ids: tuple[str, ...],
    year: int,
    quarter: int = FISCAL_YEAR_END_QUARTER,
) -> pd.DataFrame:
    """Published values for named quarterly metrics at one ticker-quarter.

    Used for the operand totals the console shows beneath a criterion. These
    come from `metrics_quarterly`, so the total on screen is the same
    versioned, era-guarded, reason-coded figure the engine computed -- not a
    second derivation of the TTM rule (AGENTS.md S2.6).
    """
    if not metric_ids:
        return pd.DataFrame(
            columns=[
                "metric_id",
                "value",
                "reason_code",
                "quality_flag",
                "metric_version",
            ]
        )
    placeholders = ", ".join("?" for _ in metric_ids)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT metric_id, value, reason_code, quality_flag, metric_version
            FROM {METRICS_QUARTERLY_TABLE}
            WHERE ticker = ? AND year = ? AND quarter = ?
              AND metric_id IN ({placeholders})
            ORDER BY metric_id
            """,
            [ticker, year, quarter, *metric_ids],
        ).fetchdf()


def trend_metric_values(
    warehouse_path: str | Path,
    *,
    ticker: str,
    metric_ids: tuple[str, ...],
    as_of_year: int,
) -> pd.DataFrame:
    """Published values for named trend metrics at one ticker-year.

    The trend-grain counterpart of `quarterly_metric_values`, used for the
    derived intermediates the console shows beneath a criterion.
    """
    if not metric_ids:
        return pd.DataFrame(
            columns=[
                "metric_id",
                "value",
                "reason_code",
                "quality_flag",
                "metric_version",
            ]
        )
    placeholders = ", ".join("?" for _ in metric_ids)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT metric_id, value, reason_code, quality_flag, metric_version
            FROM {METRICS_TREND_TABLE}
            WHERE ticker = ? AND as_of_year = ?
              AND metric_id IN ({placeholders})
            ORDER BY metric_id
            """,
            [ticker, as_of_year, *metric_ids],
        ).fetchdf()


def trend_metric_series(
    warehouse_path: str | Path,
    *,
    ticker: str,
    metric_ids: tuple[str, ...],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """A per-year derived series across a window, one row per metric-year.

    For the intermediates a threshold metric tests: `net_margin_ge20_years_10y`
    reports a fraction of years above 0.20, and only the whole series shows
    WHICH years cleared it. A single year's value cannot answer that.

    Null years are returned as rows with their reason code, never dropped.
    """
    if not metric_ids:
        return pd.DataFrame(
            columns=["metric_id", "as_of_year", "value", "reason_code"]
        )
    placeholders = ", ".join("?" for _ in metric_ids)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT metric_id, as_of_year, value, reason_code
            FROM {METRICS_TREND_TABLE}
            WHERE ticker = ? AND metric_id IN ({placeholders})
              AND as_of_year BETWEEN ? AND ?
            ORDER BY metric_id, as_of_year
            """,
            [ticker, *metric_ids, start_year, end_year],
        ).fetchdf()


def has_benchmark(warehouse_path: str | Path) -> bool:
    """Whether the benchmark series has been built."""
    with _connect(warehouse_path) as conn:
        return bool(
            conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = ?",
                [BENCHMARK_TABLE],
            ).fetchone()[0]
        )


def price_history(
    warehouse_path: str | Path,
    *,
    tickers: tuple[str, ...],
    start: date,
    end: date,
) -> pd.DataFrame:
    """Daily closes for a selection, long-form `(ticker, date, close)`.

    A window's start look-back needs prices slightly BEFORE `start`, so the
    query reaches back by `MAX_START_LOOKBACK_DAYS`; the comparison then does
    the as-of selection. Widening the window here rather than there keeps the
    look-back rule in one place.
    """
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    placeholders = ", ".join("?" for _ in tickers)
    reach = start - timedelta(days=MAX_START_LOOKBACK_DAYS)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT ticker, date, close
            FROM {PRICES_DAILY_TABLE}
            WHERE ticker IN ({placeholders})
              AND date BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            [*tickers, reach, end],
        ).fetchdf()


def benchmark_history(
    warehouse_path: str | Path, *, start: date, end: date
) -> pd.DataFrame:
    """Daily benchmark closes, long-form `(date, close)`."""
    if not has_benchmark(warehouse_path):
        return pd.DataFrame(columns=["date", "close"])
    reach = start - timedelta(days=MAX_START_LOOKBACK_DAYS)
    with _connect(warehouse_path) as conn:
        return conn.execute(
            f"""
            SELECT date, close
            FROM {BENCHMARK_TABLE}
            WHERE date BETWEEN ? AND ? AND close IS NOT NULL
            ORDER BY date
            """,
            [reach, end],
        ).fetchdf()


def price_coverage(warehouse_path: str | Path) -> tuple[date, date] | None:
    """The first and last date any price exists for, or None if unpriced."""
    if not has_benchmark(warehouse_path):
        return None
    with _connect(warehouse_path) as conn:
        row = conn.execute(
            f"SELECT MIN(date), MAX(date) FROM {BENCHMARK_TABLE}"
        ).fetchone()
    return (row[0], row[1]) if row and row[0] else None


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
