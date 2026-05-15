# R63 novel skeletons (target SH>=1.5 ^ TO<0.20)

| variant | SH | TO | FIT | conc | sub | passes? |
|---|---:|---:|---:|---|---|---|
| BB_gk_range_rev | +1.310 | 0.053 | +2.380 | P | P | no |
| EE_vol_of_vol_rev | +0.600 | 0.044 | +0.550 | P | P | no |
| GG_price_vwap_gap_rev | +0.030 | 0.136 | +0.000 | P | F(-0.05) | no |
| FF_rolling_self_sharpe | -0.220 | 0.084 | -0.110 | P | P | no |
| AA_amihud_illiq_rev | FAIL | - | - | - | - | no |  WARNING: Incompatible unit for input of "add" at index 1, expected "Unit[CSPrice
| CC_skew_returns_rev | FAIL | - | - | - | - | no |  ERROR: Attempted to use inaccessible or unknown operator "ts_skewness". <linkToC
| DD_drawdown60_rev | FAIL | - | - | - | - | no |  ERROR: Attempted to use inaccessible or unknown operator "ts_max". <linkToCommon
| HH_directional_efficiency | FAIL | - | - | - | - | no |  WARNING: Incompatible unit for input of "add" at index 1, expected "Unit[TSPrice

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
