# R98 delta-vol + nonlin + unit-fixed

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate |
|---|---:|---:|---:|---|---|---|---|---|
| R98g_ind_rel_vol_PV6 | +0.590 | 0.046 | +0.710 | 3/8 | F(0.152749) | F(-0.01) | 0.813 | no |
| R98d_drv5_p25_rev | +0.460 | 0.181 | +0.490 | 3/8 | F(0.164547) | F(0.03) | 0.249 | no |
| R98b_drv10_PV6_rev | +0.430 | 0.169 | +0.420 | 4/8 | F(0.17513) | P | 0.233 | no |
| R98a_drv5_PV6_rev | +0.400 | 0.179 | +0.360 | 3/8 | F(0.109661) | F(-0.02) | 0.235 | no |
| R98f_vol_volume_corr | +0.150 | 0.047 | +0.040 | 4/8 | P | F(-0.43) | 0.455 | no |
| R98h_rank_RV_rev | +0.080 | 0.024 | +0.030 | 4/8 | P | F(-0.0) | 0.460 | no |
| R98c_dpark5_PV6_rev | -0.560 | 0.176 | -0.790 | 3/8 | F(0.36938) | F(-0.35) | 0.206 | no |
| R98e_semi_var_ratio | FAIL | - | - | - | - | - | - | no |  WARNING: Incompatible unit for input of "add" at index 1, expected "Unit[TSPrice

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 0/8**
