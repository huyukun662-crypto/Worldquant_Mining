# D0 (delay=0) factor mining — running notes

Goal: a **submittable** delay-0 alpha — simple, with regularization
functions, economic meaning, uncommon operators, no IV fields. We only
`check` submittability (run `/simulations` and read `is.checks`); we do
NOT click Submit Alpha.

## Key facts established this session

- **delay=0 IS available** on account `2445560398@qq.com` (POST
  `/simulations` returns 201, sim COMPLETEs). The CLAUDE.md note that
  "delay 0 is not available" is **stale** (IQC2026S1 opened D0).
- **D0 submission bar is stricter** (delay-driven, confirmed: delay-1
  sims show LOW_SHARPE limit 1.25, delay-0 sims show 2.0):
  - `LOW_SHARPE`   limit **2.0**
  - `LOW_FITNESS`  limit **1.3**
  - `HIGH_TURNOVER` limit 0.7, `LOW_TURNOVER` floor 0.01
  - `CONCENTRATED_WEIGHT` limit 0.1
  - `LOW_SUB_UNIVERSE_SHARPE` (value must clear its limit)
  - `SELF_CORRELATION` (vs own submitted pool; PENDING is fine)
- Account quirks: concurrent `/simulations` limit ~2; operators
  `ts_min` / `ts_max` are NOT accessible on this tier.

## What works / doesn't (delay=0, USA, SUBINDUSTRY neut, decay 6-10)

| signal family | best SH | TO | FIT | note |
|---|---:|---:|---:|---|
| 1-day reversal `-ts_delta(close,1)` / `-ts_zscore(returns,5)` | 0.1-0.6 | 0.7-0.9 | low | turnover too high, sharpe too low |
| Bollinger reversal `-ts_zscore(close,N)` | 0.71-0.87 | 0.2-0.3 | 0.4 | decent, not enough |
| **`-quantile(ts_av_diff(close,N),gaussian)`** | **1.0-1.15** | 0.15-0.42 | 0.6-0.68 | gaussian quantile regularizer is the key lift |
| **+ `group_zscore(...,subindustry)`** | **1.18-1.22** | 0.25 | **0.72** | sector neutralization adds ~0.1-0.15 SH |
| correlated reversal combos (add two horizons) | 1.10-1.20 | 0.25-0.29 | 0.70 | near-zero diversification (signals correlated) |
| reversal × volume-shock (multiply) | 0.25 | - | - | destroys the signal |
| low-vol anomaly `-quantile(ts_std_dev(returns,20),gaussian)` | 0.16 | 0.07 | low | no edge at D0 |

**Plateau**: pure short-term price mean-reversion saturates at
**SH ≈ 1.2, FIT ≈ 0.72** at D0 on TOP3000. To reach the 2.0 bar we need
to combine the reversal workhorse with genuinely *orthogonal* economic
PV signals (intraday/overnight reversal, momentum, relative volume,
price acceleration, regression residual). batch5 screens those.

## Regularization / uncommon operators in play

- Regularization: `quantile(...,driver=gaussian)`, `winsorize`,
  `group_zscore`, `normalize`, `ts_backfill`.
- Uncommon: `ts_av_diff` (x minus its TS mean — mean reversion in one op),
  `quantile`, `ts_regression`, `group_zscore`, `ts_backfill`.
- Avoided: any implied-volatility / option (IV) fields.

## Tooling

- `scripts/wq_probe.py`  — single D0 probe + check thresholds.
- `scripts/wq_batch.py`  — concurrent (max 2) batch tester over
  (expression, settings); writes results incrementally; flags
  candidates that pass ALL D0 submission checks.
