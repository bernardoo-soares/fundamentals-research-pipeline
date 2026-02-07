# Project Architecture

## Goal
Retrieve the current S&P 500 universe and standardize local legacy quarterly
fundamentals into canonical outputs and derived ratio datasets.

## Data Flow (High Level)
1) Fetch current S&P 500 constituents
2) Narrow legacy quarterly fundamentals to canonical fields
3) Compute derived ratios and store outputs by year

## Components

### 1) Universe Builder
- Sources:
  - Wikipedia S&P 500 current constituent list.
- Output:
  - `data/universe_current.csv` with `ticker` and `as_of_date`.

### 2) Legacy Fundamentals Canonicalization
- Source:
  - `data/raw/Processed-Fundamentals/*.csv`
- Input constraints:
  - Only current S&P 500 tickers from the universe output.
- Canonical fields:
  - `saleq`, `niq`, `oiadpq`, `xintq`, `txtq`, `epspxq`, `actq`, `lctq`,
    `ppentq`, `gdwlq`, `ivltq`, `atq`, `ceqq`, `dlcq`, `dlttq`, `req`,
    `tstkq`, `oancfq`, `prstkcq`.

### 3) Ratio Computation
- Compute:
  - Operating margin, net margin, current ratio
  - Debt ratios and treasury-adjusted leverage
  - Book value, share repurchases
  - Retained earnings growth (YoY, 4-quarter lag)
  - ROA and ROE (TTM net income over 4-quarter averages)

## Outputs
- `data/universe_current.csv`
- `data/processed/canonical_legacy_q.csv`
- `data/processed/fundamentals_q_<year>.csv`
- `data/processed/ratios_q_<year>.csv`
