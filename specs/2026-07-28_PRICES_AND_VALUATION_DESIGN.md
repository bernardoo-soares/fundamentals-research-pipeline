# SP5 — Prices and valuation

Status: IMPLEMENTED — 2026-07-28 (`main`). Supersedes D6 and platform spec §9
on the choice of price source.

Ships `prices_daily`, an `eps_ttm` metric, and `valuation_current` carrying
`market_cap`, `pe_ttm` and `earnings_yield`.

---

## 1. The source changed, and why

D6 chose **Stooq** for "free EOD CSV endpoints, no API key". Measured
2026-07-28, **that premise no longer holds**: every Stooq CSV endpoint returns
a JavaScript proof-of-work anti-bot challenge (a SHA-256 grind followed by a
POST to `/__verify`) instead of CSV, on both `stooq.com` and `stooq.pl`, with
and without browser headers. The legacy quote endpoint 404s.

**The challenge was deliberately not circumvented.** It is an access control the
operator put there on purpose; bypassing it would be fragile against a change
they can make at will, and is not a unilateral call.

**SimFin's `us-shareprices-daily` replaces it, and is better here:**

| | Stooq (planned) | SimFin (shipped) |
|---|---|---|
| new dependency | connector + throttling + retry + per-ticker failure isolation | **none** — existing provider, key and cache-first loader |
| requests | ~500 throttled, ≥500 ms apart | **1 bulk download** |
| dividend-adjusted | no (price return only) | **`Adj. Close` + `Dividend`** |
| share counts | none (needed `cshfdq`) | **daily `Shares Outstanding`** |
| history | deep archive | **2020-08-31 only** |

Spec §9's items 2 and 3 (throttling, retry-with-backoff, per-ticker failure
isolation) are **moot**: a single bulk file either downloads or does not.

**The cost is real and disclosed:** history begins 2020-08-31, so valuation
cannot predate FY2020. D7 already fixes FY2024 as the analysis year, and the
`Adj. Close`/`Dividend` columns keep the deferred total-return upgrade open
instead of foreclosing it — a net gain against the plan.

## 2. No ticker aliasing — a trap worth recording

18 of 494 universe tickers have no SimFin price row. The tempting fixes are
**wrong**, and would be catastrophic rather than merely imprecise:

| naive alias | why it is wrong |
|---|---|
| `BRK.B` → `BRK-A` | different share class — would price Class B share counts at Class A's ~$700,000/share, a ~1500× error |
| `GOOGL` → `GOOG` | Class A vs Class C |
| `FOXA` → `FOX`, `NWSA` → `NWS` | likewise distinct classes |

Genuine renames exist (`FISV`→`FI`, `CPAY`←`FLT`, `XYZ`←`SQ`, `RVTY`←`PKI`,
`Q`←`QGEN`), and the rigorous route would be to join on SimFin's own entity id
rather than the symbol — but measured, `us-companies.csv` carries **no
SimFinId** for any of them, while the id join is exact for controls (AAPL, KO,
MSFT). Nothing can be verified, so nothing is mapped.

**v1 joins on exact ticker.** The 18 unpriced tickers are published with a null
valuation and `price_unavailable`, and the builder returns the list.

## 3. Two deliberate departures from spec §6.2

1. **Market cap uses the price file's own daily `Shares Outstanding`**, not
   `cshfdq_latest × 1e6`. Measured: SimFin's daily share count agrees with
   `cshoq × 1e6` for only 45.2% of tickers within 1% (median relative
   difference 1.13%) — ordinary buyback drift between quarter end and the price
   date, not a defect in either. Pairing today's close with today's share count
   is correct; pairing it with a count up to a quarter stale is not.
2. **`earnings_yield` is published for negative EPS; `pe_ttm` is not.** A
   negative P/E sorts as "cheap" when a screen ranks ascending — exactly the
   misreading the book warns against — so it is nulled with `non_positive_eps`.
   The earnings yield carries the same information correctly signed, so nulling
   it too would discard a real fact. 20 companies are in this state.

`valuation_current` is deliberately **outside the `metrics_*` namespace**, so
spec §7.1's "scorers never touch prices" is structural rather than a convention
someone could forget. A test asserts the score builder's source tables.

Determinism: `price_date` is pinned to the **maximum date in the ingested
data**, never the wall clock, so the same input yields identical rows (S3.1).

## 4. Verification (real corpus, 2026-07-28)

`prices_daily`: **584,788 rows**, 476 tickers, 2020-08-31 → 2025-08-01.
`valuation_current`: **494 rows** (every universe ticker), 476 with a market
cap, 456 with a P/E.

Market caps at 2025-08-01, against reality:

| ticker | close | market cap | P/E |
|---|---|---|---|
| NVDA | 173.72 | **$4,238.8B** | 58.5 |
| MSFT | 524.11 | **$3,895.8B** | 44.2 |
| AAPL | 202.38 | **$3,003.4B** | 33.2 |
| GOOG | 189.95 | $2,389.8B | 23.9 |
| AMZN | 214.75 | $2,290.3B | 38.0 |
| JPM | 289.37 | $795.7B | 14.4 |

P/E distribution p10 11.2 / median 24.7 / p90 63.9 — a plausible large-cap
spread.

| invariant | result |
|---|---|
| value XOR reason on `market_cap` | **0** violations |
| `NaN`/`inf` in any stored column | **0** |
| negative or zero `pe_ttm` published | **0** |
| negative `earnings_yield` kept (correctly) | 20, min −0.3587 |
| negative or null `close` in `prices_daily` | **0** |
| price gaps > 10 calendar days (spec §9.3) | **0 tickers** |
| daily moves > 50% (flagged, not dropped) | 3 rows, 3 tickers |

## 5. Historical valuation (added 2026-07-28)

Stage 1 now carries **`period_end_date`** and **`publish_date`**
(`TEMPORAL_COLUMNS`), which unlocks `valuation_history` at the
`(ticker, fiscal_year)` grain.

The date could not be derived: measured, the **fiscal quarter differs from the
calendar quarter of the period end for 21.5% of rows**, so aligning a price by
guessing would have been wrong for one company in five and silently off by up
to a quarter. AAPL FY2023 Q1 ends 2022-12-31.

Cross-era, the two are different things and are declared as such:

| field | legacy | SimFin | agreement |
|---|---|---|---|
| `period_end_date` | `datadate` | `Report Date` | **98.6% exact** |
| `publish_date` | `rdq` (earnings announcement) | `Publish Date` (filing) | **43.0% exact**, median −1 day |

The price is the last close **at or before** the period end, within
`MAX_PRICE_LOOKBACK_DAYS = 7`. Looking backward only is deliberate — a close
after the period end is information from the future. Measured: **median lag 0
days, max 3**, and **0 rows** take a price from after the period end.

`publish_date` is stored but not used as the anchor: v1 answers "what was the
company worth when its year closed", not "what could the market have known".
The gap is a median 40 days, so the distinction is material, and the column is
there so a publish-anchored variant needs no rebuild.

### 5.1 Two real defects this surfaced

**A vendor scale error reached a headline screen.** SimFin published MCD FY2024
`Shares (Basic)` as **718** against a diluted 722,000,000 for two quarters,
having read 722,000,000 for the other two. Derived EPS became **2,809,192 per
share** and a trailing P/E of **0.0** — putting McDonald's at the top of a
cheapest-stock screen. A new `share_count_scale` plausibility rule nulls a basic
count below `MIN_BASIC_TO_DILUTED_SHARE_RATIO = 0.5` of its diluted pair, and
also nulls the SimFin-era `epspxq` derived from it (legacy `epspxq` is
as-reported and untouched). Nulled values rose 151 → 224.

**P/E mixed two share bases — my own defect, caught in verification.**
SimFin's prices are **split-adjusted** while `epspxq` is as-reported. BKNG
FY2024 carries a close of **198.74** against a real ~$4,900 with a
correspondingly inflated share count: market cap comes out right because the
adjustment cancels, but `close / eps_ttm` gave a P/E of **1.1** against a true
~28. KLAC read 4.0 against ~35.

Valuation now derives from **totals**, which is invariant to split adjustment
by construction:

```
pe_ttm         = market_cap / (net_income_ttm x 1e6)
earnings_yield = (net_income_ttm x 1e6) / market_cap
```

A new `net_income_ttm` metric replaces `eps_ttm` in the valuation path.
`eps_ttm` remains for per-share trend use, where the basis is self-consistent.

Validated: AAPL's P/E by fiscal year end now reads **34.2 / 24.9 / 22.2 / 27.7
/ 37.8** (FY2020–24), all correct — FY2020 read 10.6 before the fix. The
FY2024 cheapest-large-cap screen returns CMCSA 8.9, GM 9.8, AFL 10.6, TRV 10.9,
JPM 11.5: banks, insurers, autos and energy, which is what a low-P/E screen
should return.

## 6. Open items

1. **Historical point-in-time valuation** needs fiscal report dates, which
   Stage 1 does not carry — SimFin's source files do (`Report Date`). v1
   publishes current valuation only. This is the main SP5 follow-up.
2. **Total return** is now possible (`Adj. Close`, `Dividend` are stored but
   unused). The platform spec requires it be symmetric across portfolio and
   benchmark before it ships.
3. **The `^SPX` benchmark** for SP7 is not in the SimFin share-price dataset; a
   separate source or a synthetic equal-weight benchmark is needed.
4. **18 unpriced tickers** (3.6%) — resolvable only with a verified
   security-identity mapping, never by symbol guessing (§2).
