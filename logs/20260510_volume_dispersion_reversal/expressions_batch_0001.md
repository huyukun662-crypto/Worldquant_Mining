# Expressions Batch 0001 — Volume Dispersion Reversal

Stage 3 / Agent 3 — Alpha Builder.

Mechanism: cross-section names whose dollar-volume becomes
unusually concentrated and whose price has extended in the same
direction reverse over 5-20 days. All 8 expressions consume only
time-`t` data; under `delay=1` the earliest execution is close[t+1].
Lookback windows are *placeholders* — Stage 4 / Operator runs Optuna
over each integer literal on the IS window, with hard cap
`turnover < 0.25`.

| ID | Expression | Variant of mechanism |
|----|------------|----------------------|
| E1 | `rank(ts_decay_linear(multiply(divide(ts_std_dev(volume, 20), ts_mean(volume, 20)), reverse(ts_returns(close, 5))), 10))` | volume CV × short return, decayed |
| E2 | `rank(reverse(multiply(ts_zscore(volume, 20), ts_zscore(close, 20))))` | joint vol+price z-score, reversed |
| E3 | `rank(ts_decay_linear(reverse(ts_corr(close, volume, 15)), 5))` | price-volume corr divergence, decayed |
| E4 | `rank(reverse(multiply(divide(ts_std_dev(volume, 40), ts_mean(volume, 40)), ts_returns(close, 3))))` | long-window CV × very short return |
| E5 | `rank(ts_decay_linear(reverse(multiply(ts_zscore(volume, 10), ts_returns(vwap, 5))), 15))` | short-window vol z × VWAP return, decayed |
| E6 | `rank(reverse(multiply(divide(volume, ts_mean(volume, 20)), ts_zscore(close, 20))))` | abnormal-volume × price z-score |
| E7 | `rank(reverse(multiply(ts_std_dev(returns, 20), ts_returns(close, 10))))` | idio-vol × medium return (M3 variant) |
| E8 | `rank(ts_decay_linear(reverse(multiply(divide(ts_std_dev(volume, 30), ts_mean(volume, 30)), subtract(close, vwap))), 10))` | volume CV × intraday extension, decayed |

## Per-expression economic note

**E1.** Volume CV (`std/mean`) over 20 days captures concentration.
Multiplying by `reverse(ts_returns(close, 5))` says: shorts the
recently-up names with concentrated volume. `ts_decay_linear` over
10 days controls turnover.

**E2.** Two z-scores, both 20-day. When today's volume AND today's
close are jointly extreme, the joint z-score is large; sign-flipping
sets up the reversal trade. The cleanest version of the mechanism
with no smoothing.

**E3.** `ts_corr(close, volume, 15)` is positive in trending regimes
and turns negative at exhaustion. `reverse` makes negative-corr names
the longs (likely accumulation bottoms) and positive-corr names the
shorts (likely distribution tops). Decay-linear over 5 days dampens
turnover.

**E4.** Same shape as E1 but stretches the dispersion window to 40
and shortens the return window to 3. Tests whether longer-window
dispersion + ultra-short price extension is more reliable.

**E5.** `ts_zscore(volume, 10)` is short-window abnormal volume.
`ts_returns(vwap, 5)` measures VWAP drift (less noisy than close-to-
close). Decay-linear over 15 days is the longest smoothing in the
batch, targeting the lowest-turnover regime.

**E6.** Replaces volume CV with `volume / ts_mean(volume, 20)` (today's
volume vs 20-day average) — a sharper instantaneous abnormal-volume
metric. No smoothing; expected to have higher turnover than E1/E5.
Useful as the "fast" anchor of the batch.

**E7.** Idiosyncratic volatility variant. `ts_std_dev(returns, 20)`
is per-name realized vol; `ts_returns(close, 10)` is medium return.
High-vol names that just rallied tend to fade. Mechanism overlap
with the well-known low-vol anomaly is intentional — provides a
diversification anchor across the batch.

**E8.** `subtract(close, vwap)` measures end-of-day pressure (close
above VWAP = bid pressure exhausted, close below VWAP = panic).
Multiply by 30-day volume CV to amplify when dispersion is high.
Decay-linear over 10 days.

## Expected behavior by expression

| ID | expected IS_SH | expected TO | expected OS_SH | failure if... |
|----|---------------:|------------:|---------------:|----------------|
| E1 | 1.4-1.7        | 0.05-0.10   | ≥ IS           | Sharpe collapses → mechanism is purely beta-driven |
| E2 | 1.5-2.0        | 0.10-0.20   | ≥ IS           | Turnover blows past 0.25 → need decay wrapper |
| E3 | 1.2-1.6        | 0.05-0.10   | ≥ IS           | Sharpe negative → corr mechanism is regime-dependent |
| E4 | 1.3-1.6        | 0.05-0.10   | ≥ IS           | Sharpe < E1 → long-window dispersion is noisier |
| E5 | 1.4-1.8        | 0.04-0.08   | ≥ IS           | OS Sharpe < IS by > 50% → 5d horizon overfit |
| E6 | 1.5-2.0        | 0.20-0.30   | ≥ IS           | TO > 0.25 → turnover penalty kills score |
| E7 | 1.0-1.4        | 0.04-0.08   | ≥ IS           | Sharpe < 1.25 → idio-vol effect alone is too weak |
| E8 | 1.3-1.7        | 0.05-0.10   | ≥ IS           | Sharpe < E1 → close-vwap deviation is too noisy |

## Feature-time annotation

All expressions are pure functions of `{close, open, high, low, volume,
vwap, returns}` evaluated at time `t` (no `ts_delay` of -ve d, no
`shift(-k)`, no future bars). Backtest harness lags positions by one
bar before applying returns. Consistent with `delay=1`.

## Rule-of-8 self-check

- 8 distinct expressions: yes (8 listed above).
- Single dominant mechanism: yes (volume_dispersion_reversal; M3
  contributes only E7).
- Each annotated with economic note: yes.
- Each annotated with expected turnover: yes.
- Feature-time annotation present: yes.

## Handoff to Backtest Operator

- 8 expressions above
- Per-expression Optuna budget: 25 trials over integer literals on the
  IS window (2019-01-01 → 2023-12-31) with hard cap `turnover < 0.25`.
- Backtest signal: cross-sectional rank-demean + L1-normalize per row.
- Position lag: 1 bar (matches `delay=1`).
- Score: `IS_Sharpe`; tie-break by `IS_Turnover` (lower = better).
- Validate G1 (importable) and G2 (runs end-to-end) before submission.
