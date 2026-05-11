# Research Brief — Lead-lag Price-Volume Correlation

**Session:** `20260510_pv_leadlag_corr`
**Owner:** Agent 1 (Research Librarian)
**Workflow:** [Factor_Zoo / worldquant-5-agent-workflow](https://github.com/huyukun662-crypto/Factor_Zoo)

## Objective

Mine 4 WQ-Brain-compliant factors (`IS Sharpe > 1.25`, `IS turnover < 0.25`)
on USA equities using only the operator and field set available on the
`2445560398@qq.com` Brain account tier.

## Evidence pack

### From this repo (`WQ_*REPORT.json`)

| Source | Best WQ_SH | Family | Settings |
|---|---:|---|---|
| `WQ_MINING_REPORT.json` (4 local-mined uncorrelated factors) | +0.50 | volume-volatility decay | TOP1000 / NONE / decay=4 |
| `WQ_DIRECT_REPORT.json` (40 random WQ-direct candidates) | +0.94 | `rank(reverse(ts_rank(sharesout, 40)))` | screen settings: TOP3000 / INDUSTRY / decay=4 |
| `WQ_QML_REPORT.json` (10 QuantML factors × 4 setting trials) | **+0.84** | `reverse(ts_corr(ts_delay(high,1), volume, 237))` | **TOP500 / NONE / decay=4 / trunc=0.08 / past=OFF** |

### From `QuantMLResearch/QuantML/factor_zoo/runs.md`

The lead-lag price-volume correlation family `Corr(Ref($price, k), $volume, ~237)`
dominates by ICIR — top 10 absolute |ICIR| are all in this family with
`|ICIR| > 4.3` on the QML A-share testbed, sign consistently negative
(IC_mean ≈ -0.05). Mechanism: when past-day price extremes line up with
today's volume, future returns mean-revert.

### From CLAUDE.md
- 4 IS Sharpe rule: > 1.25
- 4 IS turnover rule: < 0.25
- Account tier: `delay=0` not available; only `delay=1`
- WQ universe ceiling for this account: TOP3000

### Operators & fields confirmed available on this tier
`ts_corr`, `ts_delay`, `ts_rank`, `ts_mean`, `ts_std_dev`, `ts_decay_linear`,
`ts_zscore`, `ts_arg_min`, `ts_arg_max`, `ts_min`, `ts_max`, `rank`, `reverse`,
`scale`, `normalize`, `divide`, `multiply`, `subtract`, `add`, `log`, `abs`.
**Not** available: `s_log_1p`, `ts_returns`, `ts_median`, `ts_skewness`,
`ts_kurtosis`, `ts_slope`, `ts_partial_corr`, `Peak`.
Fields: `open close high low volume vwap returns cap sharesout adv20`.

## Candidate mechanism

**Lead-lag price-volume correlation as a contra-signal.**

Stocks where past-day price extremes (`high[t-1]`, `close[t-1]`, `vwap[t-1]`)
become highly correlated with today's volume over a long window (~year)
attract crowding / overpaying — future returns are negative. Operator
shape: `reverse(ts_corr(ts_delay(<price>, k), <volume_proxy>, <long_window>))`.

## Operator suggestions

- Time-series correlation: `ts_corr(x, y, d)` — direct WQ Brain primitive.
- Past price reference: `ts_delay(price, k)` for k in {1, 2, 5}.
- Cross-sectional wrapper: `rank(...)` to control turnover / dispersion.

## Risks / caveats

1. **Local backtest is uncalibrated** — per CLAUDE.md, do NOT use the
   yfinance harness to pre-screen this batch.
2. **Sign matters** — IC_mean is negative on the QML zoo, so we wrap
   with `reverse` so the WQ-returned Sharpe gate (>1.25) is one-sidedly
   applicable.
3. **Universe sensitivity** — best result on TOP500 / NONE; INDUSTRY
   neutralization on TOP3000 destroys signal (drops to +0.16).
4. **Long window (~237) is structural** — mechanism is annual-scale
   crowding, not momentum.
