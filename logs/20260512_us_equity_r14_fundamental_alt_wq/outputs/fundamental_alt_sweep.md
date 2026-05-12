# Round 14 - fundamental + alternative-data factor families

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1, nanHandling=ON.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | family | field | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| F1_value_btm | value | `bookvalue_ps` | +0.470 | 0.029 | +0.370 | +0.079 | 0.403 | 3/8 | no |
| F2_quality_roe | quality | `return_equity` | -0.070 | 0.040 | -0.020 | -0.010 | 0.325 | 4/8 | no |
| F3_earnings_revision | earnings_momentum | `snt1_d1_earningsrevision` | FAIL | - | - | - | - | - | no |
| F4_lowvol | low_vol_anomaly | `historical_volatility_60` | +0.230 | 0.047 | +0.160 | +0.058 | 0.827 | 4/8 | no |
| F5_nettarget_revision | analyst_targets | `snt1_d1_nettargetpercent` | FAIL | - | - | - | - | - | no |

**Survivors: 0/5**

**Distinct families covered: 0** (none)
