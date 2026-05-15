# R80 G62 fix-loop

| variant | neut | SH | TO | FIT | checks | conc | sub | sc | gate |
|---|---|---:|---:|---:|---|---|---|---|---|
| R80f_VWAPmom20_PV6 | SUBINDUSTRY | +0.980 | 0.102 | +1.450 | 6/8 | P | P | - | no |
| R80c_G62_INDUSTRY | INDUSTRY | +0.820 | 0.124 | +0.530 | 5/8 | P | P | - | no |
| R80b_rangeTS_FF5vwap | SUBINDUSTRY | +0.810 | 0.194 | +0.440 | 5/8 | P | P | - | no |
| R80a_G62_FF5vwap | SUBINDUSTRY | +0.800 | 0.187 | +0.380 | 4/8 | P | F(0.33) | - | no |
| R80d_G62_corr20 | SUBINDUSTRY | +0.700 | 0.092 | +0.390 | 5/8 | P | P | - | no |
| R80e_G62_corr5minus20 | SUBINDUSTRY | -0.040 | 0.128 | +0.000 | 4/8 | P | F(-0.42) | - | no |
| R80g_G62_tszscore60 | SUBINDUSTRY | -0.630 | 0.135 | -0.320 | 4/8 | P | F(-0.86) | - | no |
| R80h_corr_HV_over_LV | SUBINDUSTRY | -1.010 | 0.106 | -0.640 | 4/8 | P | F(-0.45) | - | no |

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
