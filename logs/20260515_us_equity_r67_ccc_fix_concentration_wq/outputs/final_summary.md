# R67 fix CCC concentration

| variant | univ | trunc | neut | SH | TO | FIT | conc | sub | passes? |
|---|---|---:|---|---:|---:|---:|---|---|---|
| HHH_CCC_trunc0.03 | TOP3000 | 0.03 | SUBINDUSTRY | +1.900 | 0.086 | +5.090 | F(0.333643) | P | no |
| III_CCC_trunc0.02 | TOP3000 | 0.02 | SUBINDUSTRY | +1.880 | 0.083 | +4.760 | F(0.303021) | P | no |
| GGG_CCC_trunc0.05 | TOP3000 | 0.05 | SUBINDUSTRY | +1.800 | 0.090 | +5.090 | F(0.367541) | P | no |
| LLL_CCC_industry | TOP3000 | 0.08 | INDUSTRY | +1.740 | 0.091 | +5.180 | F(0.384992) | P | no |
| MMM_CCC_sector | TOP3000 | 0.08 | SECTOR | +1.730 | 0.080 | +5.160 | F(0.376838) | P | no |
| KKK_BB_pow1.5 | TOP3000 | 0.08 | SUBINDUSTRY | +1.720 | 0.073 | +4.200 | F(0.185808) | P | no |
| NNN_CCC_top1000 | TOP1000 | 0.08 | SUBINDUSTRY | +0.810 | 0.085 | +1.760 | F(0.434589) | P | no |
| JJJ_rankBB_pow2 | TOP3000 | 0.08 | SUBINDUSTRY | +0.010 | 0.028 | +0.000 | P | F(-0.11) | no |

**Survivors (SH>=1.5 ^ TO<0.20 ^ conc+sub PASS): 0/8**
