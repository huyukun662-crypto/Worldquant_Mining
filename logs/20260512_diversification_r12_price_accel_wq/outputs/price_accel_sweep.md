# Round 12 - price-acceleration smoothing sweep

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Reference: R11/U3 (raw price-acc, D=20): SH=+1.230 TO=0.581

## Results

| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| W1_acc_volwt_D30 | price-acc vol-weighted, decay 30 | +2.050 | 0.171 | +3.200 | +0.418 | 0.295 | 7/8 | **YES** |
| W2_acc_volwt_D50 | price-acc vol-weighted, decay 50 | +2.030 | 0.123 | +3.820 | +0.443 | 0.308 | 7/8 | **YES** |
| W3_acc_volwt_D80 | price-acc vol-weighted, decay 80 (heavy smoothing) | +1.950 | 0.093 | +3.690 | +0.446 | 0.313 | 7/8 | **YES** |
| W4_acc_raw_D80 | price-acc raw (no vol-weight), decay 80 -- baseline | +1.900 | 0.513 | +1.640 | +0.383 | 0.155 | 7/8 | no |

**Survivors: 3/4**
