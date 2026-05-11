# QuantML port -- Round 1

Five structurally and logically distinct factors ported from the
[QuantML factor zoo](https://github.com/QuantMLResearch/QuantML)
(`factor_zoo/`) and submitted to WQ Brain `/simulations` under
USA TOP3000 with **per-factor tuned settings**.

The QuantML zoo originally uses Qlib minute-K DSL; on daily bars
`DownResample(..., 240, M)` collapses to identity, and
`Med`/`Mad`/`Std`/`Kurt` map to `ts_mean` / manual MAD /
`ts_std_dev` / fourth-moment-of-zscore. `ts_max`/`ts_min` are
inaccessible on this account tier, so amplitude uses
`mean((high - low)/close)` instead.

## Round-1 results

| id | category | SH | TO | FIT | RET | drawdown | alpha_id | decay | neut | trunc |
|----|----------|---:|---:|----:|---:|---:|----------|------:|------|------:|
| QM_R1_01 | amplitude | 0.59 | 0.06 | 0.67 | 0.16 | — | `wp5K9Vep` | 4 | INDUSTRY | 0.08 |
| QM_R1_02 | median-bias | 0.54 | 0.21 | 0.39 | 0.11 | 0.27 | `akNjbG8R` | 0 | SUBINDUSTRY | 0.05 |
| QM_R1_03 | mad | 0.31 | 0.10 | 0.24 | 0.08 | 0.74 | `d5nk1VYv` | 4 | INDUSTRY | 0.08 |
| QM_R1_04 | higher-moment | **0.78** | **0.06** | **0.68** | 0.10 | 0.19 | `78x76Jvx` | 0 | MARKET | 0.08 |
| QM_R1_05 | liquidity | -1.01 | 0.07 | -1.08 | -0.14 | 0.79 | `MPbM361L` | 4 | INDUSTRY | 0.08 |

## The five factors

### QM_R1_01 — amplitude
```
-1 * ts_mean((high - low) / close, 20)
```
*20-day realised-range proxy; short high-amplitude names.* Original
`Max($high,N)/Min($low,N)-1` collapsed because `ts_max`/`ts_min` are
not accessible.

### QM_R1_02 — median-bias (mean reversion)
```
ts_mean(close, 60) / close - 1
```
*Long names below their 60-day mean, short names above.* `Med`
substituted with `ts_mean`. **Sub-industry neutralised + tighter
truncation (0.05)** because price-reversion is a sub-industry-level
phenomenon.

### QM_R1_03 — MAD (mean absolute deviation)
```
-1 * ts_mean(abs(close - ts_mean(close, 20)), 20) / close
```
*Manual MAD normalised by close; short instability.*

### QM_R1_04 — higher moment (kurtosis)
```
-1 * ts_mean(power(ts_zscore(returns, 60), 4), 60)
```
*60-day fourth-moment-of-zscore (kurtosis); short fat-tailed names.*
**Market-neutral** since kurtosis is a pure shape statistic with no
industry loading. Best of the five (SH=0.78, TO=0.06).

### QM_R1_05 — Amihud illiquidity
```
ts_mean(abs(returns) / (vwap * volume), 20)
```
*Smoothed Amihud illiquidity; long illiquid names.* The realised SH
came out -1.01, suggesting the **liquidity premium has the opposite
sign on USA TOP3000**: liquid names outperform here. Flipping the
sign would give SH≈+1.01.

## Setting-variation rationale

The user spec said "setting 自由可调"; this round used four distinct
parameter tuples:

| dimension | values used | reason |
|-----------|-------------|--------|
| `decay` | 0 vs 4 | high-frequency factors (range, MAD, Amihud) get linear decay to compress TO; low-frequency factors (mean, kurtosis) don't need it |
| `neutralization` | INDUSTRY, SUBINDUSTRY, MARKET | matched to the factor's natural loading: pure shape -> MARKET, price-reversion -> SUBINDUSTRY |
| `truncation` | 0.05 vs 0.08 | tighter cap on the most concentrated factor (median-bias) |

## Observations & next-round candidates

- All five returned IS metrics; **none** pass the strict
  `SH>1.25 ∧ TO<0.25 ∧ FIT>1` triple gate (the threshold isn't
  required by this task, but for reference).
- QM_R1_04 is the closest to viable; raising the kurtosis window or
  combining with a slow trend signal could push SH above 1.
- QM_R1_05's sign is wrong on USA TOP3000; **flip in round 2**.
- QM_R1_02 has SH near 0.5 with TO already below 0.25 — could combine
  with a quality signal.
- Round-2 candidates from QuantML categories not yet touched:
  extreme-value information (`ts_arg_max`), price-volume correlation,
  turnover share, broker-factor replications.
