# Canonical Fundamentals Schema

## Purpose
Document the canonical fundamentals the project wants to capture as raw normalized fields and the derived fundamentals metrics the project wants to compute later.

This document is intentionally provider-agnostic.
It defines what the pipeline should capture and compute, not how the data is fetched.

## 1) Canonical Yearly CSV Shape
The canonical output format is:
1. one CSV per year
2. one row per `ticker, year, quarter`
3. sorted in ascending alphabetical order by `ticker`
4. within each ticker, sorted by `quarter` ascending (`1, 2, 3, 4`)

Example row order inside a yearly CSV:
```text
A 2023 1 ...
A 2023 2 ...
A 2023 3 ...
A 2023 4 ...
AAPL 2023 1 ...
AAPL 2023 2 ...
```

Required leading columns:
1. `ticker`
2. `year`
3. `quarter`

This row shape applies to both:
1. the normalized raw fundamentals CSVs
2. the computed ratios/features CSVs

## 2) Raw Fundamentals To Capture
These are the normalized quarterly raw fields the pipeline should preserve before any derived ratios are computed.

When stored in a Stage 1 yearly CSV, the row shape is:
`ticker, year, quarter, <raw fundamentals...>`

### 2.1 Core Raw Fields
1. `saleq`: quarterly revenue / sales
2. `niq`: quarterly net income
3. `oiadpq`: quarterly operating income
4. `xintq`: quarterly interest expense
5. `txtq`: quarterly income tax expense
6. `epspxq`: quarterly earnings per share
7. `actq`: current assets
8. `lctq`: current liabilities
9. `ppentq`: property, plant, and equipment, net
10. `gdwlq`: goodwill
11. `ivltq`: long-term investments
12. `atq`: total assets
13. `ceqq`: common/shareholder equity
14. `dlcq`: short-term debt / current debt
15. `dlttq`: long-term debt
16. `req`: retained earnings
17. `tstkq`: treasury stock
18. `oancfq`: operating cash flow
19. `prstkcq`: share repurchases / stock buybacks
20. `capxq`: capital expenditures
21. `cheq`: cash and equivalents
22. `dvpq`: dividends paid
23. `cshfdq`: diluted shares outstanding

### 2.2 Support Fields
These fields are retained because they support fallback logic, comparisons, or later derived calculations.

1. `oancfy`: annual operating cash flow support field
2. `capxy`: annual capital expenditures support field
3. `prstkcy`: annual share repurchases support field
4. `cshopq`: common share repurchase support field
5. `cshoq`: basic shares outstanding support field

### 2.2b Extended Raw Fields
These fields were added for the Buffett-style metrics engine
(`specs/2026-07-21_BUFFETT_RESEARCH_PLATFORM_DESIGN.md`). They are appended
after the support fields in the published column order.

1. `cogsq`: cost of goods sold / cost of revenue
2. `xsgaq`: selling, general and administrative expense
3. `xrdq`: research and development expense
4. `dpq`: depreciation and amortization
5. `ltq`: total liabilities
6. `invtq`: inventories
7. `rectq`: receivables, net

All seven are monetary fields published in `USD millions`. Null when the
source family does not report them (for example COGS for banks/insurance).

### 2.3 Published Raw Fundamentals Scale
Published raw fundamentals CSVs use one shared scale across provider windows so
the yearly files stay directly comparable.

Current published convention:
1. monetary fields are stored in `USD millions`
2. share-count fields are stored in `millions of shares`
3. per-share fields remain unchanged

Examples:
1. `saleq`, `niq`, `atq`, `oancfq`, `oancfy`, `capxq`, `capxy`, `cogsq`, `ltq`:
   - published in `USD millions`
2. `cshfdq`, `cshopq`, `cshoq`:
   - published in `millions of shares`
3. `epspxq`:
   - unchanged

When a provider arrives in base units, the pipeline must apply a unit
normalization pass after field mapping and before writing the yearly CSVs.

### 2.4 Published Local Historical Stage 1 Artifacts
For the implemented local historical path sourced from
`data/raw/Processed-Fundamentals`, the published Stage 1 artifacts are:
1. `data/processed/raw_fundamentals_<year>.csv`
2. one file per year in the requested range
3. leading columns fixed as `ticker, year, quarter`
4. raw and support fields only; no computed ratios

Associated QA artifacts for this path live under `data/reports/`:
1. `legacy_raw_coverage_<start>_<end>.csv`
2. `legacy_raw_missing_universe_<start>_<end>.csv`
3. `legacy_raw_conflicts_<start>_<end>.csv`

### 2.5 SimFin Raw Fundamentals Mapping Reference
The SimFin `2023-2025` implementation should use:

1. `specs/SIMFIN_STAGE1_MAPPING.md`

That reference defines, field by field, whether the SimFin mapping is:

1. `direct`
2. `derived`
3. `proxy`
4. `unsupported`

Unsupported fields should remain null and be surfaced in explicit QA artifacts
rather than being filled with weak or semantically incorrect substitutes.

For the current implementation, SimFin-mapped values are normalized into the
same published scale before the yearly raw fundamentals files are written.

## 3) Derived Fundamentals Metrics To Compute
These fields should be computed from the normalized raw fundamentals layer.
They belong to Stage 2 of the architecture.

When stored in a Stage 2 yearly CSV, the row shape is:
`ticker, year, quarter, <computed metrics...>`

### 3.1 Core Ratios And Features
1. `Operating_Margin`
2. `Net_Profit_Margin`
3. `Current_Ratio`
4. `ROA`
5. `ROE`
6. `Debt_to_Equity`
7. `Treasury_Adjusted_Debt_to_Equity`
8. `Book_Value`
9. `Retained_Earnings_Growth`
10. `Share_Repurchases`
11. `Revenue_Growth`
12. `EPS_Growth`
13. `Return_on_Shareholder_Equity`
14. `Free_Cash_Flow`
15. `Net_Debt`
16. `Dividends_Paid`
17. `Shares_Outstanding_Diluted`
18. `Short_Term_Debt`
19. `Healthy_Long_Term_Debt`

### 3.2 Deferred Market-Dependent Metrics
These may be useful later, but they require an explicit market-price input and are not required for the current Stage 1 and Stage 2 focus.

1. `P/E_Ratio`
2. `Market_Cap`
3. `P/B_Ratio`
4. `Dividend_Yield`
5. `Earnings_Yield`

## 4) Stage Boundaries
1. Stage 1 captures and normalizes the raw fundamentals fields.
2. Stage 2 computes derived metrics from Stage 1 outputs only.
3. Stage 3 may use Stage 2 outputs for scoring and ranking, but it does not introduce new accounting fundamentals.

## 5) Canonical Intent
1. The raw layer should remain as source-faithful as possible after normalization.
2. The computed layer should be reproducible from the raw layer.
3. Source choice must not change the meaning of the canonical fields.
4. The yearly CSV contract should remain stable across all years.

## Source-column notes (2026-07-24)

1. Canonical `req` is sourced from Compustat **`reunaq`** (Unadjusted Retained Earnings), not `req`. Compustat `req` is adjusted (`req = reunaq + acomincq`); SimFin publishes the as-reported line and has no AOCI column. See `contracts/field_era_semantics.py`.
2. Canonical `dvy` is total cash dividends (YTD); `dvpq` is preferred dividends only and is null in the SimFin era.
3. Canonical `prstkcq` is null across the legacy era: Compustat publishes no quarterly purchase-of-stock column.
