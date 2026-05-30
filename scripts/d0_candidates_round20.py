"""Round-20 D0 candidates: corrected news-event fields + stack toward 2.0.

Round 19 showed hump() preserves more of the news-drift edge than ts_mean:
    hump(group_zscore(news_pct_120min), 0.06) -> SH 1.64, FIT 1.06, TO 0.46,
    self_corr 0.156, CONCENTRATED_WEIGHT PASS.
But 6 candidates errored on a non-existent field `news_data_close` (correct:
news_eod_close). This round fixes the field names and probes orthogonal
news-EVENT price-action signals (all coverage 0.86-0.97 => concentration-safe),
then stacks the best with the proven hump-drift to push past 2.0.

Orthogonal news-event views (distinct from absolute 120-min drift):
  INDXPERF = news_indx_perf            stock return minus S&P 500 on news day
  REACT    = max_up_ret + max_dn_ret   net asymmetry of post-news swing
  SETTLE   = eod_close / ton_low       where it closed within the news-day range
  RUNUP    = eod_high  / ton_last      post-news high vs price at the news
  EXCSTD   = high_exc_stddev - low_exc_stddev   standardized up/down move balance
"""

DRIFT = "hump(group_zscore(news_pct_120min, industry), hump=0.06)"
INDXPERF = "group_zscore(news_indx_perf, industry)"
REACT = "group_zscore(news_max_up_ret + news_max_dn_ret, industry)"
SETTLE = "group_zscore(divide(news_eod_close, news_ton_low), industry)"
RUNUP = "group_zscore(divide(news_eod_high, news_ton_last), industry)"
EXCSTD = "group_zscore(news_high_exc_stddev - news_low_exc_stddev, industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=6, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- standalone probes of corrected news-event signals -----------
    {"name": "indxperf", "expression": INDXPERF,
     "theme": "stock-minus-SPY news-day return.", "settings": _s(6)},
    {"name": "react_asym", "expression": REACT,
     "theme": "post-news up+down swing asymmetry.", "settings": _s(6)},
    {"name": "settle", "expression": SETTLE,
     "theme": "close within news-day range.", "settings": _s(6)},
    {"name": "runup", "expression": RUNUP,
     "theme": "post-news high vs price at news.", "settings": _s(6)},
    {"name": "excstd", "expression": EXCSTD,
     "theme": "standardized up/down move balance.", "settings": _s(6)},

    # --- stack proven hump-drift + best-guess orthogonal news --------
    {"name": "drift_indxperf", "expression": f"{DRIFT} + {INDXPERF}",
     "theme": "hump-drift + index-relative.", "settings": _s(6)},
    {"name": "drift_react_settle", "expression": f"{DRIFT} + {REACT} + {SETTLE}",
     "theme": "hump-drift + reaction + settle (3 news views).", "settings": _s(6)},
    {"name": "drift_react_settle_pv",
     "expression": f"{DRIFT} + {REACT} + {SETTLE} + {PV}",
     "theme": "3 news views + PV reversal (4-leg, all safe).", "settings": _s(6)},
]
