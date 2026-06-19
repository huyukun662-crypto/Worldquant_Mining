"""Fundamental quality-value-investment composite D0 candidates.

Economic story (Fama-French 5-factor / anomaly zoo, all persistent ->
low turnover, orthogonal to short-interest / sentiment / PV factors):
  * Value        : ebit / enterprise_value  (earnings yield)        [+]
  * Profitability: ebit / assets            (operating ROA)         [+]
  * Cashflow qual: cashflow_op / assets     (cash-based profit)     [+]
  * Investment   : ts_delta(assets)/assets  (asset growth, Cooper)  [-]
  * Leverage     : debt / assets                                    [-]

Structural recipe (mirrors the high-Sharpe account alphas):
  rank(winsorize(.)) on each term  ->  sum  ->  group_neutralize
  ->  optionally vector_neut against returns (market/beta clean)
  ->  hump (turnover control).

Regularized (rank/winsorize/group_neutralize/zscore). Uncommon ops where
useful (ts_arg_max/ts_quantile). No IV, no news_short_interest. Run serial.
"""
from scripts.d0_batch import run_batch

def T(x):  # rank-winsorize a raw signal
    return f"rank(winsorize({x}, std=4))"

value  = T("divide(ebit, enterprise_value)")
prof   = T("divide(ebit, assets)")
cfq    = T("divide(cashflow_op, assets)")
inv    = T("divide(ts_delta(assets, 250), assets)")     # subtract this
lev    = T("divide(debt, assets)")                       # subtract this

# core composite (value + profitability + cashflow - investment - leverage)
CORE = f"{value} + {prof} + {cfq} - {inv} - {lev}"

C = [
 # 1) plain composite, group_neutralize by subindustry
 ("comp_sub",
  f"group_neutralize({CORE}, subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 2) composite + vector_neut against returns (remove beta/reversal)
 ("comp_vneut",
  f"vector_neut(group_neutralize({CORE}, subindustry), returns)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 3) composite + vector_neut + hump (turnover control)
 ("comp_hump",
  f"hump(vector_neut(group_neutralize({CORE}, subindustry), returns), hump=0.05)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 4) quality-value only (3 terms, concise)
 ("comp_qv",
  f"group_neutralize({value} + {prof} + {cfq}, subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
 # 5) INDUSTRY neutralization variant
 ("comp_ind",
  f"hump(vector_neut(group_neutralize({CORE}, industry), returns), hump=0.05)",
  {"neutralization":"INDUSTRY","decay":8}),
 # 6) zscore-aggregated variant (zscore each instead of rank)
 ("comp_z",
  "group_neutralize("
  "zscore(winsorize(divide(ebit, enterprise_value), std=4))"
  "+ zscore(winsorize(divide(ebit, assets), std=4))"
  "+ zscore(winsorize(divide(cashflow_op, assets), std=4))"
  "- zscore(winsorize(divide(ts_delta(assets, 250), assets), std=4))"
  ", subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":8}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=1)
