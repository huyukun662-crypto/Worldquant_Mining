# Round 6 - V1 neighborhood sweep

All variants use: zscore wrapper, INDUSTRY neutralization, decay=8, truncation=0.08, USA/TOP3000, delay=1.

Filter: SH > 1.25 AND FIT > 1.0 AND TO < 0.25

## V1 baseline (from Round 5)

`RRNj5MVb`: SH=+1.720  TO=0.225  FIT=+1.320  RET=+0.132  checks=7/8

## This round

| variant | perturbation | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---|---|---|---|---|---|---|
| V6_zwin3 | ts_zscore window: 5 -> 3 (shorter reversal) | +1.870 | 0.207 | +1.370 | +0.110 | 0.086 | 7/8 | **YES** |
| V7_zwin10 | ts_zscore window: 5 -> 10 (longer reversal) | +1.490 | 0.223 | +1.160 | +0.134 | 0.131 | 7/8 | **YES** |
| V8_decay15 | outer decay: 20 -> 15 (less smoothing) | +1.790 | 0.260 | +1.310 | +0.140 | 0.123 | 7/8 | no |
| V9_decay30 | outer decay: 20 -> 30 (more smoothing) | +1.620 | 0.183 | +1.330 | +0.124 | 0.124 | 7/8 | **YES** |
| V10_volz | liquidity weight: log(vol/adv20+1) -> ts_zscore(volume, 20) | +0.480 | 0.166 | +0.190 | +0.026 | 0.095 | 4/8 | no |

**Survivors: 3/5**
