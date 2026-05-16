# R106 blend frontier

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |
|---|---:|---:|---:|---|---|---|---|---|---|
| R106g_close05x_parkx2 | +1.690 | 0.087 | +3.310 | 7/8 | P | P | 0.630 | **YES** | O0nGaRYv |
| R106f_close_parkx3 | +1.610 | 0.092 | +3.100 | 7/8 | P | P | 0.554 | **YES** | gJm8p3Qm |
| R106h_close_parkx2_d10 | +1.550 | 0.108 | +2.980 | 7/8 | P | P | pending | **YES** | VkXGo92G |
| R106e_close_park_C9_triple | +1.490 | 0.094 | +2.750 | 7/8 | P | P | 0.472 | **YES** | j2n6mvxe |
| R106a_close_RSx2 | +1.470 | 0.096 | +2.730 | 7/8 | P | P | 0.482 | **YES** | xAeN8jPW |
| R106b_close_YZx2 | +1.460 | 0.098 | +2.720 | 7/8 | P | P | 0.477 | **YES** | VkXGjWrJ |
| R106c_close_rangeCx2 | +1.430 | 0.090 | +2.560 | 7/8 | P | P | 0.457 | **YES** | 9q9pL6lo |
| R106d_close_RVx2 | +1.310 | 0.092 | +2.240 | 7/8 | P | P | 0.460 | **YES** | JjnGZ86O |

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 8/8**

## Survivor expressions

### R106g_close05x_parkx2 -- alpha O0nGaRYv
SH=+1.690 TO=0.087 FIT=+3.310 SC={'A1nnxAdw': 0.6301, '9q9o0zme': 0.5316}
```
zscore(ts_decay_linear(add(multiply(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), 0.5), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 15))
```

### R106f_close_parkx3 -- alpha gJm8p3Qm
SH=+1.610 TO=0.092 FIT=+3.100 SC={'A1nnxAdw': 0.5543, '9q9o0zme': 0.5154}
```
zscore(ts_decay_linear(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 3)), 15))
```

### R106h_close_parkx2_d10 -- alpha VkXGo92G
SH=+1.550 TO=0.108 FIT=+2.980 SC={}
```
zscore(ts_decay_linear(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), multiply(zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60))), 2)), 10))
```

### R106e_close_park_C9_triple -- alpha j2n6mvxe
SH=+1.490 TO=0.094 FIT=+2.750 SC={'9q9o0zme': 0.4725, 'A1nnxAdw': 0.4469}
```
zscore(ts_decay_linear(add(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), zscore(reverse(ts_mean(power(log(divide(high, low)), 2), 60)))), zscore(reverse(ts_std_dev(divide(close, vwap), 60)))), 15))
```

### R106a_close_RSx2 -- alpha xAeN8jPW
SH=+1.470 TO=0.096 FIT=+2.730 SC={'9q9o0zme': 0.4818, 'A1nnxAdw': 0.4467}
```
zscore(ts_decay_linear(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), multiply(zscore(reverse(ts_mean(add(multiply(log(divide(high, close)), log(divide(high, open))), multiply(log(divide(low, close)), log(divide(low, open)))), 60))), 2)), 15))
```

### R106b_close_YZx2 -- alpha VkXGjWrJ
SH=+1.460 TO=0.098 FIT=+2.720 SC={'9q9o0zme': 0.4768, 'A1nnxAdw': 0.4281}
```
zscore(ts_decay_linear(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), multiply(zscore(reverse(add(ts_mean(power(log(divide(open, ts_delay(close, 1))), 2), 60), ts_mean(power(log(divide(close, open)), 2), 60)))), 2)), 15))
```

### R106c_close_rangeCx2 -- alpha 9q9pL6lo
SH=+1.430 TO=0.090 FIT=+2.560 SC={'9q9o0zme': 0.4568, 'A1nnxAdw': 0.4377}
```
zscore(ts_decay_linear(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), multiply(zscore(reverse(ts_mean(divide(subtract(high, low), close), 60))), 2)), 15))
```

### R106d_close_RVx2 -- alpha JjnGZ86O
SH=+1.310 TO=0.092 FIT=+2.240 SC={'9q9o0zme': 0.4599, 'A1nnxAdw': 0.3863}
```
zscore(ts_decay_linear(add(signed_power(zscore(reverse(divide(close, ts_mean(close, 60)))), 2.7), multiply(zscore(reverse(ts_std_dev(returns, 60))), 2)), 15))
```

