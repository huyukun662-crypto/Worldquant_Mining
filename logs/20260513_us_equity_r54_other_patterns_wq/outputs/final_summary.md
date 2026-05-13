# R54 other patterns

| variant | logic | SH | TO | FIT | conc | sub | passes? |
|---|---|---:|---:|---:|---|---|---|
| CCC1_range_x_clstrength | range*close-strength (pure intraday geometry, no returns) | +0.750 | 0.070 | +0.870 | P | P | no |
| CCC3_close_vs_vwap | close vs vwap deviation, reversed | +0.110 | 0.149 | +0.030 | P | F(-0.0) | no |
| CCC5_vol_ratio_direct | ts_std_dev(returns,5)/ts_std_dev(returns,60) -- standalone, no accel | +0.050 | 0.118 | +0.010 | P | F(-0.46) | no |
| CCC2_volume_acceleration | 1d change in volume/adv20 (no returns) | -0.360 | 0.324 | -0.110 | F(0.11949) | F(-0.6) | no |
| CCC4_rank_returns_minus_rank_vol | rank(returns) - rank(volume) -- pure XS, no decay | -1.150 | 0.225 | -0.760 | P | F(-1.08) | no |

**Survivors: 0/5**
