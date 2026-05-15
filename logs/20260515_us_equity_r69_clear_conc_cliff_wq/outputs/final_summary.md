# R69 clear concentration cliff

| variant | univ | trunc | neut | SH | TO | FIT | conc | sub | passes? |
|---|---|---:|---|---:|---:|---:|---|---|---|
| PV6_OOO_trunc0.03 | TOP3000 | 0.03 | SUBINDUSTRY | +1.860 | 0.083 | +4.630 | P | P | **YES** |
| PV7_OOO_trunc0.02 | TOP3000 | 0.02 | SUBINDUSTRY | +1.810 | 0.080 | +4.240 | P | P | **YES** |
| PV5_SSS_industry | TOP3000 | 0.08 | INDUSTRY | +1.720 | 0.069 | +4.230 | F(0.17) | P | no |
| PV4_SSS_trunc0.02 | TOP3000 | 0.02 | SUBINDUSTRY | +1.520 | 0.062 | +2.920 | P | P | **YES** |
| PV1_PPP_trunc0.05 | TOP3000 | 0.05 | SUBINDUSTRY | +1.490 | 0.058 | +2.880 | P | P | no |
| PV3_PPP_industry | TOP3000 | 0.08 | INDUSTRY | +1.470 | 0.056 | +3.060 | P | P | no |
| PV8_BB_pow1.1 | TOP3000 | 0.08 | SUBINDUSTRY | +1.410 | 0.056 | +2.750 | P | P | no |
| PV2_PPP_trunc0.03 | TOP3000 | 0.03 | SUBINDUSTRY | +1.380 | 0.055 | +2.460 | P | P | no |

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 3/8**

## Survivor expressions

### PV6_OOO_trunc0.03 -- alpha A1nnxAdw
SH=+1.860 TO=0.083 FIT=+4.630
settings: {"universe": "TOP3000", "delay": 1, "decay": 8, "truncation": 0.03, "neutralization": "SUBINDUSTRY"}
```
zscore(ts_decay_linear(signed_power(zscore(reverse(ts_mean(signed_power(log(divide(high, low)), 2), 20))), 2), 30))
```

### PV7_OOO_trunc0.02 -- alpha O0nn6wpp
SH=+1.810 TO=0.080 FIT=+4.240
settings: {"universe": "TOP3000", "delay": 1, "decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}
```
zscore(ts_decay_linear(signed_power(zscore(reverse(ts_mean(signed_power(log(divide(high, low)), 2), 20))), 2), 30))
```

### PV4_SSS_trunc0.02 -- alpha Jjnn80jm
SH=+1.520 TO=0.062 FIT=+2.920
settings: {"universe": "TOP3000", "delay": 1, "decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}
```
zscore(ts_decay_linear(signed_power(reverse(ts_mean(signed_power(log(divide(high, low)), 2), 20)), 1.5), 30))
```

