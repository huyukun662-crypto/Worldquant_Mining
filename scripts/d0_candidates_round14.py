"""Round-14 D0 candidates: push decay to drop concW under 0.10 (final).

Round 13 cracked the mechanism and got within 3% of passing. With the skew
standardized coarsely (sector / market-wide) the ONLY remaining failure is
CONCENTRATED_WEIGHT, and it falls monotonically with BOTH coarser grouping
AND higher decay (smoother weights):

    mz_skew_news  d12 -> concW 0.1161
                  d16 -> 0.1103
                  d20 -> 0.1042
    sec_skew_news d16 -> 0.1030   (best; SH 2.45, FIT 1.54, subSH 1.25, selfC 0.672)

Everything else PASSES (SH>2.0, FIT>1.3, TO<0.7, subSH>limit, selfC<0.70).
Need ~3% more concentration reduction => push decay further. Risk: selfC is
0.672 and may creep toward 0.70 as decay rises -> include 1.5x-news variants
(news is the orthogonal leg, standalone selfC 0.156) to pull selfC AND concW
down together.
"""

SKEW_MKT = "-zscore(implied_volatility_put_60 - implied_volatility_call_60)"
SKEW_SEC = "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, sector)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=24, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # decay sweep on the best structure (sector-zscore skew + news)
    {"name": "sec_skew_news_d22", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sector skew + news, d22.", "settings": _s(22, 0.05)},
    {"name": "sec_skew_news_d26", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sector skew + news, d26.", "settings": _s(26, 0.05)},
    {"name": "sec_skew_news_d32", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sector skew + news, d32.", "settings": _s(32, 0.05)},

    # 1.5x news: pulls concW and selfC down together
    {"name": "sec_skew_news15_d24", "expression": f"{SKEW_SEC} + 1.5 * ({NEWS})",
     "theme": "sector skew + 1.5x news, d24.", "settings": _s(24, 0.05)},
    {"name": "sec_skew_news15_d30", "expression": f"{SKEW_SEC} + 1.5 * ({NEWS})",
     "theme": "sector skew + 1.5x news, d30.", "settings": _s(30, 0.05)},

    # market-wide zscore skew at higher decay
    {"name": "mz_skew_news_d28", "expression": f"{SKEW_MKT} + {NEWS}",
     "theme": "market-z skew + news, d28.", "settings": _s(28, 0.05)},

    # sector skew + news + 0.5 PV breadth at high decay (subSH insurance)
    {"name": "sec_skew_news_pvhalf_d26", "expression": f"{SKEW_SEC} + {NEWS} + 0.5 * ({PV})",
     "theme": "sector skew + news + 0.5PV, d26.", "settings": _s(26, 0.05)},
    {"name": "sec_skew_news15_pvhalf_d28",
     "expression": f"{SKEW_SEC} + 1.5 * ({NEWS}) + 0.5 * ({PV})",
     "theme": "sector skew + 1.5x news + 0.5PV, d28.", "settings": _s(28, 0.05)},
]
