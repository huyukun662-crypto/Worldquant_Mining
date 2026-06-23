"""Fresh PV multi-signal composite D0 candidates -> target SH>=2.0.

Rationale: the only >=2.0 account alpha that does NOT use news_short_interest
is a PV multi-signal composite whose Sharpe comes from the structural
recipe:  rank(winsorize(term)) summed over orthogonal anomalies, then
group_neutralize x2, then vector_neut against `returns` (removes market/
beta -> big Sharpe lift), then hump (turnover control).

Each term is a classic, economically-grounded cross-sectional anomaly,
combined here with DIFFERENT signals than the existing alpha (fresh):
  * Short-term reversal     : -ts_zscore(returns, 5)            [+]
  * Low-volatility anomaly  : -ts_std_dev(returns, 60)          [+]
  * Amihud illiquidity      : ts_mean(|returns|/volume, 60)     [+]
  * Price-volume divergence : -ts_corr(close, volume, 20)       [+]
  * Long-term reversal      : -ts_av_diff(close, 250)           [+]
  * Recency-of-high (cold)  : ts_arg_max(close, 60)             [+]  (uncommon op)

Regularized with rank/winsorize/group_neutralize/vector_neut.
No IV, no news_short_interest.
"""
from scripts.d0_batch import run_batch

def T(x):
    return f"rank(winsorize({x}, std=4))"

rev   = T("-ts_zscore(returns, 5)")
lowv  = T("-ts_std_dev(returns, 60)")
illiq = T("ts_mean(divide(abs(returns), add(volume, 1)), 60)")
pvdiv = T("-ts_corr(close, volume, 20)")
ltrev = T("-ts_av_diff(close, 250)")
amax  = T("ts_arg_max(close, 60)")

CORE5 = f"{rev} + {lowv} + {illiq} + {pvdiv} + {ltrev}"
CORE6 = f"{CORE5} + {amax}"

def stack(core, g1="subindustry"):
    return f"hump(vector_neut(group_neutralize({core}, {g1}), returns), hump=0.05)"

C = [
 # 1) 5-term, group_neutralize only (no vneut) -- baseline
 ("pv5_base", f"group_neutralize({CORE5}, subindustry)",
  {"neutralization":"SUBINDUSTRY","decay":4}),
 # 2) 5-term, + vector_neut(returns) + hump  (the booster)
 ("pv5_vneut", stack(CORE5),
  {"neutralization":"SUBINDUSTRY","decay":4}),
 # 3) 6-term (adds cold ts_arg_max), full recipe
 ("pv6_vneut", stack(CORE6),
  {"neutralization":"SUBINDUSTRY","decay":4}),
 # 4) 6-term, INDUSTRY neut
 ("pv6_ind", stack(CORE6, "industry"),
  {"neutralization":"INDUSTRY","decay":4}),
 # 5) 6-term, MARKET neut, lighter decay
 ("pv6_mkt", stack(CORE6),
  {"neutralization":"MARKET","decay":2}),
 # 6) reversal+lowvol+illiq only (3-term concise) + vneut
 ("pv3_vneut",
  f"hump(vector_neut(group_neutralize({rev} + {lowv} + {illiq}, subindustry), returns), hump=0.05)",
  {"neutralization":"SUBINDUSTRY","decay":4}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=1)
