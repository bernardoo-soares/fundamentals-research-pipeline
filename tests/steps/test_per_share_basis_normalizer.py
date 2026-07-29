"""Tests for split-basis normalisation of per-share fields."""

from __future__ import annotations

import pandas as pd

from fundamentals_pipeline.steps.per_share_basis_normalizer import (
    SPLIT_BASIS_REPORT_COLUMNS,
    normalize_per_share_basis,
)

FACTOR = "ajexq"


def _frame(rows: list[tuple[float | None, float | None]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "epspxq": [r[0] for r in rows],
            FACTOR: [r[1] for r in rows],
        }
    )


def test_factor_of_one_leaves_the_value_unchanged() -> None:
    out, _ = normalize_per_share_basis(_frame([(1.25, 1.0)]), factor_column=FACTOR)
    assert out["epspxq"].tolist() == [1.25]


def test_value_is_divided_by_the_factor() -> None:
    out, _ = normalize_per_share_basis(_frame([(5.04, 4.0)]), factor_column=FACTOR)
    assert out["epspxq"].tolist() == [1.26]


def test_negative_eps_keeps_its_sign() -> None:
    """A loss stays a loss: the factor rescales, it does not reinterpret."""
    out, _ = normalize_per_share_basis(_frame([(-7.56, 20.0)]), factor_column=FACTOR)
    assert out["epspxq"].tolist() == [-0.378]


def test_null_factor_nulls_the_value_rather_than_passing_it_through() -> None:
    """An unknown basis is not a basis of 1 (AGENTS.md S4.2)."""
    out, report = normalize_per_share_basis(
        _frame([(5.04, None)]), factor_column=FACTOR
    )
    assert out["epspxq"].isna().all()
    assert int(report.loc[0, "rows_nulled_no_factor"]) == 1
    assert int(report.loc[0, "rows_rebased"]) == 0


def test_zero_factor_is_treated_as_no_factor() -> None:
    out, report = normalize_per_share_basis(_frame([(5.04, 0.0)]), factor_column=FACTOR)
    assert out["epspxq"].isna().all()
    assert int(report.loc[0, "rows_nulled_no_factor"]) == 1


def test_null_value_stays_null_and_is_not_counted_as_a_nulling() -> None:
    out, report = normalize_per_share_basis(_frame([(None, 4.0)]), factor_column=FACTOR)
    assert out["epspxq"].isna().all()
    assert int(report.loc[0, "rows_nulled_no_factor"]) == 0
    assert int(report.loc[0, "rows_rebased"]) == 0


def test_missing_factor_column_nulls_everything_and_says_so() -> None:
    """Silently returning the as-reported series is the defect being removed."""
    frame = pd.DataFrame({"epspxq": [5.04, 2.58]})
    out, report = normalize_per_share_basis(frame, factor_column=FACTOR)
    assert out["epspxq"].isna().all()
    assert int(report.loc[0, "rows_nulled_no_factor"]) == 2


def test_input_frame_is_not_mutated() -> None:
    frame = _frame([(5.04, 4.0)])
    normalize_per_share_basis(frame, factor_column=FACTOR)
    assert frame["epspxq"].tolist() == [5.04]


def test_report_has_the_declared_columns() -> None:
    _, report = normalize_per_share_basis(_frame([(1.0, 1.0)]), factor_column=FACTOR)
    assert tuple(report.columns) == SPLIT_BASIS_REPORT_COLUMNS


def test_absent_per_share_field_is_reported_not_crashed() -> None:
    frame = pd.DataFrame({FACTOR: [4.0]})
    out, report = normalize_per_share_basis(frame, factor_column=FACTOR)
    assert "epspxq" not in out.columns
    assert int(report.loc[0, "rows_total"]) == 1
    assert int(report.loc[0, "rows_rebased"]) == 0


def test_golden_aapl_fy2020_reproduces_the_published_restated_eps() -> None:
    """GOLDEN (real corpus, hand-verified).

    Apple's four FY2020 quarters as Compustat publishes them, with the 4:1
    split of 2020-08-31 falling in Q4. The raw sum is 10.97 -- not an EPS at
    all, since Q1-Q3 are on the pre-split basis and Q4 is on the post-split
    one. Apple's 10-K for FY2020 reports basic EPS of $3.31.

    Values read from data/raw/Processed-Fundamentals/AAPL-001690.csv.
    """
    frame = pd.DataFrame(
        {
            "epspxq": [5.04, 2.58, 2.61, 0.74],
            FACTOR: [4.0, 4.0, 4.0, 1.0],
        }
    )
    assert frame["epspxq"].sum() == 10.97

    out, _ = normalize_per_share_basis(frame, factor_column=FACTOR)
    assert round(out["epspxq"].sum(), 4) == 3.2975


def test_golden_googl_fy2022_reproduces_the_published_restated_eps() -> None:
    """GOLDEN (real corpus, hand-verified).

    Alphabet's FY2022 quarters across the 20:1 split of 2022-07-15. Raw sum
    51.43; Alphabet's FY2022 10-K reports basic EPS of $4.59.

    Values read from data/raw/Processed-Fundamentals/GOOGL-160329.csv.
    """
    frame = pd.DataFrame(
        {
            "epspxq": [24.90, 24.40, 1.07, 1.06],
            FACTOR: [20.0, 20.0, 1.0, 1.0],
        }
    )
    assert round(frame["epspxq"].sum(), 2) == 51.43

    out, _ = normalize_per_share_basis(frame, factor_column=FACTOR)
    assert round(out["epspxq"].sum(), 4) == 4.5950


def test_golden_amzn_fy2022_keeps_a_loss_a_loss() -> None:
    """GOLDEN (real corpus, hand-verified).

    Amazon's FY2022 across the 20:1 split of 2022-06-03. Raw sum -7.45;
    Amazon's FY2022 10-K reports basic EPS of $(0.27).

    Values read from data/raw/Processed-Fundamentals/AMZN-064768.csv.
    """
    frame = pd.DataFrame(
        {
            "epspxq": [-7.56, -0.20, 0.28, 0.03],
            FACTOR: [20.0, 1.0, 1.0, 1.0],
        }
    )
    assert round(frame["epspxq"].sum(), 2) == -7.45

    out, _ = normalize_per_share_basis(frame, factor_column=FACTOR)
    assert round(out["epspxq"].sum(), 4) == -0.2680
