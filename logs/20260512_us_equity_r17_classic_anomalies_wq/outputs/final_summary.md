# Round 17 - classical fundamental anomalies

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1, nanHandling=ON.

## Results (ranked by |SH|)

| variant | anomaly | SH | TO | FIT | RET | DD | checks |
|---|---|---:|---:|---:|---:|---:|---|
| P5_asset_growth_rev | Asset growth (Cooper-Gulen-Schill 2008) | +0.480 | 0.033 | +0.420 | +0.097 | 0.422 | 4/8 |
| P4_fcf_yield | FCF yield (cashflow_op - capex) / EV | +0.210 | 0.079 | +0.110 | +0.034 | 0.528 | 3/8 |
| P2_gross_profitability | Gross profitability (Novy-Marx 2013) | +0.110 | 0.019 | +0.030 | +0.011 | 0.210 | 4/8 |
| P1_accruals_rev | Accruals (Sloan 1996) | +0.030 | 0.024 | +0.010 | +0.004 | 0.547 | 4/8 |
| P3_earnings_yield | Earnings yield (Basu 1977) | FAIL | - | - | - | - | - |
