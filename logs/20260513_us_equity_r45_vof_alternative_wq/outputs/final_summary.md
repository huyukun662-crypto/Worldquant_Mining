# R45 vof alternatives

| variant | logic | SH | TO | FIT | conc | passes? |
|---|---|---:|---:|---:|---|---|
| UU4_realized_retvol | realized return vol (denser than vol-of-vol) | +2.290 | 0.159 | +4.580 | PASS | **YES** |
| UU2_ts_mean_vol | use ts_mean(vol/adv20) -- denser than std_dev | +1.870 | 0.165 | +3.370 | FAIL(0.310097) | no |
| UU3_vol_level_ratio | current vol / 60d mean vol level | +1.600 | 0.131 | +2.690 | PASS | no |
| UU1_winsorize_vof | winsorize vof at std=3 | +1.200 | 0.175 | +1.550 | PASS | no |
| UU5_vol_quantile | ts_quantile 0.9 of vol/adv20 -- top decile vol | FAIL | - | - | - | no |

**Survivors: 1/5**
