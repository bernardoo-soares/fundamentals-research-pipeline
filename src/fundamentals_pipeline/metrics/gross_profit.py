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
The arithmetic differs by era, so each era uses its own:

  legacy  saleq - cogsq - dpq     `gross_profit`
  simfin  saleq - cogsq           `as_reported_gross_profit`

The CONCEPT is single -- published gross profit -- and only the arithmetic
differs, because the two providers store different quantities. That is what the
era-semantics layer exists to express, and it is not one field meaning two things
(S4.3): a TTM window spanning the boundary is nulled `mixed_era_window` by
per-field purity, so no single value is ever assembled from both.

KNOWN BIAS IN THE LEGACY ARITHMETIC (measured 2026-07-28, flagged on every row)
------------------------------------------------------------------------------
An earlier version of this module claimed SimFin's `Cost of Revenue` "already
includes D&A" and that the legacy bias was 0.14-0.44pp of revenue. BOTH claims
were wrong, and are corrected here.

Solving per company for `a = (CostOfRevenue_simfin - cogsq_legacy) / dpq_legacy`
-- the share of total D&A the FILER placed inside cost of revenue -- gives a
TRIMODAL distribution on FY2023 (n=227 with dpq >= 2% of revenue):

  a >= 0.95   34.4%   filer folds all D&A into COGS
  a <= 0.05   26.4%   filer presents D&A entirely outside COGS
  between     32.6%   filer splits it

The poles are exact identities, not estimates. AAPL FY2023 a = 1.000 (SimFin
214,137 = cogsq 202,618 + dpq 11,519, and 214,137 IS Apple's published total cost
of sales). DIS FY2023 a = 0.000 (SimFin 59,201 = cogsq 59,201 to the dollar, with
dpq 5,369 outside it -- Disney labels that line "exclusive of depreciation and
amortization").

So SimFin PRESERVES each filer's presentation while Compustat NORMALISES D&A out
of every one. `a` is a property of the filing and is not recoverable from
Compustat alone, so the legacy arithmetic must assume a = 1. Against the
published figure that is exact where it holds (a >= 0.95: median error +0.0000)
but understates by a median 13.46pp where it does not (a <= 0.05), flipping the
book's >40% verdict for 11.8% of companies overall and 33.3% of that group. The
bias is one-directional -- it can only understate margin, never manufacture a
false ">40%" pass -- but it is far larger than previously believed, so every
legacy gross-profit row carries the `da_allocation_assumed` quality flag.

The SimFin arithmetic needs no such caveat: `Revenue - Cost of Revenue` is the
as-reported gross profit for every filer regardless of `a`.

Full evidence: spec 2026-07-26_SP3_METRIC_CATALOG_COMPLETION_DESIGN section 2.2.1
and 2026-07-28_GROSS_PROFIT_ERA_AND_RELIABILITY_FLAGS_DESIGN.
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


def as_reported_gross_profit(revenue: Term, cost: Term) -> Term:
    """Gross profit = revenue - cost, for a provider that stores the filed line.

    The SimFin-era form. No depreciation term: SimFin's `Cost of Revenue` is the
    filer's own line, already carrying whatever D&A that filer put there, so
    subtracting `dpq` would double-count it for the ~34% who included all of it
    and invent a cost for the ~26% who included none.
    """
    return revenue - cost


def annual_field(field: str) -> str:
    """Map a canonical raw field to its `fundamentals_annual` column name."""
    return f"{field}{ANNUAL_SUFFIX}"
