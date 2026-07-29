# SP6 — research console: design and UX analysis

Status: **slice 1 delivered 2026-07-29.** Supersedes platform spec §8 where
noted; §8's page inventory is retained, its *presentation* assumptions are not.

Run it with `pip install -e .[ui]` then `python -m streamlit run app/main.py`.

## 1. What the data forces

The design was derived from the warehouse, not from a template. Six
measurements taken 2026-07-29 on FY2024 (384 scored tickers) decided almost
every choice below.

| # | Measurement | What it forces |
|---|---|---|
| M1 | **Every single FY2024 row carries a badge.** `unreliable_input` 96.6%, `era_limited` 96.1% | A badge-as-warning UI is dead on arrival. Universal warnings train the eye to skip them |
| M2 | **COIN ranks #3 at 92.12 on coverage 0.273**; META #6 at 89.75 on 0.391 | Coverage cannot be a column the user might sort by. It has to be structural |
| M3 | Coverage ≥1.0: **28 tickers**. ≥0.9: **135**. ≥0.7: **310** | The honest ranking is ~135 names, not 384. The default view must say so |
| M4 | Mean composite drifts **56.8 (FY2020) → 64.6 (FY2024)** while mean coverage falls 0.87 → 0.81 | Companies did not improve; the harder criteria stopped being measurable. Cross-year composite comparison must be blocked, not merely discouraged |
| M5 | Four trend metrics are effectively dead in FY2024: `gross_margin_ge40` 6/344, `receivables_pct_sales_trend` 6/344, `goodwill_trend` 6/344, `capex_pct_net_income_avg10y` 4/344 | Never render an empty chart frame. An empty axis reads as a bug, not as "the source stopped providing this" |
| M6 | **No sector and no company name exist anywhere in the data.** `universe_current.csv` is `(as_of_date, year, ticker)` | Platform spec §8.1's "name, sector" columns and sector filter are **not buildable**. Not invented — reported |

### 1.1 The central problem

M1 and M2 together say the real problem is not "show a ranking". It is that
**the ranking lies unless the strength of its evidence is visible in the same
glance**. COIN is third on twenty-seven percent of the evidence. In a
conventional leaderboard the single most important fact about row 3 is
invisible, or worse, is a grey chip at the right edge that looks exactly like
the grey chip on all 383 other rows.

So the design's organising idea:

> **Confidence is a visual property of the score itself, never a separate
> column.**

## 2. Direction: "Assay"

The subject's world is verification — hallmarks, assay marks, tolerance bands,
audit opinions. This project's Prime Directive is *no false numbers*; its
defining act is measuring rather than assuming. The design takes its identity
from that, not from finance-dashboard convention.

### 2.1 Palette

Cool porcelain rather than the warm cream that dense financial tables read
badly on, graphite ink, and **one struck-gold accent that is rule-bound**.

| Token | Hex | Job |
|---|---|---|
| `--paper` | `#F2F4F6` | cool porcelain ground — deliberately not cream |
| `--panel` | `#FFFFFF` | raised surfaces |
| `--rule` | `#D6DBE0` | hairlines; the only divider device |
| `--ink` | `#171A1F` | primary text |
| `--pewter` | `#737C88` | **unmeasured**, secondary, absent |
| `--assay` | `#A67C00` | **measured and verified** |
| `--oxide` | `#A6392F` | checklist fail |

**The rule that makes it a system, not decoration: gold means measured.**
Nothing unverified is ever rendered in gold. Pewter is not "a muted grey for
less important things" — it means *this number is not backed by evidence*. A
reader who learns one thing about this interface learns that.

### 2.2 Type

Mono-forward, because digit alignment carries meaning here: these are columns
of figures a person compares down the page, and tabular figures are a
correctness feature, not a style. All data, all eyebrow labels and the display
numerals are monospace; prose is a humanist sans.

System stacks only — no webfont. A local research instrument must not change
appearance when the network is down.

- Display / data: `Cascadia Mono`, `SF Mono`, `JetBrains Mono`, `Consolas`
- Prose: `Segoe UI Variable Text`, `Inter`, system sans
- Scale: 11 / 12 / 13 / 15 / 22 / 44, tight tracking on the large sizes

### 2.3 Signature: the evidence bar

One element carries the whole thesis, and everything else stays quiet.

```
NVDA   ████████████████████░░░  94.4        coverage 0.90, 15/17 checklist
CPRT   ████████████████░░░░░░░  92.7        coverage 0.75
COIN   ██████░░░░░░░░░░░░░░░░░  92.1        coverage 0.27   <- reads hollow
LRCX   █████████████████████░░  89.8        coverage 0.95
ZTS    ██████████████████████░  89.0        coverage 1.00
```

- Bar **length** = composite score.
- **Solid gold** portion = `coverage_ratio × composite` — the part backed by
  measured criteria.
- **Pewter remainder** = the part that is inference from an incomplete
  scorecard.

A high score on thin evidence looks visibly hollow next to a slightly lower
score that is solid. The eye sorts by *gold length*, which is the correct
ranking heuristic, without the user being told to do anything.

This is why M1's badges are demoted: the thing they were meant to warn about is
now in the geometry.

### 2.4 What was rejected

- **A red/amber/green risk chip per row.** M1 makes it uniform, and traffic
  lights imply a verdict the data cannot support.
- **A dark "terminal" ground.** Legible, but a default; and 384-row tables of
  figures read better on light.
- **Sparklines in the ranking table.** M5 means several would be empty, and an
  empty sparkline is indistinguishable from a flat one.
- **A sector filter.** M6: the data does not exist. Building it would require
  inventing sector labels.

## 3. Constraints the UI must enforce

These are not preferences. Each traces to a measured defect.

| # | Constraint | Source |
|---|---|---|
| C1 | **Cross-year composite comparison is blocked.** One `as_of_year` at a time; no multi-year composite chart, no "vs last year" delta | M4, and the SP4 finding that FY2024 is inflated ~+5.13 by an excluded moat criterion |
| C2 | **Coverage filters, it does not merely display.** The ranking has a minimum-coverage control that defaults to a level excluding the M2 cases | M2, M3 |
| C3 | **Every flag on a row reaches the surface**, including `eps_basis_unverified`, `cross_era_window`, `da_allocation_assumed`, `tstk_unavailable` | Standing directive |
| C4 | **Nulls are gapped, never interpolated or zero-filled**, and carry their reason code in plain words | S4.2, S4.5 |
| C5 | **The UI computes nothing.** Every number is SELECTed; no arithmetic in a view | Platform spec §7.2 |
| C6 | **A metric with no data renders as a stated absence**, never an empty chart | M5 |

## 4. Architecture

```
warehouse/queries.py     SELECT-only query API; returns frames. The only
                         module the app may read the database through.
app/theme.py             the token system and CSS, in one place
app/components.py        evidence bar, criterion ledger, flag list
app/pages/               ranking, company, data health
app/main.py              thin router
```

`queries.py` opens the warehouse **read-only** and contains no arithmetic
beyond what SQL aggregates for display grouping. This keeps C5 structural
rather than a convention someone could forget, and it means the app is
testable without Streamlit.

## 5. Scope

**In (slice 1)** — the design system; Ranking; Company drilldown; Data health;
the query API; C1–C6 enforced and tested.

**Out, with reasons**

- **Portfolio vs S&P 500 (§8.3).** Needs a `^SPX` benchmark series that does
  not exist yet. That is SP7.
- **Watchlist (§8.5).** Needs `manual_annotations`, the only writable table.
  Deferred so slice 1 can be strictly read-only, which is a much easier
  guarantee to verify.
- **Sector filter and company names (§8.1).** M6 — the data does not exist.

## 6. Verification (2026-07-29)

Rendered against the real warehouse and inspected, not assumed. Four defects
were found by looking at the screen rather than at the code, and fixed:

| Found | Fix |
|---|---|
| The masthead was sliced by Streamlit's fixed toolbar | top padding, and the host chrome hidden |
| 25 bars of saturated gold read as one mustard block — the signature stopped discriminating | bar cut from 15px to 7px; the row breathes and the deficit does the work |
| The pewter deficit was a faint hatch, invisible at the 0.95-vs-1.00 distinction it exists to make | solid pewter plus a hairline seam at the boundary |
| Streamlit's red accent fought the palette on every slider and radio | `.streamlit/config.toml`, which is the supported seam, replacing brittle CSS aimed at BaseWeb internals |
| The component chart silently dropped 2 of 5 axis labels | 42px per category instead of 26px |
| The drilldown's header bar pushed its own score to the page edge | `max-width` on the header bar |
| Long "not measured" explanations overflowed their row | the right-hand ledger cell wraps |
| Dates rendered as `2025-01-31 00:00:00` — a time that was never measured | `datestr()` |
| The same "not charted" sentence repeated four times on the health page | stated once as a lead-in |

Automated checks, in `tests/console/`: 33 tests. Every view renders without
raising; a missing warehouse reports rather than crashes; the read-only
connection provably rejects a write; C1 (single-year picker, banner on every
page), C2 (coverage floor on by default, and the thinly-measured row is held
back until the floor is lowered), C3/C4 (every reason code and quality flag in
the closed vocabularies has plain-language wording — enforced, so a new code
cannot ship unexplained) and the evidence bar's arithmetic including clamping.

Full suite: 469 tests, `ruff` and `compileall` clean.

## 7. Open items

1. **Page ③ Portfolio vs S&P 500** — needs a `^SPX` series. SP7.
2. **Page ⑤ Watchlist** — needs `manual_annotations`, the only writable table.
   Deferred so slice 1 stays strictly read-only.
3. **Company names and sectors** — M6: no such data exists in the warehouse.
   Adding them means adding a source, not a view.
4. **The drilldown's "inputs row"** (platform spec §8.2.2: the raw Stage 1
   values and their fiscal periods behind each metric) is **not yet built**.
   The formula, value, points, verdict, flag and reason are all present; the
   raw operands are not. `queries.annual_fundamentals` exists for it.
