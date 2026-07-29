"""Put a per-share series onto one split basis.

Pure: frame in, frame out. No I/O, no clock, no global state (AGENTS.md S2.4).

WHY THIS EXISTS
---------------
Compustat publishes basic EPS as-reported and never restates it after a stock
split or stock dividend. It publishes `ajexq`, the cumulative adjustment factor
by ex-date, so that a consumer can put the series onto one basis. Nothing here
read that factor, and two things were silently wrong:

1. `epspxq_annual` sums four quarters. A split falling mid-year puts those four
   quarters on two different bases, so the sum is not an EPS at all. AAPL FY2020
   read 10.97 against a published 3.31.
2. The year after a split showed a fall in EPS that never happened. AAPL FY2020
   -> FY2021 read 10.97 -> 5.67 while the true basic EPS *rose*, 3.31 -> 5.67.

The second is the one that mattered. The error is one-directional -- a split can
only ever manufacture a *down* year, never an up one -- and companies split
because the price compounded. So the defect systematically penalised serial
compounders, which is the exact population a Buffett screen exists to find.
Measured 2026-07-29: 11.1% of tickers carried a wrong `eps_up_year_fraction_10y`
(48 of 431), median understatement 0.111, worst 0.444 (AAPL, 0.333 -> 0.778).

Verified against published restated EPS: AAPL FY2020 3.2975 vs 3.31, GOOGL
FY2022 4.5950 vs 4.59, AMZN FY2021 3.2965 vs 3.30, AMZN FY2022 -0.2680 vs
(0.27), SHW FY2021 7.1000 vs 7.06.

NULL FACTOR IS NOT FACTOR 1
---------------------------
A missing `ajexq` means the basis is unknown, which is not the same as knowing
it did not change. Those rows are nulled with a reason rather than passed
through as-reported, because passing them through is what produced the defect
(AGENTS.md S4.2). A zero factor is treated the same way: it is not a basis.
"""

from __future__ import annotations

import pandas as pd

from ..contracts.stage1_fundamentals_schema import PER_SHARE_FIELDS

SPLIT_BASIS_RULE = "per_share_split_basis"

# Report emitted alongside the normalized frame, so a rebuild can state how many
# values were rebased and how many were nulled for want of a factor.
SPLIT_BASIS_REPORT_COLUMNS: tuple[str, ...] = (
    "field_name",
    "rows_total",
    "rows_with_factor",
    "rows_rebased",
    "rows_nulled_no_factor",
)


def normalize_per_share_basis(
    frame: pd.DataFrame,
    *,
    factor_column: str,
    per_share_fields: tuple[str, ...] = PER_SHARE_FIELDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide each per-share field by the cumulative adjustment factor.

    Returns `(normalized_frame, report)`. The frame is a copy; the input is not
    mutated.

    Contract:
    - A row whose factor is present, finite and non-zero has each per-share
      field divided by it. A factor of exactly 1 leaves the value unchanged,
      which is the common case.
    - A row whose per-share value is present but whose factor is null, zero or
      non-finite has that per-share value **nulled**. Its basis is unknown and
      an unknown basis cannot be compared to anything.
    - A row whose per-share value is already null stays null and is not counted
      as a nulling.
    - A field absent from the frame is skipped and reported with zero rows.
    - `factor_column` absent from the frame nulls every per-share value, and the
      report says so. This is deliberate: silently returning the as-reported
      series is the defect this module exists to remove.
    """
    result = frame.copy()
    records: list[dict[str, object]] = []
    rows_total = len(result)

    if factor_column in result.columns:
        factor = pd.to_numeric(result[factor_column], errors="coerce")
        usable = factor.notna() & (factor != 0)
    else:
        factor = pd.Series(float("nan"), index=result.index, dtype="float64")
        usable = pd.Series(False, index=result.index)

    for field in per_share_fields:
        if field not in result.columns:
            records.append(
                {
                    "field_name": field,
                    "rows_total": rows_total,
                    "rows_with_factor": 0,
                    "rows_rebased": 0,
                    "rows_nulled_no_factor": 0,
                }
            )
            continue

        values = pd.to_numeric(result[field], errors="coerce")
        present = values.notna()
        rebased = present & usable
        nulled = present & ~usable

        result[field] = values.where(~rebased, values / factor).where(~nulled)

        records.append(
            {
                "field_name": field,
                "rows_total": rows_total,
                "rows_with_factor": int(usable.sum()),
                "rows_rebased": int(rebased.sum()),
                "rows_nulled_no_factor": int(nulled.sum()),
            }
        )

    report = pd.DataFrame.from_records(
        records, columns=list(SPLIT_BASIS_REPORT_COLUMNS)
    )
    return result, report
