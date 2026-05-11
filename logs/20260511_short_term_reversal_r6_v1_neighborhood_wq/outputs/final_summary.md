# Round 6 final - V1 neighborhood

Variants: 5 (expression perturbations around V1)
Survivors under SH>1.25, FIT>1.0, TO<0.25: 3

## All survivors (ranked by SH)

### V6_zwin3
- alpha_id: `QPnZ8l6p`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 3), log(add(divide(volume, adv20), 1))), 20)))`
- perturbation: ts_zscore window: 5 -> 3 (shorter reversal)
- SH=+1.870  TO=0.207  FIT=+1.370  RET=+0.110  DD=0.086
- checks: 7/8

### V9_decay30
- alpha_id: `KPnlWb9j`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 30)))`
- perturbation: outer decay: 20 -> 30 (more smoothing)
- SH=+1.620  TO=0.183  FIT=+1.330  RET=+0.124  DD=0.124
- checks: 7/8

### V7_zwin10
- alpha_id: `RRNjgP9n`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 10), log(add(divide(volume, adv20), 1))), 20)))`
- perturbation: ts_zscore window: 5 -> 10 (longer reversal)
- SH=+1.490  TO=0.223  FIT=+1.160  RET=+0.134  DD=0.131
- checks: 7/8

