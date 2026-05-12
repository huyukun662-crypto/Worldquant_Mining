# Round 12 final - price-acceleration smoothing

Variants: 4
Filter: SH>1.3, FIT>1.0, TO<0.2
Survivors: 3/4

## Survivors (ranked by SH)

### W1_acc_volwt_D30
- alpha_id: `gJmA8a7m`
- logic: price-acc vol-weighted, decay 30
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 1)), log(add(divide(volume, adv20), 1))), 30)))`
- SH=+2.050  TO=0.171  FIT=+3.200  RET=+0.418  DD=0.295
- checks: 7/8

### W2_acc_volwt_D50
- alpha_id: `YPNr7w6J`
- logic: price-acc vol-weighted, decay 50
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 1)), log(add(divide(volume, adv20), 1))), 50)))`
- SH=+2.030  TO=0.123  FIT=+3.820  RET=+0.443  DD=0.308
- checks: 7/8

### W3_acc_volwt_D80
- alpha_id: `xAe6j7jW`
- logic: price-acc vol-weighted, decay 80 (heavy smoothing)
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 1)), log(add(divide(volume, adv20), 1))), 80)))`
- SH=+1.950  TO=0.093  FIT=+3.690  RET=+0.446  DD=0.313
- checks: 7/8

