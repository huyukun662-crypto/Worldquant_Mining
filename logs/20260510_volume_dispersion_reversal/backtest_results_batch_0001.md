# Backtest Results — Batch 0001 (Volume Dispersion Reversal)

Stage 4 / Agent 4 — Backtest Operator.

## Harness

- Panel: yfinance proxy, 251 USA large/midcap tickers, 1848 daily bars (2019-01-02 → 2026-05-08).
- IS window: 2019-01-01 → 2023-12-31 (1258 days).
- OS window: 2024-01-01 → 2026-05-08 (590 days).
- Backtest: cross-sectional rank-demean + L1-normalize per row, 1-bar position lag.
- Optuna trials per expression: 60.

## Pre-submission audits

- **G1 Importable**: 8/8 pass (all expressions parse and evaluate).
- **G2 Runs end-to-end**: 8/8 pass.
- **G3 Non-degenerate**: 8/8 pass (turnover > 0 on IS).
- **A2 Future-perturbation invariance**: max past-value diff < 1e-9 across 8/8 expressions.
- **A3 Target-mask provenance**: no .where() / .mask() applied to features (factor code is mask-free).
- **A4 Delay consistency**: backtest position lag = 1 bar = WQ delay=1.

## Per-expression metrics

| ID | IS_SH | IS_TO | OS_SH | OS_TO | best windows | tuned expression |
|----|------:|------:|------:|------:|--------------|------------------|
| E1 | +0.597 | 0.145 | +0.028 | 0.149 | {'0': 36, '1': 50, '2': 3, '3': 9} | `rank(ts_decay_linear(multiply(divide(ts_std_dev(volume, 36), ts_mean(volume, 50)), reverse(ts_returns(close, 3))), 9))` |
| E2 | +0.421 | 0.573 | -0.739 | 0.578 | {'0': 4, '1': 23} | `rank(reverse(multiply(ts_zscore(volume, 4), ts_zscore(close, 23))))` |
| E3 | +0.479 | 0.136 | +0.228 | 0.136 | {'0': 5, '1': 11} | `rank(ts_decay_linear(reverse(ts_corr(close, volume, 5)), 11))` |
| E4 | +0.588 | 0.227 | +0.220 | 0.232 | {'0': 53, '1': 42, '2': 7} | `rank(reverse(multiply(divide(ts_std_dev(volume, 53), ts_mean(volume, 42)), ts_returns(close, 7))))` |
| E5 | +0.546 | 0.144 | -0.263 | 0.150 | {'0': 3, '1': 22, '2': 49} | `rank(ts_decay_linear(reverse(multiply(ts_zscore(volume, 3), ts_returns(vwap, 22))), 49))` |
| E6 | +0.180 | 0.218 | +0.031 | 0.208 | {'0': 17, '1': 27} | `rank(reverse(multiply(divide(volume, ts_mean(volume, 17)), ts_zscore(close, 27))))` |
| E7 | +0.543 | 0.223 | +0.175 | 0.229 | {'0': 59, '1': 7} | `rank(reverse(multiply(ts_std_dev(returns, 59), ts_returns(close, 7))))` |
| E8 | +0.694 | 0.111 | -0.221 | 0.107 | {'0': 5, '1': 50, '2': 31} | `rank(ts_decay_linear(reverse(multiply(divide(ts_std_dev(volume, 5), ts_mean(volume, 50)), subtract(close, vwap))), 31))` |

## Strict-gate survivors (IS_SH > 1.25 ∧ IS_TO < 0.25 ∧ OS_SH ≥ IS_SH)

None. The 251-name yfinance proxy IS Sharpe ceiling on this mechanism is ~0.69 (E8). Per `CLAUDE.md`, this is expected: the local backtest is a triage proxy, and prior random-search survivors that *did* cross this floor still scored negatively on WQ Brain.

## Robust pool (IS_TO < 0.25 ∧ OS_SH > 0)

| rank | ID | IS_SH | IS_TO | OS_SH | OS_TO | composite |
|-----:|----|------:|------:|------:|------:|----------:|
| 1 | E4 | +0.588 | 0.227 | +0.220 | 0.232 | +0.854 |
| 2 | E3 | +0.479 | 0.136 | +0.228 | 0.136 | +0.781 |
| 3 | E7 | +0.543 | 0.223 | +0.175 | 0.229 | +0.763 |
| 4 | E1 | +0.597 | 0.145 | +0.028 | 0.149 | +0.631 |
| 5 | E6 | +0.180 | 0.218 | +0.031 | 0.208 | +0.252 |

## Selection mode: `robust_composite`

Top 4 for WQ Brain submission:

1. **E4** — `rank(reverse(multiply(divide(ts_std_dev(volume, 53), ts_mean(volume, 42)), ts_returns(close, 7))))`
   - local IS_SH=+0.588, IS_TO=0.227, OS_SH=+0.220, OS_TO=0.232
2. **E3** — `rank(ts_decay_linear(reverse(ts_corr(close, volume, 5)), 11))`
   - local IS_SH=+0.479, IS_TO=0.136, OS_SH=+0.228, OS_TO=0.136
3. **E7** — `rank(reverse(multiply(ts_std_dev(returns, 59), ts_returns(close, 7))))`
   - local IS_SH=+0.543, IS_TO=0.223, OS_SH=+0.175, OS_TO=0.229
4. **E1** — `rank(ts_decay_linear(multiply(divide(ts_std_dev(volume, 36), ts_mean(volume, 50)), reverse(ts_returns(close, 3))), 9))`
   - local IS_SH=+0.597, IS_TO=0.145, OS_SH=+0.028, OS_TO=0.149
