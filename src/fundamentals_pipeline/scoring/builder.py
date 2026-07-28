"""Build the score tables from the metrics grain (callable core).

The only module in `scoring/` that touches the warehouse, mirroring
`metrics/builder.py`. Everything it calls -- the config loader, the ramps, the
scorer -- is pure; this function is the I/O edge (S2.4). Rebuild is idempotent:
the three tables are dropped and recreated.

A scorer reads only the `metrics_*` tables, so this builder reads only those
too: raw fundamentals are deliberately out of reach, which is what keeps the
metrics layer usable as a future ML feature matrix with no leakage path
(spec 7.1).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..contracts.scorecard_schema import (
    BADGE_SEPARATOR,
    FISCAL_YEAR_END_QUARTER,
    QUARTERS_PER_YEAR,
    SCORE_COMPONENTS_COLUMNS,
    SCORE_CRITERIA_COLUMNS,
    SCORES_COLUMNS,
    SCORES_PIPELINE_VERSION,
    MetricReading,
    Scorer,
    ScorerInput,
    ScorerOutput,
    create_score_components_ddl,
    create_score_criteria_ddl,
    create_scores_ddl,
)
from ..warehouse.connection import open_warehouse
from .buffett_scorer import BuffettHeuristicScorer
from .config import load_scorecard_config

_TREND_TABLE = "metrics_trend"
_QUARTERLY_TABLE = "metrics_quarterly"

# Target table -> (DDL factory, column contract). Adding a fourth score table is
# one entry here, not a fourth copy of the drop/create/insert block (S2.2).
_TARGETS: tuple[tuple[str, object, tuple[str, ...]], ...] = (
    ("scores", create_scores_ddl, SCORES_COLUMNS),
    ("score_components", create_score_components_ddl, SCORE_COMPONENTS_COLUMNS),
    ("score_criteria", create_score_criteria_ddl, SCORE_CRITERIA_COLUMNS),
)

_STAGING_PREFIX = "staging_"

# Ticker-year identity used to key the reading map and to order the output.
TickerYear = tuple[str, int]


def quarter_ordinal(year: int, quarter: int) -> int:
    """Map a fiscal quarter onto a single monotonically increasing integer.

    Lets "how many quarters apart" be plain subtraction. Valid because quarter
    is always 1..4, so the encoding never carries into the year term.
    """
    return year * QUARTERS_PER_YEAR + quarter


def _load_readings(conn) -> dict[TickerYear, dict[str, MetricReading]]:
    """Collect every metric reading the scorer may see, keyed by ticker-year.

    Two grains feed one flat map. Trend metrics are already annual. Quarterly
    metrics are taken at `FISCAL_YEAR_END_QUARTER` only: that is the same
    fiscal-year-end convention `warehouse/annualize.py` uses for stock fields,
    and falling back to an adjacent quarter when Q4 is absent would be
    imputation (S4.2), so an absent Q4 yields an absent reading instead.

    Raises ValueError if a metric_id appears at both grains -- one would
    silently overwrite the other, publishing a criterion graded off the wrong
    measurement.
    """
    trend_rows = conn.execute(
        f"SELECT ticker, as_of_year, metric_id, value, reason_code, NULL "
        f"FROM {_TREND_TABLE}"
    ).fetchall()
    quarterly_rows = conn.execute(
        f"SELECT ticker, year, metric_id, value, reason_code, quality_flag "
        f"FROM {_QUARTERLY_TABLE} WHERE quarter = {FISCAL_YEAR_END_QUARTER}"
    ).fetchall()

    trend_ids = {row[2] for row in trend_rows}
    quarterly_ids = {row[2] for row in quarterly_rows}
    collisions = sorted(trend_ids & quarterly_ids)
    if collisions:
        raise ValueError(
            f"metric_id present at both the trend and quarterly grains: "
            f"{collisions}. One reading would silently overwrite the other."
        )

    readings: dict[TickerYear, dict[str, MetricReading]] = {}
    for ticker, year, metric_id, value, reason_code, flag in (
        *trend_rows,
        *quarterly_rows,
    ):
        readings.setdefault((ticker, int(year)), {})[metric_id] = MetricReading(
            metric_id=metric_id,
            value=value,
            reason_code=reason_code,
            quality_flag=flag,
        )
    return readings


def _load_staleness(conn) -> dict[str, int]:
    """Quarters between each ticker's latest quarter and the warehouse's latest.

    The platform spec's section 6.4 definition verbatim, so staleness is a
    property of the ticker's reporting, not of the year being scored: a company
    that stopped reporting in 2023 is stale on every one of its scorecards.
    """
    rows = conn.execute(
        f"SELECT ticker, MAX(year * {QUARTERS_PER_YEAR} + quarter) "
        f"FROM {_QUARTERLY_TABLE} GROUP BY ticker"
    ).fetchall()
    if not rows:
        return {}
    latest = max(ordinal for _, ordinal in rows)
    return {ticker: int(latest - ordinal) for ticker, ordinal in rows}


def _score_rows(
    output: ScorerOutput,
    scorer: Scorer,
    staleness: int | None,
    computed_at: datetime,
    pipeline_version: str,
) -> tuple[dict, list[dict], list[dict]]:
    """Flatten one scorecard into its three table rows."""
    key = {
        "ticker": output.ticker,
        "as_of_year": output.as_of_year,
        "scorer_name": scorer.name,
        "scorer_version": scorer.version,
        "config_hash": scorer.config_hash,
    }
    provenance = {"computed_at": computed_at, "pipeline_version": pipeline_version}

    score_row = {
        **key,
        "composite": output.composite,
        "reason_code": output.reason_code,
        "coverage_ratio": output.coverage_ratio,
        "checklist_passed": output.checklist_passed,
        "checklist_applicable": output.checklist_applicable,
        "badges": BADGE_SEPARATOR.join(badge.value for badge in output.badges),
        "staleness_quarters": staleness,
        **provenance,
    }
    component_rows = [
        {
            **key,
            "component_id": component.component_id,
            "score": component.score,
            "weight": component.weight,
            "coverage_ratio": component.coverage_ratio,
            "applicable_criteria": component.applicable_criteria,
            "total_criteria": component.total_criteria,
            "era_unavailable_criteria": component.era_unavailable_criteria,
            "reason_code": component.reason_code,
            **provenance,
        }
        for component in output.components
    ]
    criterion_rows = [
        {
            **key,
            "criterion_id": criterion.criterion_id,
            "component_id": criterion.component_id,
            "metric_id": criterion.metric_id,
            "value": criterion.value,
            "points": criterion.points,
            "weight": criterion.weight,
            "checklist_verdict": criterion.checklist_verdict.value,
            "reason_code": criterion.reason_code,
            "annotation": criterion.annotation,
            "quality_flag": criterion.quality_flag,
            **provenance,
        }
        for criterion in output.criteria
    ]
    return score_row, component_rows, criterion_rows


def _replace_table(conn, table: str, ddl_factory, columns: tuple[str, ...], frame) -> None:
    """Drop, recreate and repopulate one table by explicit column list."""
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(ddl_factory())
    if frame.empty:
        return
    staging = f"{_STAGING_PREFIX}{table}"
    conn.register(staging, frame)
    try:
        column_list = ", ".join(columns)
        conn.execute(
            f"INSERT INTO {table} ({column_list}) "
            f"SELECT {column_list} FROM {staging}"
        )
    finally:
        conn.unregister(staging)


def _summarise(
    scores: pd.DataFrame, components: pd.DataFrame, criteria: pd.DataFrame
) -> dict[str, object]:
    """Counts the CLI prints and the verification step checks."""
    if scores.empty:
        return {
            "scores_rows": 0,
            "score_components_rows": 0,
            "score_criteria_rows": 0,
            "null_composites": 0,
            "badge_counts": {},
            "component_exclusions": {},
        }
    badge_counts: dict[str, int] = {}
    for badges in scores["badges"]:
        for badge in badges.split(BADGE_SEPARATOR):
            if badge:
                badge_counts[badge] = badge_counts.get(badge, 0) + 1
    excluded = components[components["score"].isna()]
    return {
        "scores_rows": int(len(scores)),
        "score_components_rows": int(len(components)),
        "score_criteria_rows": int(len(criteria)),
        "null_composites": int(scores["composite"].isna().sum()),
        "badge_counts": dict(sorted(badge_counts.items())),
        "component_exclusions": dict(
            sorted(excluded.groupby("component_id").size().astype(int).to_dict().items())
        ),
    }


def _universe(readings: Iterable[TickerYear]) -> list[TickerYear]:
    """Every ticker-year the metrics grain knows about, in a fixed order.

    Sorted rather than dict-ordered so the output is reproducible independently
    of insertion order (S3.3). The union of both grains is deliberate: scoring
    only the trend grain would silently omit the ticker-years that have no
    10-year window yet, when the honest result is a published row carrying the
    reason its composite is null.
    """
    return sorted(readings)


def build_scores(
    *,
    warehouse_path: str | Path,
    config_path: str | Path | None = None,
    scorer: Scorer | None = None,
    pipeline_version: str = SCORES_PIPELINE_VERSION,
) -> dict[str, object]:
    """Read the metrics grain, score every ticker-year, (re)build the score tables.

    Pass `scorer` to drive an alternative `Scorer` implementation; otherwise a
    `BuffettHeuristicScorer` is built from `config_path` (the packaged scorecard
    when None). Passing both is rejected rather than silently preferring one.

    Every ticker-year present in the metrics grain gets a row. One that cannot
    be scored carries a `reason_code` and a null composite -- never a composite
    of 0, which would rank an unmeasured company as the worst one, and never an
    omitted row, which would hide it entirely.
    """
    if scorer is not None and config_path is not None:
        raise ValueError(
            "Pass either `scorer` or `config_path`, not both: the scorer already "
            "carries the config it was built from."
        )
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")
    if scorer is None:
        scorer = BuffettHeuristicScorer(load_scorecard_config(config_path))

    computed_at = datetime.now(UTC).replace(tzinfo=None)

    with open_warehouse(path, read_only=False) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        missing = sorted({_TREND_TABLE, _QUARTERLY_TABLE} - tables)
        if missing:
            raise FileNotFoundError(
                f"{', '.join(missing)} not found; run metrics-build and "
                "metrics-quarterly-build first."
            )

        readings = _load_readings(conn)
        staleness = _load_staleness(conn)

        score_rows: list[dict] = []
        component_rows: list[dict] = []
        criterion_rows: list[dict] = []
        for ticker, as_of_year in _universe(readings):
            output = scorer.score(
                ScorerInput(
                    ticker=ticker,
                    as_of_year=as_of_year,
                    readings=readings[(ticker, as_of_year)],
                    # Stage 1 does not publish source_family yet; passed
                    # explicitly so the gap is visible at the call site rather
                    # than hidden behind a default.
                    source_family=None,
                    staleness_quarters=staleness.get(ticker),
                )
            )
            score_row, components, criteria = _score_rows(
                output, scorer, staleness.get(ticker), computed_at, pipeline_version
            )
            score_rows.append(score_row)
            component_rows.extend(components)
            criterion_rows.extend(criteria)

        frames = {
            "scores": pd.DataFrame(score_rows, columns=list(SCORES_COLUMNS)),
            "score_components": pd.DataFrame(
                component_rows, columns=list(SCORE_COMPONENTS_COLUMNS)
            ),
            "score_criteria": pd.DataFrame(
                criterion_rows, columns=list(SCORE_CRITERIA_COLUMNS)
            ),
        }
        for table, ddl_factory, columns in _TARGETS:
            _replace_table(conn, table, ddl_factory, columns, frames[table])

    summary = _summarise(
        frames["scores"], frames["score_components"], frames["score_criteria"]
    )
    summary.update(
        {
            "scorer_name": scorer.name,
            "scorer_version": scorer.version,
            "config_hash": scorer.config_hash,
        }
    )
    return summary
