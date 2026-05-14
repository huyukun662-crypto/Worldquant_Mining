# R55 multi-region test of rv*accel*volwt

Expression (fixed):
```
zscore(reverse(ts_decay_linear(multiply(multiply(ts_std_dev(returns, 20), subtract(returns, ts_delay(returns, 2))), log(add(divide(volume, adv20), 1))), 25)))
```

| variant | region | universe | SH | TO | FIT | conc | sub | passes? |
|---|---|---|---:|---:|---:|---|---|---|
| DDD1_GLB_TOP3000 | GLB | TOP3000 | FAIL | - | - | - | - | no |
| DDD2_EUR_TOP2500 | EUR | TOP2500 | FAIL | - | - | - | - | no |
| DDD3_EUR_TOP1200 | EUR | TOP1200 | FAIL | - | - | - | - | no |
| DDD4_CHN_TOP2000U | CHN | TOP2000U | FAIL | - | - | - | - | no |
| DDD5_ASI_MINVOL1M | ASI | MINVOL1M | FAIL | - | - | - | - | no |

**Survivors: 0/5**
