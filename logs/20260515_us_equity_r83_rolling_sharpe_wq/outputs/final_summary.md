# R83 rolling Sharpe + new angles

| variant | SH | TO | FIT | checks | conc | sub | sc | gate |
|---|---:|---:|---:|---|---|---|---|---|
| R83g_VWAPmom60_PV6 | +0.960 | 0.063 | +1.390 | 6/8 | P | P | - | no |
| R83e_relvol_x_VWAPmom | +0.760 | 0.121 | +1.030 | 6/8 | P | P | - | no |
| R83c_tsrank_vwap60_PV6 | +0.630 | 0.065 | +0.480 | 5/8 | P | P | - | no |
| R83a_rollSH_VWAP_rev | +0.520 | 0.082 | +0.340 | 5/8 | P | P | - | no |
| R83b_rollSH_PV6 | +0.480 | 0.087 | +0.310 | 5/8 | P | P | - | no |
| R83d_tsrank_VWAPmom_PV6 | +0.450 | 0.095 | +0.230 | 4/8 | P | F(0.09) | - | no |
| R83h_rollSH_cube | +0.300 | 0.095 | +0.160 | 5/8 | P | P | - | no |
| R83f_vol_spike_PV6 | -0.550 | 0.117 | -0.380 | 5/8 | P | P | - | no |

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
