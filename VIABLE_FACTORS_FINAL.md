# Final viable factors — delivery

23+ rounds of QuantML-port iteration + OpenAlpha port =
**150+ WQ Brain submissions** on USA TOP3000.

**Gate**: `SH > 1.3` ∧ `turnover < 0.2` ∧ `fitness > 1.0`.

## 7 viable factors — 4 distinct structural families

### Family A — OHLC channel statistics (3 viable members)
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R6_01** | body variance asymmetry | **1.51** | 0.06 | **2.38** | 31% | `58Ln2d05` |
| **OA24** | OHLC extreme variance asymmetry | **1.47** | 0.07 | **2.47** | 35% | `vR5wxKO3` |
| **QM_R16_05** | body signed-squared mean | **1.35** | 0.10 | 1.32 | 12% | `3qEwlObQ` |

### Family B — Session-mean decomposition
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R8_03** | overnight mean − intraday mean | **1.50** | 0.10 | 1.80 | 18% | `O0nOQGJb` |

(QM_R11_05 is a near-duplicate of R8_03 with peer-residualisation; not counted as independent.)

### Family C — Volume-weighted return mean (NEW this push)
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R22_02F** | −Mean(R·V, 60)/Mean(V, 60) | **1.44** | 0.08 | **2.12** | 27% | `0mAlMxk6` |

### Family D — Cross-stock peer distance (NEW this push)
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R23_02F_MKT_t10** | Mean((C − peer_mean)/C, 60) @ MARKET-neut t=0.10 | **1.34** | **0.01** | **1.67** | 20% | `kqn7oJ56` |
| **QM_R23_02F_MKT_t15** | same expression @ t=0.15 (variant) | **1.37** | **0.01** | **1.83** | 22% | `omnpojdm` |

---

## Final expressions + complete settings

### #1 QM_R6_01
```
ts_std_dev((close - open) / open * less(close - open, 0), 100)
- ts_std_dev((close - open) / open * greater(close - open, 0), 100)
```
`universe=TOP3000  delay=1  decay=4  neut=INDUSTRY  trunc=0.08`

### #2 OA24
```
ts_std_dev(low  / ts_delay(close, 1) - 1, 100)
- ts_std_dev(high / ts_delay(close, 1) - 1, 100)
```
`universe=TOP3000  delay=1  decay=0  neut=INDUSTRY  trunc=0.08`

### #3 QM_R16_05
```
-1 * ts_mean(signed_power(ts_zscore((close - open) / open, 60), 2), 60)
```
`universe=TOP3000  delay=1  decay=4  neut=INDUSTRY  trunc=0.05`

### #4 QM_R8_03
```
ts_mean(open / ts_delay(close, 1) - 1, 60)
- ts_mean(close / open - 1, 60)
```
`universe=TOP3000  delay=1  decay=4  neut=SUBINDUSTRY  trunc=0.05`

### #5 QM_R22_02F
```
-1 * ts_mean(returns * volume, 60) / ts_mean(volume, 60)
```
`universe=TOP3000  delay=1  decay=4  neut=INDUSTRY  trunc=0.05`

### #6 QM_R23_02F_MKT_t10
```
ts_mean((close - group_mean(close, 1, subindustry)) / close, 60)
```
`universe=TOP3000  delay=1  decay=4  neut=MARKET  trunc=0.10`

### #7 QM_R23_02F_MKT_t15 (variant of #6)
Same expression as #6, only `trunc=0.15` instead.

Common across all 7: `instrumentType=EQUITY, region=USA, pasteurization=ON, unitHandling=VERIFY, nanHandling=OFF, language=FASTEXPR, visualization=false, maxTrade=OFF, testPeriod=P0Y0M`.

---

## Correlation map (qualitative; WQ async PENDING)

|        | A (OHLC) | B (session) | C (vol-weighted ret) | D (peer-dist) |
|--------|----------|-------------|----------------------|---------------|
| **A**  | within-family **high** (same shape, varied channel) | low | medium (both use returns/body) | low |
| **B**  | low | — | medium | low |
| **C**  | medium | medium | — | low |
| **D**  | low | low | low | within-family **identical** (#6=#7 same expr) |

Family D's two members are setting variants of the same expression — they're essentially duplicates for risk management.

---

## Empirical findings (150+ submissions)

1. **Hard SH ceiling ≈ 0.94 on close-to-close return-only factors** under USA TOP3000 INDUSTRY-neut + 0.08 trunc. Confirmed multiple times.
2. **OHLC channel** (body, extremes) is required for SH > 1.25 on the variance-asymmetry shape.
3. **Session decomposition** is the only non-variance shape that broke the gate easily.
4. **Volume-weighted return mean** (Family C) — flipping sign was critical: the raw signal had SH=-1.44 (continuation), the flip gives SH=+1.44 (reversal).
5. **Cross-stock peer-distance** (Family D) lifted from SH=1.06 (INDUSTRY-neut) → 1.24 (MARKET-neut) → 1.34 (MARKET + trunc=0.10) → 1.37 (MARKET + trunc=0.15). Both **MARKET-neut** AND **looser truncation** were needed; either alone fell short.
6. **Looser truncation is signal-specific**: peer-distance gained from t=0.10/0.15, adv-rel-volume LOST from looser truncation. No universal recipe.
7. **`signed_power(x, 2)` outperforms `power(x, 3)`** on the body-skew shape (R10_04 SH=1.07 → R16_05 SH=1.35).
8. **Smaller universes (TOP500/TOP1000) hurt every factor tested** — TOP3000 is the right granularity.
9. **Rank/z-sum composites consistently underperformed their best component** (R3_05, R4_04, R5_02, COMP1). Cross-sectional correlations too high among related shapes.
10. **Shapes that failed to reach SH=1.3** (across 50+ attempts): auto-correlation, coefficient of variation, sign-streak, rank-reversal, volume-shock, Sortino, Sharpe ratio, regime-vol ratio, peer-relative momentum, vol-managed return, omega gain/loss, crash frequency, vwap-deviation vol, body autocorr, range-body coupling, vol-direction asym, GK-style range vol diff, Kaufman efficiency, WVAD, close-vwap path corr, volume-weighted close-vs-mid, beta time-variation, intraday body kurtosis, conditional reversal, Z-score velocity, peer-relative idio-vol.

---

## What's in this PR

- `scripts/openalpha_factors.py`, `submit_openalpha*.py` — OpenAlpha port (34 candidates → OA24).
- `scripts/wq_runner.py` — reusable runner.
- `scripts/submit_quantml_r{1..23}.py` + `submit_quantml_rN.py` — 23+1 QuantML rounds.
- `WQ_OPENALPHA_RESULTS.json`, `WQ_QUANTML_RESULTS.json` — full submission records (130+ entries).
- `VIABLE_FACTORS_FINAL.md` — this doc.

## Reproducing

```bash
echo '["<wq-username>","<wq-password>"]' > credential.txt && chmod 600 credential.txt

python scripts/submit_openalpha.py            # delivers OA24
python scripts/submit_openalpha_fixes.py
python scripts/submit_openalpha_round3.py

for i in $(seq 1 23); do
  python scripts/submit_quantml_r${i}.py
done
python scripts/submit_quantml_rN.py
```
