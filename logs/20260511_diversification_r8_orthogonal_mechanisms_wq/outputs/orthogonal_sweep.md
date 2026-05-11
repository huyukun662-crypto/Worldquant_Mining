# Round 8 - orthogonal-mechanism sweep

3 mechanisms (intraday range, overnight gap, liquidity flow), 5 variants.
Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.35 AND FIT > 1.0 AND TO < 0.15

## Results

| variant | mechanism | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| N1a_range_zwin20_D20 | intraday range compression | -0.510 | 0.185 | -0.220 | -0.033 | 0.206 | 4/8 | no |
| N1b_range_zwin5_D30 | intraday range compression | -0.870 | 0.225 | -0.380 | -0.044 | 0.260 | 4/8 | no |
| N2a_overnight_D5 | overnight gap mean reversion | +0.220 | 0.313 | +0.070 | +0.028 | 0.237 | 5/8 | no |
| N2b_overnight_D20 | overnight gap mean reversion | -0.170 | 0.156 | -0.060 | -0.021 | 0.264 | 5/8 | no |
| N3_liqflow_D10 | liquidity flow momentum | -1.530 | 0.131 | -2.030 | -0.231 | 1.176 | 3/8 | no |

**Survivors: 0/5**
