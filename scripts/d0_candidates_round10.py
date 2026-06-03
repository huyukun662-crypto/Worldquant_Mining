"""Round-10 D0 candidates: DECORRELATION blends to break SH 2.0.

Round 9 found the single strongest orthogonal D0 signal:

    SKEW = -group_zscore(iv_put_60 - iv_call_60, industry)
         -> SH 2.17, FIT 1.46, TO 0.375  BUT self_corr 0.808 (crowded)
            + CONCENTRATED_WEIGHT + LOW_SUB_UNIVERSE_SHARPE
            (option coverage ~0.70 -> few names -> concentrated)

It clears the 2.0 Sharpe bar alone but is un-submittable: too correlated
with the existing submitted pool and too concentrated. The fix is to
*blend* it with signals that are (a) full-coverage and (b) uncorrelated
with IV skew, which simultaneously:
  - dilutes self-correlation below 0.70  (skew becomes a fraction of the
    blend variance: 2 uncorrelated equal signals -> 0.808*0.707 ~= 0.57),
  - spreads weight onto the ~30% of names with no option data -> fixes
    CONCENTRATED_WEIGHT and LOW_SUB_UNIVERSE_SHARPE,
  - ADDS Sharpe by diversification: (2.17 + 1.43)/sqrt(2) ~= 2.55 if the
    two legs are truly uncorrelated.

Blend legs (all ~unit-variance industry z-scores, directly additive):
  SKEW : -group_zscore(iv_put_60 - iv_call_60, industry)   [2.17, crowded]
  PV   : the round-4..8 champion PV reversal+covariance core [1.43, full cov]
  NEWS : group_zscore(ts_mean(news_pct_120min, 5), industry) [1.68 raw, self_corr 0.156;
         5d-smoothed to cut the standalone TO=1.0 down toward submittable]
"""

SKEW = "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"


def _s(decay=8):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": "INDUSTRY", "truncation": 0.08}


CANDIDATES = [
    # ---- SKEW + PV (the core decorrelation play) ----------------------
    {"name": "skew_pv", "expression": f"{SKEW} + {PV}",
     "theme": "Equal-weight IV-skew + PV reversal.", "settings": _s(8)},
    {"name": "skew_pv_d12", "expression": f"{SKEW} + {PV}",
     "theme": "Same, decay 12.", "settings": _s(12)},
    {"name": "skew_pv_d4", "expression": f"{SKEW} + {PV}",
     "theme": "Same, decay 4 (faster).", "settings": _s(4)},
    # skew-weighted: keep Sharpe nearer 2.17 while still diluting self-corr.
    {"name": "skew2_pv", "expression": f"2 * ({SKEW}) + {PV}",
     "theme": "2x skew + PV (skew-dominant).", "settings": _s(8)},
    {"name": "skew15_pv", "expression": f"1.5 * ({SKEW}) + {PV}",
     "theme": "1.5x skew + PV.", "settings": _s(8)},
    # PV-weighted: push self-corr further down if 1x still >0.7.
    {"name": "skew_pv2", "expression": f"{SKEW} + 2 * ({PV})",
     "theme": "skew + 2x PV (self-corr safety).", "settings": _s(8)},

    # ---- triple blend: add orthogonal news momentum -------------------
    {"name": "skew_pv_news", "expression": f"{SKEW} + {PV} + {NEWS}",
     "theme": "Triple: skew + PV + smoothed news.", "settings": _s(8)},
    {"name": "skew2_pv_news", "expression": f"2 * ({SKEW}) + {PV} + {NEWS}",
     "theme": "2x skew + PV + news.", "settings": _s(8)},
    {"name": "skew_news", "expression": f"{SKEW} + {NEWS}",
     "theme": "skew + smoothed news (both alt-data).", "settings": _s(8)},
]
