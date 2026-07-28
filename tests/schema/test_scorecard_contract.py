"""The score tables' column tuples must agree with their own DDL.

The builder inserts by explicit column list built from these tuples. If a
column is added to one and not the other, DuckDB would either reject the insert
or -- worse, for a same-typed neighbour -- accept it into the wrong position and
publish a silently transposed score. This test is the guard against that.
"""

from __future__ import annotations

import re

import pytest

from fundamentals_pipeline.contracts.scorecard_schema import (
    BADGE_SEPARATOR,
    FISCAL_YEAR_END_QUARTER,
    QUARTERS_PER_YEAR,
    SCORE_COMPONENTS_COLUMNS,
    SCORE_CRITERIA_COLUMNS,
    SCORE_KEY_COLUMNS,
    SCORES_COLUMNS,
    MetricReading,
    ScorerOutput,
    create_score_components_ddl,
    create_score_criteria_ddl,
    create_scores_ddl,
)

_COLUMN_LINE = re.compile(r"^\s{2}(\w+)\s+(?:VARCHAR|INTEGER|DOUBLE|TIMESTAMP|BOOLEAN)")


def _ddl_columns(ddl: str) -> tuple[str, ...]:
    return tuple(
        match.group(1)
        for match in (_COLUMN_LINE.match(line) for line in ddl.splitlines())
        if match is not None
    )


@pytest.mark.parametrize(
    ("columns", "ddl"),
    [
        (SCORES_COLUMNS, create_scores_ddl()),
        (SCORE_COMPONENTS_COLUMNS, create_score_components_ddl()),
        (SCORE_CRITERIA_COLUMNS, create_score_criteria_ddl()),
    ],
)
def test_column_tuple_matches_ddl(columns: tuple[str, ...], ddl: str) -> None:
    assert _ddl_columns(ddl) == columns


@pytest.mark.parametrize(
    "columns",
    [SCORES_COLUMNS, SCORE_COMPONENTS_COLUMNS, SCORE_CRITERIA_COLUMNS],
)
def test_every_table_carries_the_reproducibility_key(columns: tuple[str, ...]) -> None:
    """Identical inputs under the same key must produce identical rows (spec 7.1)."""
    assert columns[: len(SCORE_KEY_COLUMNS)] == SCORE_KEY_COLUMNS


@pytest.mark.parametrize(
    "columns",
    [SCORES_COLUMNS, SCORE_COMPONENTS_COLUMNS, SCORE_CRITERIA_COLUMNS],
)
def test_every_table_carries_provenance(columns: tuple[str, ...]) -> None:
    """S3.5: a derived row without its pipeline version cannot be reproduced."""
    assert "computed_at" in columns
    assert "pipeline_version" in columns


def test_builder_constants_are_declared_once() -> None:
    assert FISCAL_YEAR_END_QUARTER == 4
    assert QUARTERS_PER_YEAR == 4
    assert BADGE_SEPARATOR == ","


def test_metric_reading_rejects_value_and_reason_together() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        MetricReading(metric_id="roe", value=0.2, reason_code="missing_input")


def test_metric_reading_rejects_neither() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        MetricReading(metric_id="roe", value=None, reason_code=None)


def test_scorer_output_rejects_a_zero_composite_with_a_reason() -> None:
    """A null composite must never be published as 0 (spec 7.4.3)."""
    with pytest.raises(ValueError, match="exactly one"):
        ScorerOutput(
            ticker="AAPL",
            as_of_year=2022,
            composite=0.0,
            reason_code="no_applicable_component",
            coverage_ratio=0.0,
            checklist_passed=0,
            checklist_applicable=0,
            components=(),
            criteria=(),
        )
