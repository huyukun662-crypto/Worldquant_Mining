# R50 fundamental settings tune

| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |
|---|---|---:|---:|---:|---|---|---|
| YY3_tradewhen_CF_TOP500 | trade_when CF rev / TOP500 / SUBIN | +0.900 | 0.654 | +0.270 | PASS | PASS | no |
| YY5_earnQ_TOP200_pastOFF | earnings_quality / TOP200 / SUBIN / past=OFF | +0.720 | 0.046 | +0.580 | FAIL(0.21402) | FAIL(?) | no |
| YY1_eps_D60_TOP500_SUBIN | actual_eps D=60 / TOP500 / SUBIN / trunc=0.04 | -0.030 | 0.021 | +0.000 | FAIL(0.266926) | PASS | no |
| YY2_eps_D60_TOP200_SUBIN | actual_eps D=60 / TOP200 / SUBIN / trunc=0.04 | -0.220 | 0.020 | -0.100 | FAIL(0.323149) | FAIL(?) | no |
| YY4_EP_accel_TOP500_SUBIN | E/P x accel D=25 / TOP500 / SUBIN / trunc=0.04 | -0.430 | 0.370 | -0.190 | FAIL(0.10296) | FAIL(-0.37) | no |

**Survivors: 0/5**
