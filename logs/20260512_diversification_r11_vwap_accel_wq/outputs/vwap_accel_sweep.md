# Round 11 - vwap + price-acceleration

Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | logic | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| U1_vwap_dev_rev | close-vs-VWAP reversion | +0.240 | 0.166 | +0.100 | +0.030 | 0.391 | 5/8 | no |
| U2_vwap_dev_volwt_rev | vol-weighted close-vs-VWAP reversion | +0.240 | 0.170 | +0.100 | +0.031 | 0.457 | 5/8 | no |
| U3_price_acc_rev | price acceleration reversal (2nd derivative) | +1.230 | 0.581 | +0.730 | +0.207 | 0.180 | 5/8 | no |
| U4_range_pos_acc_volwt_rev | range-position acceleration, vol-weighted, reversed | +0.900 | 0.269 | +0.350 | +0.041 | 0.064 | 5/8 | no |

**Survivors: 0/4**
