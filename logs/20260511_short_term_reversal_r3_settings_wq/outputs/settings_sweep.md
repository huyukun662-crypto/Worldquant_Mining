# Round 3 - Settings sweep on `r2_volwt_decay20`

Expression: `rank(reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 20)))`

Filter: SH > 1.25 AND FIT > 1.0 AND TO < 0.25

## Round-2 baseline (for reference)

trunc=0.08, decay=8, INDUSTRY  -> SH=1.510 TO=0.219 FIT=0.960  (FIT only)

## This round

| variant | trunc | decay | neut | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---|---|---|---|---|---|---|---|---|
| A_trunc08_decay0_IND | 0.08 | 0 | INDUSTRY | +1.960 | 0.525 | +0.980 | +0.132 | 0.078 | 6/8 | no |
| B_trunc05_decay0_IND | 0.05 | 0 | INDUSTRY | +1.960 | 0.525 | +0.980 | +0.132 | 0.078 | 6/8 | no |
| C_trunc03_decay0_IND | 0.03 | 0 | INDUSTRY | +1.960 | 0.525 | +0.980 | +0.132 | 0.078 | 6/8 | no |
| D_trunc05_decay0_SUBIN | 0.05 | 0 | SUBINDUSTRY | +2.050 | 0.533 | +0.970 | +0.119 | 0.062 | 6/8 | no |
| E_trunc03_decay0_SUBIN | 0.03 | 0 | SUBINDUSTRY | +2.050 | 0.533 | +0.970 | +0.119 | 0.062 | 6/8 | no |

**Survivors: 0/5**
