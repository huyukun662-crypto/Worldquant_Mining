# Round 7 final - low-turnover sweep

Variants: 5 (extend outer ts_decay_linear)
Filter: SH>1.35, FIT>1.0, TO<0.15
Survivors: 4/5

## Survivors (ranked by SH)

### V11_zwin3_D40_wqd8
- alpha_id: `npn9Mx8l`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 3), log(add(divide(volume, adv20), 1))), 40)))`
- SH=+1.710  TO=0.148  FIT=+1.430  RET=+0.103  DD=0.096
- checks: 7/8

### V12_zwin3_D50_wqd8
- alpha_id: `6XR7Om3p`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 3), log(add(divide(volume, adv20), 1))), 50)))`
- SH=+1.700  TO=0.135  FIT=+1.510  RET=+0.106  DD=0.107
- checks: 7/8

### V15_zwin3_D30_wqd12
- alpha_id: `vR58Vdow`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 3), log(add(divide(volume, adv20), 1))), 30)))`
- SH=+1.590  TO=0.140  FIT=+1.290  RET=+0.092  DD=0.087
- checks: 7/8

### V14_zwin5_D60_wqd8
- alpha_id: `GrnPvvpP`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 60)))`
- SH=+1.470  TO=0.130  FIT=+1.420  RET=+0.120  DD=0.169
- checks: 7/8

