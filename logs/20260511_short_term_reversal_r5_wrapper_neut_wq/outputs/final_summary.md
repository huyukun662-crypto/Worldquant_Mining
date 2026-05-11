# Round 5 final - wrapper x neutralization

Variants: 5 (5 wrapper/neut combos, expression core fixed)
Survivors: 3/5

## Best alpha (DELIVERABLE)
- variant: V1_zscore_IND
- alpha_id: `RRNj5MVb`
- expression: `zscore(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 20)))`
- settings: wrapper=zscore, neutralization=INDUSTRY, decay=8, truncation=0.08, universe=TOP3000, delay=1
- SH=+1.720  TO=0.225  FIT=+1.320  RET=+0.132
