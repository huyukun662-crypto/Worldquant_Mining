# Submit-Ready Factor Mining Report

**Account**: 2841262992@qq.com (DH58557)
**Run**: 2026-06-22, 137 simulations on WorldQuant Brain `/simulations`, delay=1, NO TOP3000.

## Final recommendation

**Alpha `blLNVogM`** (or equivalent `JjpnYpJm`):

```
expression:
  zscore(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))

settings:
  region:         USA
  universe:       TOP1000
  delay:          1
  neutralization: SUBINDUSTRY
  truncation:     0.01
  decay:          128
  pasteurization: ON
  nanHandling:    OFF      (ON gives identical result, both work)
```

**Metrics**

| metric | value |
|---|---|
| IS Sharpe | **1.31** (> 1.25 ✅) |
| IS Fitness | **1.51** (> 1.0 ✅) |
| IS Turnover | 0.122 |
| IS Returns | (in alpha record) |
| max self-correlation | 0.172 (< 0.7 ✅) |
| WQ Brain `is.checks` | **all PASS** |

The factor is a **pure Option-implied-volatility momentum signal** —
structurally orthogonal to the earlier PV-reversal survivors. Economic
intuition: a rising call-IV at the 60-day expiry signals informed-trader
demand for upside exposure; we rank that change cross-sectionally,
forward-fill stale option quotes 250 trading days so the support spans
TOP1000 (not just the ~30-40% of names with daily option flow — that was
the CONCENTRATED_WEIGHT trap), then `zscore` to give a unit-vol signal.

## Final submit checks (all PASS, no PENDING)

For `blLNVogM`:

| check | result | value | limit |
|---|---|---|---|
| LOW_SHARPE | PASS | 1.31 | > 1.25 |
| LOW_FITNESS | PASS | 1.51 | > 1.0 |
| LOW_TURNOVER | PASS | 0.122 | > 0.01 |
| HIGH_TURNOVER | PASS | 0.122 | < 0.7 |
| CONCENTRATED_WEIGHT | PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | PASS | - | - |
| MATCHES_COMPETITION | PASS | challenge / IQC2026S1 | - |
| SELF_CORRELATION | PASS (verified via `/alphas/{id}/correlations/self`) | max 0.172 | < 0.7 |

## Three survivors (all PASS-ALL, ranked by IS Sharpe)

| # | alpha_id | expression | univ | trunc | nan | SH | FIT | TO | self-corr |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **blLNVogM** | `zscore(ts_backfill(ts_delta(implied_volatility_call_60, 10), 250))` | TOP1000 | 0.01 | OFF | 1.31 | 1.51 | 0.122 | 0.172 |
| 2 | JjpnYpJm | same as #1 | TOP1000 | 0.01 | ON | 1.31 | 1.51 | 0.122 | 0.172 |
| 3 | QPanqgmg | `… + 0.3 * zscore(-ts_rank(returns, 10))` (hybrid with PV reversal) | TOP1000 | 0.05 | ON | 1.25 | 1.43 | 0.154 | 0.203 |

All three are submit-eligible. **#1 is the recommended factor** —
pure Option signal, lowest correlation to existing alphas, highest
fitness.

## How the mining loop got here

This was a 6-module search, ~137 WQ Brain simulations total:

| module | category | candidates | trials | PASS-ALL |
|---|---|---|---|---|
| 1 | PV reversal | 14 | 39 | 6 |
| 2 | Option / News (naive) | 12 | 36 | 0 |
| 3 | Option signal-flip + Fundamental crosses | 8 | 16 | 0 |
| 4 | IV-momentum heavy-decay amplification | 8 | 24 | 0 |
| 5 | Fix CONCENTRATED via wrapper / trunc | 6 | 18 | 0 |
| 6 | Fix CONCENTRATED via ts_backfill(250) + nanHandling | 8 | 8 | **3** |

Key insight per module:
- **M2 → M3**: negative Sharpe on `ts_delta(implied_volatility_call_30, 5)`
  meant the signal was real but inverted — flip sign.
- **M3 → M4**: SH 1.10, FIT 0.63 → switched to `implied_volatility_call_60`
  with delta=10 horizon and decay=128 → SH 1.30, FIT 0.97.
- **M4 → M5/M6**: every variant cleared LOW_SHARPE / LOW_FITNESS but
  failed CONCENTRATED_WEIGHT because option data covers only ~30-40% of
  TOP1000. Fix: `ts_backfill(., 250)` forward-fills stale option signals,
  spreading the alpha across all names so the weight stops concentrating.

## Module-1 survivors (kept as diversifiers)

For reference, the 6 PV-reversal alphas from Module 1 are still
submit-eligible (independent search dimension). Top:

- `A1wgAdZE`: `-ts_rank(returns, 5)` TOP1000/INDUSTRY/decay=32 — SH=2.07 FIT=1.18 TO=0.51

These remain available if you want a 2-factor portfolio (Option IV + PV
reversal) — their self-correlation against each other should be near 0
by construction.

## Files

- `MINE_MOD6_RESULTS.json` — module-6 raw results
- `MINE_ROUND2.json` — module-1 raw results
- `scripts/mine_module{1..6}.py` — staged miners (each module learns from the previous)
