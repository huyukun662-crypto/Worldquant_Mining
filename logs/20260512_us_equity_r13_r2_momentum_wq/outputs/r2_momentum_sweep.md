# Round 13 - R^2 momentum family on USA TOP3000

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Reference (R4 finding): 40-120d momentum LONG is dead on TOP3000 (7/8 negative SH)

## Results

| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| X1_mom252_long | pure 252d cumulative return, LONG (no reverse) | -0.710 | 0.043 | -0.900 | -0.200 | 1.282 | 3/8 | no |
| X2_mom12_1_long | 12-1 skip-month momentum, LONG (Asness convention) | -0.110 | 0.090 | -0.050 | -0.021 | 0.491 | 4/8 | no |
| X3_riskadj_mom252_long | risk-adjusted 252d momentum (returns / std_dev), LONG | -0.550 | 0.046 | -0.540 | -0.119 | 0.861 | 4/8 | no |
| X4_mom252_reversed | 252d cumulative return REVERSED (long-horizon mean reversion) | +0.710 | 0.043 | +0.900 | +0.200 | 0.371 | 4/8 | no |
| X5_mom12_1_reversed | 12-1 skip-month REVERSED (mean reversion w/ skip) | FAIL | - | - | - | - | - | no |

**Survivors: 0/5**
