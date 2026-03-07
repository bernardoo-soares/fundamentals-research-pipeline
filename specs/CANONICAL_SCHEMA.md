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
2. `prstkcy`: annual share repurchases support field
3. `cshopq`: common share repurchase support field
4. `cshoq`: basic shares outstanding support field

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
