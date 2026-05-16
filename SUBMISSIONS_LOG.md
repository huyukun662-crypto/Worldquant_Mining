# R107b SUBMITTED

alpha_id: 1YopvX8W
name: R107b_close04_park2_SH173
status: ACTIVE (was UNSUBMITTED -> POST /submit returned HTTP 201)
date: 2026-05-16

## Metrics
- SH: 1.73
- TO: 0.083
- FIT: 3.43
- Returns: 49.04%
- DD: 29.72%

## Self-correlation (vs portfolio at submit time)
- vs A1nnxAdw (SH 1.86): 0.6863
- vs 9q9o0zme (SH 2.33): pending (likely 0.5)

## Expression
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.4), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 15))
```

## Settings
- region: USA, universe: TOP3000
- delay: 1, decay: 8, truncation: 0.08
- neutralization: SUBINDUSTRY, pasteurization: ON

## Mining lineage
R102 (blend pattern discovery, R102g SH 1.51)
-> R105 (C9 substitution, R105c SH 1.46)
-> R106 (vol estimator + ratio search, R106g SH 1.69 SC 0.63)
-> R107 (frontier push, R107b SH 1.73 SC 0.69) **SUBMITTED**

