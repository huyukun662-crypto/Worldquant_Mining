# Round 15 - NEW alpha_ids passing SH>=2.0, TO<0.25

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH >= 2.0 AND FIT > 1.0 AND TO < 0.25

Reference: R12/W1 (gJmA8a7m): SH=+2.050 TO=0.171; R12/W2 (YPNr7w6J): SH=+2.030 TO=0.123

## Results

| variant | logic | weight | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| G1_accel2_volwt_D40 | 2-day acceleration, vol-weighted, D=40 | log(vol/adv20+1) | +2.100 | 0.146 | +3.630 | +0.437 | 0.370 | 7/8 | **YES** |
| G2_accel3_volwt_D40 | 3-day acceleration, vol-weighted, D=40 | log(vol/adv20+1) | +2.110 | 0.151 | +3.610 | +0.443 | 0.361 | 7/8 | **YES** |
| G3_accel5_volwt_D40 | 5-day relative move, vol-weighted, D=40 | log(vol/adv20+1) | +1.990 | 0.157 | +3.210 | +0.409 | 0.351 | 7/8 | no |
| G4_accel1_range_D40 | 1-day accel x intraday range (compound), D=40 | (high-low)/close | +0.590 | 0.139 | +0.600 | +0.144 | 0.436 | 5/8 | no |
| G5_accel1_volz_D40 | 1-day accel x ts_zscore(volume, 60) (alt vol weight), D=40 | ts_zscore(volume, 60) | +1.230 | 0.108 | +1.380 | +0.156 | 0.264 | 6/8 | no |

**Survivors: 2/5**
