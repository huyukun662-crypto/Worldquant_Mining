# R95 tame vol estimators

| variant | neut | trunc | SH | TO | FIT | checks | conc | sub | sc | gate |
|---|---|---:|---:|---:|---:|---|---|---|---|---|
| R95d_park_p25_d15_t004 | SUBINDUSTRY | 0.04 | +2.160 | 0.082 | +7.110 | 6/8 | F(0.249774) | P | - | no |
| R95e_park_p25_d15_IND | INDUSTRY | 0.08 | +2.080 | 0.085 | +7.250 | 6/8 | F(0.293182) | P | - | no |
| R95b_park_PV6_d15 | SUBINDUSTRY | 0.08 | +2.040 | 0.073 | +6.220 | 6/8 | F(0.187883) | P | - | no |
| R95f_rs_PV6_d15 | SUBINDUSTRY | 0.08 | +1.880 | 0.070 | +5.320 | 6/8 | F(0.179855) | P | - | no |
| R95c_park_p25_d30 | SUBINDUSTRY | 0.08 | +1.820 | 0.079 | +6.120 | 6/8 | F(0.25311) | P | - | no |
| R95h_park20_p25_d15 | SUBINDUSTRY | 0.08 | +1.790 | 0.128 | +5.840 | 6/8 | F(0.319536) | P | - | no |
| R95g_rs_p25_d15_IND | INDUSTRY | 0.08 | +1.760 | 0.080 | +5.530 | 6/8 | F(0.291328) | P | - | no |
| R95a_park_linear_d15 | SUBINDUSTRY | 0.08 | +1.300 | 0.037 | +2.330 | 7/8 | P | P | - | **YES** |

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS): 1/8**

## Survivor expressions

### R95a_park_linear_d15 -- alpha P0n361bK
SH=+1.300 TO=0.037 FIT=+2.330
```
zscore(ts_decay_linear(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 15))
```

