# Round 16 final - more NEW SH>=2 alphas

Variants: 5
Filter: SH>=2.0, FIT>1.0, TO<0.25
Survivors: 5/5

## Survivors (ranked by SH)

### H3_accel2_D30
- alpha_id: `LLnjQ5x6`
- W=2 D=30
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 2)), log(add(divide(volume, adv20), 1))), 30)))`
- SH=+2.190  TO=0.176  FIT=+3.450  RET=+0.437  DD=0.317
- checks: 7/8

### H5_accel3_D60
- alpha_id: `88OoMr3V`
- W=3 D=60
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 3)), log(add(divide(volume, adv20), 1))), 60)))`
- SH=+2.120  TO=0.117  FIT=+4.030  RET=+0.452  DD=0.371
- checks: 7/8

### H2_accel1_D25
- alpha_id: `QPnJ8XAr`
- W=1 D=25
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 1)), log(add(divide(volume, adv20), 1))), 25)))`
- SH=+2.110  TO=0.194  FIT=+3.080  RET=+0.414  DD=0.217
- checks: 7/8

### H4_accel2_D50
- alpha_id: `LLnjQ0le`
- W=2 D=50
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 2)), log(add(divide(volume, adv20), 1))), 50)))`
- SH=+2.100  TO=0.127  FIT=+3.940  RET=+0.447  DD=0.366
- checks: 7/8

### H1_accel1_D20
- alpha_id: `zq5MxbNX`
- W=1 D=20
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 1)), log(add(divide(volume, adv20), 1))), 20)))`
- SH=+2.090  TO=0.224  FIT=+2.790  RET=+0.400  DD=0.158
- checks: 7/8

