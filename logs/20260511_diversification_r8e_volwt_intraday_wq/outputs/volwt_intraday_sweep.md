# Round 8e - vol-weighted intraday reversal

Settings: zscore wrapper, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | neut | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| M15_volwt_D10_IND | INDUSTRY | +1.240 | 0.241 | +1.180 | +0.218 | 0.233 | 5/8 | no |
| M16_volwt_D15_IND | INDUSTRY | +1.460 | 0.197 | +1.660 | +0.254 | 0.188 | 7/8 | **YES** |
| M17_volwt_D20_IND | INDUSTRY | +1.670 | 0.168 | +2.200 | +0.291 | 0.179 | 7/8 | **YES** |
| M18_volwt_D10_SUBIN | SUBINDUSTRY | +1.520 | 0.242 | +1.520 | +0.243 | 0.147 | 7/8 | no |

**Survivors: 2/4**
