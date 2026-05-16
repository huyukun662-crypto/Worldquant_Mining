# Deliverable: 97 Zero-Warning Alphas (USA TOP3000, Delay=1)

All filtered to: SH > 1.25, Turnover < 0.25, Fitness > 1.0, **zero failing checks**.

Region=USA Pasteurization=ON Language=FASTEXPR for every entry.


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

## 6. `le7l2wXx` — SH 1.91 / TO 0.057 / FIT 2.83

```
ts_corr(high, low, 1000)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 7. `qMnrplZ2` — SH 1.90 / TO 0.053 / FIT 3.09

```
ts_std_dev((close - open) / open * less(close - open, 0), 200) - ts_std_dev((close - open) / open * greater(close - open, 0), 200)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 8. `gJmEJmk0` — SH 1.89 / TO 0.046 / FIT 2.96

```
ts_std_dev((close - open) / open * less(close - open, 0), 300) - ts_std_dev((close - open) / open * greater(close - open, 0), 300)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 9. `zq5W1zW8` — SH 1.88 / TO 0.058 / FIT 2.61

```
-1 * ts_mean(power(max(ts_delta(mdl77_liquidityriskfactor_milliq, 1), 0), 2), 100) * ts_std_dev(mdl77_liquidityriskfactor_bap20d, 100) / ts_mean(mdl77_liquidityriskfactor_bap20d, 100)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 10. `2rvP17jb` — SH 1.87 / TO 0.056 / FIT 2.71

```
ts_corr(high, low, 750)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 11. `3qErvxqX` — SH 1.86 / TO 0.060 / FIT 2.86

```
ts_std_dev((close - open) / open * less(close - open, 0), 150) - ts_std_dev((close - open) / open * greater(close - open, 0), 150)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 12. `omnMOmzl` — SH 1.86 / TO 0.044 / FIT 2.90

```
ts_std_dev((close - open) / open * less(close - open, 0), 350) - ts_std_dev((close - open) / open * greater(close - open, 0), 350)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 13. `gJmMxm5l` — SH 1.85 / TO 0.058 / FIT 2.73

```
ts_corr(high, low, 1500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 14. `WjNGGVPO` — SH 1.85 / TO 0.055 / FIT 2.73

```
ts_decay_linear(ts_corr(high, low, 1000), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 15. `0mAo1ZdK` — SH 1.83 / TO 0.056 / FIT 2.61

```
ts_corr(high, low, 600)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 16. `RRN8pEMa` — SH 1.83 / TO 0.059 / FIT 2.70

```
ts_corr(high, low, 2000)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 17. `kqn2l09l` — SH 1.82 / TO 0.035 / FIT 2.78

```
ts_decay_linear(ts_std_dev((close - open) / open * less(close - open, 0), 250) - ts_std_dev((close - open) / open * greater(close - open, 0), 250), 14)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 18. `E5qE3G5P` — SH 1.81 / TO 0.043 / FIT 2.19

```
ts_corr(high, ts_delay(high, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 19. `QPndXLdG` — SH 1.80 / TO 0.035 / FIT 2.23

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 300), 3), 300)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 20. `wp5lJJJv` — SH 1.80 / TO 0.053 / FIT 2.55

```
ts_decay_linear(ts_corr(high, low, 500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 21. `9q9onM9V` — SH 1.79 / TO 0.053 / FIT 2.47

```
ts_corr(high, low, 400)
```

`Decay=4 Truncation=0.03 Neutralization=INDUSTRY`

## 22. `88OgX1Jz` — SH 1.79 / TO 0.049 / FIT 2.35

```
ts_corr(close, open, 750)
```

`Decay=2 Truncation=0.02 Neutralization=INDUSTRY`

## 23. `akNn7wKv` — SH 1.78 / TO 0.056 / FIT 2.60

```
ts_decay_linear(ts_corr(high, low, 1500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 24. `npn2mw2d` — SH 1.78 / TO 0.043 / FIT 2.11

```
ts_corr(vwap, ts_delay(high, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 25. `d5n0bzOE` — SH 1.77 / TO 0.039 / FIT 1.96

```
ts_corr(high, ts_delay(high, 10), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 26. `kqn5lmVl` — SH 1.76 / TO 0.044 / FIT 2.19

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 250), 3), 250)
```

`Decay=1 Truncation=0.03 Neutralization=INDUSTRY`

## 27. `VkXPNvaY` — SH 1.76 / TO 0.057 / FIT 2.58

```
ts_decay_linear(ts_corr(high, low, 2000), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 28. `JjnlAqae` — SH 1.73 / TO 0.054 / FIT 2.34

```
ts_corr(high, low, 350)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 29. `1YodEYkQ` — SH 1.73 / TO 0.040 / FIT 1.89

```
ts_corr(vwap, ts_delay(vwap, 10), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 30. `A1nPNMml` — SH 1.72 / TO 0.059 / FIT 2.44

```
ts_corr(vwap, low, 1000)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 31. `MPbRZbZz` — SH 1.70 / TO 0.101 / FIT 2.50

```
ts_std_dev((close - open) / open * less(close - open, 0), 60) - ts_std_dev((close - open) / open * greater(close - open, 0), 60)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 32. `1Yo6Re5z` — SH 1.69 / TO 0.043 / FIT 1.98

```
ts_corr(close, ts_delay(close, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 33. `GrnJZgjo` — SH 1.68 / TO 0.030 / FIT 1.98

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 400), 3), 400)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 34. `mLqbQ9PK` — SH 1.67 / TO 0.060 / FIT 2.36

```
ts_corr(vwap, low, 1500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 35. `LLnAjgGv` — SH 1.66 / TO 0.041 / FIT 2.83

```
ts_std_dev(low / ts_delay(close, 1) - 1, 250) - ts_std_dev(high / ts_delay(close, 1) - 1, 250)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 36. `3qERZj2O` — SH 1.66 / TO 0.045 / FIT 1.94

```
ts_corr(vwap, ts_delay(vwap, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 37. `XgknYeV8` — SH 1.65 / TO 0.044 / FIT 1.95

```
ts_corr(high, ts_delay(low, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 38. `A1nPGjkl` — SH 1.65 / TO 0.058 / FIT 2.26

```
ts_corr(vwap, low, 750)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 39. `E5qWLLOr` — SH 1.62 / TO 0.077 / FIT 2.32

```
ts_std_dev((close - open) / open * less(close - open, 0), 100) - ts_std_dev((close - open) / open * greater(close - open, 0), 100)
```

`Decay=2 Truncation=0.04 Neutralization=SUBINDUSTRY`

## 40. `QPnVQLKQ` — SH 1.62 / TO 0.036 / FIT 1.88

```
ts_decay_linear(ts_corr(high, ts_delay(high, 5), 500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 41. `78x1ZKPb` — SH 1.61 / TO 0.032 / FIT 1.71

```
ts_decay_linear(ts_corr(vwap, ts_delay(vwap, 10), 500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 42. `MPbxmlzM` — SH 1.59 / TO 0.060 / FIT 2.03

```
-1 * ts_mean(power(max(ts_delta(mdl77_liquidityriskfactor_milliq, 1), 0), 2), 100) * ts_std_dev(high - low, 100) / ts_mean(high - low, 100)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 43. `JjnOWJP2` — SH 1.59 / TO 0.035 / FIT 1.81

```
ts_decay_linear(ts_corr(vwap, ts_delay(high, 5), 500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 44. `rKbkG3LE` — SH 1.57 / TO 0.035 / FIT 2.54

```
ts_std_dev(low / ts_delay(close, 1) - 1, 400) - ts_std_dev(high / ts_delay(close, 1) - 1, 400)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 45. `vR5a685r` — SH 1.57 / TO 0.054 / FIT 1.92

```
ts_corr(close, open, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 46. `kqn05AqP` — SH 1.56 / TO 0.056 / FIT 2.04

```
ts_corr(vwap, low, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 47. `KPnnEd7p` — SH 1.55 / TO 0.042 / FIT 1.67

```
trade_when(volume > ts_mean(volume, 120), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 48. `j2n1O5KE` — SH 1.55 / TO 0.039 / FIT 1.68

```
trade_when(snt_buzz > ts_mean(snt_buzz, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 49. `d5neGpLv` — SH 1.54 / TO 0.055 / FIT 1.86

```
ts_corr(high, close, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 50. `0mAA7dLv` — SH 1.53 / TO 0.037 / FIT 1.64

```
trade_when(volume > ts_mean(volume, 60) * 1.5, -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 51. `j2ng0VvO` — SH 1.53 / TO 0.035 / FIT 1.67

```
winsorize(-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 150) / ts_mean(mdl77_liquidityriskfactor_milliq, 150) * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_bap20d, 1)), 150) / ts_mean(mdl77_liquidityriskfactor_bap20d, 150), std=3.0)
```

`Decay=4 Truncation=0.15 Neutralization=INDUSTRY`

## 52. `le7l5JGl` — SH 1.53 / TO 0.059 / FIT 1.81

```
ts_corr(high, vwap, 1000)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 53. `MPbQzn3z` — SH 1.53 / TO 0.055 / FIT 2.02

```
ts_decay_linear(ts_corr(vwap, low, 500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 54. `d5n0ExRv` — SH 1.52 / TO 0.044 / FIT 1.69

```
ts_corr(low, ts_delay(low, 5), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 55. `QPnepQVw` — SH 1.51 / TO 0.056 / FIT 1.90

```
ts_corr(high, low, 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 56. `RRNrpKna` — SH 1.51 / TO 0.039 / FIT 1.63

```
winsorize(-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100) * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_bap20d, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_bap20d, 100), std=3.0)
```

`Decay=4 Truncation=0.15 Neutralization=INDUSTRY`

## 57. `A1nPvlQR` — SH 1.51 / TO 0.039 / FIT 1.54

```
ts_corr(low, ts_delay(low, 10), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 58. `O0nOQGJb` — SH 1.50 / TO 0.097 / FIT 1.80

```
ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 59. `pwnO9bEV` — SH 1.50 / TO 0.045 / FIT 1.74

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 200), 3), 200)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 60. `wp5lz6Gp` — SH 1.50 / TO 0.057 / FIT 1.84

```
ts_corr(high, low, 200)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 61. `WjNMm87o` — SH 1.49 / TO 0.096 / FIT 1.81

```
(ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60)) - group_mean(ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60), 1, subindustry)
```

`Decay=4 Truncation=0.08 Neutralization=INDUSTRY`

## 62. `kqnrYRWd` — SH 1.49 / TO 0.054 / FIT 2.35

```
ts_std_dev(low / ts_delay(close, 1) - 1, 100) - ts_std_dev(high / ts_delay(close, 1) - 1, 100)
```

`Decay=4 Truncation=0.04 Neutralization=INDUSTRY`

## 63. `MPbw2PQ6` — SH 1.49 / TO 0.030 / FIT 2.67

```
-1 * ts_mean(power((high - low) / ts_delay(close, 1), 2), 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 64. `E5qYq82m` — SH 1.49 / TO 0.038 / FIT 1.58

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 65. `E5qqEwaJ` — SH 1.49 / TO 0.026 / FIT 1.70

```
trade_when(ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100) > ts_mean(ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), 250), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 66. `A1n65vwQ` — SH 1.48 / TO 0.029 / FIT 2.62

```
-1 * ts_mean(power((high - low) / ts_delay(close, 1), 2), 300)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 67. `npnYZkgE` — SH 1.48 / TO 0.040 / FIT 1.54

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 80) / ts_mean(mdl77_liquidityriskfactor_milliq, 80)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 68. `WjNna0GG` — SH 1.48 / TO 0.048 / FIT 1.52

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 60) / ts_mean(mdl77_liquidityriskfactor_milliq, 60)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 69. `9q9bJX5q` — SH 1.48 / TO 0.035 / FIT 1.56

```
-1 * zscore(ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100))
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 70. `RRNrM1ka` — SH 1.48 / TO 0.034 / FIT 1.58

```
trade_when(adv20 > ts_mean(adv20, 120), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 71. `kqn0JNkL` — SH 1.48 / TO 0.029 / FIT 1.35

```
ts_corr(low, ts_delay(low, 20), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 72. `XgkqM1QX` — SH 1.47 / TO 0.047 / FIT 1.36

```
-1 * ts_corr((close - open) / open, (high - low) / close, 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 73. `A1n65d5w` — SH 1.47 / TO 0.028 / FIT 2.57

```
-1 * ts_mean(power((high - low) / ts_delay(close, 1), 2), 400)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 74. `QPnnaNoX` — SH 1.47 / TO 0.036 / FIT 1.55

```
trade_when(volume < ts_mean(volume, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 75. `gJmM77mg` — SH 1.47 / TO 0.030 / FIT 1.34

```
ts_corr(vwap, ts_delay(vwap, 20), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 76. `MPbbkjwL` — SH 1.45 / TO 0.037 / FIT 1.51

```
trade_when(volume > ts_mean(volume, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 77. `0mAlMxk6` — SH 1.44 / TO 0.078 / FIT 2.12

```
-1 * ts_mean(returns * volume, 60) / ts_mean(volume, 60)
```

`Decay=4 Truncation=0.05 Neutralization=INDUSTRY`

## 78. `78x0x7RO` — SH 1.44 / TO 0.064 / FIT 1.42

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 40) / ts_mean(mdl77_liquidityriskfactor_milliq, 40)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 79. `QPnQMd9M` — SH 1.44 / TO 0.043 / FIT 1.52

```
trade_when((high - low) > ts_mean(high - low, 60), -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 80. `E5qEV1z0` — SH 1.44 / TO 0.029 / FIT 1.30

```
ts_corr(high, ts_delay(high, 20), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 81. `mLqq8wbx` — SH 1.42 / TO 0.036 / FIT 1.47

```
trade_when(returns > 0, -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 82. `MPb9ZY5M` — SH 1.41 / TO 0.056 / FIT 1.56

```
ts_corr(high, vwap, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 83. `1YodEO0Q` — SH 1.41 / TO 0.056 / FIT 1.56

```
ts_corr(vwap, high, 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 84. `LLnk3NLe` — SH 1.40 / TO 0.043 / FIT 1.43

```
trade_when(news_indx_perf > 0, -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), -1)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 85. `e7ng2OKM` — SH 1.39 / TO 0.030 / FIT 1.47

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 150) / ts_mean(mdl77_liquidityriskfactor_milliq, 150)
```

`Decay=0 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 86. `omnnVn16` — SH 1.39 / TO 0.029 / FIT 1.42

```
ts_decay_linear(-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100), 30)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 87. `akNOEEzW` — SH 1.39 / TO 0.043 / FIT 1.84

```
winsorize(-1 * ts_mean(returns * volume, 250) / ts_mean(volume, 250), std=2.0)
```

`Decay=4 Truncation=0.1 Neutralization=INDUSTRY`

## 88. `d5nnQpow` — SH 1.38 / TO 0.032 / FIT 1.47

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 60) / ts_mean(mdl77_liquidityriskfactor_milliq, 60) - ts_std_dev(mdl77_liquidityriskfactor_milliq, 250) / ts_mean(mdl77_liquidityriskfactor_milliq, 250)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 89. `3qEwlObQ` — SH 1.35 / TO 0.102 / FIT 1.32

```
-1 * ts_mean(signed_power(ts_zscore((close - open) / open, 60), 2), 60)
```

`Decay=4 Truncation=0.05 Neutralization=INDUSTRY`

## 90. `qMngAAlj` — SH 1.34 / TO 0.040 / FIT 1.30

```
-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 91. `LLnp0PV1` — SH 1.32 / TO 0.043 / FIT 1.39

```
winsorize(-1 * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_milliq, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_milliq, 100) * ts_mean(abs(ts_delta(mdl77_liquidityriskfactor_bap20d, 1)), 100) / ts_mean(mdl77_liquidityriskfactor_bap20d, 100) * ts_std_dev(high - low, 100) / ts_mean(high - low, 100) * ts_std_dev(volume, 100) / ts_mean(volume, 100) * power(rank(cap), 3), std=3.0)
```

`Decay=4 Truncation=0.1 Neutralization=INDUSTRY`

## 92. `XgkrOwda` — SH 1.29 / TO 0.076 / FIT 1.15

```
rank((ts_std_dev((close - open) / open * less(close - open, 0), 100) - ts_std_dev((close - open) / open * greater(close - open, 0), 100))) + rank((ts_mean(open / ts_delay(close, 1) - 1, 60) - ts_mean(close / open - 1, 60)))
```

`Decay=4 Truncation=0.05 Neutralization=INDUSTRY`

## 93. `QPneKexW` — SH 1.29 / TO 0.031 / FIT 1.63

```
-1 * ts_mean(power(ts_zscore((close - open) / open, 250), 4), 250)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 94. `npn28YNM` — SH 1.29 / TO 0.036 / FIT 1.34

```
ts_decay_linear(ts_corr(low, ts_delay(low, 5), 500), 20)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

## 95. `blNVVdRq` — SH 1.28 / TO 0.023 / FIT 1.35

```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 250) / ts_mean(mdl77_liquidityriskfactor_milliq, 250)
```

`Decay=4 Truncation=0.05 Neutralization=SUBINDUSTRY`

## 96. `1YobRqgX` — SH 1.27 / TO 0.067 / FIT 1.75

```
-1 * ts_mean(returns * volume, 100) / ts_mean(volume, 100)
```

`Decay=2 Truncation=0.04 Neutralization=INDUSTRY`

## 97. `GrnLJkL5` — SH 1.26 / TO 0.057 / FIT 1.35

```
ts_corr(vwap, ts_delay(vwap, 1), 500)
```

`Decay=2 Truncation=0.03 Neutralization=INDUSTRY`

