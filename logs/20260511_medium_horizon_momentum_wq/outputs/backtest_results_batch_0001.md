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
| 1 | mom_mean60 | -0.720 | 0.073 | -0.650 | -0.103 | 0.572 | 4/8 | `E5qORRbG` |
| 2 | mom_decay60 | -0.520 | 0.086 | -0.390 | -0.070 | 0.459 | 4/8 | `LLnVZ0z2` |
| 3 | mom_sharpe60 | -0.680 | 0.074 | -0.550 | -0.082 | 0.482 | 4/8 | `3qEQjgo6` |
| 4 | mom_mean40 | -0.530 | 0.090 | -0.400 | -0.070 | 0.408 | 4/8 | `E5qOVKMP` |
| 5 | mom_pricez60 | -0.690 | 0.107 | -0.560 | -0.083 | 0.472 | 4/8 | `58Lnj27X` |
| 6 | mom_near120high | FAIL: ERROR: Attempted to use inaccessible or unknown operator "ts | - | - | - | - | - | - |
| 7 | mom_riskadj_decay | -0.570 | 0.087 | -0.420 | -0.068 | 0.430 | 4/8 | `Xgkm9ej8` |
| 8 | mom_volwt40 | -0.510 | 0.090 | -0.380 | -0.068 | 0.398 | 4/8 | `VkX1NJXb` |
