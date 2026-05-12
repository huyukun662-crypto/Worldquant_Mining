# Round 10 - vol-weighted corr/argmin

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| T1_corr_ret_volwt_rev | return-vol corr reversal, vol-weighted | +0.760 | 0.092 | +0.460 | +0.045 | 0.115 | 5/8 | no |
| T2_corr_close_volwt_rev | close-volume corr reversal, vol-weighted | FAIL | - | - | - | - | - | no |
| T3_argmin_volwt_rev | days-since-60d-low reversal, vol-weighted | +0.350 | 0.081 | +0.180 | +0.034 | 0.152 | 5/8 | no |
| T4_argmax_volwt_rev | days-since-60d-high reversal, vol-weighted (probe) | -0.580 | 0.076 | -0.410 | -0.063 | 0.366 | 4/8 | no |

**Survivors: 0/4**
