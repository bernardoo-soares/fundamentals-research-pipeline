"""The gross-profit rule, stated once for every grain that needs it.

Pure: no I/O. Both Stage 2 grains derive gross profit -- `quarterly.py` from a
TTM sum and `windows.py` from annual columns -- so the arithmetic and the
evidence for it live here rather than in two places (AGENTS.md S2.6).

WHY DEPRECIATION IS SUBTRACTED
------------------------------
Compustat states `cogsq` and `xsgaq` BEFORE depreciation. Its income-statement
identity is `saleq - (cogsq + xsgaq) = oibdpq`, operating income *before* D&A,
with `oibdpq - dpq = oiadpq` after. Measured on 9,035 legacy quarters across 176
tickers (2006-2022), agreement within 0.5% of revenue:

  xoprq == cogsq + xsgaq      99.69%
  saleq - xoprq == oibdpq     99.59%

So Compustat's `cogsq` is not the cost-of-goods line a filing reports, and
`saleq - cogsq` is gross profit before depreciation. It overstates the published
figure by a median 4.09pp of revenue (p90 12.58pp) -- against a book threshold of
> 40% gross margin.

Verified against published filings; `cogsq + dpq` recovers reported COGS:

  AAPL FY2022   cogsq 212,442  +dpq -> 223,546  = published exactly
  KO   FY2021   cogsq  13,905  +dpq ->  15,357  = published exactly
  PG   FY2021   within 216 of published (0.28% of revenue)
  MMM  FY2021   within 154 (0.44%)
  JNJ  FY2021   within 135 (0.14%)

KO FY2021 gross profit is therefore 38,655 - 13,905 - 1,452 = 23,298, exactly
Coca-Cola's published figure, where the uncorrected form gives 24,750.

ERA SPECIFICITY
---------------
This arithmetic is LEGACY-ONLY. SimFin's `Cost of Revenue` already includes D&A,
so subtracting `dpq` again would double-count it. Every metric built on gross
profit therefore restricts itself to the legacy era: the issue is not merely that
the two eras disagree but that the correct arithmetic differs between them, and
one formula spanning both would mix two definitions in one field (S4.3).

KNOWN BIAS (conservative, disclosed)
------------------------------------
`dpq` is total D&A, including the portion belonging to SG&A rather than cost of
goods, so subtracting all of it slightly over-subtracts: gross profit is
understated by a measured 0.14-0.44pp of revenue (exact for AAPL and KO). The
bias understates margin, so it cannot manufacture a false ">40%" pass, and it is
10-30x smaller than the 4.09pp error it replaces.
"""

from __future__ import annotations

from typing import TypeVar

Term = TypeVar("Term")

# The three canonical raw fields composing gross profit, in subtraction order.
# Each grain maps these to its own column names (`saleq` at the quarterly grain,
# `saleq_annual` at the annual grain); the roles and the arithmetic are declared
# only here.
REVENUE_FIELD = "saleq"
COST_FIELD = "cogsq"
DEPRECIATION_FIELD = "dpq"

ANNUAL_SUFFIX = "_annual"


def gross_profit(revenue: Term, cost: Term, depreciation: Term) -> Term:
    """Gross profit = revenue - cost - depreciation. See the module docstring.

    Generic over anything supporting subtraction, so the same rule serves scalar
    TTM totals and pandas Series over annual columns. Carries no null policy of
    its own: each grain applies its own (`missing_input` when a term is absent,
    `negative_base`/`zero_denominator` when the result is unusable as a
    denominator).
    """
    return revenue - cost - depreciation


def annual_field(field: str) -> str:
    """Map a canonical raw field to its `fundamentals_annual` column name."""
    return f"{field}{ANNUAL_SUFFIX}"
