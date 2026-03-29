# SimFin Stage 1 Mapping Reference

Date: 2026-03-22

## Purpose
Define the field-by-field mapping from cached SimFin statement datasets to the
project's Stage 1 raw fundamentals schema.

This document is an implementation reference for the SimFin `2023-2025` Stage 1
builder. It is based on the actual cached headers currently present under:

- `data/raw/vendor/simfin_cache/us-income-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-balance-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-cashflow-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-income-banks-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-balance-banks-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-cashflow-banks-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-income-insurance-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-balance-insurance-quarterly.csv`
- `data/raw/vendor/simfin_cache/us-cashflow-insurance-quarterly.csv`

## Classification Legend
1. `direct`
   - Exact or near-exact semantic match from a single SimFin column.
2. `derived`
   - Must be computed from one or more SimFin columns.
3. `proxy`
   - Not an exact semantic match, but a defensible sector-specific substitute.
4. `unsupported`
   - Not currently supported from the cached SimFin datasets with acceptable
     confidence.

## Quarter Grain and Output Keys
The Stage 1 output grain remains:

1. `ticker`
2. `year`
3. `quarter`

Quarter extraction should come from:

1. `Fiscal Year`
2. `Fiscal Period`
3. `Report Date`

Accepted quarter labels:

- `Q1`
- `Q2`
- `Q3`
- `Q4`

## Base SimFin Statement Families
The Stage 1 builder should load and union three statement families:

1. General corporate
   - `us-income-quarterly.csv`
   - `us-balance-quarterly.csv`
   - `us-cashflow-quarterly.csv`
2. Banks
   - `us-income-banks-quarterly.csv`
   - `us-balance-banks-quarterly.csv`
   - `us-cashflow-banks-quarterly.csv`
3. Insurance
   - `us-income-insurance-quarterly.csv`
   - `us-balance-insurance-quarterly.csv`
   - `us-cashflow-insurance-quarterly.csv`

## Stage 1 Mapping Table
| Stage 1 field | Classification | General mapping | Bank mapping | Insurance mapping | Notes |
|---|---|---|---|---|---|
| `saleq` | `direct` | `Revenue` | `Revenue` | `Revenue` | Accept as top-line revenue equivalent for all three families. |
| `niq` | `direct` | `Net Income` | `Net Income` | `Net Income` | Use quarterly net income. |
| `oiadpq` | `direct` | `Operating Income (Loss)` | `Operating Income (Loss)` | `Operating Income (Loss)` | Best operating-profit equivalent available. |
| `xintq` | `direct` or `unsupported` | `Interest Expense, Net` | `unsupported` | `unsupported` | Available in general income only in current cache. |
| `txtq` | `direct` | `Income Tax (Expense) Benefit, Net` | `Income Tax (Expense) Benefit, Net` | `Income Tax (Expense) Benefit, Net` | Quarterly tax expense / benefit. |
| `epspxq` | `derived` | `Net Income (Common) / Shares (Basic)` | same | same | SimFin cached quarterly statements do not expose a direct EPS field in the current files. |
| `actq` | `direct` or `unsupported` | `Total Current Assets` | `unsupported` | `unsupported` | Do not fabricate current-assets equivalents for banks or insurers in Stage 1. |
| `lctq` | `direct` or `unsupported` | `Total Current Liabilities` | `unsupported` | `unsupported` | Do not fabricate current-liabilities equivalents for banks or insurers in Stage 1. |
| `ppentq` | `direct` or `proxy` | `Property, Plant & Equipment, Net` | `Net Fixed Assets` | `Property, Plant & Equipment, Net` | Bank mapping is a proxy, not an exact semantic match. |
| `gdwlq` | `direct` or `unsupported` | `Goodwill` | `unsupported` | `unsupported` | Available in general balance cache only. |
| `ivltq` | `direct` or `proxy` | `Long Term Investments & Receivables` | `Short & Long Term Investments` | `Total Investments` | Bank and insurance mappings are proxies. |
| `atq` | `direct` | `Total Assets` | `Total Assets` | `Total Assets` | Strong direct mapping. |
| `ceqq` | `direct` | `Total Equity` | `Total Equity` | `Total Equity` | Use total equity consistently. |
| `dlcq` | `direct` | `Short Term Debt` | `Short Term Debt` | `Short Term Debt` | Nullable where source is blank. |
| `dlttq` | `direct` | `Long Term Debt` | `Long Term Debt` | `Long Term Debt` | Nullable where source is blank. |
| `req` | `direct` | `Retained Earnings` | `Retained Earnings` | `Retained Earnings` | Strong direct mapping. |
| `tstkq` | `direct` or `unsupported` | `Treasury Stock` | `Treasury Stock` | `Treasury Stock` | Nullable where source is blank. |
| `oancfq` | `direct` | `Net Cash from Operating Activities` | `Net Cash from Operating Activities` | `Net Cash from Operating Activities` | Strong direct quarterly mapping. |
| `prstkcq` | `direct` with sign transform | `Cash from (Repurchase of) Equity` | same | same | Convert outflow sign to positive spend in Stage 1 output. |
| `capxq` | `direct` with sign transform | `Change in Fixed Assets & Intangibles` | same | same | Convert outflow sign to positive spend in Stage 1 output. |
| `cheq` | `direct` | `Cash, Cash Equivalents & Short Term Investments` | `Cash, Cash Equivalents & Short Term Investments` | `Cash, Cash Equivalents & Short Term Investments` | Strong direct mapping. |
| `dvpq` | `direct` with sign transform | `Dividends Paid` | `Dividends Paid` | `Dividends Paid` | Convert outflow sign to positive spend in Stage 1 output. |
| `cshfdq` | `direct` | `Shares (Diluted)` | `Shares (Diluted)` | `Shares (Diluted)` | Strong direct mapping. |
| `oancfy` | `direct` with annual dataset | annual `Net Cash from Operating Activities` | same | same | Repeat the ticker-year annual cashflow value across the quarterly rows for that fiscal year. |
| `capxy` | `direct` with annual dataset and sign transform | annual `Change in Fixed Assets & Intangibles` | same | same | Use the annual cashflow statement and convert outflow sign to positive spend. |
| `prstkcy` | `direct` with annual dataset and sign transform | annual `Cash from (Repurchase of) Equity` | same | same | Use the annual cashflow statement and convert outflow sign to positive spend. |
| `cshopq` | `unsupported` | no verified shares-repurchased field | no verified shares-repurchased field | no verified shares-repurchased field | Do not map this to cash spent on repurchases; that is semantically wrong. |
| `cshoq` | `direct` | `Shares (Basic)` | `Shares (Basic)` | `Shares (Basic)` | Strong direct mapping. |

## Fields That Should Not Be Forced
The following Stage 1 fields should remain nullable when no high-confidence
SimFin mapping exists:

1. `xintq` for banks and insurance
2. `actq` for banks and insurance
3. `lctq` for banks and insurance
4. `gdwlq` outside the general corporate balance file
5. `cshopq`

## Sign Conventions
These SimFin cashflow columns should be normalized so Stage 1 stores positive
cash outflows for spend-oriented fields:

1. `prstkcq`
   - source: `Cash from (Repurchase of) Equity`
   - transform: negate source value, floor negative spend at null or zero per
     implementation policy
2. `capxq`
   - source: `Change in Fixed Assets & Intangibles`
   - transform: negate source value
3. `dvpq`
   - source: `Dividends Paid`
   - transform: negate source value

## Recommended Internal Mapping Policy
Implementation should keep Stage 1 field names internal to the pipeline even if
the final exported CSV later adopts friendlier labels.

Reason:

1. existing local Stage 1 outputs already use the current Stage 1 names
2. Stage 2 ratio logic is defined against those fields
3. keeping a stable internal contract makes provider substitution easier

## Open Issues Before Production Build
1. Decide exact `epspxq` derivation policy:
   - `Net Income (Common) / Shares (Basic)` is the current best available rule
   - review whether diluted-share denominator is preferable
2. Decide null policy for spend fields when source value is positive:
   - preserve negated value as-is
   - or clamp to positive spend only
3. Keep `cshopq` nullable unless a real shares-repurchased source is found.

## Current Recommendation For Stage 1 SimFin Build
Implement the production SimFin Stage 1 builder with:

1. `direct` mappings where available
2. `derived` mapping for `epspxq`
3. `proxy` mappings only for:
   - `ppentq` in banks
   - `ivltq` in banks
   - `ivltq` in insurance
4. annual cashflow support fields populated from annual datasets when available
5. `unsupported` fields left null and surfaced in QA reports

This is preferable to forcing weak mappings just to fill the CSV.
