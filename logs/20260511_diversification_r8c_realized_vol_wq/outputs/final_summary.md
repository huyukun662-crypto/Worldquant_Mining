# Round 8c final - realized-vol family

Variants: 5
Filter: SH>1.3, FIT>1.0, TO<0.2
Survivors: 1/5
Distinct families covered: 1

## Survivors (ranked by SH, grouped by family)

### Family: L_liquidity_flow

#### M10_liqflip_w30D10
- alpha_id: `2rvMNKmP`
- expression: `zscore(reverse(ts_decay_linear(divide(subtract(adv20, ts_delay(adv20, 30)), ts_delay(adv20, 30)), 10)))`
- notes: 30d delta in adv20, REVERSED (bridge between M1=20d and M2=60d)
- SH=+1.520  TO=0.110  FIT=+2.200  RET=+0.263  DD=0.211
- checks: 5/8

