"""ts_regression liquidity/price-impact signal + fresh composite.

ts_regression(returns, volume/adv20, d, lag=0, rettype) regresses daily
returns on relative volume -> captures the price-impact / illiquidity
beta (Amihud-style, but as a rolling regression). This operator family
is the one demonstrably carrying IC on this account/period.

Step 1: sweep rettype to locate the IC-bearing output.
Step 2: fresh multi-signal composite using it + reversal + low-vol +
        analyst dispersion, fully neutralized.

No IV, no news_short_interest.
"""
from scripts.d0_batch import run_batch

REL = "divide(volume, adv20)"
def reg(rt, d=60):
    return f"ts_regression(returns, {REL}, {d}, lag=0, rettype={rt})"

def T(x):
    return f"rank(winsorize({x}, std=4))"

def stack(core, g1="pv13_r2_min5_3000_sector"):
    return (f"hump(vector_neut(group_neutralize(group_neutralize({core}, {g1}), "
            f"subindustry), returns), hump=0.05)")

disp = T("group_zscore(ts_backfill(divide(subtract(vec_avg(anl4_basicconqf_high), "
         "vec_avg(anl4_basicconqf_low)), add(abs(vec_avg(anl4_basicconqf_mean)),1)), 66), subindustry)")
rev  = T("-ts_zscore(returns, 5)")
lowv = T("-ts_std_dev(returns, 60)")

C = [
 # rettype sweep, each group_neutralize + vector_neut(returns)
 ("reg_rt0", f"vector_neut(group_neutralize({reg(0)}, subindustry), returns)", {"neutralization":"SUBINDUSTRY","decay":4}),
 ("reg_rt1", f"vector_neut(group_neutralize({reg(1)}, subindustry), returns)", {"neutralization":"SUBINDUSTRY","decay":4}),
 ("reg_rt2", f"vector_neut(group_neutralize({reg(2)}, subindustry), returns)", {"neutralization":"SUBINDUSTRY","decay":4}),
 ("reg_rt3", f"vector_neut(group_neutralize({reg(3)}, subindustry), returns)", {"neutralization":"SUBINDUSTRY","decay":4}),
 ("reg_rt4", f"vector_neut(group_neutralize({reg(4)}, subindustry), returns)", {"neutralization":"SUBINDUSTRY","decay":4}),
 ("reg_rt5", f"vector_neut(group_neutralize({reg(5)}, subindustry), returns)", {"neutralization":"SUBINDUSTRY","decay":4}),
 # fresh composite: liquidity-reg(rt4) + reversal + lowvol + analyst dispersion
 ("reg_comp",
  stack(f"{T(reg(4))} + {rev} + {lowv} + {disp}"),
  {"neutralization":"SUBINDUSTRY","decay":4}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=1)
