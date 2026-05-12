# Round 22 - dynamic IV skew (time-series transformations)

## Results (ranked by SH)

| variant | logic | SH | TO | FIT | conc | sub-uni | checks |
|---|---|---:|---:|---:|---|---|---|
| U5_skew180_normalized | 180-tenor skew / its 60d std, REVERSED | +1.340 | 0.125 | +1.430 | FAIL (0.422305) | FAIL (0.2) | 5/8 |
| U2_skew30_ts_zscore_60 | 60d ts_zscore of 30-tenor IV skew, REVERSED | -0.360 | 0.216 | -0.080 | FAIL (0.187643) | FAIL (-0.32) | 3/8 |
| U1_skew180_ts_zscore_60 | 60d ts_zscore of 180-tenor IV skew, REVERSED | -0.390 | 0.196 | -0.110 | FAIL (0.155754) | FAIL (-0.21) | 3/8 |
| U3_skew180_minus_mean60 | 180-tenor skew minus its 60d mean, REVERSED | -0.570 | 0.290 | -0.240 | FAIL (0.153846) | FAIL (-0.57) | 3/8 |
| U4_skew180_ts_zscore_20 | 20d ts_zscore of 180-tenor IV skew, REVERSED | -0.650 | 0.231 | -0.210 | FAIL (0.133361) | FAIL (-0.44) | 3/8 |

**Survivors (all checks passed): 0/5**
