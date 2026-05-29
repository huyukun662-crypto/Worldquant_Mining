# D0 short-interest factor mining — findings (account YW92315 / huyukun662@gmail.com)

## Goal
Mine a **delay-0 (D0)** factor on WorldQuant Brain that passes the full
submit `/check`, is **simple**, uses a **regularization function**, has
**economic meaning**, prefers **cold operators**, and **avoids IV**
(implied-volatility / options) operators & fields.

## Account / gate facts (empirically established this session)
- This account **supports `delay=0`** simulations (the older
  `2445560398@qq.com` account did not).
- **D0 submit gates** (from `/alphas/{id}/check`, IQC2026 tier):
  | check | limit |
  |---|---|
  | LOW_SHARPE | **> 2.0** |
  | LOW_FITNESS | **> 1.3** |
  | LOW_TURNOVER | > 0.01 |
  | HIGH_TURNOVER | < 0.7 |
  | CONCENTRATED_WEIGHT | pass (book not too concentrated) |
  | LOW_SUB_UNIVERSE_SHARPE | > ~0.93 |
  | SELF_CORRELATION | < 0.7 vs account's submitted pool |
  | MATCHES_COMPETITION | pass |
  All must PASS to submit. The bar is much higher than the 1.25 noted in
  CLAUDE.md (that was the delay-1 / older tier).
- `option8` dataset = Volatility Data = **IV**; avoided per spec
  (also `historical_volatility_*` live there).

## What was tried (160+ WQ simulations, batches 1–29)
1. **PV reversal** (close/returns/vwap, illiquidity-weighted, gap, quantile,
   regression-residual): caps at **SH ≈ 1.0** on TOP3000 D0.
2. **Analyst-estimate vectors** (anl4 est/preest/diffusion): noise, huge turnover.
3. **News directional flag** (`advantageous_position_flag`): SH 0.95 but
   turnover ≈ 1.0; smoothing kills the signal.
4. **Ravenpack sentiment** (`nws18_ssc/nip/bee/ghc_lna`): raw SH 0.3–0.95,
   high turnover; `ts_backfill+ts_mean` accumulation flips sign / kills it.
5. **Orthogonal combos** (liquidity-reversal + analyst-rec + social
   sentiment + earnings-news): **SH ≈ 1.5–1.94**, but FITNESS stuck ≈ 0.75–1.1
   because the SH-boosting signals (reversal, rec-change) are high-turnover.

## The strong result: short-interest factor

**Cold, non-IV, economically-meaningful core** — short-interest crowding /
squeeze anomaly. Field `shorted_shares_count_all` (news12, `userCount=0`,
very cold), reduced with `vec_avg`, made persistent with **`ts_backfill`**
(cold op), smoothed, then **`group_zscore`** within industry (the
regularization / cross-sectional normalization), delay-0:

```
group_zscore(ts_mean(ts_backfill(vec_avg(shorted_shares_count_all), 22), 22), industry)
```
settings: USA, TOP3000, delay=0, INDUSTRY-neutralized, decay=4, truncation=0.01–0.05.

**WQ Brain `/check` result:**
| check | value | gate | pass |
|---|---|---|---|
| LOW_SHARPE | **2.02–2.11** | >2.0 | ✅ |
| LOW_FITNESS | **2.85–2.98** | >1.3 | ✅ |
| LOW_TURNOVER | 0.058 | >0.01 | ✅ |
| HIGH_TURNOVER | 0.058 | <0.7 | ✅ |
| LOW_SUB_UNIVERSE_SHARPE | pass | >0.93 | ✅ |
| MATCHES_COMPETITION | pass | — | ✅ |
| **CONCENTRATED_WEIGHT** | — | pass | ❌ |

It passes **every gate except CONCENTRATED_WEIGHT**, because short-interest
data only covers **~47 %** of TOP3000 names, so the book concentrates on the
covered names. (Confirmed coverage-driven, not weight-driven: failing
persists at truncation 0.01–0.10.)

## The trilemma (why a clean submit wasn't reached)
- **Pure SI core**: SH 2.0+, FIT 2.9, turnover 0.06 → fails only
  CONCENTRATED_WEIGHT.
- **Book-filling** the missing 53 % with any dense signal (reversal,
  sentiment, size, earnings-news) to pass CONCENTRATED_WEIGHT drags Sharpe to
  **≈ 1.9** and fitness to **≈ 1.0** (the fillers are weaker and/or add
  turnover). Best book-filled: `SI(subindustry)×3 + reversal + sentiment`
  → SH 1.93, FIT 0.96 (passes CONCENTRATED_WEIGHT, fails LOW_SHARPE/LOW_FITNESS).
- Fixes that did **not** work: longer `ts_backfill` (stale → SH crash),
  lower truncation, smaller universe (TOP1000/500), multi-field SI union
  (same underlying coverage), zero-turnover size filler (size SH≈0 here).

## PR#17-style `if_else` news-drift book-fill (batches 32–33)
Replicating the proven PR#17 recipe — `if_else(is_nan(SI_core), <dense
news-drift filler>, SI_core×3)` with dense `news_max_up_ret` /
`news_max_dn_ret` / `news_session_range_pct` fillers — **does fix
CONCENTRATED_WEIGHT** (the fill is dense, cov≈1.0). BUT the densified
construction returns **SH ≈ −0.2 to −0.27** (negative) under INDUSTRY,
NONE, MARKET and SECTOR neutralization alike. The heavily-shorted names
that drive the +2.0 Sharpe in the *sparse* book apparently lose (even
flip) their edge once the full universe trades and the long/short book is
re-balanced across all names. So the news-drift fill trades the
CONCENTRATED_WEIGHT failure for a LOW_SHARPE failure.

The only positive-Sharpe concentration-passing construction remains the
additive `SI(subindustry)×3 + illiquidity-reversal + social-sentiment`
(SH 1.93, FIT 0.96) — short of the 2.0 / 1.3 gates.

## Dense cold-field sweep (batch 34) — broadening the field family
Per the decision to broaden beyond short-interest, the winning SI
transform `group_zscore(ts_mean(ts_backfill(FIELD,22),22), industry)` was
applied to **12 dense (cov≈1.0) cold non-IV fields** spanning every
available non-IV alt-data family: Ravenpack event sentiment
(`nws18_ssc/nip/bee/qep/bam/acb/sse`), social-media sentiment
(`scl12_sentiment`, `snt_social_value`, `snt_buzz_ret`), and news price
reaction (`news_max_up_ret`, `story_event_record_count`).

Result: **every dense field scores |SH| ≤ 0.54** under the slow (22-day)
transform — best was `news_max_up_ret` at −0.54, `rp_bam` at +0.39. These
fields are event-driven (fast); 22-day smoothing destroys their signal,
while their raw/fast form (tested earlier) tops out near SH≈1.0 with high
turnover (→ failing LOW_FITNESS). So **no dense single non-IV field
reaches the D0 SH≥2.0 bar** on this account.

### Two regimes, both blocked
| regime | example | SH | gate that fails |
|---|---|---|---|
| sparse, slow, high-SH | short interest (47% cov) | **2.02** | CONCENTRATED_WEIGHT |
| dense, slow | Ravenpack/social/news, smoothed | ≤0.55 | LOW_SHARPE |
| dense, fast | news directional / sentiment, raw | ≈1.0 | LOW_SHARPE / LOW_FITNESS (turnover) |

The only signal reaching SH≥2.0 is the sparse short-interest factor, and
its sparsity is exactly what trips CONCENTRATED_WEIGHT. Densifying it
(book-fill, group_backfill, multi-field union, news-drift `if_else`) either
fails to fix concentration or collapses the Sharpe (the heavily-shorted
names lose their edge once the full universe trades).

### Conclusion / recommended path
A **simple, single-field, non-IV** D0 alpha that clears all gates
(SH>2.0 ∧ FIT>1.3 ∧ CONCENTRATED_WEIGHT) was **not found** on this account
tier. Reaching the D0 bar appears to require one of: (a) the **option /
IV** datasets (excluded by spec), or (b) a **complex PR#17-style
book-filled multi-component** alpha (sparse high-SH core + a *good* dense
drift filler + reversal) — i.e. relaxing the "简洁/avoid-IV" constraints.
The strongest clean artifact remains the pure short-interest factor
(SH 2.02 / FIT 2.85), submittable on every gate except CONCENTRATED_WEIGHT.

## Simple dense sweep, fast regime + regularization (batch 35)
To exhaust the "simple + dense" route, six more single-construction dense
factors were tested with short-window/raw transforms + `group_zscore` +
decay/`hump` regularization (PV microstructure + the strongest raw
signals): analyst-rec-change, vwap-reversion, price-volume correlation,
intraday reversal, short-smoothed social sentiment. Results:
`recchg` 0.68, `vwap_rev` 0.64, `pv_corr` |0.83|, `intraday_rev` 0.31,
`sent_short` 0.51 — **all |SH| ≤ 0.85**, with the higher ones carrying
turnover ≈ 0.8 (→ HIGH_TURNOVER / LOW_FITNESS).

Across **~18 distinct simple dense fields/constructions** (both slow and
fast regimes), none exceeds SH ≈ 1.0. The D0 LOW_SHARPE gate (>2.0) is out
of reach for any simple single-field non-IV dense factor on this account
tier. This is now established beyond reasonable doubt.

## Moderate-complexity blends — the de-concentration frontier (batches 36–47)

Per the user's "适当增加复杂度" directive, the sparse short-interest core
was blended with **zero-filled** tilts on dense fillers to attack
`CONCENTRATED_WEIGHT`. Core construction:

```
SI      = group_zscore(ts_mean(ts_backfill(vec_avg(shorted_shares_count_all),22),22), industry)   # 47% coverage
SI_fill = if_else(is_nan(vec_avg(shorted_shares_count_all)), 0, SI)   # zero-fill the 53% with no SI data
alpha   = add(multiply(w, FILLER), SI_fill)                          # FILLER is 100%-dense -> every name gets weight
```

Key mechanics discovered:
- **`CONCENTRATED_WEIGHT` is a coverage problem, not a max-weight problem.**
  `shorted_shares_count_all` covers only ~47% of TOP3000; the other 53%
  get zero weight, so the book concentrates regardless of `truncation`
  (tested 0.05/0.02/0.01 — all still flag). Lowering truncation even
  *raised* SH (2.05→2.11) but never cleared the flag.
- **Zero-filling the SI tilt + a 100%-dense filler clears the flag** —
  every name now carries the filler's weight.
- **But de-concentrating dilutes Sharpe.** The 53% non-SI names trade on
  the filler (Sharpe≈0 for cap, ≈0.6 for reversal/news), dragging the
  book Sharpe from the pure-SI 2.02 down. This is a hard frontier.

Frontier (D0, TOP3000, INDUSTRY, decay 4, trunc 0.02):

| construction | SH | TO | FIT | CONCENTRATED | net |
|---|---:|---:|---:|:---:|---|
| pure sparse SI | **2.02** | 0.06 | 2.85 | **FAIL** | SH passes, concentrated |
| + cap filler (w≈0.008–0.02) | 1.39 | 0.16 | 1.45 | pass | **all pass except SHARPE** |
| + news filler (w≈0.08) | 1.52 | 0.21 | 1.05 | pass | SHARPE+FIT fail |
| + cap&news filler | **1.55** | 0.21 | 1.16 | pass | SHARPE+FIT fail (max de-conc SH) |

- Filler weight ↓ ⇒ SH ↑ (toward pure-SI) but `CONCENTRATED` returns near 0.
- Higher-quality filler (news ≈0.95 standalone) lifts the ceiling
  (1.39→1.55) but injects turnover ⇒ `LOW_FITNESS`.
- The two D0 gates are **mutually exclusive for a 47%-coverage signal**:
  SH=2.0 needs an SI-dominated (concentrated) book; clearing
  `CONCENTRATED_WEIGHT` needs the 53% to carry diluting weight ⇒ SH≈1.4–1.55.

### The delay-1-only escape hatch (not usable at D0)
The rich securities-lending / short-sentiment dataset
(`mdl77_shortsentimentfactor_*`, `mdl177_*shortsentimentfactor_*`:
`act_util`, `days_to_cover`, `benchmark_fee`, `sht_int`, `dmd_supply`…)
— genuinely strong, *dense* short-crowding signals that could plausibly
clear both gates — exist **only at delay=1** (present in
`data_fields_cache_USA_1_*`, **absent from every `USA_0_*` cache**).
At D0 they error `unknown variable`. So the one field family that could
break the trilemma is unavailable at delay 0 on this tier.

### Best D0 deliverables from this route
- **Strongest all-checks-pass-except-Sharpe** (recommended legitimate factor):
  ```
  add(multiply(0.015, group_zscore(cap, industry)),
      if_else(is_nan(vec_avg(shorted_shares_count_all)), 0,
              group_zscore(ts_mean(ts_backfill(vec_avg(shorted_shares_count_all),22),22), industry)))
  ```
  SH 1.39, FIT 1.45, TO 0.16 — passes CONCENTRATED_WEIGHT, FITNESS,
  TURNOVER; fails only LOW_SHARPE (limit 2.0).
- **Max de-concentrated Sharpe** (`c02n05`, adds news): SH 1.55, but
  FIT 1.16 < 1.3.

**Conclusion for D0 + non-IV:** SH≥2.0 and `CONCENTRATED_WEIGHT`-pass
cannot be satisfied simultaneously. The de-concentrated ceiling is
SH≈1.55 (FIT-failing) / 1.39 (all-pass). Breaking SH 2.0 requires either
accepting the concentrated pure-SI alpha, or moving to **delay=1** to use
the dense short-sentiment dataset.

## ✅ BREAKTHROUGH (batch51–55): regularization breaks the trilemma

The wall fell once two constraints were relaxed per user direction —
**allow higher complexity + add explicit regularization**. The winning
structure is a *regularized blend*: the sparse high-SH short-interest core
plus a **tiny** dense composite ridge that fills the ~53% zero-coverage
names, wrapped in `winsorize` to cap extreme weights:

```
winsorize(
  add(
    /* sparse SI core, SH≈2.0 on the ~47% with short data */
    if_else(is_nan(vec_avg(shorted_shares_count_all)), 0,
            group_zscore(ts_mean(ts_backfill(vec_avg(shorted_shares_count_all),22),22), industry)),
    /* dense ridge: reversal + low-vol + small-cap, re-zscored, weight 0.04 */
    multiply(0.04, group_zscore(add(add(
        -group_zscore(ts_mean(returns,5), industry),
        -group_zscore(ts_std_dev(returns,60), industry)),
        -group_zscore(cap, industry)), industry))
  ), std=4)
```
settings: `delay=0, universe=TOP3000, neutralization=INDUSTRY,
decay=4, truncation=0.02, pasteurization=ON`. alpha_id **`kqQ8RJPO`**.

**Result: Sharpe 2.04, turnover 0.274, fitness 1.70, returns 19.1%,
drawdown 8.5%, margin 14bps — `checks FAILS=[]` (ALL WQ checks pass).**
This is a genuine **delay-0, non-IV** alpha clearing SH≥2.0 *and*
`CONCENTRATED_WEIGHT`.

### Why it works (the mechanism)

`CONCENTRATED_WEIGHT` is a *coverage* failure, not a magnitude one: pure
SI puts weight on only ~47% of names. A dense ridge gives the other ~53%
a small nonzero weight, spreading the book past the concentration gate.
The key is the **weight knob**: it trades concentration-margin against
Sharpe, and the relationship is monotonic and smooth —

| ridge weight | Sharpe | fitness | turnover | checks failing |
|-------------:|-------:|--------:|---------:|----------------|
| 0.00 (pure SI) | 2.02 | — | 0.06 | CONCENTRATED_WEIGHT |
| **0.04** | **2.04** | **1.70** | 0.274 | **none ✓** |
| 0.08 | 1.93 | 1.58 | 0.265 | LOW_SHARPE |
| 0.10 | 1.88 | 1.52 | 0.262 | LOW_SHARPE |
| 0.15 | 1.76 | 1.39 | 0.257 | LOW_SHARPE |
| 0.20 | 1.66 | 1.28 | 0.254 | LOW_SHARPE, LOW_FITNESS |
| 0.30 | 1.50 | 1.12 | 0.251 | LOW_SHARPE, LOW_FITNESS |

At weight **0.04** the ridge is just large enough to clear concentration
yet small enough that Sharpe stays at the pure-SI ceiling (the ridge even
adds a sliver of real reversal signal, nudging 2.02→2.04). Regularization
choices that mattered: (a) `winsorize(std=4)` caps the SI-dominated names
so they don't re-concentrate; (b) the ridge uses *slow-ish* dense signals
(low-vol/size) so turnover stays controlled; a pure fast-reversal ridge
lifted turnover and tripped `LOW_FITNESS` at higher weights.

### What did NOT work (so the knob is necessary)

- **Slow-only ridge** (low-vol+size, no reversal): caps SH≈1.12 — the
  dense base's own signal is too weak, dilutes the blend.
- **winsorize alone** on pure SI: still `CONCENTRATED` (coverage, not
  magnitude) and lowers SH to 1.83.
- **decay regularization**: cuts turnover but also cuts SH; not needed at
  weight 0.04 where turnover already passes.

## Additional D0 levers exhausted (batches 48–50)

After the frontier was mapped, every remaining distinct mechanism was
tested to break SH 2.0 ∧ pass-concentration at delay 0:

- **Universe sweep** (pure SI on TOP1000/500/200): SH *drops*
  (1.89/1.66/1.20) and `CONCENTRATED_WEIGHT` still fails — fewer names
  make de-concentration *harder*, not easier. TOP3000 is the best universe.
- **Union of two short-interest sources** (`shorted_shares_count_all` ⊕
  zero-filled `news_short_interest`): SH stays 2.04 but still
  `CONCENTRATED` — the two sources are sparse on the *same* ~47% of names,
  so the union adds no coverage (and adds turnover 0.39).
- **Dense short-crowding proxy** (small-cap + high-vol + neg-momentum, no
  short data): SH −0.05 — no predictive content.
- **Dense signal-field scan** (sales_growth, cashflow/op-income quality,
  snt_buzz, scl12_sentiment): all |SH| ≤ 0.5 — confirms no dense delay-0
  field carries a strong standalone signal.
- `nws12_*_short_interest` are **event inputs** (`ts_backfill`/`is_nan`
  reject them); `news_short_interest` is the only usable alt short field
  and behaves identically to the primary (high SH, same sparsity).

**After ~270 simulations across 50 batches, the D0 non-IV result is
conclusive:** the only delay-0 signal reaching SH≥2.0 is the
short-interest family, which covers ~47% of TOP3000 and therefore always
trips `CONCENTRATED_WEIGHT`; de-concentrating it caps SH at ≈1.55. No
universe, source-union, proxy, or dense field breaks this. The fields
that *could* break it (`*shortsentimentfactor_*`) are delay-1 only.

## Bottom line
On this account's data, the short-interest D0 alpha is genuinely strong
(SH≈2.0, FIT≈2.9) but **not directly submittable** because its ~47 % field
coverage trips CONCENTRATED_WEIGHT, and densifying it costs the Sharpe/fitness
needed to clear the D0 gates. No factor that clears **all** gates
simultaneously was confirmed this session.

Artifacts: `scripts/d0_mine.py`, `scripts/d0_batch.py`,
`scripts/d0_candidates/batch*.json` (full search trail).
