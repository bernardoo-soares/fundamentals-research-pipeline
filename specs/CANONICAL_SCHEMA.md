# Canonical Schema (Sprint 0 Contract)

## Purpose
Define the strict raw-field contract for SEC ingestion and normalization before any ratio computation.

This schema is intentionally narrow:
1. Fetch only approved raw fundamentals fields.
2. Defer all derived metrics/ratios to later computation stages.
3. Preserve audit columns for reproducibility.

## Grain
One row per:
1. `ticker`
2. `fyearq`
3. `fqtr`

## Required Key Columns
1. `ticker` (`string`): symbol from `data/universe_current.csv`.
2. `fyearq` (`int`): fiscal year.
3. `fqtr` (`int` in `1..4`): fiscal quarter.

## Required Traceability Columns
1. `cik` (`string`): SEC CIK, zero-padded to 10 digits.
2. `period_end` (`date`): quarter/annual period end date from SEC fact.
3. `filed_date` (`date`): SEC filing date for the selected fact.
4. `form_type` (`string`): expected `10-Q` or `10-K`.
5. `accn` (`string`): SEC accession number.
6. `source_system` (`string`): for this stage use `sec-companyfacts`.
7. `source_tag_map_version` (`string`): mapping contract version.
8. `source_tag_<field>` (`string`): selected SEC tag per canonical raw field.
9. `quality_tier_<field>` (`string`): `primary`, `fallback`, or `proxy`.

## Fetch-Only Raw Fields
These are the only canonical raw fundamentals fields fetched from SEC for this phase:
1. `saleq` (`float`)
2. `niq` (`float`)
3. `oiadpq` (`float`)
4. `xintq` (`float`)
5. `txtq` (`float`)
6. `epspxq` (`float`)
7. `actq` (`float`)
8. `lctq` (`float`)
9. `ppentq` (`float`)
10. `gdwlq` (`float`)
11. `ivltq` (`float`)
12. `atq` (`float`)
13. `ceqq` (`float`)
14. `dlcq` (`float`)
15. `dlttq` (`float`)
16. `req` (`float`)
17. `tstkq` (`float`)
18. `oancfq` (`float`)
19. `prstkcq` (`float`)

## Helper Fallback Fields
Used only to improve fill rate of canonical raw fields:
1. `oancfy` (`float`) for operating cash flow fallback logic.
2. `prstkcy` (`float`) for annual repurchase fallback logic.
3. `cshopq` (`float`) as share repurchase proxy.

## Compute-Only Fields (Not Fetched)
These must be derived later from canonical raw fields:
1. `Operating_Margin`
2. `Net_Profit_Margin`
3. `Current_Ratio`
4. `ROA`
5. `ROE`
6. `Debt_to_Equity`
7. `Short_Term_Debt`
8. `Healthy_Long_Term_Debt`
9. `Treasury_Adjusted_Debt_to_Equity`
10. `Book_Value`
11. `Retained_Earnings_Growth`
12. `Share_Repurchases`
13. `Revenue_Growth`
14. `EPS_Growth`
15. `Return_on_Shareholder_Equity`
16. `P/E_Ratio`
17. `Market_Cap`
18. `P/B_Ratio`
19. `Dividend_Yield`
20. `Earnings_Yield`

## Mapping Contract File
Contract source:
`src/trading_bot/config/sec_metric_map.yml`

Validator source:
`src/trading_bot/config/sec_metric_contract.py`

Each metric definition must include:
1. `fact_type`
2. `unit_priority`
3. `form_priority`
4. `tag_priority`
5. `transform_rule`
6. `quality_tier`

Optional:
1. `helper_fallbacks`
2. `component_tags`

## Constraints
1. No extra canonical fields beyond fetch-only and helper fields in Sprint 0.
2. No compute-only fields in mapping contract.
3. Supported forms only: `10-Q`, `10-K`.
4. Mapping contract changes must include schema test updates.
