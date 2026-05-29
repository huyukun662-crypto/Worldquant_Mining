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

## Bottom line
On this account's data, the short-interest D0 alpha is genuinely strong
(SH≈2.0, FIT≈2.9) but **not directly submittable** because its ~47 % field
coverage trips CONCENTRATED_WEIGHT, and densifying it costs the Sharpe/fitness
needed to clear the D0 gates. No factor that clears **all** gates
simultaneously was confirmed this session.

Artifacts: `scripts/d0_mine.py`, `scripts/d0_batch.py`,
`scripts/d0_candidates/batch*.json` (full search trail).
