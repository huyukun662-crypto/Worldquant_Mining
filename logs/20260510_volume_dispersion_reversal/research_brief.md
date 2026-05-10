# Research Brief — Volume Dispersion & Price-Extension Reversal

Stage 1 / Agent 1 — Research Librarian.

## Objective

Mine 4 alphas that satisfy WorldQuant Brain's authoritative gates
(`IS_Sharpe > 1.25 ∧ IS_Turnover < 0.25 ∧ OS_Sharpe ≥ IS_Sharpe`) on the
USA TOP3000 universe with delay=1, using only the price-volume fields
available on this account tier. No factor templates may be reused
(`worldquant_mining/factor_templates.py` is reference-only per
`CLAUDE.md`).

## Available platform surface

Source: `constants/upstream_data_fields_USA_TOP3000.json`,
`constants/data_fields_union_USA.json`, and account-tier audits in
`mining_pipeline/expressions.py:32`.

- **PV fields actually exposed on this account**: `close`, `open`, `high`,
  `low`, `volume`, `vwap`, `returns`, `cap`, `sharesout`, `adv20`.
  - `dollar_volume` is NOT a WQ field — use `multiply(close, volume)`.
  - The advN family is restricted to `adv20`; advN for N ∈ {5, 60, 120}
    is not exposed.
- **Universe**: TOP200, TOP500, TOP1000, TOP3000 (all USA, delay=1).
  `delay=0` is unavailable on this tier (`HTTP 400 "Delay 0 not
  available"`); `wq_pipeline.SETTING_SPACE['delay']=[1]`.
- **Operators**: full canonical set (176 ops) per `worldquant_mining/operators.py`.
  The local mining pipeline implements a subset in `mining_pipeline/operators.py`:
  `ts_zscore, ts_rank, ts_delta, ts_mean, ts_std_dev, ts_returns,
  ts_decay_linear, ts_corr, rank, zscore, scale, normalize, add,
  subtract, multiply, divide, log, abs, reverse, sign, s_log_1p,
  ts_sum, ts_min, ts_max, ts_arg_max, ts_arg_min, ts_delay,
  signed_power, power, winsorize`.
- **Setting search axes** (`mining_pipeline/wq_pipeline.py:50`):
  `universe ∈ {TOP200, TOP500, TOP1000, TOP3000}`,
  `decay ∈ {0, 4, 8, 16, 32, 64}`,
  `truncation ∈ {0.01, 0.05, 0.08, 0.10}`,
  `neutralization ∈ {NONE, MARKET, INDUSTRY, SUBINDUSTRY, SECTOR}`,
  `pasteurization ∈ {ON, OFF}`.

## Lessons from prior submissions (`WQ_SUBMISSION_RESULTS.json`)

Two random-generated factors that passed local gates collapsed on
WQ Brain:

| local IS / local OS  | WQ Brain SH | WQ TO | WQ FIT |
|---------------------:|------------:|------:|-------:|
| 1.32 / 1.78          |     -0.150  | 0.026 |  -0.07 |
| 1.30 / 1.80          |     +0.010  | 0.033 |   0.00 |

Three structural reasons (CLAUDE.md):

1. **Universe** — local 251-name yfinance large/midcap vs WQ TOP3000.
2. **Backtest mechanics** — local equal-weight L/S, `gross=1`; WQ runs
   `INDUSTRY` neutralized, `truncation=0.08`, `pasteurization=ON`.
3. **Field semantics** — local `adv20 = ts_mean(close*volume, 20)` (dollar
   volume); WQ `adv20 = ts_mean(volume, 20)` (share volume). Mining
   should be robust to either definition.

Implication: random expression search on a 251-name proxy is not
sufficient. **Mechanism-driven** generation with mechanisms known to
survive industry neutralization is the only path that has any chance
of platform-grade Sharpe.

## Mechanism candidates (top 3)

### M1 — Volume-dispersion reversal (recommended)

When intra-window dollar-volume becomes **unusually concentrated**
(high CV of volume) AND price has extended in the same direction over
that window, the move reflects retail-flow exhaustion and tends to
reverse over the next 5-20 days.

- Why it survives industry neutralization: dispersion is a
  cross-sectional property, not a sector beta. Industry-demeaned
  volume CV stays informative.
- Why turnover stays low: signal is a smoothed product of two
  smoothly-varying moments (window stdev / mean), not a raw return.
- Operators needed: `ts_std_dev`, `ts_mean`, `divide`, `ts_zscore`,
  `multiply`, `reverse`, `ts_corr`, `ts_decay_linear`, `rank`.

### M2 — Price-volume divergence (corr-based)

`ts_corr(close, volume, d)` flips sign at local tops/bottoms.
Negative correlation + recent high → distribution; positive
correlation + recent low → accumulation. Decay-linear smoothing
controls turnover.

### M3 — Idiosyncratic volatility mean-reversion

Cross-sectional rank of `ts_std_dev(returns, d)` × recent return → high
idiosyncratic vol stocks that just spiked tend to fade. Less
attractive than M1 because it overlaps with the well-known low-vol
anomaly and is more correlated with size.

## Recommendation

Pick **M1 (Volume-dispersion reversal)** as the dominant mechanism
for this batch. M2 is incorporated as one of the 8 implementation
variants since `ts_corr(close, volume, d)` is mechanically a
co-dispersion measure. M3 contributes one variant via
`ts_std_dev(returns, ...)` but is not the lead mechanism.

## Caveats

- **Look-ahead**: all expressions consume only fields known at close[t].
  Backtest harness lags positions by one day (`mining_pipeline/backtest.py:60`),
  consistent with WQ `delay=1`.
- **Field semantics drift**: local `adv20` is dollar volume, WQ `adv20`
  is share volume. Avoid `adv20` in expressions where possible; prefer
  `ts_mean(volume, d)` or `multiply(close, volume)` for explicit
  dollar-volume so the meaning is identical on both sides.
- **Universe size**: local 251 vs WQ 3000 — local Sharpe is a
  necessary but not sufficient condition. The local triage gate at
  `IS_SH > 1.25 ∧ TO < 0.25` is intentionally tight to throw out the
  ~99% of garbage that local random search generates.
- **Cost**: WQ submissions are 86-180s each, ~2-3 concurrent → ~30-60
  per hour. The 8-expression batch limit (one Optuna sweep over
  setting-space per expression) fits the throughput budget.

## Handoff to Hypothesis Architect

- Mechanism: M1 — volume dispersion × price extension → reversal.
- Operators: see list under M1.
- Constraints:
  - Avoid `adv20` where `multiply(close, volume)` or `ts_mean(volume, d)`
    can be used instead.
  - All factors wrapped in a CS op (`rank`, `zscore`, `scale`).
  - Smoothing via `ts_decay_linear(..., d)` to keep turnover < 0.25.
  - Single dominant mechanism, 8 distinct implementations.
