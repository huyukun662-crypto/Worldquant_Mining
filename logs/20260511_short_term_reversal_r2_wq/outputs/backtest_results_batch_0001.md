# Backtest Results - batch_0001

Settings:
```json
{
  "instrumentType": "EQUITY",
  "region": "USA",
  "universe": "TOP3000",
  "delay": 1,
  "decay": 8,
  "neutralization": "INDUSTRY",
  "truncation": 0.08,
  "pasteurization": "ON",
  "unitHandling": "VERIFY",
  "nanHandling": "OFF",
  "language": "FASTEXPR",
  "visualization": false,
  "maxTrade": "OFF",
  "testPeriod": "P0Y0M"
}
```

| # | id | SH | TO | FIT | RET | DD | checks | alpha_id |
|---|----|----|----|-----|-----|----|---|---|
| 1 | r2_volwt_decay20 | +1.510 | 0.219 | +0.960 | +0.089 | 0.085 | 6/8 | `LLnVnzEm` |
| 2 | r2_zscore10_decay16 | +1.420 | 0.274 | +0.890 | +0.107 | 0.061 | 6/8 | `npnx31d8` |
| 3 | r2_tsrank10_decay16 | +1.370 | 0.260 | +0.820 | +0.092 | 0.060 | 6/8 | `WjN19n6j` |
| 4 | r2_volwt_decay30 | +1.410 | 0.174 | +0.960 | +0.081 | 0.090 | 6/8 | `akNjoxz6` |
| 5 | r2_vwap_decay20 | +0.610 | 0.152 | +0.330 | +0.045 | 0.096 | 5/8 | `QPnZQXmr` |
| 6 | r2_volnorm_decay16 | +0.770 | 0.152 | +0.520 | +0.070 | 0.102 | 5/8 | `3qEQAlVg` |
| 7 | r2_zscore10_volwt_decay20 | +1.320 | 0.216 | +0.850 | +0.089 | 0.082 | 6/8 | `E5qOwAkm` |
| 8 | r2_volnorm_zscore_decay20 | +0.980 | 0.244 | +0.480 | +0.059 | 0.094 | 5/8 | `1Yok77GK` |
