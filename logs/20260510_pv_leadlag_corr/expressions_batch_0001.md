# Expressions Batch 0001 — Lead-lag Price-Volume Correlation

**Owner:** Agent 3 (Alpha Builder)
**Session:** `20260510_pv_leadlag_corr`
**Mechanism:** lead_lag_price_volume_corr
**Constraint:** exactly 8 expressions, structurally distinct, one dominant mechanism

| # | Expression | Variation axis | Expected turnover |
|---|-----------|----------------|-------------------|
| 1 | `reverse(ts_corr(ts_delay(high, 1), volume, 237))` | baseline (best prior result, +0.84) | very low (~0.03) |
| 2 | `reverse(ts_corr(ts_delay(high, 5), volume, 237))` | wider lag (5d → weekly delay) | very low |
| 3 | `reverse(ts_corr(ts_delay(close, 1), volume, 237))` | close instead of high (intraday closure) | very low |
| 4 | `reverse(ts_corr(ts_delay(vwap, 1), volume, 237))` | vwap (avg traded price) instead of high | very low |
| 5 | `reverse(ts_corr(ts_delay(high, 1), ts_delay(volume, 1), 237))` | both delayed (pure t-1 corr surface) | very low |
| 6 | `reverse(ts_corr(ts_delay(high, 1), volume, 120))` | half-window (~6mo) — robustness on horizon | very low |
| 7 | `reverse(rank(ts_corr(ts_delay(high, 1), volume, 237)))` | cross-sectional rank wrapper for normalization | very low |
| 8 | `reverse(ts_corr(ts_delay(high, 1), multiply(volume, vwap), 237))` | replace volume with dollar volume | very low |

## Economic explanation per expression

1. **Baseline.** `Corr(high[t-1], volume[t], 237)` — over a year, do
   prior-day intraday peaks systematically pair with today's heavier volume?
   When yes, the name is at a "crowded high" attractor; mean-reversion
   sells. Reverse turns sell-signal into long-friendly Sharpe.

2. **5-day lag.** Same mechanism but tests for weekly persistence rather
   than overnight carry. If 5-day-old peaks still predict today's volume,
   the crowding structure is institutional-rebalance, not retail-day-trader.

3. **Close, not high.** Tests whether the signal is from intraday tops
   specifically (high) or from session-end commitment (close). Different
   institutional readings.

4. **VWAP variant.** Substitutes vwap for high. VWAP captures average
   transacted price over the prior day; this isolates "true cost basis"
   crowding rather than wick crowding.

5. **Both delayed.** `Corr(high[t-1], volume[t-1], 237)` is a pure
   yesterday-on-yesterday correlation. Removes the lead-lag mechanic and
   tests whether contemporaneous co-movement carries the same alpha.
   Acts as a falsification probe for #1.

6. **Half-window.** Tests horizon sensitivity. If signal is annual-scale
   crowding, 120-day window should weaken Sharpe markedly. If signal is
   shorter-cycle, 120 may be stronger.

7. **Rank wrapper.** Adds cross-sectional rank for dispersion control —
   makes the signal more robust to unit/scale and tightens turnover
   distribution.

8. **Dollar volume.** Replaces volume with `volume * vwap` (dollar
   volume). Tests whether the alpha is share-flow specific or money-flow
   specific.

## Hard constraints check (Agent 3 self-audit)

- [x] Exactly 8 expressions
- [x] Single dominant mechanism (lead-lag price-volume corr)
- [x] Structurally distinct (different field, lag, window, or wrapper per row)
- [x] All operators on the available WQ Brain tier (no s_log_1p, ts_returns, ts_median)
- [x] All fields on the available tier (no num_trades, sharesout missing)
- [x] Each expression has a one-paragraph economic rationale
- [x] Expected turnover stated (very low across the batch — annual-scale signal)

## Handoff

Pass to Agent 4 (Backtest Operator) with the settings dict from
`session_metadata.yml`. Agent 4 must validate G1 (importable) before
submission and report all 8 outcomes back to Agent 5.
