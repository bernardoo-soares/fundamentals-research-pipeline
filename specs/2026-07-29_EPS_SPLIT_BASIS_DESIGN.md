# EPS split basis — design and verification

Status: implemented 2026-07-29. Supersedes the split-silent treatment of
`epspxq` in every prior slice.

## 1. The defect

`epspxq` is basic EPS as-reported. Compustat never restates it after a stock
split or stock dividend; it publishes `ajexq`, the cumulative adjustment factor
by ex-date, so a consumer can put the series onto one basis. Nothing in this
pipeline read that factor.

Two consequences, both live in shipped output:

**Annual levels were not EPS at all.** `epspxq_annual` sums four quarters. When
a split falls mid-year those four quarters sit on two different bases, so the
sum is a quantity with no meaning. Apple's FY2020 read **10.97** against a
published **3.31**.

**Trend direction was inverted at every split.** The year after a split showed
a fall that never happened. Apple FY2020 → FY2021 read 10.97 → 5.67, recorded
as a down year, while Apple's actual basic EPS *rose* from 3.31 to 5.67.

`eps_up_year_fraction_10y` is a shipped SP4 scoring criterion and consumes
exactly this series.

### 1.1 Why the direction of the error is the point

The error is **one-directional**. A split divides EPS and multiplies the share
count, so it can only ever manufacture a *down* year — never an up one.

Companies split their stock because the price compounded. So the defect
systematically penalised serial compounders, which is the precise population a
Buffett screen exists to find. It was not noise around a true value; it was a
bias pointing away from the answer.

Apple scored **0.333** where the truth is **0.778**.

## 2. Measurements (2026-07-29, real corpus)

### 2.1 The factor works

`epspxq / ajexq` reproduces published restated EPS:

| Company | raw annual sum | ÷ `ajexq` | published basic EPS |
|---|---|---|---|
| AAPL FY2019 | 11.94 | 2.9850 | 2.99 |
| AAPL FY2020 | 10.97 | **3.2975** | 3.31 |
| AAPL FY2021 | 5.67 | 5.6700 | 5.67 |
| GOOGL FY2022 | 51.43 | **4.5950** | 4.59 |
| AMZN FY2021 | 65.93 | **3.2965** | 3.30 |
| AMZN FY2022 | −7.45 | **−0.2680** | (0.27) |
| SHW FY2021 | 10.18 | **7.1000** | 7.06 |

Residual differences are quarterly rounding in the source, not method error.

The factor is cumulative and compounds correctly across successive splits:
NVDA runs `ajexq` = 40 through FY2021 Q1 and 10 thereafter — the July-2021 4:1
multiplied by the later June-2024 10:1.

### 2.2 Exposure

| Quantity | Measured |
|---|---|
| Tickers splitting at least once, 2005–2022 | **164 of 464 (35.3%)** |
| Ticker-years whose annual sum straddled two bases | 190 of 7,918 (2.40%) |
| Ticker-years with a corrupted YoY direction | 226 of 7,918 (2.85%) |
| Legacy rows with an EPS but no factor | **0 of 84,230** |

### 2.3 Damage to the shipped metric

Recomputing `eps_up_year_fraction_10y` for FY2022 with and without adjustment,
over the 431 tickers with a complete 10-year window:

| | |
|---|---|
| Tickers whose value changed | **48 (11.1%)** |
| Median signed change | **+0.111** — exactly one spurious down year |
| Worst | **+0.444** (AAPL 0.333 → 0.778) |
| Direction | **every change positive**; the metric could only understate |
| Tickers flipping a ≥0.80 verdict | 7 (1.6%) |

### 2.4 Damage to the Buffett composite

| | |
|---|---|
| Tickers whose FY2022 composite moved | **48 of 441** |
| Median signed movement | **+0.556** |
| Largest | **+2.222** (AAPL 72.74 → 74.96) |
| Direction | **all positive** |

## 3. What was fixed, and what was not

### 3.1 Fixed: the legacy era

`ajexq` is stored as a Stage 1 support field and legacy `epspxq` is divided by
it at Stage 1 (`steps/per_share_basis_normalizer.py`).

This is **not imputation** (S4.2). It reads a factor the provider publishes for
this exact purpose, and it discards nothing: `ajexq` is itself stored, so the
as-reported figure remains recoverable as `epspxq × ajexq`.

`ajexq` is declared in `ADJUSTMENT_FACTOR_FIELDS` and excluded from
`MONETARY_RAW_FIELDS`, so unit normalisation can never scale a ratio. It is
deliberately not annualised: carrying an `ajexq_annual` would invite someone to
apply the factor a second time.

**A null factor nulls the value; it never defaults to 1.** An unknown basis is
not a known-unchanged basis. Measured cost of that policy: zero rows.

### 3.2 Not fixed: the SimFin era

SimFin publishes no adjustment factor, and **restates share counts
inconsistently**. Of 20 splitters checked at the FY2022/FY2023 boundary, 15
agree with the `ajexq`-adjusted legacy basis (APH, AVGO, CMG, COO, CPRT, CTAS,
DECK, LRCX, MNST, NVDA, PCAR, SMCI, TECH, WRB, WSM) and 5 do not (WMT, ODFL,
TPL, SRE, PANW).

So the basis there cannot be verified. It is flagged, not guessed.

### 3.3 Rejected: a heuristic split detector

The obvious fallback is "null any pair whose implied share count steps by more
than X". **Rejected**, because it cannot distinguish a split from
merger-funded share issuance. EQT (1.457), TFC (1.424) and SJM (1.418) all step
past any plausible threshold in FY2024 for exactly that reason, and their EPS
directions are genuine.

A threshold there would trade a measured, exactly-fixable bias for an
unmeasured, unfixable one. Use the provider's own factor where it exists;
disclose where it does not.

## 4. The flag mechanism

`metrics_trend` had no `quality_flag` column, so a trend metric could only
either null a value or publish it silently. Both were wrong for this case: the
value is usually right, and its limitation had nowhere to travel.

Added:

- `ReasonCode.EPS_BASIS_UNVERIFIED` — a per-share window reaching into the
  SimFin era.
- `ReasonCode.CROSS_ERA_WINDOW` — a window crossing the boundary for a field
  whose divergence was measured as mild enough to publish.
- `MetricPoint.quality_flag`, a `quality_flag` column on `metrics_trend`, and
  `windows.flag_mixed_era` — the softer sibling of `require_single_era`, which
  attaches a flag instead of nulling.
- `QUALITY_FLAGS` and `validate_quality_flag` moved from
  `metrics_quarterly_schema` into the shared `metric_reason_codes`, so the two
  Stage 2 grains cannot drift apart (S2.6).
- The scoring loader now reads the trend grain's flag. It previously selected a
  literal `NULL` there, which silently discarded anything the trend layer might
  have said.

`buyback_years_10y` gets `cross_era_window` in the same change. Its
one-directional bias — reading LOW by up to 2 of 10 years for SimFin-served
tickers — was already measured and written in a docstring, where no UI could
see it. That is the standing directive's whole point.

## 5. Version bumps (S3.6)

| Unit | Was | Now |
|---|---|---|
| `eps_up_year_fraction_10y` | 2 | **3** |
| `buyback_years_10y` | 1 | **2** |

## 6. Verification on the real corpus

Full rebuild: Stage 1 (both providers) → era resolution → warehouse → trend and
quarterly metrics → scores → prices → valuation.

| Check | Result |
|---|---|
| AAPL FY2019–22 `epspxq_annual` | 2.985 / 3.2975 / 5.67 / 6.14 against published 2.99 / 3.31 / 5.67 / 6.15 |
| Corrected metric values match the offline prediction | AAPL 0.778, APH 0.778, BF.B 0.556, CNC 0.556, IDXX 0.889, NKE 0.667, CSX 0.667 — all exact |
| Flag precision, FY2023 | **all 107 unflagged rows are single-era windows; all 338 flagged are two-era.** No false positives, no false negatives |
| Flagged rows with a null value | **0** |
| Unknown flags reaching a stored column | **0** |
| Flag reaches `score_criteria` | 675 `eps_basis_unverified`, 654 `cross_era_window` |
| FY2024 tickers carrying the EPS flag | 337 of 384 |
| EPS coverage | legacy 98.8%, SimFin 99.9% — no regression |
| Quality gate | 436 tests, `ruff`, `compileall` all clean |

FY2024 leaderboard after the fix: NVDA 94.4, CPRT 92.7, COIN 92.1, MNST 91.8,
LRCX 89.8, META 89.8, GOOGL 89.7, ZTS 89.0, IDXX 88.9, AMAT 88.6. Six of those
are serial splitters — the population the defect had been suppressing.

## 7. Open items

1. **Share-count fields carry the same basis problem.** `cshoq`, `cshfdq` and
   `cshprq` are as-reported and un-normalised. No metric or valuation path
   consumes them today — valuation takes its shares from `prices_daily`, where
   price and share count are internally consistent — so this is recorded as a
   known latent issue rather than fixed speculatively. Any future consumer of
   those fields must divide by `ajexq` first.
2. **`ajexq` shifts when the extract is refreshed.** It is cumulative to the
   extract's most recent date, so a future split rebases the whole history.
   Direction — which is what the trend metric uses — is invariant to a common
   rescale, but stated *levels* are on "the extract's current basis" and should
   be described that way.
3. **`eps_ttm` was left at version 1.** It now consumes the corrected series
   automatically, and no golden pinned a split-year value, so no golden broke.
   Its own docstring approximation note (intra-year share drift) is unchanged
   and still applies.
