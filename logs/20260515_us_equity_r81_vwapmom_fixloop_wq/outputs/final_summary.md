# R81 VWAP-mom fix-loop

| variant | trunc | neut | SH | TO | FIT | checks | conc | sub | sc | gate |
|---|---:|---|---:|---:|---:|---|---|---|---|---|
| R81a_VWAPmom_zIN_pow3 | 0.08 | SUBINDUSTRY | +1.280 | 0.113 | +2.680 | 6/8 | F(0.307369) | P | - | no |
| R81g_VWAPmom_PV6_D60 | 0.08 | SUBINDUSTRY | +1.020 | 0.081 | +1.550 | 5/8 | F(0.101784) | P | - | no |
| R81b_VWAPmom_PV6_IND | 0.08 | INDUSTRY | +1.000 | 0.100 | +1.540 | 6/8 | P | P | - | no |
| R81h_VWAPmom30_PV6 | 0.08 | SUBINDUSTRY | +0.870 | 0.085 | +1.230 | 6/8 | P | P | - | no |
| R81d_VWAPmom_FF5 | 0.08 | SUBINDUSTRY | +0.800 | 0.184 | +0.430 | 4/8 | P | F(0.14) | - | no |
| R81c_VWAPmom_PV6_tr03 | 0.03 | SUBINDUSTRY | +0.720 | 0.097 | +0.820 | 5/8 | P | P | - | no |
| R81e_VWAPmom_x_rangeTS | 0.08 | SUBINDUSTRY | -0.980 | 0.107 | -1.670 | 3/8 | F(0.138754) | F(-0.62) | - | no |
| R81f_VWAPmom_pow25 | - | - | FAIL | - | - | - | - | - | - | no |  ReadTimeout: HTTPSConnectionPool(host='api.worldquantbrain.com', port=443): Read

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
