# R49 fundamental new structures

| variant | logic | SH | TO | FIT | conc | sub-uni | passes? |
|---|---|---:|---:|---:|---|---|---|
| XX4_trade_when_cf | trade_when cashflow_op>0: do reversal (TRADE_WHEN structure) | +1.590 | 0.588 | +0.570 | PASS | PASS | no |
| XX5_rank_of_ranks | divide(rank(E/P), rank(asset_growth)) -- cross-sectional only | +0.530 | 0.044 | +0.360 | PASS | FAIL(-0.93) | no |
| XX1_EP_reversal | E/P x reversal smoothed (fundamental-weighted PV reversal) | +0.420 | 0.282 | +0.200 | PASS | FAIL(0.1) | no |
| XX2_ROE_accel | ROE x accel smoothed (quality-weighted PV accel) | -0.360 | 0.360 | -0.150 | FAIL(0.144214) | PASS | no |
| XX3_EP_yoy_change | 1-year change in E/P (NO decay, NO reverse) | -0.380 | 0.055 | -0.270 | FAIL(0.116145) | PASS | no |

**Survivors: 0/5**
