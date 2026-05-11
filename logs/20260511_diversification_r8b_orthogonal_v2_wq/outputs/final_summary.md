# Round 8b final - orthogonal mechanisms v2

Variants: 5
Filter: SH>1.35, FIT>1.0, TO<0.15
Survivors: 1/5
Distinct families covered: 1

## Survivors (ranked by SH, grouped by family)

### Family: L_liquidity_flow

#### M1_liqflip_w20D10
- alpha_id: `9q9YREA2`
- expression: `zscore(reverse(ts_decay_linear(divide(subtract(adv20, ts_delay(adv20, 20)), ts_delay(adv20, 20)), 10)))`
- notes: 20d delta in adv20, REVERSED; rising-liquidity stocks underperform
- SH=+1.530  TO=0.131  FIT=+2.030  RET=+0.231  DD=0.198
- checks: 6/8

