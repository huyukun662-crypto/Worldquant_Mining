# Round 15 final - NEW alpha_ids SH>=2 TO<0.25

Variants: 5
Filter: SH>=2.0, FIT>1.0, TO<0.25
Survivors: 2/5

## Survivors (ranked by SH)

### G2_accel3_volwt_D40
- alpha_id: `78xARJo2`
- logic: 3-day acceleration, vol-weighted, D=40
- weight: log(vol/adv20+1)
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 3)), log(add(divide(volume, adv20), 1))), 40)))`
- SH=+2.110  TO=0.151  FIT=+3.610  RET=+0.443  DD=0.361
- checks: 7/8

### G1_accel2_volwt_D40
- alpha_id: `9q9v3ok1`
- logic: 2-day acceleration, vol-weighted, D=40
- weight: log(vol/adv20+1)
- expression: `zscore(reverse(ts_decay_linear(multiply(subtract(returns, ts_delay(returns, 2)), log(add(divide(volume, adv20), 1))), 40)))`
- SH=+2.100  TO=0.146  FIT=+3.630  RET=+0.437  DD=0.370
- checks: 7/8

