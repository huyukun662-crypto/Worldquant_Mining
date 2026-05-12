# Round 9 - structurally distinct alphas (no overlap)

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | logic | structure | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| S1_corr_rev | return-vol corr reversal | ts_corr inside smoothed reverse | +0.620 | 0.106 | +0.320 | +0.034 | 0.126 | 5/8 | no |
| S2_liqlong | relative-volume LONG (sustained attention) | no reverse, smoothed level signal | -1.020 | 0.171 | -0.810 | -0.106 | 0.559 | 4/8 | no |
| S3_argmin_rev | days-since-60d-low reversal | ts_arg_min inside smoothed reverse (new operator) | +0.340 | 0.065 | +0.180 | +0.033 | 0.130 | 5/8 | no |
| S4_corr_long | close-volume corr continuation (attention) | ts_corr inside smoothed NO reverse | -0.890 | 0.129 | -0.580 | -0.054 | 0.388 | 4/8 | no |

**Survivors: 0/4**
