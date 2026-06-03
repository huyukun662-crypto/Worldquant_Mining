"""Round-5 D0 candidates: break the SH~1.43 plateau with ORTHOGONAL families.

Rounds 1-4 capped at SH 1.43 because every term was the same reversal/crowding
family (mutually correlated, and 0.53 self-corr to the pool). decay 16 is the
sweet spot (fitness 1.5). To add Sharpe we must add *orthogonal* return drivers:

  Core (reversal/crowding, SH 1.43 @ d16):
    -zscore(ts_covariance(returns, volume, 20))
    -group_zscore(ts_av_diff(close, 5), industry)
  Orthogonal additions (different families):
    LV   -zscore(ts_std_dev(returns, 20))                       low-volatility anomaly
    LVi  -group_zscore(ts_std_dev(returns, 20), industry)       industry-relative low-vol
    CV   -zscore(divide(close, vwap))                           intraday strength fade
    RNG  -group_zscore(ts_mean(divide(subtract(high, low), close), 20), industry)  low-range stability

All operators tier-available; D0; per-term regularized (zscore/group_zscore);
niche core; no IV; no template reuse. TOP3000, decay 16.
"""

CORE = ("-zscore(ts_covariance(returns, volume, 20)) "
        "- group_zscore(ts_av_diff(close, 5), industry)")
LV = "- zscore(ts_std_dev(returns, 20))"
LVi = "- group_zscore(ts_std_dev(returns, 20), industry)"
CV = "- zscore(divide(close, vwap))"
RNG = "- group_zscore(ts_mean(divide(subtract(high, low), close), 20), industry)"
COVi = "-group_zscore(ts_covariance(returns, volume, 20), industry)"

def _s(decay=16, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut}

CANDIDATES = [
    {"name": "core_lv", "expression": f"{CORE} {LV}",
     "theme": "Core + low-volatility anomaly (orthogonal family).", "settings": _s()},
    {"name": "core_lvi", "expression": f"{CORE} {LVi}",
     "theme": "Core + industry-relative low-vol.", "settings": _s()},
    {"name": "core_lv_cv", "expression": f"{CORE} {LV} {CV}",
     "theme": "Core + low-vol + intraday strength fade.", "settings": _s()},
    {"name": "core_lv_rng", "expression": f"{CORE} {LV} {RNG}",
     "theme": "Core + low-vol + low-range stability.", "settings": _s()},
    {"name": "core_lv_subind", "expression": f"{CORE} {LV}",
     "theme": "Core + low-vol, SUBINDUSTRY.", "settings": _s(neut="SUBINDUSTRY")},
    {"name": "core_lv_cv_rng", "expression": f"{CORE} {LV} {CV} {RNG}",
     "theme": "Core + low-vol + intraday fade + low-range (4 families).", "settings": _s()},
    {"name": "covi_s2_lvi", "expression": f"{COVi} - group_zscore(ts_av_diff(close, 5), industry) {LVi}",
     "theme": "Fully industry-relative: cov-fade + reversal + low-vol.", "settings": _s()},
    {"name": "core_cv", "expression": f"{CORE} {CV}",
     "theme": "Core + intraday strength fade only.", "settings": _s()},
]
