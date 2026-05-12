# Round 28 - NEW alphas SH>=1.75 TO<0.2 FIT>1.25

## Results (ranked by SH)

| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| CC2_accel2_D35 | accel(W=2) vol-weighted, D=35 (bridge 30/40) | +2.120 | 0.160 | +3.490 | +0.433 | 0.359 | 7/8 | **YES** |
| CC3_accel2_D45 | accel(W=2) vol-weighted, D=45 (bridge 40/50) | +2.100 | 0.136 | +3.790 | +0.443 | 0.367 | 7/8 | **YES** |
| CC1_accel4_D40 | accel(W=4) vol-weighted, D=40 (extend W beyond {1,2,3}) | +2.060 | 0.154 | +3.470 | +0.438 | 0.366 | 7/8 | **YES** |
| CC4_accel_x_intraday | accel(W=1) x (close-open)/open compound, D=40 (no vol weight) | +1.380 | 0.072 | +2.660 | +0.465 | 0.655 | 7/8 | no |
| CC5_accel_x_histvol | accel(W=1) x historical_volatility_20, D=40 (alt vol weight) | +1.170 | 0.391 | +0.920 | +0.242 | 0.369 | 3/8 | no |

**Survivors: 3/5**
