# Research Brief - medium_horizon_momentum

## Objective
Mine USA-equity factors that pass WQ Brain IS gates:
SH > 1.25, fitness > 1.0, turnover < 0.25.

## Mechanism candidate
**Short-term price reversal**: Stocks with extreme recent returns tend to
mean-revert over the next 1-5 trading days. Documented since Jegadeesh
(1990); persistent on US equities. Effect is amplified after high-volume
moves (forced flow / sentiment overshoot).

## Datasets / fields available on this WQ tier
- Price-volume: close, open, high, low, volume, vwap, returns
- Cross-sectional cap: cap, sharesout
- Derived: adv20 (20d ADV in shares - WQ semantics)

## Operators in scope
- Time-series smoothing: ts_mean, ts_decay_linear, ts_zscore, ts_rank
- Normalization: divide, ts_std_dev (vol scaling)
- Volume conditioning: divide(volume, adv20), s_log_1p
- Cross-sectional wrap: rank (chosen over zscore/scale because robust to
  outliers and produces uniform-distribution signals that play nicely
  with INDUSTRY neutralization)

## Caveats / failure modes
1. **Turnover risk** - raw reversal at 1-3 days typically exceeds 0.40
   daily TO. Smoothing via ts_decay_linear or longer windows brings it
   under 0.25.
2. **Industry correlation** - sector momentum can mask stock-level
   reversal; INDUSTRY neutralization is non-optional.
3. **Cost wipeout** - WQ Brain accounts for transaction cost in
   `is.checks`; even if SH > 1.25, the LOW_FITNESS check
   may fail if returns are too small to cover assumed costs.

## Prior submissions on this WQ tier (CLAUDE.md historical)
- Local-pipeline volume-only factors (ts_std_dev(volume,11) variants)
  scored 1.32 / 1.30 IS Sharpe locally but -0.15 / 0.01 on WQ Brain.
  Conclusion: volume-only signals do not survive WQ TOP3000 with
  INDUSTRY neutralization. This run uses returns-anchored variants
  with volume only as a conditioning signal.
