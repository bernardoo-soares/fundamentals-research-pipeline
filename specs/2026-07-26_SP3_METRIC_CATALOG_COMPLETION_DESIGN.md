# SP3 Completion — Remaining Metric Catalog

Status: **IMPLEMENTED** — 2026-07-26. Part 1 (gross-profit family, 5 metrics) in
PR #12; Part 2 (5 remaining trend metrics) on branch
`feature/sp3-trend-metrics`. **SP3 is complete apart from the three
price-dependent metrics, which are SP5 work by dependency (§1.3).**

**Real-corpus verification of Part 2 (2026-07-26 rebuild).** Measured, not
expected:

*Warehouse.* `metrics_trend` 46,773 → **67,853** rows, 10 → **15** metrics.
Combined with Part 1, SP3 took the two Stage 2 tables from 18 metrics to **28**.

| metric | rows | values | mixed_era_window | insufficient_history | missing_input | negative_base |
|---|---|---|---|---|---|---|
| `negative_equity_strong_earnings` | 4,216 | 4,184 | — | 28 | 4 | — |
| `capex_pct_net_income_avg10y` | 4,216 | 3,318 | 649 | 36 | — | 213 |
| `receivables_pct_sales_trend_10y` | 4,216 | 3,461 | 665 | 90 | — | — |
| `inventory_earnings_correspondence_10y` | 4,216 | 4,099 | — | 117 | — | — |
| `goodwill_trend` | 4,216 | 3,418 | 654 | 144 | — | — |

The two unguarded metrics show **zero** `mixed_era_window`, and the three guarded
ones show 649–665: the guard fires exactly where declared and nowhere else.
`capex_pct`'s 213 `negative_base` are windows whose cumulative net income is
negative — correctly refused rather than reported as a signed percentage.

*Goldens, read back from the rebuilt warehouse (not fixtures):*
`AZO` FY2022 `negative_equity_strong_earnings` = **1.0** (equity −3,538.9 with 10
of 10 profitable years); `KO` FY2022 `capex_pct_net_income_avg10y` =
**0.257778** = 18,875 / 73,222, just above the spec's "< 25% great" anchor and
well inside "< 50% good" — the expected shape for a low-capital-intensity brand.

*Real-world cohort check.* 23 companies carry
`negative_equity_strong_earnings = 1` at FY2022: AON, AZO, CAH, DPZ, FICO, FTNT,
HCA, HLT, HPQ, LII, LOW, MAS, MCD, MCK, MO, MSCI, MTCH, ORLY, PM, SBUX, TDG,
VRSN, YUM. That is a recognisable roster of sustained-buyback franchises with
negative book equity, which is the cohort the book's special case describes —
independent evidence that the conjunction identifies the intended companies
rather than distressed ones.

*`goodwill_trend` is legacy-only in effect, as designed.* Windows ending
2006–2022: 3,308 values of 3,425 rows (97%). Windows ending 2023+: **110 of 791
(14%)** — and those 110 are correct, not leakage: era resolution serves FY2023
from legacy for many tickers, so those windows are genuinely legacy-pure.

*Invariants.* 0 `inf`/`NaN`, 0 value-XOR-reason violations across 67,853 rows.

*Gate.* 301 tests pass (286 at branch point, +15), `ruff` and `compileall` clean.

**Real-corpus verification of Part 1 (2026-07-26 rebuild).** Measured, not
expected:

*Warehouse.* `metrics_quarterly` 303,228 → **437,996** rows, 9 → 13 metrics.
`metrics_trend` 42,557 → **46,773** rows, 9 → 10 metrics.

*The four new quarterly metrics, all legacy-restricted:*

| metric | rows | values | era_not_supported | mixed_era_window | missing_input | negative_base |
|---|---|---|---|---|---|---|
| `gross_margin` | 33,692 | 25,567 | 1,574 | 883 | 5,668 | 0 |
| `sga_pct_gross_profit` | 33,692 | 20,436 | 1,464 | 790 | 10,741 | 261 |
| `dep_pct_gross_profit` | 33,692 | 25,176 | 1,568 | 883 | 5,668 | 397 |
| `rd_pct_gross_profit` | 33,692 | 10,746 | 669 | 358 | 21,800 | 119 |

`rd_pct_gross_profit`'s large `missing_input` is expected and correct: `xrdq` is
populated for only 3,264 of 7,665 legacy annual rows because most companies
report no R&D line. Null with a reason, never zero (S4.2).

*The era restriction bites, exactly as designed.* `gross_margin` by era:
**legacy 25,567 values of 30,660 rows; SimFin 0 values of 3,032 rows.** Not one
SimFin-era row carries a gross-profit value.

*`metrics_trend` gains its first `mixed_era_window` rows in the project's
history* — the flag had never fired on real data. `gross_margin_ge40_years_10y`:
3,113 values, **617 `mixed_era_window`**, 486 `insufficient_history`.

*Golden values, read back from the rebuilt warehouse (not from a fixture):*
KO 2021Q4 `gross_margin` = **0.602716**, exactly Coca-Cola's published FY2021
gross margin; `dep_pct_gross_profit` = **0.062323**, reproducing the platform
spec's own book anchor ("KO ≈ 6%"); `sga_pct_gross_profit` = 0.513520.

*Invariants.* 0 `inf`/`NaN` and 0 value-XOR-reason violations in both tables; 0
quality flags on a null.

*Gate.* 286 tests pass (269 at branch point, +17), `ruff` and `compileall` clean.

Closes the Stage 2 metrics engine (SP3) by building every catalogued metric that
is computable without price data. Platform spec §6.2 is the catalog; §6.5 records
what was built in PRs #5 and #8.

Prime Directive: **no false numbers.** Every rate and step quoted here was
measured on the real corpus; none is inherited or expected.

---

## 1. Gap analysis (measured against the registries)

Built: **18** — 9 trend (`revenue_cagr_2y/4y/10y`,
`retained_earnings_cagr_10y`, `eps_up_year_fraction_10y`,
`net_income_up_year_fraction_10y`, `net_margin_ge20_years_10y`,
`buyback_years_10y`, `dividend_payer_years_10y`) and 9 quarterly (`net_margin`,
`roa`, `roe`, `debt_to_equity_adj`, `current_ratio`, `st_lt_debt_ratio`,
`lt_debt_payback_years`, `interest_pct_operating_income`,
`treasury_stock_present`).

### 1.1 To build — 10 metrics

| metric | grain | inputs | era treatment |
|---|---|---|---|
| `gross_margin` | quarterly TTM | `saleq`, `cogsq`, `dpq` | legacy only |
| `sga_pct_gross_profit` | quarterly TTM | `xsgaq`, `saleq`, `cogsq`, `dpq` | legacy only |
| `rd_pct_gross_profit` | quarterly TTM | `xrdq`, `saleq`, `cogsq`, `dpq` | legacy only |
| `dep_pct_gross_profit` | quarterly TTM | `dpq`, `saleq`, `cogsq` | legacy only |
| `gross_margin_ge40_years_10y` | trend 10y | `saleq_annual`, `cogsq_annual`, `dpq_annual` | `requires_single_era` |
| `negative_equity_strong_earnings` | trend 10y | `ceqq_q4`, `niq_annual` | none needed |
| `capex_pct_net_income_avg10y` | trend 10y | `capxy_annual`, `niq_annual` | `requires_single_era` |
| `receivables_pct_sales_trend_10y` | trend 10y | `rectq_q4`, `saleq_annual` | `requires_single_era` |
| `inventory_earnings_correspondence_10y` | trend 10y | `invtq_q4`, `niq_annual` | none needed |
| `goodwill_trend` | trend 10y | `gdwlq_q4` | `requires_single_era` |

### 1.2 Already satisfied — catalog reconciliation

- **`eps_annual`** (`Σ quarterly epspxq`) is not a derived metric: it is the
  published `epspxq_annual` column on `fundamentals_annual`. Building a metric
  that restates a stored column would duplicate a rule (S2.6). Recorded as
  satisfied at the annual layer.
- **`net_margin` "annual & TTM"** — the TTM form ships (PR #8). See §5.1 for why
  no separate annual-point grain is introduced.

### 1.3 Blocked on SP5 — 3 metrics

`market_cap`, `pe_ttm`, `earnings_yield` all require `close_latest` from a
`prices_daily` table that does not exist. They are catalogued as
"price-dependent; computed at query time" and cannot be built here. **SP3 is
complete except for these three, which are SP5 work by dependency, not deferred
by choice.**

---

## 2. ROOT CAUSE FOUND: Compustat `cogsq` and `xsgaq` are pre-depreciation

**The catalog's `gross_margin` formula is wrong for the legacy era, and building
it as specified would have shipped false numbers for 92% of the corpus.** Found
while constructing the golden test for this slice.

### 2.1 The measurement

Compustat's own income-statement identity, tested on **9,035 legacy quarters
across 176 tickers** (2006–2022), agreement within 0.5% of revenue:

| identity | holds |
|---|---|
| `xoprq == cogsq + xsgaq` | **99.69%** |
| `saleq − xoprq == oibdpq` (operating income **before** D&A) | **99.59%** |

So Compustat's structure is `saleq − (cogsq + xsgaq) = oibdpq`, and
`oibdpq − dpq = oiadpq`. **`cogsq` and `xsgaq` are both stated before
depreciation; `dpq` is subtracted separately downstream.** Compustat's `cogsq` is
therefore not the COGS line a filing reports.

Confirmed independently against published filings — revenue matches exactly for
all five, while `cogsq` is far below published COGS and `cogsq + dpq` closes it:

| ticker | FY | `cogsq` gap vs published COGS | `cogsq + dpq` gap |
|---|---|---|---|
| AAPL | 2022 | −11,104 | **0** |
| KO | 2021 | −1,452 | **0** |
| PG | 2021 | −2,951 | −216 |
| MMM | 2021 | −2,069 | −154 |
| JNJ | 2021 | −7,525 | −135 |

The naive formula `(saleq − cogsq) / saleq` computes a **pre-depreciation** gross
margin, overstating the published figure by a **median 4.09pp, p90 12.58pp**
(n=9,003 legacy quarters) — against a book threshold of >40%.

### 2.2 This root-causes the `cogsq` cross-era divergence

The `cogsq` declaration has recorded since 2026-07-24 that the D&A explanation is
"PLAUSIBLE BUT UNCONFIRMED", because testing it needed SimFin's D&A column, which
is ~40% populated and gave an inconclusive n=89. **Testing it from the Compustat
side instead sidesteps that entirely**, and the identity above confirms it at
n=9,035.

It also explains the previously unexplained direction of that divergence — "legacy
gross margin is systematically HIGHER by a median +2.45pp (80.6% of companies)" —
because legacy COGS omits D&A while SimFin's Cost of Revenue includes it.

Correcting the formula substantially closes the cross-era gap (FY2023 same-year,
353 dual-provider tickers, against SimFin gross margin):

| legacy variant | n | median step | median rel | agree@1% | flip@0.40 |
|---|---|---|---|---|---|
| `(saleq − cogsq)/saleq` (catalog) | 309 | 0.0350 | 0.0738 | 0.100 | 0.149 |
| `(saleq − cogsq − dpq)/saleq` (**corrected**) | 298 | **0.0138** | **0.0376** | **0.386** | 0.128 |

Agreement at 1% improves 3.9× and the median step halves. A residual remains
(0.386 against a 0.90 threshold), consistent with `dpq` including D&A allocated
to SG&A rather than COGS, so the divergence is **substantially but not fully**
explained.

> **SUPERSEDED 2026-07-28 — see §2.2.1.** That last clause was a hypothesis,
> never a measurement, and it turned out to be about a third of the story. It is
> retained above as written so the record shows what was believed and when.

### 2.2.1 The residual, root-caused (2026-07-28)

Solve per company for the share of total D&A the **filer** placed inside cost of
revenue:

```
a = (Cost of Revenue_simfin − cogsq_legacy) / dpq_legacy
```

Measured on FY2023, n=227 with `dpq ≥ 2%` of revenue so that `a` is well
determined. **`a` is trimodal, not a constant:**

| group | share | meaning |
|---|---|---|
| `a ≥ 0.95` | **34.4%** | filer folds all D&A into COGS |
| `a ≤ 0.05` | **26.4%** | filer shows D&A entirely outside COGS |
| between | **32.6%** | filer splits it |

The poles are exact accounting identities, not estimates:

| ticker | FY2023 | `a` | evidence |
|---|---|---|---|
| AAPL | 214,137 = 202,618 + 11,519 | **1.000** | 214,137 *is* Apple's published total cost of sales; gross margin 44.13% is the published figure |
| KO, AMZN | — | **1.000** | exact |
| DIS | 59,201 = 59,201, `dpq` 5,369 outside | **0.000** | both providers carry the same line; Disney labels it *"exclusive of depreciation and amortization"* |
| CMCSA | 36,761 vs `cogsq` 83,922 | **−3.29** | SimFin holds Comcast's *"Programming and production"*; Compustat also absorbs *"Other operating and administrative"* |

So **SimFin preserves each filer's presentation; Compustat normalises D&A out of
every one.** `a` is a property of the filing and is **not recoverable from
Compustat alone**. A third cause appears for filers with no gross-profit line
(`a < 0`): the providers synthesise *different cost-of-revenue scopes*, and for
those companies gross margin is not a published quantity at all.

**What this costs the shipped formula.** `saleq − cogsq − dpq` assumes `a = 1`
universally. Against the published (SimFin) gross margin:

| group | n | median error | agreement@1% |
|---|---|---|---|
| `a ≥ 0.95` | 93 | **+0.0000** | 0.860 |
| `0.05 < a < 0.95` | 74 | −0.0199 | 0.162 |
| `a ≤ 0.05` | 60 | **−0.1346** | **0.000** |

On the book's own **>40%** test the shipped formula flips the verdict for
**11.8%** of companies overall and **33.3%** of the `a ≤ 0.05` group. The naive
formula is no better overall (12.5%) — it is simply wrong on the opposite group.
**Neither formula is universally correct**, because the truth is per-filer and
the legacy provider does not carry it. The golden tests that validated the
correction (KO, AAPL) are both `a = 1.000` companies, i.e. drawn from exactly
the group where the formula is exact.

### 2.2.2 The consequence: the family may be restricted to the wrong era

The gross-profit family is currently **legacy-only**. But the measurement above
says the published gross margin is computable *exactly* in the **SimFin** era —
`(Revenue − Cost of Revenue)/Revenue` is the as-reported figure, correct for
every filer regardless of `a` — and is **not** exactly computable in the legacy
era for anyone whose `a ≠ 1`.

SimFin-era coverage supports it: **FY2024 has `cogsq` on 336 of 389 tickers
(86.4%)**, median gross margin 0.4732, 60.1% above the 40% line.

That is the same 30%-weight `profitability_moat` component SP4 measured as empty
at FY2024 (spec `2026-07-26_SP4_BUFFETT_SCORER_DESIGN` §1). **Not acted on here
— reversing a shipped era restriction changes published numbers and is its own
slice**, with an open question this measurement does not settle: whether a
synthesised gross margin should be published at all for the `a < 0` filers who
report no gross-profit line.

### 2.3 The corrected formula, validated three ways on KO FY2021

```
gross_profit_ttm = saleq_ttm − cogsq_ttm − dpq_ttm
                 = 38,655 − 13,905 − 1,452 = 23,298
```

1. **23,298 is exactly Coca-Cola's published FY2021 gross profit.**
2. `gross_margin` = 23,298 / 38,655 = **0.602716**, exactly the published ratio.
   The naive formula gives 0.640279 — overstated by 3.76pp.
3. `dep_pct_gross_profit` = 1,452 / 23,298 = **0.0623**, matching the platform
   spec's own book anchor for this metric, "low is better (KO ≈ 6%)".

That third check is the strongest available evidence: the book anchor recorded in
the catalog is only reproducible with the corrected denominator, which means the
catalog's *anchor* and the catalog's *formula* disagreed with each other.

### 2.4 Consequences adopted in this design

1. `gross_profit` is defined as `saleq − cogsq − dpq` (§5.2), not `saleq − cogsq`.
2. **The formula is era-specific**, since SimFin's `Cost of Revenue` already
   includes D&A. That is now the primary justification for the legacy-era
   restriction on all four metrics: not merely that the eras disagree, but that
   the correct arithmetic differs per era. Running one formula across both would
   be exactly the semantic mixing S4.3 forbids.
3. **Disclosed residual bias.** `dpq` is total D&A, including the part belonging
   to SG&A, so subtracting all of it slightly over-subtracts and biases
   `gross_margin` **down** by a measured 0.14–0.44pp (PG 216, MMM 154, JNJ 135
   against revenue; exact for AAPL and KO). The bias is conservative — it
   understates margin, so it cannot manufacture a false >40% pass — and is 10–30×
   smaller than the 4.09pp error it replaces. Recorded on the metric.
4. `sga_pct_gross_profit` carries a second, smaller bias in the same direction:
   `xsgaq` is also pre-depreciation, so it understates published SG&A (KO FY2021
   11,964 against a published 12,144, a 1.5% shortfall).

---

## 3. Era treatment, decided by measurement

The FY2023 overlap window carries both providers for the same companies, so
computing each metric twice — once from each provider's staged frame, annualized
identically — **isolates the provider effect from real business change**. This is
strictly better than the 2022→2023 step used in PR #9, which confounds the two.
Both were measured; the same-year figures govern.

Same-year FY2023, 353 dual-provider tickers, all four quarters required per
provider:

| metric | n | median step | p90 step | median rel | agree@1% | book-threshold flip |
|---|---|---|---|---|---|---|
| `gross_margin` | 309 | **0.0350** | 0.1935 | 0.0738 | 0.100 | **14.9% cross 0.40** |
| `sga_pct_gross_profit` | 274 | **0.0687** | 0.2665 | 0.1633 | 0.066 | — |
| `rd_pct_gross_profit` | 118 | 0.0117 | 0.0469 | 0.0724 | 0.051 | — |
| `dep_pct_gross_profit` | 292 | 0.0100 | 0.0965 | 0.0962 | 0.068 | — |
| `receivables_pct_sales` | 299 | 0.0025 | 0.0662 | 0.0214 | 0.452 | — |

(The confounded 2022→2023 step for the same metrics: 0.0382, 0.0764, 0.0195,
0.0134, 0.0135 — close enough to the isolated figures to show the provider
effect, not business change, dominates.)

Input-field verdicts from the FY2023 cross-era audit:

| field | verdict | rate | median rel |
|---|---|---|---|
| `cogsq` | `divergent_declared` | 0.143 | 0.0752 |
| `xsgaq` | CONTRADICTION | 0.288 | 0.1273 |
| `xrdq` | CONTRADICTION | 0.860 | 0.0000 |
| `dpq` | CONTRADICTION | 0.782 | 0.0000 |
| `rectq` | CONTRADICTION | 0.566 | 0.0000 |
| `capxy` | CONTRADICTION | 0.551 | 0.0034 |
| `invtq` | `agree` | 0.901 | 0.0000 |
| `ceqq` | `agree` | 0.964 | 0.0000 |
| `gdwlq` | `insufficient_overlap` | n/a | n/a |

### 3.1 The gross-profit family is restricted to the legacy era

`gross_margin`'s 14.9% threshold-flip **independently re-confirms** the 13.6%
figure measured 2026-07-24 and recorded on the `cogsq` declaration, now at the annualized grain. The platform spec's directive is explicit: "Any gross-margin
metric must be restricted to a single era or dropped; it must NOT be computed
across the 2022/2023 boundary."

`gross_profit = saleq − cogsq` carries `cogsq`'s divergence into the denominator
of all four point metrics, so **all four take the legacy-era restriction**,
exactly as `interest_pct_operating_income` did when both its legs diverged.
`sga_pct_gross_profit` is the worst of them — median step 6.87pp, median relative
16.3%, only 6.6% of companies agreeing within 1% — because `xsgaq` (0.288) and
`cogsq` compound.

**This is a real capability loss and must not be understated.** Gross margin
> 40% is a headline Buffett criterion, and restricting it to the legacy era means
it is unavailable for FY2023 onward — the years a user actually screens on. The
honest alternative is not to relax the restriction but to root-cause `cogsq`;
that is the single highest-value remaining Stage 1 investigation, and it now
gates four shipped metrics rather than zero.

### 3.2 Where no restriction is needed

`negative_equity_strong_earnings` (`ceqq` 0.964, `niq` 0.949) and
`inventory_earnings_correspondence_10y` (`invtq` 0.901 at median 0.0000, `niq`
0.949) rest on fields the audit judges `agree` with an exact median. They follow
the `net_margin_ge20_years_10y` precedent: no era guard.

### 3.3 `requires_single_era` becomes live for the first time

`TrendMetric.requires_single_era` and `windows.require_single_era` have existed
since PR #5 but **no registry entry sets the flag** — `metrics_trend` contains
zero `mixed_era_window` rows today, and the enforcement path has never run on
real data. Four of the new trend metrics set it.

A useful consequence: a 10-year window cannot be SimFin-pure until 2032 (SimFin
begins 2023), so at the 10-year grain `requires_single_era` **is** a legacy-only
restriction for the foreseeable corpus. No separate trend-grain
`supported_eras` mechanism is therefore needed, and none is built — adding one
would be speculative generality (S2).

### 3.4 An inconsistency found in shipped metrics — recorded, not silently changed

Three **already-shipped** trend metrics sit on non-equivalent or contradicted
fields without an era guard:

| metric | field | field verdict |
|---|---|---|
| `eps_up_year_fraction_10y` | `epspxq` | `divergent_declared` (0.717) |
| `buyback_years_10y` | `prstkcy` | `divergent_declared` (0.201) |
| `dividend_payer_years_10y` | `dvy` | `agree` (0.929) — fine |

Both `eps_up_year_fraction_10y` and `buyback_years_10y` instead carry a long
measured caveat in their formula string, which is PR #5-era practice from before
the era machinery existed. That is weaker than a guard: the caveat informs a
reader, the guard nulls the row.

**Not changed here.** Adding guards would null values already in the warehouse
and requires its own version bump, coverage measurement and verification. It is
recorded as the top SP3 follow-up rather than folded into this slice, so the
change stays reviewable and the coverage loss stays attributable. Flagging it is
required by S4.7; fixing it silently is not permitted.

---

## 4. Metric definitions the catalog underspecifies

The catalog states these three loosely. Each is pinned here as an exact
deterministic rule, since "trend of" and "YoY changes" are not formulas.

1. **`receivables_pct_sales_trend_10y`** — catalog: "trend of `rectq_q4 /
   saleq_annual` (down = good)". Defined as the **ordinary-least-squares slope
   per year** of that ratio over the window's present years, requiring ≥ 8 of 10
   and ≥ 2 distinct years. Negative = receivables shrinking relative to sales =
   good. OLS rather than last-minus-first because the latter is decided by two
   points and inverts on a single outlier year.
2. **`inventory_earnings_correspondence_10y`** — catalog: "fraction of window
   years where inventory YoY and `niq_annual` YoY move the same direction".
   Defined over **consecutive present year-pairs** (same pairing rule as
   `up_year_fraction_metric`), counting a pair when `sign(Δinvtq) ==
   sign(Δniq)`, with a zero change on either side counting as **not**
   corresponding — a flat series must not read as agreement.
3. **`goodwill_trend`** — catalog: "YoY changes in `gdwlq_q4`", which is a series,
   not a value. Defined as the **fraction of consecutive present year-pairs in
   which goodwill increased**, reusing `up_year_fraction_metric`. Answers "how
   often does this company add goodwill", i.e. serial acquisitiveness, which is
   the book's concern. `gdwlq` is 0/758 populated in the SimFin era (measured),
   so this is legacy-only in fact as well as by declaration.

---

## 5. Design

### 5.1 Grain: no third table

The catalog says `gross_margin` "(annual & TTM)" and states the gross-profit
ratios over `_annual` inputs. All four ship at the **quarterly TTM grain only**,
in `metrics_quarterly`, alongside `net_margin` / `roa` / `roe`.

Rationale: TTM is the more current form of the same quantity and is what a screen
should read; `metrics_quarterly` already carries the TTM machinery and per-field
era purity; and an annual-point grain would need a third table or an abuse of
`metrics_trend` (which is keyed by `as_of_year` for *windowed* values). Adding a
grain to restate TTM at lower frequency is duplication (S2.6). Recorded here as
an explicit deviation from the catalog's wording rather than a silent one.

### 5.2 One definition of gross profit (`metrics/quarterly.py`)

Four metrics need `saleq_ttm − cogsq_ttm`. It is defined once (S2.6), using the corrected arithmetic established in §2:

```python
GROSS_PROFIT_REVENUE_FIELD = "saleq"
GROSS_PROFIT_COST_FIELD = "cogsq"

def ttm_gross_profit(prepared: pd.DataFrame) -> dict[int, TtmResult]:
    """TTM gross profit = saleq_ttm - cogsq_ttm, propagating era-mixing.

    Mixed when either leg is mixed: cogsq is eras_equivalent=False, so any
    four-quarter window spanning the provider boundary is impure.
    """

def gross_margin_metric() -> ComputeFn:      # gross_profit / saleq_ttm
def ttm_over_gross_profit(field: str) -> ComputeFn:   # field_ttm / gross_profit
```

`ttm_over_gross_profit` serves `sga_pct`, `rd_pct` and `dep_pct` — one
combinator, three declarative registry entries, no dispatcher.

Null policy, inherited from `_denominator_reason`: gross profit of exactly 0 →
`zero_denominator`; negative gross profit → `negative_base`. A negative gross
profit is real (a company selling below cost) but makes the ratio meaningless, so
it is reasoned-null rather than reported.

### 5.3 New trend combinators (`metrics/windows.py`)

```python
def difference(a: str, b: str) -> SeriesFn:            # a - b per year
def sum_ratio_metric(num, den, n, min_present) -> ComputeFn   # Σnum / Σden
def slope_metric(series_fn, n) -> ComputeFn                    # OLS slope/year
def direction_correspondence_metric(a, b, n) -> ComputeFn      # sign agreement
def conjunction_metric(...) -> ComputeFn                       # negative_equity
```

`sum_ratio_metric` implements the catalog's "over window years where both present
(≥ 8 required)" for `capex_pct_net_income_avg10y`: it sums only years where
**both** legs are present, and requires 8, distinct from the 0.8·n floor the
other combinators use.

### 5.4 Determinism

Every new combinator sorts by year before computing, uses only the two endpoint
or windowed values, and takes no clock or randomness. `slope_metric` uses a
closed-form OLS on integer years, so it is float-deterministic given a fixed
input order (S3.3).

---

## 6. Verification plan

1. **Golden tests with hand-verified values (S4.4).** At least one per new
   metric, computed from real published figures with the derivation written into
   the test. Synthetic fixtures test mechanics only and are not called golden.
2. **Real-corpus rebuild**: row counts, coverage, and reason-code distribution
   before and after; every new metric's null reasons must be attributable.
3. **The era restriction must demonstrably bite**: `gross_margin` must be
   `era_not_supported` on SimFin-era rows and non-null on legacy rows, and
   `metrics_trend` must gain its first `mixed_era_window` rows.
4. **Invariants**: 0 `inf`/`NaN`, 0 value-XOR-reason violations, 0 quality flags
   on a null.

## 7. Out of scope

1. Era guards on the three shipped metrics in §2.4 — recorded as the top
   follow-up.
2. Root-causing `cogsq` — now gating four metrics; the highest-value remaining
   Stage 1 investigation.
3. `market_cap` / `pe_ttm` / `earnings_yield` — SP5 by dependency (§1.3).
4. A "not cross-era comparable" quality flag as an alternative to era
   restriction. It would let a SimFin-era `gross_margin` ship annotated rather
   than nulled, which may be the better long-term answer for a headline
   criterion, but it is a third era concept alongside `mixed_era_window` and
   `era_not_supported` and needs its own design.
