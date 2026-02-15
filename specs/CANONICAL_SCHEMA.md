# Canonical SEC Contract and Long Output Schema

## Purpose
Define the current SEC contract that is enforced in code and the current output
shape produced by `sec-normalize-long`.

This stage is intentionally "raw and auditable":
1. map SEC tags to canonical raw fields,
2. keep source metadata for traceability,
3. defer wide-table construction and ratio computation to later stages.

## 1) SEC Metric Mapping Contract

Contract file:
`src/trading_bot/contracts/sec_metric_map.yml`

Validator:
`src/trading_bot/contracts/sec_metric_contract.py`

### 1.1 Required Canonical Fields
The contract must define exactly these fields:
1. Fetch-only raw fields:
`saleq`, `niq`, `oiadpq`, `xintq`, `txtq`, `epspxq`, `actq`, `lctq`, `ppentq`,
`gdwlq`, `ivltq`, `atq`, `ceqq`, `dlcq`, `dlttq`, `req`, `tstkq`, `oancfq`,
`prstkcq`, `capxq`, `cheq`, `dvpq`, `cshfdq`.
2. Helper fallback fields:
`oancfy`, `prstkcy`, `cshopq`, `cshoq`.

### 1.2 Required Mapping Keys (per metric)
1. `fact_type`
2. `unit_priority`
3. `form_priority`
4. `tag_priority`
5. `transform_rule`
6. `quality_tier`

Optional:
1. `helper_fallbacks`
2. `component_tags`

### 1.3 Allowed Values
1. `fact_type`: `duration` or `instant`
2. `form_priority`: `10-Q`, `10-K`
3. `transform_rule`:
`direct`, `q4_extract`, `direct_with_annual_fallback`, `direct_or_sum_components`
4. `quality_tier`: `primary`, `fallback`, `proxy`

### 1.4 Contract Constraints
1. Compute-only metrics are forbidden in the SEC mapping contract.
2. `helper_fallbacks` can reference only helper fields.
3. `direct_or_sum_components` requires non-empty `component_tags`.

## 2) SEC Long Facts Output

Produced by:
`python -m trading_bot sec-normalize-long ...`

Default output:
`data/processed/sec_facts_long_2023_2025.csv`

### 2.1 Time Window
Rows are filtered to `start_year <= fyearq <= end_year` (defaults: 2023-2025).

### 2.2 Row Grain and Dedupe
Output is long-form (multiple rows per ticker-quarter, one per canonical field
candidate). Deterministic dedupe keeps the latest fact by `filed_date` then
`accn` for each key:
1. `ticker`
2. `canonical_field`
3. `fyearq`
4. `fqtr`
5. `period_end`
6. `form_type`
7. `source_tag`
8. `unit`

### 2.3 Output Columns
1. `ticker`
2. `cik`
3. `fyearq`
4. `fqtr`
5. `period_start`
6. `period_end`
7. `filed_date`
8. `form_type`
9. `accn`
10. `frame`
11. `canonical_field`
12. `value`
13. `unit`
14. `source_tag`
15. `quality_tier`
16. `fact_type`
17. `transform_rule`
18. `is_component_tag`
19. `source_system`
20. `source_tag_map_version`

### 2.4 Current Scope Note
`sec-normalize-long` captures mapped SEC facts and mapping metadata. It does not
yet execute wide-table transforms (for example Q4 extraction or component
summing) inside this step.
