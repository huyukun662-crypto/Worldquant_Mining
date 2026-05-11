# Round 8d - intraday-return reversal

3 intraday variants + 1 adv20-level alt.
Settings: zscore wrapper, INDUSTRY, decay=8, trunc=0.08, TOP3000, delay=1.

Filter: SH > 1.3 AND FIT > 1.0 AND TO < 0.2

## Results

| variant | family | SH | TO | FIT | RET | DD | checks | survives? |
|---|---|---:|---:|---:|---:|---:|---|---|
| M11_intraday_D5 | I_intraday_reversal | +1.450 | 0.327 | +1.210 | +0.227 | 0.131 | 7/8 | no |
| M12_intraday_D10 | I_intraday_reversal | +1.270 | 0.240 | +1.140 | +0.193 | 0.136 | 7/8 | no |
| M13_intraday_D20 | I_intraday_reversal | +1.250 | 0.166 | +1.340 | +0.189 | 0.155 | 7/8 | no |
| M14_advratio_D20 | L_liquidity_flow | +0.150 | 0.086 | +0.050 | +0.011 | 0.247 | 4/8 | no |

**Survivors: 0/4**

**Distinct families covered: 0** (none)
