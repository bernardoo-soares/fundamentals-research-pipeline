# Stage 1 Plausibility Gate + Era Semantics Batch 2 (SP1c) — Design Specification

Date: 2026-07-24
Status: Implemented 2026-07-24
Relation: Follows `specs/2026-07-24_STAGE1_CROSS_ERA_REMEDIATION_DESIGN.md` (SP1b,
merged as `de4f993`). Unblocks the next Stage 2 slice (`metrics_quarterly` + TTM),
five of whose six metrics read fields that were in CONTRADICTION.

---

## 1. Why this slice, and why before `metrics_quarterly`

The planned next slice computes six metrics. Measured against the cross-era
audit, **five were blocked**:

| metric | inputs | state before |
|---|---|---|
| `net_margin` | niq, saleq | blocked by `saleq` |
| `roe` | niq, ceqq | blocked by `ceqq` |
| `roa` | niq, atq | clean |
| `lt_debt_payback_years` | dlttq, niq | blocked by `dlttq` |
| `debt_to_equity_adj` | ltq, ceqq, tstkq | blocked by `ceqq` |
| `st_lt_debt_ratio` | dlcq, dlttq | blocked by both |

Building TTM metrics on fields whose meaning changes at the provider boundary
would repeat the `retained_earnings_cagr_10y` defect at greater scale, so the
four blocking fields were investigated first.

## 2. Findings

Method as established in SP1b §2.6: vendor dictionary for sibling variants,
then candidate columns scored against the provider column on the FY2023
overlap, always with an `atq` control (97.2% agreement, median 0.0000 — so the
unit scale and fiscal alignment are sound and the gaps below are real).

### 2.1 `ceqq` — fixable, wrong column

SimFin publishes one equity line, "Total Equity", which **includes**
noncontrolling interests. Compustat `ceqq` is Common/Ordinary Equity and
excludes them.

| candidate | agree @1% | median rel. diff |
|---|---|---|
| `ceqq` (common equity) | 64.7% | 0.0012 |
| `teqq` (total equity) | 86.3% | 0.0000 |
| **`seqq + mibtq`** | **94.0%** | **0.0000** |
| `ceqq + mibtq` | 88.0% | 0.0000 |

`mibtq` is null for 5.1% of rows and exactly zero for 45.6% of those present;
treating null as zero holds agreement at 94.0% while recovering the rows,
which is the measurement that justifies it — a company reporting no
noncontrolling-interest line has none. Post-fix the audit reports **0.964**.

**Consequence for ROE, recorded rather than hidden.** The numerator is
parent-only income in both eras (legacy `niq` agrees 92.0% with SimFin Net
Income; pre-noncontrolling `ibmiiq` agrees only 67.6%), so pairing it with
total equity slightly understates ROE where noncontrolling interests are
material. The effect is small — `mibtq` is exactly zero for 45.6% of rows and
the common-vs-total median gap is 0.12% — and SimFin offers no common-equity
line, so this is the only cross-era-comparable choice.

### 2.2 `dlttq` and `dlcq` — classification boundaries, not remapping errors

| field | best candidate | agree @1% |
|---|---|---|
| `dlttq` | `dlttq` 9.8%; `dlttq+dd1q` 1.7%; `lltq` 0.0% | **9.8%** |
| `dlcq` | `dlcq` 8.7%; `dd1q` 3.9%; `dlcq-dd1q` 6.6% | **8.7%** |

No Compustat column matches either — the same shape as `ppentq`. `dlcq` also
diverges on coverage: SimFin leaves it null for 28.2% of companies against
0.9% for Compustat, so the providers disagree on whether the concept even
applies. Both declared `eras_equivalent=False`; `lt_debt_payback_years` and
`st_lt_debt_ratio` must use the single-era guard from SP1b §2.9.

### 2.3 `saleq` — not a definitional mismatch, a provider data defect

The concepts match: median relative difference is exactly **0.0000**, and
`revtq` scores no better than `saleq` (84.7% vs 83.5%). The residual is data
quality. Eight FY2023 tickers carried **negative Q4 revenue**:

| ticker | Q1 | Q2 | Q3 | Q4 | implied FY | true FY (legacy) |
|---|---|---|---|---|---|---|
| MAR | 5615 | 6075 | 5928 | **-11318** | 6300 | 23713 |
| DLTR | 7324 | 7325 | 7315 | **-5183** | 16781 | 30604 |
| HLT | 2293 | 2660 | 2673 | **-3218** | 4408 | 10235 |
| WDC | 3736 | 3107 | 2803 | **-3391** | 6255 | 12318 |
| NDAQ | 1533 | 1433 | 1451 | **-522** | 3895 | 6064 |

SimFin derives some Q4 figures as a residual; when the fiscal calendars
disagree the residual goes negative. For **0%** of these tickers did the four
quarters still sum to the true annual — revenue read roughly halved. This fed
`revenue_cagr_2y/4y/10y` and `net_margin_ge20_years_10y`, all shipped.

The defect is **not** SimFin-specific: the live warehouse also held 23 legacy
negative-revenue quarters and 41 legacy negative-COGS quarters.

## 3. The plausibility gate (§2.3's fix)

New `warehouse/plausibility.py`, driven by a declarative
`NON_NEGATIVE_FIELDS` tuple in the Stage 1 contract: fields that cannot be
negative under any accounting treatment are nulled when negative, and every
rejection is recorded.

Deliberately conservative. Excluded because they can legitimately be negative:
`niq`, `oiadpq` (losses), `xintq`, `txtq` (net interest income, tax benefits),
`oancfq`, `capxq` (net outflows, disposals), `prstkcy` (SimFin states net
equity flow), `req`, `ceqq` (accumulated deficits), `ivltq`, `tstkq` (sign
conventions vary).

Nulling one quarter correctly nulls that fiscal year, because annualization
already requires all four quarters present — a null annual instead of a wrong
one. `load_fundamentals_quarterly` returns the violations, and
`rebuild_warehouse` writes
`data/reports/plausibility_violations_<start>_<end>.csv`, written even when
empty so a run always states what it rejected.

## 4. Measured results

- Cross-era contradictions **14 → 10**.
- `ceqq` 0.654 → **0.964 agree**; `saleq` → **agree**; `dlttq`, `dlcq` →
  `divergent_declared`.
- Plausibility gate nulled **152** impossible values: cogsq 58, saleq 35,
  dpq 31, xsgaq 12, xrdq 6, dlttq 4, ltq 4, ppentq 1, rectq 1.
- **0** impossible values remain in the warehouse.
- MAR/DLTR/HLT/WDC/NDAQ FY2023 revenue is now **null rather than halved**.
- `metrics_trend` still 42,557 rows.

### 4.1 Next-slice readiness

| metric | state |
|---|---|
| `net_margin` | **clean** |
| `roe` | **clean** (with the ROE note in §2.1) |
| `roa` | **clean** |
| `debt_to_equity_adj` | **clean** |
| `lt_debt_payback_years` | single-era only (`dlttq` divergent) |
| `st_lt_debt_ratio` | single-era only (`dlcq`, `dlttq` divergent) |

## 5. `saleq` threshold, and why it is not silencing

`saleq` is declared equivalent with `min_agreement_rate = 0.80` rather than the
0.90 default. The contract requires a written justification for any lowered
threshold, and it is recorded on the declaration: the concepts match at median
0.0000, the residual tail is provider data quality, and the impossible portion
of that tail is now gated rather than tolerated. The remaining tail is
enumerated in the reconciliation report and stays an open item — the threshold
accepts it visibly instead of reclassifying the field as divergent, which would
have wrongly implied the two providers mean different things by revenue.

## 6. Known limitations

1. The `saleq` residual beyond the impossible values (~16% of the overlap) is
   still unexplained. It is not fiscal misalignment: only 15.5% of disagreeing
   tickers also disagree on `atq`, and the correlation between the two
   residuals is 0.359.
2. Nulling impossible values reduces coverage for the affected ticker-years.
   That is the intended trade: `revenue_cagr` now returns `missing_input` for
   those companies instead of a figure derived from halved revenue.
3. `NON_NEGATIVE_FIELDS` is a judgement about accounting, not a measurement.
   It is deliberately conservative, so it will not catch an impossible value in
   a field that is merely usually positive.
4. Ten fields remain in CONTRADICTION: `capxy`, `cheq`, `cshfdq`, `cshoq`,
   `dpq`, `oancfy`, `oiadpq`, `rectq`, `xrdq`, `xsgaq`. None blocks the next
   slice.
