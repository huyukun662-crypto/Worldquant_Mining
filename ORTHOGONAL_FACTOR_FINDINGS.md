# Second D0 factor — uncorrelated with the short-interest winner

## Goal
Mine a second delay-0 factor **uncorrelated** with the short-interest
winner `KPkVxEb1` (the regularized SH-2.08 alpha), to act as a genuine
diversifier.

## Approach
Hunt economically-orthogonal signal families (value, quality, analyst
estimates, earnings surprise, news) rather than anything short/positioning
related. Short interest captures *short-side crowding*; an uncorrelated
factor must be driven by something else.

## Orthogonal-core scan (D0, TOP3000, INDUSTRY, batches o1–o5)
| core | family | SH | note |
|---|---|---:|---|
| analyst forecast **dispersion** `(high-low)/mean` | analyst4 | **1.01** | best orthogonal core |
| analyst predicted-uncertainty `pu` | analyst4 | 0.86 | very low turnover |
| dispersion + value | mixed | 0.92 | |
| book-to-price | fundamental6 | 0.69 | classic value, slow |
| analyst revision (consensus Δ) | analyst4 | 0.51 | |
| ROE | fundamental6 | 0.33 | |
| earnings surprise (eps ratio / growth) | news12/fnd | ≤0.05 | weak/negative at D0 |
| earnings yield (ebit/EV) | fundamental6 | 0.17 | |

**Orthogonal D0 signals cap at SH ≈ 1.0 individually.** Short interest
remains the only D0 family reaching SH ≈ 2.0 — so an *uncorrelated* factor
cannot also clear the 2.0 submit gate at delay 0.

## Building the factor up via orthogonal diversification (o6–o8)
Single orthogonal cores cap ~1.0, but **stacking independent orthogonal
signals lifts Sharpe through diversification** while staying uncorrelated
with short interest:

| composite | SH | fitness | corr vs KPkVxEb1 |
|---|---:|---:|---:|
| dispersion only | 1.01 | 0.45 | **-0.010** |
| + 0.5·uncertainty(pu) | 1.31 | 0.71 | — |
| + 0.4·value (book/price) | 1.58 | 0.95 | **0.057** |
| **+ 0.3·quality (ROE)** ⭐ | **1.64** | 1.05 | **0.126** |
| + profitability/retained-earnings | ≤1.21 | — | hurt (too noisy at D0) |

The peak orthogonal composite is the **4-way: dispersion + uncertainty +
value + quality**, SH **1.64**.

## FINAL orthogonal factor (alpha `9qJ8M2JK`)
```
group_zscore(
  add(add(add(
    group_zscore(ts_backfill(divide(subtract(
        vec_avg(anl4_basicconqf_high), vec_avg(anl4_basicconqf_low)),
        vec_avg(anl4_basicconqf_mean)), 66), industry),          /* dispersion */
    multiply(0.5, group_zscore(ts_backfill(vec_avg(anl4_basicconqf_pu),66), industry))),  /* uncertainty */
    multiply(0.4, group_zscore(ts_backfill(divide(bookvalue_ps, close),66), industry))),  /* value */
    multiply(0.3, group_zscore(ts_backfill(return_equity,66), industry))),                /* quality */
  industry)
```
settings: `delay=0, TOP3000, INDUSTRY, decay=4, truncation=0.02`.
**SH 1.64, fitness 1.05, turnover 0.19, returns 7.8%, drawdown 6.6%.**

## Orthogonality CONFIRMED (the key result)
Daily-PnL Pearson correlation vs the short-interest winner, over 1,235
days via `scripts/d0_corr.py`:

```
KPkVxEb1 (short-interest, SH 2.08)  vs  9qJ8M2JK (4-way composite, SH 1.64)
    corr = +0.126        # low — a genuine diversifier
KPkVxEb1  vs  kqQvJ9ad  (dispersion-only, SH 1.01)
    corr = -0.010        # essentially zero
KPkVxEb1  vs  2rJ9GwzJ  (3-way, no ROE, SH 1.58)
    corr = +0.057        # maximally orthogonal variant
```

The two factors are driven by **independent economics** — short-side
crowding (factor 1) vs analyst disagreement / value / quality (factor 2) —
and the measured PnL correlation (0.13, well under the 0.7 self-correlation
gate) confirms it. SH 1.64 is below the 2.0 submit gate, as expected for an
orthogonal D0 signal. Full result in `WQ_ORTHOGONAL_FACTOR_RESULTS.json`.

## Construction notes / pitfalls
- Analyst fields update sparsely → **must `ts_backfill`** before any
  time-series op, else turnover explodes (raw dispersion TO=1.57 vs
  backfilled TO=0.25).
- The `anl4_dez1*v4_est/_preest` "detailed-estimate revision" fields (cov
  1.0) are **event-typed**: `ts_backfill`/`subtract`/`ts_mean` all reject
  them, so dense revision momentum is not simply constructible.
- Cross-field EPS surprise hits **unit mismatches** (`news_eps_actual`
  Unit[] vs `est_epsr` Unit[CSShare:-1]); only same-unit arithmetic works.

## ✅ Making it SUBMITTABLE (goal: "挖到可以提交为止") — factor 2 final

The pure orthogonal composite caps at SH 1.64 (below the 2.0 gate). To get
a **submittable** second factor that is still distinct from factor 1, blend
the short-interest level core with the orthogonal composite — two
near-independent signals (corr 0.13) whose blend clears SH 2.0 while the
PnL correlation to the pure-short-interest factor 1 stays well under the
0.7 self-correlation gate:

```
winsorize(
  add(
    multiply(0.85, <short_interest_level_core, zero-filled>),
    multiply(0.15, <4-way orthogonal composite>)
  ), std=4)
```

Blend frontier (all variants pass SH>2.0, fitness>1.3, all WQ checks):

| SI weight | SH | fitness | corr vs factor 1 | alpha_id |
|---:|---:|---:|---:|---|
| 0.70 | 2.02 | 1.47 | 0.353 | mLZ0gmJ5 |
| 0.75 | 2.04 | 1.50 | 0.375 | VkOzlgxb |
| 0.80 | 2.05 | 1.53 | 0.399 | lerGzrMl |
| **0.85** ⭐ | **2.07** | **1.56** | **0.424** | **QPEzl0Er** |

**Chosen factor 2 = `QPEzl0Er`** (SI weight 0.85): SH 2.07, fitness 1.56,
turnover 0.216, returns 12.3%, drawdown 5.9%, **all hard checks PASS**,
self-correlation vs factor 1 = **0.424 < 0.7**. Full result in
`WQ_FACTOR2_SUBMITTABLE_RESULTS.json`.

### Two submittable, mutually-distinct D0 factors
| | core economics | SH | fitness | submit |
|---|---|---:|---:|---|
| factor 1 `KPkVxEb1` | short-side crowding | 2.08 | 1.75 | ✓ |
| factor 2 `QPEzl0Er` | short crowding + analyst uncertainty/value/quality | 2.07 | 1.56 | ✓ (corr 0.42) |

## ✅ POOL-orthogonal factor (goal: "挖与这些不相关的因子") — factor 3

Inspected the account's actual 19-alpha pool: it is **saturated with IV
(`implied_volatility_*`, SH 2.4) and price/volume technicals**
(`ts_corr(high,close)`, intraday `(close-open)/open`, range, reversal).
So the pool-orthogonal direction is **fundamental/analyst**, not
price/volume (which would collide) and not IV (avoided per spec).

Measured **max correlation against the whole pool** via WQ
`/alphas/{id}/correlations/self`:

| factor | SH | max pool corr | note |
|---|---:|---:|---|
| pure dispersion | 1.01 | **0.226** | lowest correlation |
| **dispersion + 0.5·pu + 0.2·value** ⭐ | **1.54** | **0.262** | best Sharpe at low corr |
| 4-way (+ROE) | 1.64 | 0.365 | ROE/value raise corr |
| SI×fundamental blends (SH>2.0) | 2.0+ | ~0.42 | SI floor |
| pure short interest | 2.08 | 0.531 | |

**Factor 3 = `wpLkemQQ`**: `group_zscore(dispersion + 0.5·pu +
0.2·book/price)`, SH 1.54, turnover 0.21, **max pool correlation 0.262** —
far below the 0.42 of the earlier blend. Value weight is the correlation
driver (0.2→corr 0.26, 0.4→corr 0.45+); keeping it light is what makes this
factor genuinely pool-orthogonal. Full result in
`WQ_FACTOR3_POOL_ORTHOGONAL_RESULTS.json`.

### Hard constraint discovered
At **D0 without IV**, *any* SH>2.0 factor must rely on short interest,
which inherently correlates ~0.42 with the pool's IV/price-volume alphas
(heavily-shorted ⇒ high IV). Therefore **submittable (SH>2.0) and
pool-uncorrelated (<0.3) are mutually exclusive** on this account at delay
0 without IV. Factor 3 maximizes Sharpe (1.54) subject to true
pool-orthogonality (0.262); reaching SH 2.0 would require either IV (out of
spec) or accepting ~0.42 pool correlation (the SI blend, e.g. `QPEzl0Er`).
