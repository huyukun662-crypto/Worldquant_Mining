"""Round-16 D0 candidates: concentration-SAFE >=2.0 blend, NO option/IV leg.

Rounds 9-15 chased the IV-skew signal (SH 2.17 standalone) but every blend
containing it FAILS CONCENTRATED_WEIGHT -- option coverage is only ~70% and
sits on large-cap optionable names, so the option leg concentrates the book
no matter how we smooth, truncate, coarsen, or dilute it. Direct proof on
single-leg alphas:

    iv_skew60_neg  SH 2.17  -> concW FAIL    (option, 70% cov)
    iv_mom / term            -> concW FAIL
    news_mom       SH 1.68  -> concW PASS     <-- NOT the culprit!
    PV core        SH 1.43  -> concW PASS
    sentiment      SH ~0.4  -> concW PASS

So the high-Sharpe-but-concentrated IV leg is a dead end on this account. But
news_mom (SH 1.68) and the PV reversal core (SH 1.43) BOTH pass concentration
and are economically orthogonal (post-news drift vs price/volume reversal).
A risk-balanced blend of two uncorrelated concentration-safe legs should reach
~ (1.68+1.43)/sqrt(2) ~= 2.2 Sharpe AND inherit their concentration PASS.

This round drops every option field and blends only concentration-safe,
broad-coverage legs:
    NEWS = group_zscore(ts_mean(news_pct_120min, 5), industry)  [smoothed: tames
           the standalone TO=1.0 toward <0.7]
    PV   = -zscore(ts_covariance(returns,volume,20)) - group_zscore(ts_av_diff(close,5),industry)
    SENT = group_zscore(scl12_sentiment, industry)  [coverage 1.0, dense]
News is the stronger / more orthogonal leg (standalone self_corr 0.156) so the
blends are news-weighted.
"""

NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")
SENT = "group_zscore(scl12_sentiment, industry)"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- news + PV, weight & decay sweep (the core play) --------------
    {"name": "news_pv_d8", "expression": f"{NEWS} + {PV}",
     "theme": "news + PV equal, d8.", "settings": _s(8, 0.05)},
    {"name": "news_pv_d12", "expression": f"{NEWS} + {PV}",
     "theme": "news + PV equal, d12.", "settings": _s(12, 0.05)},
    {"name": "news15_pv_d8", "expression": f"1.5 * ({NEWS}) + {PV}",
     "theme": "1.5x news + PV (news-weighted), d8.", "settings": _s(8, 0.05)},
    {"name": "news2_pv_d8", "expression": f"2 * ({NEWS}) + {PV}",
     "theme": "2x news + PV, d8.", "settings": _s(8, 0.05)},
    {"name": "news2_pv_d6", "expression": f"2 * ({NEWS}) + {PV}",
     "theme": "2x news + PV, d6 (less smoothing, more SH).", "settings": _s(6, 0.05)},

    # --- add the dense full-coverage sentiment leg -------------------
    {"name": "news_pv_sent_d8", "expression": f"{NEWS} + {PV} + {SENT}",
     "theme": "news + PV + sentiment, d8.", "settings": _s(8, 0.05)},
    {"name": "news15_pv_sent_d8", "expression": f"1.5 * ({NEWS}) + {PV} + {SENT}",
     "theme": "1.5x news + PV + sentiment, d8.", "settings": _s(8, 0.05)},

    # --- news-dominant + light PV for breadth, faster -----------------
    {"name": "news2_pvhalf_d6", "expression": f"2 * ({NEWS}) + 0.5 * ({PV})",
     "theme": "2x news + 0.5 PV, d6.", "settings": _s(6, 0.05)},
]
