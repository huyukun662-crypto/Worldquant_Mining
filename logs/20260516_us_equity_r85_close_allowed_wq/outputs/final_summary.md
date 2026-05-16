# R85 close-allowed re-entry

| variant | SH | TO | FIT | checks | conc | sub | sc | gate |
|---|---:|---:|---:|---|---|---|---|---|
| R85b_MA60_reversion_PV6 | +1.000 | 0.072 | +1.390 | 6/8 | P | P | - | no |
| R85a_close_ret20_rev_PV6 | +0.850 | 0.097 | +1.250 | 5/8 | P | F(0.31) | - | no |
| R85d_zscore_close_rev_PV6 | +0.710 | 0.070 | +0.570 | 5/8 | P | P | - | no |
| R85e_bollinger_pct_rev_PV6 | -0.030 | 0.116 | -0.010 | 4/8 | F(0.499669) | P | - | no |
| R85f_VW_return_PV6 | -0.400 | 0.115 | -0.360 | 4/8 | F(0.102229) | P | - | no |
| R85c_close_over_vwap_PV6 | -0.500 | 0.170 | -0.410 | 5/8 | P | P | - | no |
| R85h_close_vol_corr20_PV6 | -0.690 | 0.087 | -0.410 | 4/8 | P | F(-0.7) | - | no |
| R85g_dist_from_60d_high_PV6 | FAIL | - | - | - | - | - | - | no |  ERROR: Attempted to use inaccessible or unknown operator "ts_max". <linkToCommon

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
