# Round 25 - Model category fields

## Results (ranked by SH)

| variant | logic | field | SH | TO | FIT | conc | sub-uni | checks |
|---|---|---|---:|---:|---:|---|---|---|
| Z1_low_beta | low-beta anomaly: SPY beta REVERSED | `beta_last_60_days_spy` | +0.010 | 0.122 | +0.000 | FAIL (?) | PASS | 4/8 |
| Z2_low_distress | low-distress quality: distress_risk_measure REVERSED | `distress_risk_measure` | FAIL | - | - | - | - | - |
| Z3_equity_value_score | proprietary value composite LONG | `equity_value_score` | FAIL | - | - | - | - | - |
| Z4_fcfyield_forward_roe | FCF yield x forward ROE LONG (value x quality) | `fcf_yield_times_forward_roe` | FAIL | - | - | - | - | - |
| Z5_consensus_rating | analyst consensus rating LONG | `consensus_analyst_rating` | FAIL | - | - | - | - | - |

**Pass all checks + SH>0.5: 0/5**
