# Round 7 - low-turnover sweep (raised bar)

All variants: zscore wrapper, INDUSTRY, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.35 AND FIT > 1.0 AND TO < 0.15

## Reference points

- R6/V6 `QPnZ8l6p` (zwin=3, D=20, wqd=8): SH=+1.870 TO=0.207
- R6/V9 `KPnlWb9j` (zwin=5, D=30, wqd=8): SH=+1.620 TO=0.183
- R5/V1 `RRNj5MVb` (zwin=5, D=20, wqd=8): SH=+1.720 TO=0.225

## This round

| variant | zwin | outer | wq_decay | SH | TO | FIT | RET | DD | checks | survives? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| V11_zwin3_D40_wqd8 | 3 | 40 | 8 | +1.710 | 0.148 | +1.430 | +0.103 | 0.096 | 7/8 | **YES** |
| V12_zwin3_D50_wqd8 | 3 | 50 | 8 | +1.700 | 0.135 | +1.510 | +0.106 | 0.107 | 7/8 | **YES** |
| V13_zwin5_D40_wqd8 | 5 | 40 | 8 | +1.540 | 0.158 | +1.340 | +0.120 | 0.135 | 7/8 | no |
| V14_zwin5_D60_wqd8 | 5 | 60 | 8 | +1.470 | 0.130 | +1.420 | +0.120 | 0.169 | 7/8 | **YES** |
| V15_zwin3_D30_wqd12 | 3 | 30 | 12 | +1.590 | 0.140 | +1.290 | +0.092 | 0.087 | 7/8 | **YES** |

**Survivors: 4/5**
