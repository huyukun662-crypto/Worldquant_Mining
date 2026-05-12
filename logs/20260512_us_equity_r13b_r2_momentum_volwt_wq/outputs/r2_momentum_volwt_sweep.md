# Round 13b - vol-weighted long-horizon mean reversion

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

Reference: R13/X4 (raw): SH=+0.710 TO=0.043 FIT=+0.900

## Results

| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| Y1_x4_volwt_D20 | X4 vol-weighted, decay 20 | +0.920 | 0.056 | +1.290 | +0.247 | 0.367 | 5/8 | no |
| Y2_x4_volwt_D50 | X4 vol-weighted, decay 50 | +0.830 | 0.042 | +1.130 | +0.231 | 0.349 | 5/8 | no |
| Y3_x5_volwt_D20 | X5 (12-1 skip-month) vol-weighted REVERSED, decay 20 | -0.100 | 0.094 | -0.040 | -0.019 | 0.518 | 3/8 | no |

**Survivors: 0/3**
