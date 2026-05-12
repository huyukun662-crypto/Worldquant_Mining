# Round 20 - fix CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE on IV skew

## Results (ranked by SH)

| variant | fix | neut | SH | TO | FIT | RET | DD | checks |
|---|---|---|---:|---:|---:|---:|---:|---|
| S2_R3_SUBINDUSTRY | SUBINDUSTRY neut (finer residualization) | SUBINDUSTRY | +2.180 | 0.207 | +2.280 | +0.227 | 0.117 | 5/8 |
| S1_R3_quantile | quantile(uniform) replaces zscore | INDUSTRY | +1.530 | 0.128 | +1.100 | +0.066 | 0.037 | 5/8 |
| S3_R3_quantile_SUBIN | quantile + SUBINDUSTRY (combined) | SUBINDUSTRY | +1.510 | 0.142 | +0.990 | +0.061 | 0.034 | 4/8 |
| S5_Q1_quantile_SUBIN | Q1 30-tenor + quantile + SUBINDUSTRY | SUBINDUSTRY | +1.250 | 0.171 | +0.630 | +0.043 | 0.038 | 4/8 |
| S4_R4_quantile_SUBIN | R4 vol-wt + quantile + SUBINDUSTRY | SUBINDUSTRY | +1.020 | 0.169 | +0.490 | +0.038 | 0.040 | 3/8 |
