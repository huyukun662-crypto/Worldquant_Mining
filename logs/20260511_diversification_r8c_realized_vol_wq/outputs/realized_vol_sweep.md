# Round 8c - realized-vol family

4 RV variants + 1 liquidity-flow bridge.
Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | family | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| M6_volrev_W20D20 | RV_realized_vol | +0.470 | 0.052 | +0.420 | +0.099 | 0.648 | 5/8 | no |
| M7_volrev_W60D20 | RV_realized_vol | +0.420 | 0.027 | +0.360 | +0.093 | 0.692 | 5/8 | no |
| M8_volrev_W20D30 | RV_realized_vol | +0.460 | 0.044 | +0.410 | +0.099 | 0.689 | 5/8 | no |
| M9_volmom_W60D20 | RV_realized_vol | -0.420 | 0.027 | -0.360 | -0.092 | 1.099 | 4/8 | no |
| M10_liqflip_w30D10 | L_liquidity_flow | +1.520 | 0.110 | +2.200 | +0.263 | 0.211 | 5/8 | **YES** |

**Survivors: 1/5**

**Distinct families covered: 1** (L_liquidity_flow)
