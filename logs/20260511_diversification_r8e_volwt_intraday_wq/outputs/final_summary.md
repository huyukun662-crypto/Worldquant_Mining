# Round 8e final - vol-weighted intraday reversal

Variants: 4
Filter: SH>1.3, FIT>1.0, TO<0.2
Survivors: 2/4

## Survivors (ranked by SH)

### M17_volwt_D20_IND
- alpha_id: `GrnPdaXQ`
- expression: `zscore(reverse(ts_decay_linear(multiply(divide(subtract(close, open), open), log(add(divide(volume, adv20), 1))), 20)))`
- neutralization: INDUSTRY
- notes: intraday * vol weight, 20d decay (lower TO)
- SH=+1.670  TO=0.168  FIT=+2.200  RET=+0.291  DD=0.179
- checks: 7/8

### M16_volwt_D15_IND
- alpha_id: `A1n9l85R`
- expression: `zscore(reverse(ts_decay_linear(multiply(divide(subtract(close, open), open), log(add(divide(volume, adv20), 1))), 15)))`
- neutralization: INDUSTRY
- notes: intraday * vol weight, 15d decay (mid -- sweet spot probe)
- SH=+1.460  TO=0.197  FIT=+1.660  RET=+0.254  DD=0.188
- checks: 7/8

