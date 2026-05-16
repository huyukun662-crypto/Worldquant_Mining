# R104 ten cold factors

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |
|---|---:|---:|---:|---|---|---|---|---|---|
| C9_vwap_dispersion | +1.830 | 0.057 | +4.270 | 7/8 | P | P | 0.891 | no | QPn9wdEw |
| C8_spearman_VR | +0.650 | 0.187 | +0.390 | 5/8 | P | P | 0.235 | no | omngdj56 |
| C2_days_since_low | +0.480 | 0.085 | +0.290 | 5/8 | P | P | 0.231 | no | VkX3QWkG |
| C5_range_zscore_rev | -0.080 | 0.173 | -0.020 | 4/8 | P | F(-0.42) | 0.204 | no | VkX3rbnb |
| C3_autocorr_1d_rev | -0.300 | 0.067 | -0.120 | 5/8 | P | P | 0.209 | no | Grne26MZ |
| C1_days_since_high | -0.400 | 0.086 | -0.220 | 4/8 | P | F(-0.42) | 0.196 | no | mLqVnoqx |
| C7_liquidity_ret_corr | -0.950 | 0.082 | -0.680 | 4/8 | P | F(-0.94) | 0.306 | no | MPbLr7Nr |
| C4_close_vwap_drift | -1.100 | 0.093 | -2.060 | 3/8 | F(0.159226) | F(-0.78) | 0.376 | no | pwnK2vEx |
| C6_slope60_rev | FAIL | - | - | - | - | - | - | no | - | ERROR: Got invalid value "0" for attribute "lookback", should be a positive inte
| C10_adv5_over_adv60 | FAIL | - | - | - | - | - | - | no | - | ERROR: Attempted to use unknown variable "adv5". <linkToCommonErrorMessages>Lear

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 0/10**
