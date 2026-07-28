# SP4b — Gross profit in the SimFin era, and reliability flags that reach the UI

Status: DESIGN — 2026-07-28 (branch `feature/sp4-buffett-scorer`).

Two problems, one slice, because the first must not ship without the second.

1. The gross-profit family is restricted to the era where its arithmetic is
   **wrong for 65.6% of companies**, and excluded from the era where it is
   **exactly right for all of them**. That is what empties the 30%-weight
   `profitability_moat` component at FY2024 (SP4 spec §1).
2. A metric's reliability caveats **die at the scoring seam**. `MetricReading`
   carries `value` and `reason_code` but not `quality_flag`, so nothing a metric
   knows about its own trustworthiness reaches `score_criteria`, and therefore
   nothing reaches the UI.

Standing directive (2026-07-28): **any value that is not 100% covered or fully
reliable must carry a machine-readable flag on the row that reaches the UI.** A
caveat recorded in a spec, a docstring or a `divergence_note` does not satisfy
this. That directive is what makes (2) a blocker for (1): enabling a second era
adds a second reliability class, and shipping it unflagged would leave the user
unable to tell the exact number from the assumed one.

Prime Directive: **no false numbers.**

---

## 1. The measurement this rests on

Full evidence in `2026-07-26_SP3_METRIC_CATALOG_COMPLETION_DESIGN` §2.2.1
(measured 2026-07-28). In summary, solving per company for

```
a = (Cost of Revenue_simfin − cogsq_legacy) / dpq_legacy
```

— the share of total D&A the **filer** placed inside cost of revenue — gives a
**trimodal** distribution (n=227, FY2023): 34.4% at `a ≥ 0.95`, 26.4% at
`a ≤ 0.05`, 32.6% between. **SimFin preserves each filer's presentation;
Compustat normalises D&A out of every one.**

| formula | assumes | exact for | error where wrong |
|---|---|---|---|
| `saleq − cogsq − dpq` (shipped, legacy) | `a = 1` | 34.4% | median **−13.46pp** at `a ≤ 0.05` |
| `saleq − cogsq` (SimFin, as-reported) | nothing | **all** | — |

AAPL FY2023: SimFin Cost of Revenue 214,137 **is** Apple's published total cost
of sales, giving the published 44.13% gross margin. The shipped legacy formula
flips the book's >40% verdict for **11.8%** of companies overall and **33.3%** of
the `a ≤ 0.05` group.

**Coverage that this unlocks:** SimFin FY2024 carries `cogsq` on **336 of 389**
tickers (86.4%), median gross margin 0.4732.

## 2. What changes

### 2.1 Era-specific arithmetic, one concept

| era | gross profit | why |
|---|---|---|
| legacy | `saleq − cogsq − dpq` | Compustat normalises D&A out of `cogsq`; `a` is unrecoverable, so `a = 1` is assumed |
| simfin | `saleq − cogsq` | SimFin's Cost of Revenue **is** the as-reported line |

This is not one field meaning two things (S4.3). The **concept** is single —
*published gross profit* — and the arithmetic differs because the two providers
store different quantities, which is precisely what the era-semantics layer
exists to express. A TTM window spanning the boundary is already nulled
`mixed_era_window` by per-field purity, since `cogsq` is declared
non-equivalent, so no single value is ever assembled from both.

The five metrics lose `supported_eras=_LEGACY_ONLY` and gain era-dispatched
arithmetic.

### 2.2 The reliability flags

Extends the existing `quality_flag` vocabulary — an advisory marker that
co-exists with a real value, distinct from a `reason_code`, which explains a
null. The `tstk_unavailable` flag is the precedent.

| flag | fires on | meaning |
|---|---|---|
| `da_allocation_assumed` | **every legacy-era gross-profit row** | `a = 1` was assumed. Exact for ~34% of filers; understates gross margin by a median 13.46pp for the ~26% who present D&A outside cost of revenue. The value is real but carries a known, measured, one-directional bias. |

Deliberately **not** a reason code: the legacy value is not null and is correct
for a third of the corpus. Deliberately **not** silent: it is wrong enough, often
enough, to change a >40% verdict for a third of one group.

SimFin-era rows carry **no** flag on this axis — the as-reported figure needs no
caveat.

### 2.3 Flags reach the UI (the general fix)

`quality_flag` is currently dropped between `metrics_quarterly` and the score
tables. This slice carries it through the whole seam:

```
metrics_quarterly.quality_flag
  -> MetricReading.quality_flag          (contract, new field)
  -> CriterionResult.quality_flag        (contract, new field)
  -> score_criteria.quality_flag         (column, new)
  -> ScoreBadge.UNRELIABLE_INPUT         (score grain, new)
```

`ScoreBadge.UNRELIABLE_INPUT` fires when **any** applicable criterion carried a
quality flag, joining `low_confidence` and `stale_data`. The per-criterion flag
is what the UI shows on drill-down; the badge is what it shows in a list.

This benefits every metric, not just gross profit — `tstk_unavailable` on
`debt_to_equity_adj` has been invisible to the scoring layer since it shipped.

**Invariant:** a `quality_flag` requires a non-null value (already enforced on
`QuarterPoint`); the same rule is enforced on `MetricReading`.

## 3. What this slice does NOT do

**Per-ticker cost-of-revenue scope divergence is deferred**, with its
measurement already recorded. For filers who report no gross-profit subtotal, the
two providers synthesise *different scopes*: CMCSA FY2023 `a = −3.29`, where
SimFin's Cost of Revenue (36,761) is Comcast's "Programming and production" line
while Compustat's `cogsq` (83,922) also absorbs "Other operating and
administrative". SimFin still publishes a Gross Profit for such companies
(84,811, a 69.8% margin), so the null-coverage gate does **not** catch them.

Detecting this needs a per-ticker classification measured on the FY2023 overlap
and carried forward as ticker metadata. That is a legitimate flag — it is
metadata, not an imputed value — but it introduces a cross-era artifact that pure
`metrics/` cannot compute, so it belongs in its own slice with its own audit
step. **Recorded as an open item, not silently accepted.**

Also out of scope: the 21.4% of SimFin rows with neither Cost of Revenue nor
Gross Profit. Those already null out with `missing_input` and are correctly
excluded — no change needed.

## 4. Verification plan

1. Golden, legacy: KO FY2021 `0.602716` must not move — the legacy arithmetic is
   unchanged, only flagged.
2. Golden, SimFin: **AAPL FY2023 gross margin = 169,148 / 383,285 = 0.441261**,
   Apple's published figure, hand-derived in the test.
3. Property: every legacy gross-profit row with a value carries
   `da_allocation_assumed`; no SimFin row does; a flag never accompanies a null.
4. Real corpus: FY2024 `profitability_moat` coverage and exclusion count before
   and after; flag distribution; `unreliable_input` badge count.
5. The SP4 comparability finding (§7.4 of the SP4 spec) must be **re-measured**,
   not assumed to persist — restoring the moat component at FY2024 is expected to
   change the FY2022↔FY2024 relationship it described.

## 5. Verification results (measured 2026-07-28 on the rebuilt warehouse)

Status: **IMPLEMENTED**. 385 tests pass; `ruff` and `compileall` clean.

### 5.1 The blocker is cleared

| `profitability_moat` | FY2022 | FY2024 before | FY2024 after |
|---|---|---|---|
| tickers excluded | 51 of 466 | **379 of 384** | **52 of 384** |
| mean coverage | 0.785 | **0.159** | **0.638** |

`gross_margin` non-null at FY2024: **5 → 336**. Across the corpus,
`era_not_supported` falls **6,766 → 1,491**: the 5,275 suppressed gross-profit
rows now compute. At FY2024 the moat component moves from *worst-covered by a
factor of three* to **second-best**.

### 5.2 Goldens

| check | result |
|---|---|
| AAPL FY2023 (SimFin era) | **0.4413** = Apple's published 44.13% |
| AAPL FY2024 (SimFin era) | 0.4621, unflagged |
| AAPL FY2022 (legacy era) | 0.4331, flagged `da_allocation_assumed` |
| KO FY2021 (legacy era) | **0.6027 — unmoved**, now flagged |

The legacy arithmetic is unchanged, exactly as intended: only its caveat is now
visible, and only the SimFin era gained a value.

### 5.3 Flags reach the UI

| layer | result |
|---|---|
| `metrics_quarterly.quality_flag` | 81,925 `da_allocation_assumed`, 1,415 `tstk_unavailable` |
| `score_criteria.quality_flag` | 21,588 + 314 — **the seam now carries it** |
| `scores.badges` `unreliable_input` | 417 at FY2022, 245 at FY2023, 155 at FY2024 |
| flag accompanying a null | **0** violations |

`tstk_unavailable` had been invisible to the scoring layer since it shipped;
it now surfaces too.

### 5.4 Comparability: improved, not resolved

The SP4 spec §7.4 finding was **re-measured, not assumed**:

| | FY2022 | FY2024 | gap |
|---|---|---|---|
| before this slice | 60.08 | 67.09 | **+7.00** |
| after | 60.08 | **64.36** | **+4.28** |

Restoring the moat component removes about 40% of the inflation. The rest is
**not** gross-profit related — it is `capital_allocation` (FY2024 mean coverage
0.525, 97 tickers excluded) and the era-guarded `growth_context` /
`debt_discipline` metrics. **Cross-year comparison remains invalid** and SP6
must still block it; the warning is smaller, not gone.

One genuine residual, now flagged rather than hidden: legacy gross margin is
systematically **lower** than SimFin's, because the `a = 1` assumption
over-subtracts for the ~26% of filers who present D&A outside cost of revenue.
FY2024 moat scores 57.09 against FY2022's 46.83 partly for that reason. Every
affected row carries `da_allocation_assumed`, which is precisely what the flag
is for.

## 6. Open items

1. **Per-ticker cost-of-revenue scope divergence** (§3) — CMCSA-type filers,
   measurable on the FY2023 overlap, needs its own slice.
2. **Cross-year comparison must still be blocked in SP6** (§5.4).
3. `capital_allocation` is now the weakest FY2024 component (0.525) and sits on
   the `min_component_coverage` floor. Next candidate for the same treatment.

## 7. Change log

1. 2026-07-28 — design opened, on measurements taken the same day.
2. 2026-07-28 — implemented and verified. `gross_margin`,
   `sga_pct_gross_profit`, `rd_pct_gross_profit` and `dep_pct_gross_profit`
   bumped to version `2` (S3.6: a changed computation must break its goldens,
   and it did — four registry tests asserted the legacy-only intent and were
   rewritten against the measurement).
