# R51 truly new structures

| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |
|---|---|---:|---:|---:|---|---|---|
| ZZ3_vol_ratio_accel | ts_std_dev(ret,5)/ts_std_dev(ret,60) x accel x volwt rev | +1.930 | 0.176 | +2.630 | PASS | PASS | **YES** |
| ZZ2_nested_zscore | ts_zscore(ts_zscore(returns,5),20) x volwt rev | +1.600 | 0.221 | +1.030 | PASS | PASS | no |
| ZZ5_sign_mag_decomp | sign(returns) x abs(accel) x volwt rev | +1.460 | 0.154 | +1.650 | PASS | PASS | no |
| ZZ1_revdiff_5m20 | differential: ts_zscore(returns,5)-ts_zscore(returns,20) x volwt rev | -0.470 | 0.187 | -0.200 | PASS | PASS | no |
| ZZ4_xs_rank_diff | rank(ts_zscore(returns,5)) - rank(volume/adv20) -- pure XS | -1.560 | 0.437 | -0.670 | PASS | FAIL(-1.55) | no |

**Survivors: 1/5**
