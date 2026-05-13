# R39 NEW PV alphas (target SH>=1.75 TO<0.2 FIT>1.25)

| variant | logic | SH | TO | FIT | survives? |
|---|---|---:|---:|---:|---|
| NN4_volofvol_rev | volume-of-volume (std-dev of relative volume), REVERSED | +1.560 | 0.087 | +2.270 | no |
| NN5_ret_range_volwt_rev | returns x range x vol-weight, REVERSED (compound triple) | +1.510 | 0.175 | +2.500 | no |
| NN2_jerk_volwt_rev | 3rd derivative (jerk) of price, vol-weighted, REVERSED | +1.160 | 0.185 | +1.140 | no |
| NN3_rangepos_accel_volwt_rev | range-position acceleration, vol-weighted, REVERSED | +0.840 | 0.220 | +0.350 | no |
| NN1_range_volwt_rev | daily range / close, vol-weighted, REVERSED (range mean-reversion) | +0.750 | 0.103 | +0.940 | no |
