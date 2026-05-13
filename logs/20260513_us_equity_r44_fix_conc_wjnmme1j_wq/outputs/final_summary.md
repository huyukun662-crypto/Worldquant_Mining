# R44 fix CONCENTRATED_WEIGHT

| variant | logic | SH | TO | FIT | conc | passes? |
|---|---|---:|---:|---:|---|---|
| SS2_trunc04_IND | trunc=0.04 INDUSTRY | +1.860 | 0.152 | +3.660 | FAIL(0.321294) | no |
| SS1_trunc05_IND | trunc=0.05 INDUSTRY | +1.850 | 0.152 | +3.710 | FAIL(0.34204) | no |
| SS3_trunc04_SUBIN | trunc=0.04 SUBINDUSTRY | +1.680 | 0.152 | +3.200 | FAIL(0.338483) | no |
| SS4_quantile_IND | quantile(uniform) wrapper | +0.660 | 0.164 | +0.320 | PASS | no |
| SS5_winsorize_trunc05 | winsorize(std=3) + trunc=0.05 | +0.410 | 0.213 | +0.250 | PASS | no |

**Survivors: 0/5**
