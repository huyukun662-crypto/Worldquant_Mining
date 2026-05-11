# Final viable factors — delivery

Nineteen rounds of QuantML-port iteration plus OpenAlpha port =
**110+ WQ Brain submissions** on USA TOP3000.

**Gate**: `SH > 1.3` ∧ `turnover < 0.2` ∧ `fitness > 1.0`.

## 4 viable factors

| # | factor | shape family | SH | TO | FIT | ann.ret | alpha_id |
|---|--------|--------------|---:|---:|---:|---:|----------|
| 1 | **QM_R6_01** body variance asymmetry | variance-asym (OHLC) | **1.51** | 0.06 | **2.38** | 31% | `58Ln2d05` |
| 2 | **OA24** OHLC tail asymmetry | variance-asym (OHLC) | **1.47** | 0.07 | **2.47** | 35% | `vR5wxKO3` |
| 3 | **QM_R8_03** session decomposition | mean diff (sessions) | **1.50** | 0.10 | 1.80 | 18% | `O0nOQGJb` |
| 4 | **QM_R16_05** body signed-squared mean | signed magnitude (body) | **1.35** | 0.10 | 1.32 | 12% | `3qEwlObQ` |

Plus QM_R11_05 — peer-residualised version of #3, metrics match
to 2 dp → not an independent signal.

---

## Factor 1 — QM_R6_01 (body variance asymmetry)

```text
ts_std_dev((close - open) / open * less(close - open, 0), 100)
- ts_std_dev((close - open) / open * greater(close - open, 0), 100)

settings: universe=TOP3000, delay=1, decay=4,
          neutralization=INDUSTRY, truncation=0.08
```

100-day cross-sectional asymmetric variance of intraday body. Long
names whose down-body days have more variable returns than their
up-body days.

## Factor 2 — OA24 (OHLC tail asymmetry)

```text
ts_std_dev(low  / ts_delay(close, 1) - 1, 100)
- ts_std_dev(high / ts_delay(close, 1) - 1, 100)

settings: universe=TOP3000, delay=1, decay=0,
          neutralization=INDUSTRY, truncation=0.08
```

Same shape as #1, different price channel: high/low vs prior
close (carries overnight gap + intraday extreme).

## Factor 3 — QM_R8_03 (overnight − intraday decomposition)

```text
ts_mean(open / ts_delay(close, 1) - 1, 60)
- ts_mean(close / open - 1, 60)

settings: universe=TOP3000, delay=1, decay=4,
          neutralization=SUBINDUSTRY, truncation=0.05
```

60-day mean overnight gap minus 60-day mean intraday return.
Captures the **overnight premium / intraday drift** asymmetry.

## Factor 4 — QM_R16_05 (body signed-squared mean)

```text
-1 * ts_mean(signed_power(ts_zscore(
              (close - open) / open, 60), 2), 60)

settings: universe=TOP3000, delay=1, decay=4,
          neutralization=INDUSTRY, truncation=0.05
```

Average of `sign(x) * x²` of the 60-day z-scored intraday body.
Outlier-dampened skew-like statistic. **Same input channel as #1**
but a different statistical moment (signed-magnitude mean, not
asymmetric variance).

---

## Correlation matrix (qualitative; WQ's `SELF_CORRELATION` async)

|  | #1 | #2 | #3 | #4 |
|--|----|----|----|----|
| **#1** body var asym | — | **high** (same shape) | low | **high** (same channel) |
| **#2** OHLC tail asym | high | — | low | medium |
| **#3** session decomp | low | low | — | low |
| **#4** body signed^2 | high | medium | low | — |

- **#1 ↔ #4** are on the **same OHLC body channel**; high correlation expected.
- **#3** is the structural outlier — independent of all others.

## Path summary (19 rounds)

| round | thrust | best | viable added |
|-------|--------|-----:|:------------:|
| OpenAlpha | translation pass | — | OA24 |
| R1-3 | core QuantML categories | 0.84 | — |
| R4 | OHLC pressure + composites | 0.94 | — |
| R5 | R4 tuning | 0.83 | — |
| R6 | OHLC candlestick | **1.51** | R6_01 |
| R7 | orthogonal operators | 0.44 | — |
| R8 | session decomp + omega | **1.50** | R8_03 |
| R9-10 | ratios + peer-relative | 1.07 | — |
| R11 | peer-residualisation | 1.49 | R11_05 (≈ R8_03) |
| R12 | smaller universe test | 1.13 | — (TOP3000 wins) |
| R13-14 | new shapes (CV / beta-vol / etc) | 1.07 | — |
| R15-16 | R10_04 grid search | **1.35** | R16_05 |
| R17-19 | beta-vol / shadows / autocorr | 0.94 | — (hard wall) |

## Empirical findings (110+ submissions)

1. **Hard SH ceiling ≈ 0.94 on close-to-close returns** under USA TOP3000 / INDUSTRY-neut / 0.08 truncation. Reached by R4_02 (asym vol on returns), R18_05 (same retuned), R17 (all beta-vol variants).
2. **Breaking SH = 1.25 requires the OHLC channel** — intraday body / extreme prices vs prior close. Confirmed by R6_01 (body asym, 1.51), OA24 (OHLC tail asym, 1.47), R16_05 (body signed², 1.35).
3. **Session decomposition** is the only non-variance shape that broke the gate (R8_03, 1.50). All other shape families tried (auto-corr, CV, sign-streak, rank-reversal, volume-shock, Sortino, Sharpe ratio, regime-vol ratio, peer-relative momentum, vol-managed return, omega gain/loss, crash frequency, vwap-deviation vol, body autocorr, range-body coupling, vol-direction asym) topped out below SH ≈ 1.1.
4. **Smaller universe (TOP500/TOP1000) hurt every factor** tested (R12). TOP3000 is the right granularity on this account tier.
5. **`signed_power(x, 2)` outperforms `power(x, 3)`** on the skew-style shape on this data: R10_04 (power³, 1.07) → R16_05 (signed_power², 1.35). The outlier dampening shifts SH/return tradeoff favourably.
6. **Composites (rank average / z-sum) underperformed their best component** every time (R3_05, R4_04, R5_02). Cross-sectional correlation among variance-asymmetry shapes is too high.

## Reproducing

```bash
echo '["<wq-username>","<wq-password>"]' > credential.txt && chmod 600 credential.txt

# OpenAlpha port (produces OA24 in round 1)
python scripts/submit_openalpha.py
python scripts/submit_openalpha_fixes.py
python scripts/submit_openalpha_round3.py

# QuantML port rounds 1-19
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19; do
  python scripts/submit_quantml_r${i}.py
done

# 3-factor orthogonality probe
python scripts/submit_quantml_rN.py
```

Results are written incrementally to `WQ_QUANTML_RESULTS.json` (~95
entries) and `WQ_OPENALPHA_RESULTS.json` (34 entries).
