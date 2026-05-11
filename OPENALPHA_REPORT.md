# OpenAlpha → WQ Brain USA TOP3000

Port of the 34 alpha expressions in
[`ziyouqitan/OpenAlpha`](https://github.com/ziyouqitan/OpenAlpha) (CSI-500 DSL)
into WQ Brain FASTEXPR, submitted to `/simulations` under USA TOP3000.

**Simulation settings** (CLAUDE.md canonical):

```
region=USA  universe=TOP3000  delay=1  decay=0
neutralization=INDUSTRY  truncation=0.08  pasteurization=ON
unitHandling=VERIFY  nanHandling=OFF  language=FASTEXPR
```

**Survivor gate (per user spec)**: `IS Sharpe > 1.25` ∧ `IS turnover < 0.25`
∧ `IS fitness > 1`.

## Summary

| count | meaning |
|------:|---------|
| 34 | translated factors |
| 30 | submissions returned IS metrics |
|  4 | residual unit errors (untranslatable on this account tier) |
|  **1** | **survivors** |

## Survivor

| id | SH | TO | FIT | returns | drawdown | alpha_id |
|----|---:|---:|---:|---:|---:|---|
| **OA24** | **1.47** | **0.07** | **2.47** | 0.354 | 0.397 | `vR5wxKO3` |

```text
expression: ts_std_dev(low / ts_delay(close, 1) - 1, 100)
          - ts_std_dev(high / ts_delay(close, 1) - 1, 100)
original  : ts_std(low/ts_delay(close,1)-1,100) - ts_std(high/ts_delay(close,1)-1,100)
```

**Interpretation.** Cross-sectional 100-day downside-vs-upside realised
volatility asymmetry. Long names with higher downside vol (vs prior
close), short names with higher upside vol. Captures a risk-premium /
disposition-effect signal that survives industry-neutralisation with
very low turnover (7%) and high fitness (2.47).

## Near misses

Factors that passed one or two gates but not all three:

| id | SH | TO | FIT | issue |
|----|---:|---:|---:|-------|
| OA30 | **1.85** | 0.54 | 0.75 | TO too high |
| OA32 | **1.58** | 0.80 | 0.61 | TO too high |
| OA02 | **1.36** | 0.73 | 0.41 | TO too high |
| OA08 | **1.41** | 0.82 | 0.42 | TO too high |
| OA21 | 0.93 | **0.13** | 0.79 | SH below 1.25 |

These are candidates for follow-up tuning: increase `decay` in the
simulation settings, wrap in `ts_decay_linear`, or add a longer averaging
window to reduce TO. Out of scope for this initial port.

## Methodology

Three submission rounds were required because some operators in the
OpenAlpha DSL have no direct WQ Brain analogue on this account tier,
and FASTEXPR's `unitHandling=VERIFY` rejects mismatched physical units.

| round | scope | log |
|-------|-------|-----|
| 1 | direct translation of all 34 | `logs/openalpha_submit.log` |
| 2 | manual `ts_returns` / volume-`rank()` / power-based skew & kurt | `logs/openalpha_fixes.log` |
| 3 | `ts_zscore` wrapper to strip units before `power()` | `logs/openalpha_r3.log` |
| 4 | strip `returns` unit in regression 2nd arg | `logs/openalpha_r4.log` |

### Translation table

| OpenAlpha | WQ Brain FASTEXPR |
|-----------|-------------------|
| `cs_rank(x)` | `rank(x)` |
| `ts_correlation(x, y, d)` | `ts_corr(x, y, d)` |
| `ts_std(x, d)` | `ts_std_dev(x, d)` |
| `ts_ret(x, 1)` / `ret1` | `(x/ts_delay(x,1) - 1)` / `returns` |
| `csi_500_ret1` | `group_mean(returns, 1, market)` |
| `amount` | `vwap * volume` |
| `np.abs(x)` | `abs(x)` |
| `ts_ols(y, x, d)[0]` (beta) | `ts_regression(y, x, d, rettype=2)` |
| `ts_ols(y, x, d)[2]` (resid) | `ts_regression(y, x, d, rettype=0)` |
| `ts_skewness(x, d)` (inaccessible) | `ts_mean(power(ts_zscore(x, d), 3), d)` |
| `ts_kurtosis(x, d)` (inaccessible) | `ts_mean(power(ts_zscore(x, d), 4), d) - 3` |
| `cs_indneut`, `cs_booksize`, `at_mask(..., csi_500_weight>0)`, `ts_fill` | dropped (handled by simulation settings or no USA analogue) |

### Residual errors

| id | reason |
|----|--------|
| OA16 | `ts_regression(returns, volume, ...)` — 2nd arg expects `Unit[TSPrice:1]`, accepted no available substitute. |
| OA28 | same root cause with `vwap*volume`. |
| OA33 | depends on `csi_500_open`/`csi_500_close` (no USA equivalent); excluded from the translation. |
| OA34, OA35 | `ts_regression` 2nd-arg unit mismatch on `returns`. `rank(returns)` / `ts_zscore(returns,d)` did not strip the CSPrice unit in round 4; left as residual error. |

## Reproducing

```bash
# Credentials (gitignored)
echo '["<wq-username>","<wq-password>"]' > credential.txt && chmod 600 credential.txt

# Round 1: all 34
python scripts/submit_openalpha.py

# Round 2: fix ts_returns + volume units + manual skew/kurt
python scripts/submit_openalpha_fixes.py

# Round 3: ts_zscore wrapper for skew/kurt + regression unit fix
python scripts/submit_openalpha_round3.py
```

Output files (gitignored only for the OHLCV cache; reports ARE committed):

- `WQ_OPENALPHA_RESULTS.json` — all 34 entries, ok or error.
- `WQ_OPENALPHA_REPORT.json` — survivor subset.
