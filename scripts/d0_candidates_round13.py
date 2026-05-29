"""Round-13 D0 candidates: COARSEN skew standardization to kill CONCENTRATED_WEIGHT.

Round 12 isolated the mechanism. CONCENTRATED_WEIGHT moved like this:
    group_zscore(skew, SUBINDUSTRY) -> concW 0.215  (worse: tiny groups, wild z)
    group_zscore(skew, INDUSTRY)    -> concW 0.116
    winsorize(industry zscore, 2.0) -> concW 0.106  (better: tail capped)
=> the concentration is driven by EXTREME standardized skew values, and those
get larger the FINER the standardization group. So the fix is the opposite of
Round 12's rank/winsorize tinkering: standardize the skew over a COARSER set so
the cross-sectional distribution is tighter.

    group_zscore(skew, industry)  ->  zscore(skew)           [market-wide, tightest]
                                  ->  group_zscore(skew, sector)  [coarser than industry]

Minimal-perturbation baseline: the Round-11 champion sn_d12_t05
(-group_zscore(skew,industry)+news, d12 t05) passes EVERYTHING except concW
(0.1156, needs <0.10). c1 below changes ONLY the skew standardization to
market-wide zscore; the rest is identical. Variants add decay (fitness) and a
0.5x PV breadth leg (sub-universe insurance).
"""

SKEW_MKT = "-zscore(implied_volatility_put_60 - implied_volatility_call_60)"
SKEW_SEC = "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, sector)"
SKEW_WINS = "-winsorize(zscore(implied_volatility_put_60 - implied_volatility_call_60), std=2.5)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=16, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # c1: minimal change from champion -- only skew std -> market-wide zscore
    {"name": "mz_skew_news_d12", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-zscore skew + news, d12 t05 (min change).", "settings": _s(12, 0.05)},
    {"name": "mz_skew_news_d16", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-zscore skew + news, d16.", "settings": _s(16, 0.05)},
    {"name": "mz_skew_news_d20", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-zscore skew + news, d20 (fitness).", "settings": _s(20, 0.05)},

    # sector-grouped skew (coarser than industry, finer than market)
    {"name": "sec_skew_news_d16", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sector-zscore skew + news, d16.", "settings": _s(16, 0.05)},

    # market-z skew + PV breadth for sub-universe
    {"name": "mz_skew_news_pvhalf_d16", "expression": f"{SKEW_MKT} + {NEWS} + 0.5 * ({PV})",
     "theme": "market-z skew + news + 0.5PV, d16.", "settings": _s(16, 0.05)},
    {"name": "mz_skew_news_pvhalf_d20", "expression": f"{SKEW_MKT} + {NEWS} + 0.5 * ({PV})",
     "theme": "market-z skew + news + 0.5PV, d20.", "settings": _s(20, 0.05)},

    # stack market-z + winsorize (tightest concentration)
    {"name": "mzwins_news_pvhalf_d16", "expression": f"{SKEW_WINS} + {NEWS} + 0.5 * ({PV})",
     "theme": "winsorized market-z skew + news + 0.5PV, d16.", "settings": _s(16, 0.05)},

    # market-z skew + news + 0.5PV at tighter truncation
    {"name": "mz_skew_news_pvhalf_d16_t04", "expression": f"{SKEW_MKT} + {NEWS} + 0.5 * ({PV})",
     "theme": "market-z + news + 0.5PV, d16 t04.", "settings": _s(16, 0.04)},
]
