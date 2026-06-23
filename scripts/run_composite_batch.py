"""Fundamental + analyst composite D0 candidates (v2, with ts_backfill).

KEY FIX: at delay=0 the fundamental/analyst fields are sparse/stale, so
each raw field MUST be ts_backfill'd (the working account alphas all do
this, e.g. ts_backfill(divide(sales,cap),22)). Without it the signal is
~0.

Economic terms (all persistent -> low turnover, orthogonal to
short-interest / sentiment / PV factors):
  * Value         : ebit / enterprise_value      (earnings yield)     [+]
  * Profitability : ebit / assets                (operating ROA)      [+]
  * Cashflow qual : cashflow_op / assets         (cash profitability) [+]
  * Investment    : ts_delta(assets)/assets      (asset growth)       [-]
  * Analyst coverage : vec_avg(anl4..numest)     (attention)          [+]
  * Analyst dispersion: (high-low)/|mean| of EPS estimates            [+]

Recipe: rank(winsorize(ts_backfill(term))) -> sum -> group_neutralize
-> optional vector_neut(returns) -> hump.  No IV, no news_short_interest.
"""
from scripts.d0_batch import run_batch

def Tb(x, bf=120):  # backfill -> winsorize -> rank
    return f"rank(winsorize(ts_backfill({x}, {bf}), std=4))"

value = Tb("divide(ebit, enterprise_value)")
prof  = Tb("divide(ebit, assets)")
cfq   = Tb("divide(cashflow_op, assets)")
inv   = Tb("divide(ts_delta(assets, 250), assets)", 250)
cov   = Tb("vec_avg(anl4_basicconqf_numest)", 66)
disp  = Tb("divide(subtract(vec_avg(anl4_basicconqf_high), vec_avg(anl4_basicconqf_low)), "
           "add(abs(vec_avg(anl4_basicconqf_mean)), 1))", 66)

# fundamental-only 5-term core
FUND = f"{value} + {prof} + {cfq} - {inv}"
# fundamental + analyst attention/dispersion
FULL = f"{value} + {prof} + {cfq} - {inv} + {cov} + {disp}"

C = [
 # 1) fundamental-only, group_neutralize
 ("f_sub",   f"group_neutralize({FUND}, subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 2) fundamental + vector_neut(returns)
 ("f_vneut", f"vector_neut(group_neutralize({FUND}, subindustry), returns)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 3) FULL (fund + analyst), vector_neut + hump
 ("full_hump",
  f"hump(vector_neut(group_neutralize({FULL}, subindustry), returns), hump=0.05)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 4) FULL, plain group_neutralize
 ("full_sub", f"group_neutralize({FULL}, subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 5) value+profitability+coverage+dispersion (drop noisy cfq/inv)
 ("qva", f"group_neutralize({value} + {prof} + {cov} + {disp}, subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 6) FULL with INDUSTRY neut + hump
 ("full_ind",
  f"hump(vector_neut(group_neutralize({FULL}, industry), returns), hump=0.05)",
  {"neutralization":"INDUSTRY","decay":8}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=1)
