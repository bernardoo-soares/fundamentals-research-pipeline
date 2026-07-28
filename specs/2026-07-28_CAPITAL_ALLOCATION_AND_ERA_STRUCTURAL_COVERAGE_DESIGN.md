# SP4c — capital_allocation investigated, and era-structural coverage separated

Status: IMPLEMENTED — 2026-07-28 (branch `feature/sp4-buffett-scorer`).

`capital_allocation` was the weakest FY2024 component after SP4b (mean coverage
0.525, 97 of 384 excluded, sitting on the `min_component_coverage` floor). This
slice investigated it.

**The headline is negative and should be read as such: `capital_allocation`
cannot be fixed, and this slice does not fix it.** Two candidate remediations
were measured and both were refuted. What shipped instead is the root-cause
record for why, plus one genuine defect the investigation exposed on the way.

---

## 1. Refuted: lifting `treasury_stock_present` by reading null as zero

`treasury_stock_present` falls from 466/466 at FY2022 to 221/384 at FY2024
because SimFin omits the treasury-stock line for 41.6% of tickers. The obvious
remedy is to read a missing line as "no treasury stock" — companies that hold
it must report it, since it is a contra-equity account.

**Measured on the FY2023 overlap, and it is wrong.** Of the 147 Q4 rows where
SimFin omits the line, Compustat reports:

| Compustat value | share |
|---|---|
| exactly 0 | **95.9%** |
| a real position (median **7,728**) | **4.1%** |

95.9% is not good enough for a **binary** claim. `treasury_stock_present` is a
presence flag, so a wrong answer does not shift the criterion slightly — it
flips it outright, asserting "this company has never bought back stock" about
companies holding billions in treasury. It is also imputation regardless (S4.2).

`missing_input` stays. Pinned by
`test_simfin_null_treasury_stock_must_not_be_read_as_zero` so the next person to
have this idea meets the measurement first.

## 2. Refuted: removing the era guard on `capxy`

`capex_intensity` is `mixed_era_window` for **323 of 344** FY2024 tickers, by far
the largest single hole. It is guarded because `capxy` is contradicted at 0.551.

**Root cause found — the guard is correct.** The providers measure **gross vs
net** capital expenditure. Compustat `capxy` is gross spend on PP&E; SimFin's
"Change in Fixed Assets & Intangibles" is a *net* change — purchases less
disposals, and it spans intangibles too.

The decisive evidence is the **sign**. After the builder's outflow negation,
SimFin `capxy` comes out **negative** for disposal-heavy filers, which a gross
spend figure can never be:

| ticker | legacy | SimFin |
|---|---|---|
| PEP | 5,518 | **−198** |
| DE | 4,468 | **−483** |
| URI (equipment rental) | 4,070 | **−1,278** |
| GS | 2,316 | **−962** |
| SPGI | 143 | **−871** |

At Q4, 46.0% match *exactly* and the rest form a one-sided tail (p90 signed
relative difference +0.338, legacy above SimFin for 86.8%) — the shape of a
scope difference confined to filers with material disposals, not noise.

### 2.1 Separately measured and excluded: the year-to-date basis mismatch

Worth recording because it looks like the answer and is not. SimFin repeats the
**full-year** figure on all four quarters (**100.0%** of 366 ticker-years are
constant across Q1–Q4) while Compustat genuinely accumulates (**99.1%**
monotonic). AAPL FY2023 legacy runs 3,787 / 6,703 / 8,796 / **10,959** against
SimFin's flat 10,959.

Pooled over all quarters that would give `capxy` 0.139 — but
`cross_era_semantic_audit` **already restricts `Basis.YEAR_TO_DATE` fields to
Q4**, and `annualize.py` already reads them only at Q4. The basis mismatch is
fully handled and is *not* what the 0.551 measures.

`capxy` is now declared `eras_equivalent=False` with this evidence
(contradictions 8 → 7 — a corrected declaration, not a masked one).

### 2.2 The consequence, stated plainly

`capex_pct_net_income_avg10y` is unavailable from FY2023 onward, because every
10-year window spans the boundary, and **stays unavailable until FY2032** unless
a gross-capex source is added. That is a real, permanent capability loss on a
15%-weight component. Mixing gross and net capex in a 10-year average would be a
false number, so the guard is not negotiable.

## 3. What did ship: era-structural coverage is no longer a company gap

The investigation exposed a genuine defect in `coverage_ratio`. It counted a
criterion nulled by an **era guard** identically to one missing for a
**company-specific** reason. But an era-guarded criterion is absent for *every*
company in the era — counting it as a per-company gap blames the company for a
provider limitation, and can push a whole component below the coverage floor for
a reason that has nothing to do with it.

This is the same class of error as SP4 §7.3's grain mistake: conflating "we lack
data about this company" with "this measurement does not exist here."

`ERA_STRUCTURAL_REASON_CODES` (`era_not_supported`, `mixed_era_window`) now
leave the coverage **denominator**, at both component and scorecard grain.
Because removing them must not make the limitation invisible:

- `score_components.era_unavailable_criteria` records how many were dropped, so
  the UI can say *"3 of 3 measurable, 1 unavailable this era"* rather than the
  indistinguishable *"3 of 4"*;
- `ScoreBadge.ERA_LIMITED` fires whenever any criterion was era-unavailable;
- a component with **zero** measurable criteria is excluded with the new
  `ALL_CRITERIA_ERA_UNAVAILABLE`, not silently scored on nothing.

**This is a transparency fix, not a `capital_allocation` fix**, and the
measurement says so: `excluded_now == excluded_measurable` at 97 for
`capital_allocation`. Presenting it as a remedy would be fitting a narrative to
a change.

## 4. Verification (measured on the rebuilt corpus)

FY2024 mean component coverage, before → after:

| component | before | after | excluded before → after |
|---|---|---|---|
| `capital_allocation` | 0.525 | 0.687 | 97 → **97** (unchanged, as predicted) |
| `profitability_moat` | 0.638 | 0.748 | 52 → 52 |
| `debt_discipline` | 0.703 | 0.847 | 40 → **21** |
| `growth_context` | 0.654 | 0.861 | 53 → 53 |
| `earnings_consistency` | 0.936 | 0.936 | 2 → 2 |

**19 companies gained a debt-discipline score** they were previously denied
because SimFin does not carry a field.

`era_limited` badge: **0** at FY2021 and FY2022 (no guard bites there — the
control), **366 of 493** at FY2023, **369 of 384** at FY2024. Exactly the
expected shape.

Invariants re-measured: 0 value-XOR-reason violations across all three tables,
0 coverage ratios outside [0,1], 0 weight-sum violations, 0 rows where
`era_unavailable_criteria > total_criteria`.

Comparability tracker: FY2022 60.08 vs FY2024 **64.52** (gap +4.44 against
+4.28 before — coverage accounting changed, the scores barely moved). Reported
FY2024 mean coverage rises 0.687 → **0.811**, which is the honest figure.
**Cross-year comparison remains invalid.**

## 5. Open items

1. **`capex_pct_net_income_avg10y` needs a gross-capex source** to return before
   FY2032. This is the only route to a healthy `capital_allocation` in the
   SimFin era.
2. `treasury_stock_present` needs SimFin coverage, not a fill.
3. `prstkcy` at Q4 is 0.201 — the weakest remaining cash-flow field, already
   `divergent_declared`.
4. `oancfy` sits at 0.884 against a 0.90 threshold with 79.0% exact matches; a
   threshold review with justification is warranted rather than a code change.
