"""Round-19 D0 candidates: sweep the NEWS family for a concentration-safe >=2.0.

User pick: mine the news family. news_pct_120min (post-news 120-min price drift)
is the proven concentration-safe high-Sharpe leg -- standalone SH 1.68, concW
PASS, self_corr 0.156 -- but its raw turnover is ~1.0 (LOW_FITNESS). Two angles:

  1. TAME TURNOVER with `hump` (suppresses small day-to-day position changes)
     instead of ts_mean smoothing, which preserves more of the 1.68 edge ->
     try to lift news-alone fitness toward submittable.
  2. ADD ORTHOGONAL NEWS VIEWS built from the news-event price-action fields
     (intraday run-up, news-day volume) and stack several concentration-safe
     news legs (+ PV) toward 2.0.

All legs use broad-coverage (>=0.7) news fields => expected concentration-safe.
"""

NEWS = "group_zscore(news_pct_120min, industry)"           # post-news drift (SH 1.68)
NEWS_SM = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
RUNUP = "group_zscore(divide(news_eod_high, news_data_close), industry)"   # intraday high vs close
SETTLE = "group_zscore(divide(news_data_close, news_ton_low), industry)"    # close vs pre-news low
NVOL = "group_zscore(news_close_vol, industry)"            # news-day volume / attention
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=6, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- tame news-drift turnover with hump (preserve SH) -------------
    {"name": "newsmom_hump03_d4", "expression": f"hump({NEWS}, hump=0.03)",
     "theme": "news drift, hump 0.03 (cut TO).", "settings": _s(4)},
    {"name": "newsmom_hump06_d4", "expression": f"hump({NEWS}, hump=0.06)",
     "theme": "news drift, hump 0.06.", "settings": _s(4)},

    # --- new orthogonal news-event signals (standalone probes) --------
    {"name": "news_runup", "expression": RUNUP,
     "theme": "intraday high / close on news day.", "settings": _s(6)},
    {"name": "news_settle", "expression": SETTLE,
     "theme": "close / pre-news low.", "settings": _s(6)},
    {"name": "news_vol", "expression": NVOL,
     "theme": "news-day close volume (attention).", "settings": _s(6)},

    # --- stack multiple concentration-safe news legs ------------------
    {"name": "news_drift_settle", "expression": f"{NEWS_SM} + {SETTLE}",
     "theme": "smoothed drift + settle.", "settings": _s(6)},
    {"name": "news_drift_settle_vol", "expression": f"{NEWS_SM} + {SETTLE} + {NVOL}",
     "theme": "drift + settle + volume (3 news views).", "settings": _s(6)},

    # --- best news stack + PV (push to 2.0) ---------------------------
    {"name": "news2hump_settle_pv",
     "expression": f"2 * hump({NEWS}, hump=0.04) + {SETTLE} + {PV}",
     "theme": "2x hump-drift + settle + PV.", "settings": _s(6)},
]
