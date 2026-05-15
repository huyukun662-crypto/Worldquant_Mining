# R64 amplify BB + fix unit/operator errors

| variant | SH | TO | FIT | conc | sub | passes? |
|---|---:|---:|---:|---|---|---|
| OO_BB_w60_D60 | +1.320 | 0.035 | +2.390 | P | P | no |
| II_BB_decay60 | +1.300 | 0.041 | +2.370 | P | P | no |
| LL_amihud_ratio | +0.990 | 0.044 | +0.970 | P | F(0.36) | no |
| MM_close_zscore60_rev | +0.590 | 0.060 | +0.430 | P | P | no |
| PP_close_in_range_rev | +0.400 | 0.074 | +0.200 | P | F(0.01) | no |
| KK_BB_x_logvol | -0.650 | 0.117 | -0.860 | P | F(-0.52) | no |
| JJ_BB_x_revmom5 | -0.860 | 0.238 | -0.760 | F(0.104509) | F(-0.69) | no |
| NN_skew_via_moment3 | FAIL | - | - | - | - | no |  ERROR: Attempted to use inaccessible or unknown operator "ts_moment". <linkToCom

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
