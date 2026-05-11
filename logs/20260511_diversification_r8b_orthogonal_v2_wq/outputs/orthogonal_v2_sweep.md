# Round 8b - orthogonal mechanisms v2

3 families (liquidity-flow / volume-burst / close-strength), 5 variants.
Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.35 AND FIT > 1.0 AND TO < 0.15

## Results

| variant | family | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| M1_liqflip_w20D10 | L_liquidity_flow | +1.530 | 0.131 | +2.030 | +0.231 | 0.198 | 6/8 | **YES** |
| M2_liqflip_w60D10 | L_liquidity_flow | +1.270 | 0.096 | +1.830 | +0.261 | 0.352 | 5/8 | no |
| M3_volz60_D20 | V_volume_burst | -0.470 | 0.121 | -0.210 | -0.025 | 0.182 | 4/8 | no |
| M4_clstrength_D20 | C_close_strength | +0.790 | 0.161 | +0.520 | +0.069 | 0.106 | 5/8 | no |
| M5_clstrength_D30 | C_close_strength | +0.650 | 0.132 | +0.440 | +0.060 | 0.133 | 4/8 | no |

**Survivors: 1/5**

**Distinct families covered: 1** (L_liquidity_flow)
