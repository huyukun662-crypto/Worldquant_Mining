# R91 orthogonal bases (PARTIAL -- 6/8, auth failed on rest)

| variant | SH | TO | FIT | checks | conc | sub | gate |
|---|---:|---:|---:|---|---|---|---|
| R91d_no_outer_zscore | +1.180 | 0.099 | +1.990 | 6/8 | P | P | no |
| R91e_power_after_smooth | +1.120 | 0.104 | +1.790 | 6/8 | P | P | no |
| R91c_MA20_rev_p25 | +1.020 | 0.151 | +1.480 | 6/8 | P | P | no |
| R91b_tszscore60_rev | +0.830 | 0.104 | +0.720 | 5/8 | P | P | no |
| R91f_log_MA60_rev | +0.280 | 0.098 | +0.230 | 5/8 | P | P | no |
| R91a_MACD_short_long | +0.270 | 0.083 | +0.210 | 5/8 | P | P | no |

Notes:
- R91d (MA60 base, no outer zscore) = SH 1.18 conc PASS (ties prior MA60 ceiling).
- All other orthogonal bases (MACD, ts_zscore, MA20, log, MA20/MA60) underperform MA60.
- R91g (ts_rank reversed) + R91h (vol-adj Bollinger) not run due to auth fail.
