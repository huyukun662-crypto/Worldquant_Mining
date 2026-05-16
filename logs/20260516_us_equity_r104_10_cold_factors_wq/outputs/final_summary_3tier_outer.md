# R104 ten cold factors

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |
|---|---:|---:|---:|---|---|---|---|---|---|
| C2_days_since_low | +1.060 | 0.094 | +0.720 | 5/8 | P | P | 0.109 | no | GrneRmQQ |
| C4_close_vwap_drift | +1.010 | 0.075 | +0.630 | 5/8 | P | P | 0.105 | no | qMn6QdrZ |
| C8_spearman_VR | +0.370 | 0.074 | +0.110 | 5/8 | P | P | 0.202 | no | O0nG1p3q |
| C9_vwap_dispersion | -0.130 | 0.077 | -0.030 | 5/8 | P | P | 0.270 | no | E5qGZmeL |
| C3_autocorr_1d_rev | -0.200 | 0.075 | -0.050 | 4/8 | P | F(-0.61) | 0.022 | no | mLqVEwA2 |
| C5_range_zscore_rev | -0.550 | 0.163 | -0.230 | 4/8 | P | F(-0.56) | 0.107 | no | 0mAM1r01 |
| C7_liquidity_ret_corr | -0.820 | 0.083 | -0.370 | 4/8 | P | F(-0.74) | 0.104 | no | MPbLJE1o |
| C1_days_since_high | -0.850 | 0.094 | -0.520 | 5/8 | P | P | 0.177 | no | 2rvNYvYJ |
| C6_slope60_rev | FAIL | - | - | - | - | - | - | no | - | ERROR: Got invalid value "0" for attribute "lookback", should be a positive inte
| C10_adv5_over_adv60 | FAIL | - | - | - | - | - | - | no | - | ERROR: Attempted to use unknown variable "adv5". <linkToCommonErrorMessages>Lear

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 0/10**
