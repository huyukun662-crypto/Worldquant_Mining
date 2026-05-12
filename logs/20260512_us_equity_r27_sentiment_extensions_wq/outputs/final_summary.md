# Round 27 - extend AA4 social-sentiment alpha

Reference: AA4 (snt_social_value LONG D=20): SH=+0.340 conc=PASS sub=PASS 0.45

## Results (ranked by SH)

| variant | logic | SH | TO | FIT | conc | sub-uni | checks |
|---|---|---:|---:|---:|---|---|---|
| BB3_social_volume_long | snt_social_volume LONG (alt sentiment field) | +0.630 | 0.141 | +0.290 | PASS | PASS | 5/8 |
| BB4_compound_value_plus_volume | snt_social_value + snt_social_volume compound | +0.570 | 0.140 | +0.250 | PASS | PASS | 5/8 |
| BB1_social_value_D40 | snt_social_value LONG D=40 (more smoothing) | +0.390 | 0.100 | +0.160 | PASS | PASS | 5/8 |
| BB2_social_value_D10 | snt_social_value LONG D=10 (less smoothing) | +0.280 | 0.190 | +0.070 | PASS | PASS | 5/8 |
| BB5_ts_zscore_social_value | 60d ts_zscore of snt_social_value LONG | -0.120 | 0.153 | -0.020 | PASS | PASS | 5/8 |

**Pass all checks + SH>0.2: 4/5**
