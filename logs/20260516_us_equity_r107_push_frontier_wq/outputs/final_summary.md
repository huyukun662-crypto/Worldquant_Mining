# R107 push frontier

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |
|---|---:|---:|---:|---|---|---|---|---|---|
| R107a_c03_park2 | +1.750 | 0.077 | +3.500 | 7/8 | P | P | 0.749 | no | blNQpPEm |
| R107g_c03_park3 | +1.740 | 0.068 | +3.510 | 7/8 | P | P | pending | **YES** | d5nZgevj |
| R107b_c04_park2 | +1.730 | 0.083 | +3.430 | 7/8 | P | P | 0.686 | **YES** | 1YopvX8W |
| R107c_c05_park25 | +1.730 | 0.083 | +3.430 | 7/8 | P | P | pending | **YES** | E5qGo5R0 |
| R107d_c05_park2_d10 | +1.720 | 0.097 | +3.410 | 7/8 | P | P | pending | **YES** | d5nZebLv |
| R107e_c05_park2_d12 | +1.720 | 0.093 | +3.410 | 7/8 | P | P | pending | **YES** | XgkowqWX |
| R107h_c05_park2_IND | +1.630 | 0.084 | +3.200 | 7/8 | P | P | pending | **YES** | 88Op7Xea |
| R107f_c05_park_C9 | +1.620 | 0.082 | +3.040 | 7/8 | P | P | pending | **YES** | KPnGYV9N |

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 7/8**

## Survivor expressions

### R107g_c03_park3 -- alpha d5nZgevj
SH=+1.740 TO=0.068 FIT=+3.510 SC={}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.3), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 3)), 15))
```

### R107b_c04_park2 -- alpha 1YopvX8W
SH=+1.730 TO=0.083 FIT=+3.430 SC={'A1nnxAdw': 0.6863, '9q9o0zme': 0.5385}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.4), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 15))
```

### R107c_c05_park25 -- alpha E5qGo5R0
SH=+1.730 TO=0.083 FIT=+3.430 SC={}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.5), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2.5)), 15))
```

### R107d_c05_park2_d10 -- alpha d5nZebLv
SH=+1.720 TO=0.097 FIT=+3.410 SC={}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.5), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 10))
```

### R107e_c05_park2_d12 -- alpha XgkowqWX
SH=+1.720 TO=0.093 FIT=+3.410 SC={}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.5), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 12))
```

### R107h_c05_park2_IND -- alpha 88Op7Xea
SH=+1.630 TO=0.084 FIT=+3.200 SC={}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.5), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 15))
```

### R107f_c05_park_C9 -- alpha KPnGYV9N
SH=+1.620 TO=0.082 FIT=+3.040 SC={}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.5), add(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), zscore(reverse(ts_std_dev(divide(close, vwap), 60))))), 15))
```

