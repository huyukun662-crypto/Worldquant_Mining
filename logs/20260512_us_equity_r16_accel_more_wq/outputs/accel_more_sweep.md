# Round 16 - more NEW SH>=2 alphas in price-accel family

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH >= 2.0 AND FIT > 1.0 AND TO < 0.25

## Results

| variant | W | D | SH | TO | FIT | RET | DD | checks | survives? |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| H1_accel1_D20 | 1 | 20 | +2.090 | 0.224 | +2.790 | +0.400 | 0.158 | 7/8 | **YES** |
| H2_accel1_D25 | 1 | 25 | +2.110 | 0.194 | +3.080 | +0.414 | 0.217 | 7/8 | **YES** |
| H3_accel2_D30 | 2 | 30 | +2.190 | 0.176 | +3.450 | +0.437 | 0.317 | 7/8 | **YES** |
| H4_accel2_D50 | 2 | 50 | +2.100 | 0.127 | +3.940 | +0.447 | 0.366 | 7/8 | **YES** |
| H5_accel3_D60 | 3 | 60 | +2.120 | 0.117 | +4.030 | +0.452 | 0.371 | 7/8 | **YES** |

**Survivors: 5/5**
