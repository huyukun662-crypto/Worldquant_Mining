# Round 26 - new account field access probe

## Results

| variant | logic | SH | TO | FIT | conc | sub-uni | status |
|---|---|---:|---:|---:|---|---|---|
| AA1_earnings_quality | cashflow_op / income LONG (V3 retry) | +0.670 | 0.039 | +0.430 | PASS | FAIL (-0.42) | ok |
| AA2_asset_growth_rev | 252d asset growth REVERSED (P5 retry) | +0.520 | 0.033 | +0.450 | FAIL (0.164825) | PASS | ok |
| AA3_correlation_60d_rev | 60d corr w/ SPY REVERSED (low-corr LONG) | -0.100 | 0.124 | -0.020 | FAIL (?) | PASS | ok |
| AA4_social_sent_long | snt_social_value LONG (Q3 retry) | +0.340 | 0.143 | +0.110 | PASS | PASS | ok |
| AA5_BM_long | book-to-market LONG (cheap stocks) | +0.460 | 0.031 | +0.340 | FAIL (0.221822) | FAIL (0.02) | ok |
