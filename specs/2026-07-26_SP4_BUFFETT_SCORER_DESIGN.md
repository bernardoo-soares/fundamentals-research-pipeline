# SP4 — Buffett Scoring Framework

Status: IMPLEMENTED — 2026-07-28 (branch `feature/sp4-buffett-scorer`).
Designed 2026-07-26; the pure engine shipped in `20c4e25`, the builder, schema
registration, CLI and real-corpus verification on 2026-07-28. Section 7 records
what was measured on the built tables, including **two corrections to this
document's own design-time claims** (§7.3, §7.4).

Implements platform spec §7: the `Scorer` protocol, the `BuffettHeuristicScorer`
v1 with graded ramps and the literal book checklist, and the `scores` /
`score_criteria` tables.

Prime Directive: **no false numbers.** A score is a number a human acts on with
money, so every criterion carries its metric value, points, weight, checklist
verdict and reason code, and a score that cannot be computed honestly is not
published.

---

## 1. The blocking finding: the moat component collapses at FY2024

Measured before designing. All 23 criteria metrics from §7.2 now exist (SP3
completed them), but their **availability is not uniform across as-of years**,
because five of them are legacy-era restricted or era-guarded — restrictions
added in PRs #12/#13 in response to real data defects, after §7.2's weights were
written.

Non-null criterion values, FY2022 (462 tickers with trend rows) vs FY2024 (357):

| component | criterion | FY2022 | FY2024 |
|---|---|---|---|
| **Profitability & moat (30%)** | `gross_margin` | 417 | **5** |
| | `gross_margin_ge40_years_10y` | 397 | **6** |
| | `sga_pct_gross_profit` | 343 | **5** |
| | `rd_pct_gross_profit` | 184 | **2** |
| | `dep_pct_gross_profit` | 413 | **5** |
| | `net_margin_ge20_years_10y` | 442 | 343 |
| **Earnings consistency (20%)** | all 4 | 434–461 | 343–371 |
| **Debt discipline (25%)** | `interest_pct_operating_income` | 414 | **4** |
| | other 4 | 390–456 | 279–367 |
| **Capital allocation (15%)** | `capex_pct_net_income_avg10y` | 421 | **4** |
| | other 3 | 295–466 | 221–332 |
| **Growth context (10%)** | `receivables_pct_sales_trend_10y` | 436 | **6** |
| | other 3 | 433–454 | 325–340 |

**At FY2024, five of the six Profitability criteria are empty.** Under §7.4.1's
renormalization rule as written, the 30%-weight component would rest entirely on
`net_margin_ge20_years_10y` — one criterion carrying **six times** its designed
5% share, silently. That is not "the same component measured with less data"; it
is a different measurement wearing the same label.

D7 declares FY2024 the platform's current analysis year, so this is not an edge
case — it is the year a user screens on.

### 1.1 Consequence adopted: a declared minimum component coverage

§7.4.1 handles a component with *zero* applicable criteria (exclude and
renormalize) but not one with *one of six*. This design adds a declared floor:

```yaml
min_component_coverage: 0.50   # a component needs a majority of its criteria
```

A component below the floor is **excluded exactly like a zero-coverage one**, and
top-level weights renormalize across the survivors. Measured separation at
FY2024 makes 0.50 a clean cut rather than a fitted one:

| component | FY2024 coverage | verdict at 0.50 |
|---|---|---|
| profitability_moat | 1/6 = **0.167** | excluded |
| capital_allocation | 3/4 = 0.75 | kept |
| growth_context | 3/4 = 0.75 | kept |
| debt_discipline | 4/5 = 0.80 | kept |
| earnings_consistency | 4/4 = 1.00 | kept |

The next-lowest component sits at 0.75, so the floor has 0.25 of headroom on
either side and no component is near it. At FY2022 every component is at or near
1.00 and nothing is excluded.

### 1.2 What this means for the product, stated plainly

**FY2022 is the last as-of year at which a full Buffett scorecard can be
computed.** At FY2024 the composite is assembled from four components with no
moat measure at all — and moat is the centre of the thesis, not a nice-to-have.
The score is still honest (the exclusion and the coverage ratio are recorded and
badged), but it answers a narrower question.

This is a direct downstream cost of the `cogsq` era defect. It raises
root-causing the remaining `cogsq` residual from "largest open item" to "the
thing blocking the product's headline year", and it should be weighed against
building SP5/SP6 first.

Scores are computed for **every** as-of year — the `scores` table grain is
`(ticker, as_of_year, scorer_name, scorer_version, config_hash)` — so the UI can
offer both, with coverage badges telling the user which year to trust. No
as-of year is special-cased in code.

---

## 2. Architecture

### 2.1 The seam (`contracts/scorecard_schema.py`)

```python
class Scorer(Protocol):
    name: str
    version: str
    def score(self, inp: ScorerInput) -> ScorerOutput: ...
```

Frozen value objects: `ScorerInput` (ticker, as_of_year, metric values with
reason codes, source_family, staleness_quarters), `CriterionResult` (criterion_id,
metric_id, value, points, weight, checklist verdict, reason_code, annotation),
`ScorerOutput` (composite, component scores, coverage, badges, criteria).

`ChecklistVerdict` is a closed `StrEnum`: `PASS | FAIL | NOT_APPLICABLE`.

Scorers read **only** `metrics_*` tables — never raw fundamentals, never prices.
Scores never feed back into metrics, so there is no leakage path by construction
and the metrics layer doubles as a future ML feature matrix.

### 2.2 Config, hash-pinned (`scoring/buffett_scorecard.yml`)

Every weight, ramp anchor, checklist threshold and the coverage floor is a
config value, never a literal in a function (S1.3). `config_hash =
sha256(canonical serialisation)` is stored on every score row, so a config edit
is visible in the data rather than silently changing history.

Canonicalisation is explicit (sorted keys, fixed float formatting, UTF-8) so the
hash is stable across YAML round-trips — hashing raw file bytes would change on
a whitespace edit and is therefore not used.

### 2.3 Pure compute (`scoring/`)

- `ramps.py` — piecewise-linear interpolation over declared `(x, points)`
  anchors. Pure, no I/O.
- `checklist.py` — the literal book rules, each a declared comparison
  (`>`, `>=`, `<`, `<=`) against a threshold.
- `buffett_scorer.py` — assembles criteria into components into a composite.

`scoring/builder.py` is the only module that touches the warehouse, mirroring
`metrics/builder.py`.

### 2.4 Ramps

A ramp is a list of anchors, evaluated by linear interpolation and clamped
outside the ends. `gross_margin` from §7.3:

```yaml
gross_margin:
  ramp: [[0.20, 0], [0.40, 80], [0.60, 100]]
  checklist: {op: ">", threshold: 0.40}
  weight: 0.30
```

Anchors must be strictly increasing in `x`; the loader rejects otherwise, since
a non-monotonic ramp would make points ambiguous. Descending-good metrics (lower
is better: `sga_pct_gross_profit`, `interest_pct_operating_income`,
`lt_debt_payback_years`, `debt_to_equity_adj`, `capex_pct_net_income_avg10y`,
`receivables_pct_sales_trend_10y`) are expressed with **descending points** over
ascending x, so one evaluator serves both directions and no metric needs an
`invert` flag.

## 3. Null handling (§7.4), restated exactly

1. A criterion whose metric is null for any reason is `NOT_APPLICABLE`,
   contributes no points and no weight; remaining weights renormalize **within
   the component**.
2. A component with zero applicable criteria — **or coverage below
   `min_component_coverage` (§1.1)** — is excluded; top-level weights
   renormalize across the survivors.
3. If *every* component is excluded, the composite is **null with a reason
   code**, never 0. A zero composite would rank a company as terrible when the
   truth is that nothing is known about it. This is the value-XOR-reason
   invariant applied at the score grain.
4. `negative_equity_strong_earnings == 1` replaces the `roe` criterion with full
   points and the annotation "negative equity with durable earnings — book
   special case" (§7.4.3). Measured: 23 companies at FY2022 (AZO, ORLY, MCD, PM,
   MO, SBUX, TDG …), a recognisable roster of sustained-buyback franchises.
5. R&D null is `NOT_APPLICABLE`, never penalised and never rewarded (§6.3.2):
   a null `xrdq` cannot be distinguished from "no R&D programme".
6. Badges: `coverage_ratio < 0.60` ⇒ `low_confidence`; `staleness_quarters > 4`
   ⇒ `stale_data`.

## 4. Determinism

Criteria are evaluated in declared config order; components in declared order.
Renormalisation divides by a sum accumulated in that fixed order, so the result
is float-reproducible. No clock, no randomness, no dict-ordering dependence.
`computed_at` is metadata and never influences a value (S3.4).

## 5. Verification plan

1. Golden: a hand-computed scorecard for one real company, every criterion's
   points and the composite derived by hand in the test.
2. Property: composite is null-or-reasoned when all components are excluded;
   points always within `[0, 100]`; weights within a component always sum to 1.0
   after renormalisation (or the component is excluded).
3. Real corpus: score distribution, coverage distribution, badge counts, and the
   FY2022-vs-FY2024 component-exclusion difference.
4. Determinism: scoring the same input twice yields identical rows; the config
   hash is stable across a YAML round-trip.

## 6. The builder (implemented 2026-07-28)

`scoring/builder.py` is the only module in `scoring/` that touches the
warehouse. `build_scores(warehouse_path=…, config_path=…, scorer=…)` reads the
metrics grain, drives any `Scorer`, and rebuilds `scores`, `score_components`
and `score_criteria` idempotently. CLI: `scores-build`.

### 6.1 Grain join

Trend metrics are already annual. Quarterly metrics are read at
`FISCAL_YEAR_END_QUARTER` (Q4) **only** — the same fiscal-year-end convention
`warehouse/annualize.py` applies to every stock field. Falling back to an
adjacent quarter when Q4 is absent would be imputation (S4.2), so an absent Q4
yields an absent reading. Measured: 0 of 7,436 trend ticker-years lack a Q4 row,
so the strict rule costs nothing.

The two grains share **0** `metric_id` values (15 trend, 13 quarterly), which
makes one flat reading map unambiguous. The builder re-checks this at load time
and raises rather than letting one grain silently overwrite the other.

### 6.2 Scored universe

The **union** of both grains' ticker-years, not the trend grain alone.
Measured: 987 ticker-years are quarterly-only (412 at 2006, 415 at 2007, the
remainder tickers whose history starts mid-corpus). Scoring only the trend grain
would omit them silently; publishing them with a null composite and a reason
code says the same thing out loud. Total universe: **8,423** ticker-years,
exactly `fundamentals_annual`'s row count.

### 6.3 `Scorer.config_hash`

`config_hash` moved onto the `Scorer` protocol. It is the third element of the
reproducibility key, so the builder must record it without knowing which scorer
it is driving — a heuristic scorer hashes its scorecard YAML, an MLScorer would
hash its weights.

### 6.4 Staleness

The platform spec's §6.4 definition verbatim: quarters between the ticker's
latest available quarter and the warehouse's latest. It is therefore a property
of the ticker's *reporting*, not of the year being scored.

---

## 7. Real-corpus verification (2026-07-28)

Built against `data/warehouse/research.duckdb`, `config_hash`
`8d9af564e1eec40dcd2e71ae06d2f65a124efbad3e0b9103ec2bc88f3fed5e88`.

| table | rows |
|---|---|
| `scores` | 8,423 |
| `score_components` | 42,115 |
| `score_criteria` | 193,729 |

### 7.1 Invariants, measured on the built tables

| invariant | result |
|---|---|
| value XOR reason, all three tables | **0** violations |
| `NaN`/`inf` in any stored numeric column | **0** |
| composite within [0, 100] | **0** violations |
| component weights sum to 1.0 per scored ticker-year | **0** violations |
| criterion weights sum to 1.0 within each scored component | **0** violations |
| null composites | 69 of 8,423, all `no_applicable_component` |

### 7.2 Golden: KO FY2022, hand-checked end to end

Composite recomputed by hand from the stored component rows:

```
capital_allocation    80.879989 x 0.15 = 12.131998
debt_discipline       79.761516 x 0.25 = 19.940379
earnings_consistency  68.316539 x 0.20 = 13.663308
growth_context        54.599983 x 0.10 =  5.459998
profitability_moat    80.744923 x 0.30 = 24.223477
                                  SUM  = 75.419160
```

Stored composite: `75.41916049834354`. ✅

The wiring is confirmed against a *previously* hand-verified corpus value:
`capex_intensity` reads **0.257778**, which is exactly PR #13's hand-derived
golden for KO FY2022 (18,875 / 73,222). The metric→criterion→component→composite
chain therefore carries a known-true number through unchanged.

Ramp arithmetic spot-checked: `gross_margin` 0.5814 on `[[0.20,0],[0.40,80],
[0.60,100]]` ⇒ 80 + ((0.5814−0.40)/0.20)×20 = 98.14 (stored 98.1434). ✅
`rd_discipline` is `n.a.` with `missing_input` and the component renormalises
over 5 of 6 criteria at 0.20 each. ✅ The negative-equity override fired for
**23** tickers at FY2022, matching §3.4's measured roster.

### 7.3 CORRECTION — §1.1's headroom claim was measured at the wrong grain

§1.1 states: *"The next-lowest component sits at 0.75, so the floor has 0.25 of
headroom on either side and no component is near it."* **Measured on the built
table, that is wrong.** Per-ticker component coverage at FY2024:

| component | mean coverage | median | tickers below the 0.50 floor |
|---|---|---|---|
| `profitability_moat` | 0.159 | 0.167 | **379 of 384 (98.7%)** |
| `capital_allocation` | 0.525 | **0.500** | **97 of 384 (25.3%)** |
| `growth_context` | 0.654 | 0.750 | 53 of 384 |
| `debt_discipline` | 0.703 | 0.800 | 40 of 384 |
| `earnings_consistency` | 0.936 | 1.000 | 2 of 384 |

The design figure counted **non-null criterion values pooled across tickers**;
the floor is applied to **per-ticker component coverage**. These are different
quantities — four criteria each ~75% populated on *different* tickers give far
less than 0.75 per ticker.

Consequence: the floor is clear of `profitability_moat` (0.159, unambiguous)
but runs straight through `capital_allocation`, whose median sits exactly on it.
A quarter of the FY2024 universe is decided by that boundary, so small data
changes will flip components in and out for those tickers.

**Not acted on in this slice.** Moving a declared threshold to fit observed data
needs its own measurement and its own justification; 0.50 remains correct for
the reason it was adopted. Logged as an open item.

### 7.4 CORRECTION — FY2024 composites are NOT comparable to FY2022 composites

The exclusion mechanism does not merely narrow the question — it **inflates the
score**, because the component it removes is the harshest one.

Mean component score at FY2022: `profitability_moat` **46.83**, then
`growth_context` 55.56, `earnings_consistency` 62.00, `debt_discipline` 67.98,
`capital_allocation` 71.82. Moat is the hardest component by 8.7 points.

Recomputing FY2022 composites with `profitability_moat` dropped — exactly what
the FY2024 exclusion does — for the same 466 companies:

| quantity | value |
|---|---|
| mean published FY2022 composite | 60.08 |
| mean FY2022 composite without moat | 65.21 |
| **mean shift** | **+5.13** (p90 **+13.45**) |
| observed FY2022 → FY2024 mean gap | **+7.00** (60.08 → 67.09) |

**The exclusion accounts for roughly three quarters of the entire apparent
"FY2024 companies score better" effect.** FY2024 is not a year in which the
S&P 500 got more Buffett-like; it is a year in which the hardest test was not
administered. §1.2 said the FY2024 score "answers a narrower question" — the
measurement shows it also answers it more generously.

**Consequence: cross-year composite comparison is invalid and SP6 must not
offer it.** Ranking within a single `as_of_year` remains sound.

### 7.5 Coverage does not gate ranking — badges alone are insufficient

| measurement | FY2022 |
|---|---|
| `corr(coverage_ratio, composite)` | 0.196 |
| low-confidence rows inside the top 20 by composite | 2 |
| minimum coverage inside the top 20 | **0.174** (SOLV, a 4-criterion scorecard ranked 9th of 466) |

The 2006–2007 cohort (827 rows, mean coverage 0.434, max 0.522 — no 10-year
window exists yet) has composite p50 **63.8** against FY2022's **61.1**, and
reaches **100.0** where no full-coverage FY2022 company exceeds **93.6**. Thin
scorecards are not systematically worse; they are noisier and they reach higher.

Every one of those 827 rows carries the `low_confidence` badge and its
`coverage_ratio`, so the data is honest. But a badge is advisory: **SP6 must
filter on coverage, not merely display it**, or the top of every screen will be
occupied by the companies about which least is known.

### 7.6 Coverage by year, and the staleness badge

Mean coverage by as-of year: 0.43 (2006–2009) → 0.49 (2010–2014) → **0.79 at
2015**, the first year a 10-year window can complete on a corpus starting in
2006 → ~0.87 (2016–2022) → 0.62 (2023) → **0.56 (2024)**, the era-restriction
cliff. 4,521 of 8,423 rows carry `low_confidence`, almost all of them pre-2015.

`stale_data` fired on **10** rows, all `SNDK`, whose fundamentals stop at 2015Q4
(acquired in 2016) — 36 quarters behind the warehouse frontier of 2024Q4. 109
tickers last reported 2023Q4 and sit at staleness exactly 4, which the declared
`> 4` threshold does not badge.

---

## 8. Out of scope

1. The UI (SP5/SP6) — this slice writes tables only.
2. Sector scorecards for banks/insurance. D5's renormalisation handles them:
   their inapplicable criteria null out and the coverage badge shows it.
   Publishing `source_family` to Stage 1 would let D5 renormalise deliberately
   rather than incidentally, and is still open.
3. Any `MLScorer`. The protocol exists so it can be added without touching this
   one.

---

## 9. Open items raised by the verification

1. **Cross-year comparison must be blocked in SP6** (§7.4). The composite is
   only meaningful within one `as_of_year`.
2. **SP6 must filter on `coverage_ratio`, not just display it** (§7.5).
3. **`min_component_coverage` sits on `capital_allocation`'s FY2024 median**
   (§7.3). Revisit with its own measurement; do not tune it opportunistically.
4. **Root-causing the `cogsq` residual is now the highest-value open item.** It
   is what empties `profitability_moat` at FY2024, which in turn is what makes
   the headline year both narrower (§1.2) and more generous (§7.4).
5. **`source_family` is still unpublished at Stage 1**, so `ScorerInput` carries
   `None`. D5's sector renormalisation remains incidental rather than
   deliberate.
