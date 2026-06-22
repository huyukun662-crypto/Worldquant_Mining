# Submit-Ready Factor Mining Report

**Account**: 2841262992@qq.com (DH58557)
**Run**: 2026-06-22, 39 simulations on WorldQuant Brain `/simulations`, delay=1, NO TOP3000.
**Method**: curated simple finance-grounded candidates × {TOP1000/TOP500} × {INDUSTRY/SUBINDUSTRY} × heavy decay (16/32/64). No Alpha101 / classical template reuse.

## Survivors (all WQ `is.checks` PASS + self-correlation < 0.7)

Ranked by WQ Brain IS Sharpe:

| # | alpha_id | expression | universe | neut | decay | SH | TO | FIT | RET | DD | max self-corr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **A1wgAdZE** | `-ts_rank(returns, 5)` | TOP1000 | INDUSTRY | 32 | **2.07** | 0.509 | **1.18** | 0.165 | 0.07 | 0.351 |
| 2 | KPbX1kNN | `-ts_rank(returns, 10)` | TOP1000 | SUBINDUSTRY | 64 | 1.93 | 0.393 | 1.18 | 0.146 | 0.06 | 0.431 |
| 3 | MPpKrmOr | `-ts_rank(returns, 5)`  | TOP1000 | SUBINDUSTRY | 64 | 1.90 | 0.367 | 1.05 | 0.112 | 0.04 | 0.327 |
| 4 | blLowo5m | `-ts_rank(returns, 10)` | TOP1000 | INDUSTRY | 32 | 1.77 | 0.493 | 1.07 | 0.180 | 0.11 | 0.462 |
| 5 | P0pwVlzp | `-ts_rank(returns, 10)` | TOP500  | INDUSTRY | 16 | 1.75 | 0.565 | 1.00 | 0.183 | 0.09 | 0.395 |
| 6 | omK3dgzk | `-ts_rank(returns, 20)` | TOP1000 | SUBINDUSTRY | 64 | 1.62 | 0.356 | 1.04 | 0.148 | 0.07 | 0.476 |

## Recommended factor to submit

**Alpha ID `A1wgAdZE`** — best IS Sharpe (2.07), best fitness (1.18), low drawdown (0.07):

```
expression:  -ts_rank(returns, 5)
settings:
  region:         USA
  universe:       TOP1000
  delay:          1
  neutralization: INDUSTRY
  truncation:     0.08
  decay:          32
  pasteurization: ON
```

Backup candidate **`KPbX1kNN`** (`-ts_rank(returns, 10)` @ TOP1000/SUBINDUSTRY/decay=64) has nearly identical SH (1.93) with a more conservative turnover (0.39) and is structurally less correlated with #1 (different window), so it's a good diversifier.

## Submit checks (all PASS — verified pre-submit)

For `A1wgAdZE`:

| check | result | value | limit |
|---|---|---|---|
| LOW_SHARPE | PASS | 2.07 | > 1.25 |
| LOW_FITNESS | PASS | 1.18 | > 1.0 |
| LOW_TURNOVER | PASS | 0.509 | > 0.01 |
| HIGH_TURNOVER | PASS | 0.509 | < 0.7 |
| CONCENTRATED_WEIGHT | PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | PASS | - | - |
| MATCHES_COMPETITION | PASS | challenge, IQC2026S1 | - |
| SELF_CORRELATION | PASS (verified via `/alphas/{id}/correlations/self`) | max 0.351 | < 0.7 |

All boxes ticked. Ready for manual submit via WQ web UI.

## Key insight that unlocked the result

Smoke test on 3 quick candidates revealed `-ts_rank(returns, 5)` had strong signal (SH 1.4–1.87 at decay=4) but failed HIGH_TURNOVER (0.75–0.93) and LOW_FITNESS (0.45–0.79). The fix was simply to crank `decay` to 32–64. That suppresses daily portfolio rebalancing without killing the underlying short-term reversal signal, lifting fitness above 1.0 and dropping turnover under 0.7. All 6 survivors come from the `-ts_rank(returns, N)` family — the same finance idea (short-term cross-sectional reversal) at three different lookbacks. Other ideas tested (mean-reversion z-score, price-volume correlation, VWAP delta, vol-of-vol, intraday position) either lacked Sharpe or hit unit-incompatibility errors.

## Files

- `MINE_ROUND2.json` — full 39-trial results (gitignored)
- `scripts/mine_simple.py` — the miner driver
