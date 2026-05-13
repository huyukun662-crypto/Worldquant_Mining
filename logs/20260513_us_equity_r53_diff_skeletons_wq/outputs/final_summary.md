# R53 different skeletons

| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |
|---|---|---:|---:|---:|---|---|---|
| BBB5_reverse_inside | reverse INSIDE: smooth(reversed_signal) | +2.150 | 0.191 | +2.790 | PASS | PASS | **YES** |
| BBB3_signed_power | signed_power transform of accel signal | +2.040 | 0.158 | +3.440 | PASS | PASS | **YES** |
| BBB1_ts_sum_smoothing | ts_sum instead of ts_decay_linear | +1.990 | 0.156 | +2.650 | PASS | PASS | **YES** |
| BBB2_scale_no_decay | scale wrapper + NO decay (instant signal) | +1.780 | 0.761 | +0.760 | PASS | PASS | no |
| BBB4_group_neutralize_inner | group_neutralize inner signal first | +1.090 | 0.236 | +0.920 | PASS | PASS | no |

**Survivors: 3/5**
