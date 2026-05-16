# Deliverable: 66 Zero-Warning Alphas (USA TOP3000, Delay=1)

All filtered to: SH > 1.25, Turnover < 0.25, Fitness > 1.0, **zero failing checks**.

All settings: Region=USA, Pasteurization=ON, Language=FASTEXPR.


## 1. `N1nmZvj7` — SH 1.94 / TO 0.049 / FIT 3.08

```
ts_std_dev((close - open) / open * less(close - open, 0), 250) - ts_std_dev((close - open) / open * greater(close - open, 0), 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 2. `rKbvv1qm` — SH 1.94 / TO 0.050 / FIT 3.13

```
((ts_std_dev((close - open) / open * less(close - open, 0), 150) - ts_std_dev((close - open) / open * greater(close - open, 0), 150)) + (ts_std_dev((close - open) / open * less(close - open, 0), 250) - ts_std_dev((close - open) / open * greater(close - open, 0), 250)) + (ts_std_dev((close - open) / open * less(close - open, 0), 400) - ts_std_dev((close - open) / open * greater(close - open, 0), 400))) / 3
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 3. `KPnxl0XE` — SH 1.94 / TO 0.050 / FIT 2.69

```
ts_corr(high, low, 500)
```

`Decay=2 Truncation=0.02 Neutralization=INDUSTRY`

## 4. `e7nwXjpz` — SH 1.93 / TO 0.043 / FIT 3.19

```
ts_std_dev((close - open) / open * less(close - open, 0), 400) - ts_std_dev((close - open) / open * greater(close - open, 0), 400)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 5. `A1nMjJXE` — SH 1.92 / TO 0.041 / FIT 3.17

```
ts_std_dev((close - open) / open * less(close - open, 0), 500) - ts_std_dev((close - open) / open * greater(close - open, 0), 500)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 6. `qMnrplZ2` — SH 1.90 / TO 0.053 / FIT 3.09

```
ts_std_dev((close - open) / open * less(close - open, 0), 200) - ts_std_dev((close - open) / open * greater(close - open, 0), 200)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 7. `gJmEJmk0` — SH 1.89 / TO 0.046 / FIT 2.96

```
ts_std_dev((close - open) / open * less(close - open, 0), 300) - ts_std_dev((close - open) / open * greater(close - open, 0), 300)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 8. `zq5W1zW8` — SH 1.88 / TO 0.058 / FIT 2.61

```
-1 * ts_mean(power(max(ts_delta(mdl77_liquidityriskfactor_milliq, 1), 0), 2), 100) * ts_std_dev(mdl77_liquidityriskfactor_bap20d, 100) / ts_mean(mdl77_liquidityriskfactor_bap20d, 100)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 9. `2rvP17jb` — SH 1.87 / TO 0.056 / FIT 2.71

```
ts_corr(high, low, 750)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 10. `3qErvxqX` — SH 1.86 / TO 0.060 / FIT 2.86

```
ts_std_dev((close - open) / open * less(close - open, 0), 150) - ts_std_dev((close - open) / open * greater(close - open, 0), 150)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 11. `omnMOmzl` — SH 1.86 / TO 0.044 / FIT 2.90

```
ts_std_dev((close - open) / open * less(close - open, 0), 350) - ts_std_dev((close - open) / open * greater(close - open, 0), 350)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 12. `0mAo1ZdK` — SH 1.83 / TO 0.056 / FIT 2.61

```
ts_corr(high, low, 600)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 13. `kqn2l09l` — SH 1.82 / TO 0.035 / FIT 2.78

```
ts_decay_linear(ts_std_dev((close - open) / open * less(close - open, 0), 250) - ts_std_dev((close - open) / open * greater(close - open, 0), 250), 14)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 14. `QPndXLdG` — SH 1.80 / TO 0.035 / FIT 2.23

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 300), 3), 300)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 15. `9q9onM9V` — SH 1.79 / TO 0.053 / FIT 2.47

```
ts_corr(high, low, 400)
```

`Decay=4 Truncation=0.03 Neutralization=INDUSTRY`

## 16. `88OgX1Jz` — SH 1.79 / TO 0.049 / FIT 2.35

```
ts_corr(close, open, 750)
```

`Decay=2 Truncation=0.02 Neutralization=INDUSTRY`

## 17. `kqn5lmVl` — SH 1.76 / TO 0.044 / FIT 2.19

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 250), 3), 250)
```

`Decay=1 Truncation=0.03 Neutralization=INDUSTRY`

## 18. `JjnlAqae` — SH 1.73 / TO 0.054 / FIT 2.34

```
ts_corr(high, low, 350)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 19. `MPbRZbZz` — SH 1.70 / TO 0.101 / FIT 2.50

```
ts_std_dev((close - open) / open * less(close - open, 0), 60) - ts_std_dev((close - open) / open * greater(close - open, 0), 60)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 20. `1Yo6Re5z` — SH 1.69 / TO 0.043 / FIT 1.98

```
ts_corr(close, ts_delay(close, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 21. `GrnJZgjo` — SH 1.68 / TO 0.030 / FIT 1.98

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 400), 3), 400)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 22. `LLnAjgGv` — SH 1.66 / TO 0.041 / FIT 2.83

```
ts_std_dev(low / ts_delay(close, 1) - 1, 250) - ts_std_dev(high / ts_delay(close, 1) - 1, 250)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 23. `E5qWLLOr` — SH 1.62 / TO 0.077 / FIT 2.32

```
ts_std_dev((close - open) / open * less(close - open, 0), 100) - ts_std_dev((close - open) / open * greater(close - open, 0), 100)
```

`Decay=2 Truncation=0.04 Neutralization=SUBINDUSTRY`

## 24. `MPbxmlzM` — SH 1.59 / TO 0.060 / FIT 2.03

```
-1 * ts_mean(power(max(ts_delta(mdl77_liquidityriskfactor_milliq, 1), 0), 2), 100) * ts_std_dev(high - low, 100) / ts_mean(high - low, 100)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 25. `rKbkG3LE` — SH 1.57 / TO 0.035 / FIT 2.54

```
ts_std_dev(low / ts_delay(close, 1) - 1, 400) - ts_std_dev(high / ts_delay(close, 1) - 1, 400)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 26. `vR5a685r` — SH 1.57 / TO 0.054 / FIT 1.92

```
ts_corr(close, open, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 27. `KPnnEd7p` — SH 1.55 / TO 0.042 / FIT 1.67

```
trade_when(volume > ts_mean(volume, 120), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 28. `j2n1O5KE` — SH 1.55 / TO 0.039 / FIT 1.68

```
trade_when(snt_buzz > ts_mean(snt_buzz, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 29. `d5neGpLv` — SH 1.54 / TO 0.055 / FIT 1.86

```
ts_corr(high, close, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 30. `0mAA7dLv` — SH 1.53 / TO 0.037 / FIT 1.64

```
trade_when(volume > ts_mean(volume, 60) * 1.5, -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 31. `j2ng0VvO` — SH 1.53 / TO 0.035 / FIT 1.67

```
winsorize(-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 150) / ts_mean(mdl77_liquidityriskfactor_milliq, 150) * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_bap20d, 1)), 150) / ts_mean(mdl77_liquidityriskfactor_bap20d, 150), std=3.0)
```

`Decay=4 Truncation=0.15 Neutralization=INDUSTRY`

## 32. `QPnepQVw` — SH 1.51 / TO 0.056 / FIT 1.90

```
ts_corr(high, low, 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 33. `RRNrpKna` — SH 1.51 / TO 0.039 / FIT 1.63

```
winsorize(-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100) * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_bap20d, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_bap20d, 100), std=3.0)
```

`Decay=4 Truncation=0.15 Neutralization=INDUSTRY`

## 34. `O0nOQGJb` — SH 1.50 / TO 0.097 / FIT 1.80

```
ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 35. `pwnO9bEV` — SH 1.50 / TO 0.045 / FIT 1.74

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 200), 3), 200)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 36. `WjNMm87o` — SH 1.49 / TO 0.096 / FIT 1.81

```
(ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60)) - group_mean(ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60), 1, subindustry)
```

`Decay=4 Truncation=0.08 Neutralization=INDUSTRY`

## 37. `kqnrYRWd` — SH 1.49 / TO 0.054 / FIT 2.35

```
ts_std_dev(low / ts_delay(close, 1) - 1, 100) - ts_std_dev(high / ts_delay(close, 1) - 1, 100)
```

`Decay=4 Truncation=0.04 Neutralization=INDUSTRY`

## 38. `MPbw2PQ6` — SH 1.49 / TO 0.030 / FIT 2.67

```
-1 * ts_mean(power((high - low) / ts_delay(close, 1), 2), 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 39. `E5qYq82m` — SH 1.49 / TO 0.038 / FIT 1.58

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 40. `E5qqEwaJ` — SH 1.49 / TO 0.026 / FIT 1.70

```
trade_when(ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100) > ts_mean(ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), 250), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 41. `A1n65vwQ` — SH 1.48 / TO 0.029 / FIT 2.62

```
-1 * ts_mean(power((high - low) / ts_delay(close, 1), 2), 300)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 42. `npnYZkgE` — SH 1.48 / TO 0.040 / FIT 1.54

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 80) / ts_mean(mdl77_liquidityriskfactor_milliq, 80)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 43. `WjNna0GG` — SH 1.48 / TO 0.048 / FIT 1.52

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 60) / ts_mean(mdl77_liquidityriskfactor_milliq, 60)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 44. `9q9bJX5q` — SH 1.48 / TO 0.035 / FIT 1.56

```
-1 * zscore(ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100))
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 45. `RRNrM1ka` — SH 1.48 / TO 0.034 / FIT 1.58

```
trade_when(adv20 > ts_mean(adv20, 120), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 46. `XgkqM1QX` — SH 1.47 / TO 0.047 / FIT 1.36

```
-1 * ts_corr((close - open) / open, (high - low) / close, 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 47. `A1n65d5w` — SH 1.47 / TO 0.028 / FIT 2.57

```
-1 * ts_mean(power((high - low) / ts_delay(close, 1), 2), 400)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 48. `QPnnaNoX` — SH 1.47 / TO 0.036 / FIT 1.55

```
trade_when(volume < ts_mean(volume, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 49. `MPbbkjwL` — SH 1.45 / TO 0.037 / FIT 1.51

```
trade_when(volume > ts_mean(volume, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 50. `0mAlMxk6` — SH 1.44 / TO 0.078 / FIT 2.12

```
-1 * ts_mean(returns * volume, 60) / ts_mean(volume, 60)
```

`Decay=4 Truncation=0.05 Neutralization=INDUSTRY`

## 51. `78x0x7RO` — SH 1.44 / TO 0.064 / FIT 1.42

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 40) / ts_mean(mdl77_liquidityriskfactor_milliq, 40)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 52. `QPnQMd9M` — SH 1.44 / TO 0.043 / FIT 1.52

```
trade_when((high - low) > ts_mean(high - low, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 53. `mLqq8wbx` — SH 1.42 / TO 0.036 / FIT 1.47

```
trade_when(returns > 0, -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 54. `MPb9ZY5M` — SH 1.41 / TO 0.056 / FIT 1.56

```
ts_corr(high, vwap, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 55. `LLnk3NLe` — SH 1.40 / TO 0.043 / FIT 1.43

```
trade_when(news_indx_perf > 0, -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 56. `e7ng2OKM` — SH 1.39 / TO 0.030 / FIT 1.47

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 150) / ts_mean(mdl77_liquidityriskfactor_milliq, 150)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 57. `omnnVn16` — SH 1.39 / TO 0.029 / FIT 1.42

```
ts_decay_linear(-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), 30)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 58. `akNOEEzW` — SH 1.39 / TO 0.043 / FIT 1.84

```
winsorize(-1 * ts_mean(returns * volume, 250) / ts_mean(volume, 250), std=2.0)
```

`Decay=4 Truncation=0.1 Neutralization=INDUSTRY`

## 59. `d5nnQpow` — SH 1.38 / TO 0.032 / FIT 1.47

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 60) / ts_mean(mdl77_liquidityriskfactor_milliq, 60) - ts_std_dev(mdl77_liquidityriskfactor_milliq, 250) / ts_mean(mdl77_liquidityriskfactor_milliq, 250)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 60. `3qEwlObQ` — SH 1.35 / TO 0.102 / FIT 1.32

```
-1 * ts_mean(signed_power(ts_zscore((close - open) / open, 60), 2), 60)
```

`Decay=4 Truncation=0.05 Neutralization=INDUSTRY`

## 61. `qMngAAlj` — SH 1.34 / TO 0.040 / FIT 1.30

```
-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 62. `LLnp0PV1` — SH 1.32 / TO 0.043 / FIT 1.39

```
winsorize(-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100) * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_bap20d, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_bap20d, 100) * ts_std_dev(high - low, 100) / ts_mean(high - low, 100) * ts_std_dev(volume, 100) / ts_mean(volume, 100) * power(rank(cap), 3), std=3.0)
```

`Decay=4 Truncation=0.1 Neutralization=INDUSTRY`

## 63. `XgkrOwda` — SH 1.29 / TO 0.076 / FIT 1.15

```
rank((ts_std_dev((close - open) / open * less(close - open, 0), 100) - ts_std_dev((close - open) / open * greater(close - open, 0), 100))) + rank((ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60)))
```

`Decay=4 Truncation=0.05 Neutralization=INDUSTRY`

## 64. `QPneKexW` — SH 1.29 / TO 0.031 / FIT 1.63

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 250), 4), 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 65. `blNVVdRq` — SH 1.28 / TO 0.023 / FIT 1.35

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 250) / ts_mean(mdl77_liquidityriskfactor_milliq, 250)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 66. `1YobRqgX` — SH 1.27 / TO 0.067 / FIT 1.75

```
-1 * ts_mean(returns * volume, 100) / ts_mean(volume, 100)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

