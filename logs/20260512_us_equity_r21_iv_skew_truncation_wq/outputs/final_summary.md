# Round 21 - aggressive truncation + winsorize on IV skew

## Results (ranked by SH, only ok)

| variant | fix | SH | TO | FIT | conc_pass? | subuni_pass? | checks |
|---|---|---:|---:|---:|---|---|---|
| T3_trunc02_SUBIN | truncation=0.02 + SUBINDUSTRY (very aggressive) | +2.210 | 0.199 | +2.330 | FAIL (0.153846) | FAIL (0.8) | 5/8 |
| T1_trunc05_SUBIN | truncation=0.05 + SUBINDUSTRY | +2.180 | 0.206 | +2.290 | FAIL (0.153846) | FAIL (0.74) | 5/8 |
| T2_trunc03_SUBIN | truncation=0.03 + SUBINDUSTRY (aggressive) | +2.180 | 0.203 | +2.300 | FAIL (0.153846) | FAIL (0.75) | 5/8 |
| T4_winsorize_std2 | winsorize(zscore(.), std=2) -- explicit bound | +1.710 | 0.176 | +1.360 | FAIL (0.153846) | FAIL (0.38) | 5/8 |
| T5_trunc03_TOP1000 | truncation=0.03 + SUBINDUSTRY + universe=TOP1000 | +0.840 | 0.090 | +0.830 | FAIL (?) | YES | 4/8 |

**Survivors clearing all checks + SH>1.25 + TO<0.25: 0/5**
