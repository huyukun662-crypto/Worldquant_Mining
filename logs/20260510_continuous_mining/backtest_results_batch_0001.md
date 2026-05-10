# Continuous-Mining Round — Batch 0001 (Stage 4 / Operator)

## Harness

- Panel: 251-name yfinance proxy, 1848 daily bars (2019-01-02 → 2026-05-08).
- IS window: 2019-01-01 → 2023-12-31 (1258 d).
- OS window: 2024-01-01 → 2026-05-08 (590 d).
- Backtest: cross-sectional rank-demean + L1-normalize per row, 1-bar position lag.
- Optuna trials per expression: 40.
- Candidates evaluated: 700.
- Wall time: 22.8 min.

## Stop condition

Stop when 4 *structurally distinct* survivors of the strict gates `IS_SH > 1.25 ∧ IS_TO < 0.25 ∧ OS_SH ≥ IS_SH` are accumulated.

## Pre-submission audits

- **G1 Importable**: every survivor parses + evaluates.
- **G2 Runs end-to-end**: every survivor produces a (T, N) signal.
- **G3 Non-degenerate**: every survivor has `IS_TO > 0` and `IS_SH > 1.25`.
- **A4 Delay consistency**: position lag = 1 bar = WQ delay=1.

## Distinct survivors found (4)

| rank | IS_SH | IS_TO | OS_SH | OS_TO | structural signature | tuned expression |
|-----:|------:|------:|------:|------:|---------------------|------------------|
| 1 | +1.319 | 0.007 | +1.803 | 0.007 | `zscore(ts_mean(ts_std_dev(subtract(vwap,volume),_),_))...` | `zscore(ts_mean(ts_std_dev(subtract(vwap, volume), 16), 45))` |
| 2 | +1.293 | 0.016 | +1.667 | 0.018 | `zscore(ts_mean(ts_std_dev(divide(adv20,high),_),_))...` | `zscore(ts_mean(ts_std_dev(divide(adv20, high), 33), 3))` |
| 3 | +1.280 | 0.006 | +1.754 | 0.006 | `scale(ts_decay_linear(ts_std_dev(add(vwap,volume),_),_))...` | `scale(ts_decay_linear(ts_std_dev(add(vwap, volume), 45), 33))` |
| 4 | +1.257 | 0.003 | +1.813 | 0.002 | `scale(ts_decay_linear(ts_decay_linear(add(volume,high),_),_)...` | `scale(ts_decay_linear(ts_decay_linear(add(volume, high), 42), 46))` |

