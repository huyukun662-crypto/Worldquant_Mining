# R48 NEW logic families

| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |
|---|---|---:|---:|---:|---|---|---|
| WW2_rv_intraday_volwt | rv x intraday x volwt rev | +2.050 | 0.153 | +3.720 | PASS | PASS | **YES** |
| WW1_rv_reversal_volwt | rv x reversal x volwt rev (vol-amplified reversal) | +1.830 | 0.195 | +2.140 | PASS | PASS | **YES** |
| WW3_range_accel_volwt | range x accel x volwt rev (range-amplified accel) | +1.790 | 0.162 | +2.970 | PASS | PASS | **YES** |
| WW4_absret_reversal_volwt | abs(returns) x reversal x volwt rev | +1.520 | 0.151 | +1.970 | PASS | PASS | no |
| WW5_rv_range_volwt | rv x range x volwt rev (no return direction) | +1.440 | 0.084 | +2.590 | PASS | PASS | no |

**Fully-passing survivors: 3/5**
