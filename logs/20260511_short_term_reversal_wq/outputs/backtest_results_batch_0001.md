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
| 1 | stm_rev_mean5 | +0.910 | 0.304 | +0.560 | +0.115 | 0.134 | 5/8 | `6XRm3K0G` |
| 2 | stm_rev_decay8 | +0.880 | 0.268 | +0.570 | +0.111 | 0.131 | 5/8 | `O0nQkO0v` |
| 3 | stm_rev_zscore10 | +1.970 | 0.686 | +0.970 | +0.165 | 0.075 | 6/8 | `Grn16wrG` |
| 4 | stm_rev_volcond | +0.960 | 0.306 | +0.590 | +0.115 | 0.123 | 5/8 | `9q9ZKMQx` |
| 5 | stm_rev_volnorm | +1.330 | 0.397 | +0.750 | +0.127 | 0.115 | 6/8 | `akNjP37v` |
| 6 | stm_rev_vwap | +1.200 | 0.325 | +0.660 | +0.099 | 0.084 | 5/8 | `rKbpzlP1` |
| 7 | stm_rev_tsrank10 | +1.950 | 0.688 | +0.930 | +0.155 | 0.069 | 6/8 | `9q9Z6eZK` |
| 8 | stm_rev_volwt_decay | +1.660 | 0.324 | +0.950 | +0.106 | 0.095 | 6/8 | `1Yoknw6K` |
