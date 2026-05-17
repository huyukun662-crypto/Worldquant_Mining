# R118 decay sweep break gate

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |
|---|---:|---:|---:|---|---|---|---|---|---|
| R118a_117d_decay5 | +1.370 | 0.229 | +0.950 | 6/8 | P | P | 0.462 | no | kqngeQpg |
| R118b_117d_decay6 | +1.300 | 0.212 | +0.910 | 6/8 | P | P | 0.468 | no | 9q9Wgkor |
| R118g_117d_d3_pf15 | +1.300 | 0.184 | +1.000 | 7/8 | P | P | 0.490 | **YES** | 9q9WbJ1r |
| R118d_117j_decay5 | +1.250 | 0.215 | +0.910 | 6/8 | P | P | 0.467 | no | MPb3lKbL |
| R118i_ma3x15_buyback_d5 | +1.250 | 0.201 | +0.930 | 6/8 | P | P | 0.489 | no | P0ng6e37 |
| R118c_117d_decay7 | +1.240 | 0.198 | +0.890 | 5/8 | P | P | 0.474 | no | xAebwqgw |
| R118e_117j_decay6 | +1.200 | 0.200 | +0.890 | 5/8 | P | P | 0.471 | no | VkX0w5dA |
| R118h_117d_d5_pf15 | +1.180 | 0.153 | +0.960 | 5/8 | P | P | 0.499 | no | 2rvmQxPP |
| R118f_117j_decay7 | +1.150 | 0.186 | +0.870 | 5/8 | P | P | 0.474 | no | 2rvmQbAw |
| R118j_117j_d5_pf15 | +1.100 | 0.143 | +0.950 | 5/8 | P | P | 0.492 | no | KPnr6E8j |

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 1/10**

## Survivor expressions

### R118g_117d_d3_pf15 -- alpha 9q9WbJ1r
SH=+1.300 TO=0.184 FIT=+1.000 SC={'1YopvX8W': 0.4903, 'A1nnxAdw': 0.3886, '9q9o0zme': 0.2164}
```
zscore(ts_decay_linear(add(multiply(zscore(last_diff_value(sign(subtract(close, ts_mean(close, 3))), 10)), 2), zscore(reverse(divide(subtract(sharesout, ts_delay(sharesout, 252)), sharesout)))), 3))
```

