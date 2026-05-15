# R77 pure PV (no close/open/returns)

| variant | SH | TO | FIT | checks | conc | sub | gate |
|---|---:|---:|---:|---|---|---|---|
| R77c_G62_neg_corrH_rankV | +0.880 | 0.127 | +0.540 | 5/8 | P | P | no |
| R77d_G90_neg_rank_corrRV | +0.810 | 0.130 | +0.430 | 5/8 | P | P | no |
| R77f_G141_neg_rank_corrHV | +0.770 | 0.118 | +0.360 | 5/8 | P | P | no |
| R77h_range_TS_5o60_rev | +0.610 | 0.094 | +0.450 | 5/8 | P | P | no |
| R77e_G109_range_smooth_ratio | -0.250 | 0.171 | -0.090 | 4/8 | P | F(-0.21) | no |
| R77g_G177_dayssince_high_rev | -0.620 | 0.094 | -0.410 | 4/8 | P | F(-0.44) | no |
| R77b_G42_rankStdH_corrHV | -1.010 | 0.103 | -0.680 | 4/8 | P | F(-0.73) | no |
| R77a_G13_sqrtHL_minus_vwap | FAIL | - | - | - | - | - | no |  WARNING: Incompatible unit for input of "subtract" at index 1, expected "Unit[CS

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
