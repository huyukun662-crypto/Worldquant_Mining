# Round 5 - wrapper x neutralization sweep

Core (under wrapper): `reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 20))`

Filter: SH > 1.25 AND FIT > 1.0 AND TO < 0.25

## R2 baseline (for reference)

`rank` wrapper / INDUSTRY -> SH=1.510 TO=0.219 FIT=0.960  (FIT only)

## This round

| variant | wrapper | neut | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---|---|---|---|---|---|---|---|
| V1_zscore_IND | zscore | INDUSTRY | +1.720 | 0.225 | +1.320 | +0.132 | 0.121 | 7/8 | **YES** |
| V2_scale_IND | scale | INDUSTRY | +1.680 | 0.225 | +1.320 | +0.138 | 0.122 | 7/8 | **YES** |
| V3_rank_MARKET | rank | MARKET | +1.280 | 0.222 | +0.910 | +0.112 | 0.103 | 6/8 | no |
| V4_rank_NONE | rank | NONE | +0.830 | 0.089 | +1.460 | +0.388 | 0.696 | 6/8 | no |
| V5_zscore_MARKET | zscore | MARKET | +1.530 | 0.230 | +1.250 | +0.153 | 0.155 | 7/8 | **YES** |

**Survivors: 3/5**
