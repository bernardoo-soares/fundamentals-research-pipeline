# Session handoff — 2026-07-29

State of the art after this session. Read this first, then
`specs/2026-07-29_SP6_UI_DESIGN.md` for the console and
`specs/2026-07-29_EPS_SPLIT_BASIS_DESIGN.md` for the data fix.

**Everything is committed and pushed to `main`. 682 tests, `ruff` and
`compileall` clean.**

---

## 1. Where the project is

The pipeline is complete end to end and has a working research console on top
of it. SP1–SP7 are done; the roadmap items that remain are refresh automation
and a genuine external audit.

| Sub-project | State |
|---|---|
| SP1 Stage 1 fundamentals, cross-era resolution | done |
| SP2 warehouse + `fundamentals_annual` | done |
| SP3 metric catalog (20 trend + 23 quarterly) | done |
| SP4 Buffett scoring | done |
| SP5 prices and valuation | done |
| SP6 research console (5 pages) | done |
| SP7 selection vs S&P 500 | done |
| SP8 refresh automation | **not started** |

Run it:

```powershell
python -m streamlit run app/main.py     # http://localhost:8501
```

Full rebuild sequence is in `AGENTS.md` → How To Run.

### Warehouse tables

`fundamentals_quarterly`, `fundamentals_annual`, `metrics_trend`,
`metrics_quarterly`, `scores`, `score_components`, `score_criteria`,
`prices_daily`, `valuation_current`, `valuation_history`, `companies`,
`market_history`, `manual_annotations`, `build_log`.

---

## 2. What this session did

Eight commits, `a6f10df` → `ba767bd`.

### 2.1 A real defect in shipped numbers: EPS split basis (`d7ae569`)

Compustat publishes `epspxq` **as-reported** and never restates it after a
split; it publishes `ajexq`, the cumulative adjustment factor, instead.
Nothing read that factor.

- `epspxq_annual` summed four quarters that could sit on two different bases.
  AAPL FY2020 read **10.97** against a published **3.31**.
- A split registered as a collapse in EPS. The error was **one-directional** —
  a split can only invent a *down* year — and companies split because the
  price compounded, so it systematically penalised serial compounders.
- Measured: **11.1% of tickers** carried a wrong `eps_up_year_fraction_10y`,
  median understatement 0.111, worst 0.444 (AAPL read 0.333 against a true
  0.778). **48 of 441 FY2022 composites moved, every one upward.**

Fixed by dividing the legacy series by `ajexq`, which reproduces published
restated EPS exactly. The SimFin era has no such factor and restates
inconsistently, so it carries `eps_basis_unverified` rather than a guess.

### 2.2 SP6 console (`045a5a8`, `0f6eb7f`, `db29b42`, `3fa59ee`)

Design identity **"Assay"**, whose one rule is **gold means measured**.

The signature is the **evidence bar**: bar length is the composite, the solid
gold portion is `coverage × composite`. It exists because two measurements
made a conventional leaderboard dishonest — every FY2024 row carries a badge
(96.6% `unreliable_input`), and COIN ranks 3rd at 92.1 on **27% coverage**.

Also delivered:
- **The inputs row.** Every criterion opens onto its Stage 1 operands by
  fiscal period, with a `provider` row showing where the legacy→SimFin seam
  falls inside the window.
- **Engine-published operand totals.** 10 of the 23 quarterly metrics exist to
  publish a derived total (`revenue_ttm`, `gross_profit_ttm`, …), plus 5 trend
  intermediates (per-year series, masked window sums). The console never
  re-derives a total in a view.
- **Company names and GICS sectors** (`companies`, 503 rows, 98.0% coverage).

### 2.3 SP7 and the watchlist (`3ac5707`)

Selection vs benchmark, equal-weight buy-and-hold, and `manual_annotations`.

### 2.4 Yahoo Finance for the market layer (`ba767bd`)

Replaced the SPY proxy and the 4.92-year history:

| | Before | After |
|---|---|---|
| Benchmark | SPY (ETF) | **`^GSPC`, the index itself** |
| History | 4.92 years | **26.6 years (2000-01-03 →)** |
| Windows | 1–4 years | **1, 2, 3, 5, 10, 20** |
| Coverage | 476/494 | **493/494** |

No new dependency (`requests`). Cached to disk (317 MB in
`data/raw/vendor/yahoo_cache/`), which is what makes the build reproducible.

---

## 3. Bugs found by *running* the thing, not reading it

Worth internalising — each was invisible in code review.

1. **`requests.Session().headers.setdefault("User-Agent", …)` is a silent
   no-op.** The session already carries `python-requests/x.y.z`, and Yahoo's
   edge answers that agent with **429**. Hours of "rate limiting" were one
   wrong line. Now asserted by a test.
2. **A rebuild would have destroyed every note.** `rebuild_warehouse` builds
   into a temp file and `os.replace`s it. `carry_annotations` now moves
   `manual_annotations` across the swap; a test does a real rebuild and
   asserts the note survives.
3. **Reads were taking a write lock.** `ensure_table` was called from every
   read, so opening the watchlist needed exclusive access and Dropbox holding
   the file produced a traceback.
4. **A linear chart axis lied by omission.** Over 20 years the benchmark's
   +486.9% rendered as a flat line at zero. Log scale by default beyond 3y.
5. **`net_margin_annual` rendered at 1 decimal**, so 0.2411 (clears 0.20) and
   0.1619 (fails) both printed `0.2` — destroying the discrimination the row
   existed to make.
6. **The window filter ran before the as-of look-back**, so the documented
   weekend/holiday tolerance never worked. Dense real prices hid it.
7. **I invented a ticker mismatch that did not exist** — rewrote `.`→`-` for
   class shares when both sides already wrote `BRK.B`, leaving Berkshire
   unnamed. Measure both sides before normalising between them.

---

## 4. Constraints that are real, not TODOs

Do not "fix" these; they are properties of the data.

1. **Cross-year composite comparison is blocked and must stay blocked.** Mean
   composite drifts 56.8 (FY2020) → 64.6 (FY2024) purely because harder
   criteria stopped being measurable.
2. **Coverage is the real axis.** 384 companies scored at any coverage, **135
   at ≥0.90, 28 at 1.00**. The ranking defaults to a 0.70 floor.
3. **Four metrics are structurally dead** in FY2024 (4–6 of 344):
   `capex_pct_net_income_avg10y`, `goodwill_trend`,
   `gross_margin_ge40_years_10y`, `receivables_pct_sales_trend_10y`.
   `capex_pct` does not recover until FY2032.
4. **`companies` is current membership, not point-in-time.** GICS reclassifies;
   the sector shown against FY2015 is today's label. It filters and labels —
   nothing derived keys off it.
5. **10 tickers have no current-membership row** (index departures) and
   **HOLX** has no Yahoo series. Both are named on screen, never guessed.

---

## 5. Where to continue

In the order I would take them.

### 5.1 An external audit — the highest-value thing left

**Every verification so far has checked internal consistency plus spot figures
recalled from memory. Nothing has been reconciled against a primary source.**
Pick 5 companies, open their actual 10-Ks, and reconcile revenue, net income,
EPS, equity and the derived scores line by line. That is the one exercise that
could still invalidate a lot, and it has not been done.

### 5.2 SP8 — refresh automation

Nothing re-runs on a schedule; every rebuild has been manual. Wants: a single
`refresh` command chaining the stages, a diff report (new quarters,
restatements, coverage deltas), and gate results.

### 5.3 Known latent issues, recorded but not fixed

- **Share-count fields carry the same split-basis problem as EPS did.**
  `cshoq`, `cshfdq`, `cshprq` are as-reported and un-normalised. Nothing
  consumes them today (valuation takes shares from `prices_daily`), so it was
  recorded rather than fixed speculatively. **Any future consumer must divide
  by `ajexq` first.**
- **Trend window aggregates beyond the five published.** Only the
  consistency-fraction family and the capex pair publish intermediates.
- **`prstkcy` at 0.201 and `oancfy` at 0.884** cross-era agreement were both
  flagged for review and never revisited.
- **Total-return comparison.** Both `prices_daily` and Yahoo carry the data;
  the console deliberately shows price return only, on both sides.

### 5.4 Smaller

- 18 tickers unpriced in `valuation_history` (SimFin coverage).
- Per-ticker cost-of-revenue scope divergence (the CMCSA class).
- The console has no test that renders against a *fixture* warehouse for the
  Vs-market page; it currently relies on the real one.

---

## 6. Ground rules that keep paying off

From `AGENTS.md`, restated because this session proved each of them:

- **Verify input semantics before writing the transform** (S4.1). Checking
  that Yahoo's `close` is split- but not dividend-adjusted took one query and
  prevented a wrong basis.
- **No imputation, ever** (S4.2). A null `ajexq` nulls the value; it never
  defaults to 1.
- **Report what was measured, never what was expected** (S4.7).
- **Screenshot the app.** Rendering without an exception is not the same as
  rendering correctly; six of the seven bugs above came from looking.
- **Declared inputs are guarded both ways.** `tests/metrics/test_declared_inputs.py`
  runs 130 checks so the audit trail cannot drift from the computation.
