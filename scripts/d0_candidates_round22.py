"""Round-22 D0 candidates: blend the concentration-SAFE temporal-skew + news + PV.

BREAKTHROUGH in Round 21 (verified from WQ_D0_CHECK_REPORT.json):
per-name TEMPORAL normalization of the IV skew finally passes
CONCENTRATED_WEIGHT, which every cross-sectional form failed:

    tsr_skew60  = group_zscore(ts_rank(call60-put60, 60), industry)
                  -> SH 0.96, TO 0.15, concW PASS, self_corr 0.058
    tsr_skew120 = group_zscore(ts_rank(call60-put60,120), industry)
                  -> SH 1.16, TO 0.12, concW PASS, self_corr 0.066
    tsz_skew120 = group_zscore(ts_zscore(call60-put60,120), industry)
                  -> SH 1.16, TO 0.12, concW PASS, self_corr 0.066

So we now have THREE concentration-safe, broad, mutually-orthogonal legs:
    TSKEW (SH ~1.16, self_corr 0.07)   -- option positioning vs own history
    NEWS  (SH ~1.68 raw / smoothed)    -- post-news drift
    PV    (SH ~1.43)                   -- price/volume reversal
The Round-21 blends (tskew+news+pv) never recorded -- the run stopped after
the 3 standalone probes. This round re-runs them, sweeps weights/decay, and
because the legs are near-uncorrelated (self_corr 0.07 for tskew), the blend
should diversify toward SH ~2.0 while EVERY leg keeps concW PASS.
"""

SKEW = "implied_volatility_call_60 - implied_volatility_put_60"
TSKEW = f"group_zscore(ts_zscore({SKEW}, 120), industry)"
TSKEW_R = f"group_zscore(ts_rank({SKEW}, 120), industry)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- two-leg blends ----------------------------------------------
    {"name": "tskew_news", "expression": f"{TSKEW} + {NEWS}",
     "theme": "tz-skew120 + news.", "settings": _s(8)},
    {"name": "tskew_pv", "expression": f"{TSKEW} + {PV}",
     "theme": "tz-skew120 + PV.", "settings": _s(8)},

    # --- three-leg blends (the core play) ----------------------------
    {"name": "tskew_news_pv", "expression": f"{TSKEW} + {NEWS} + {PV}",
     "theme": "tz-skew + news + PV, equal.", "settings": _s(8)},
    {"name": "tskew_news_pv_d12", "expression": f"{TSKEW} + {NEWS} + {PV}",
     "theme": "tz-skew + news + PV, decay12.", "settings": _s(12)},

    # --- upweight the orthogonal high-Sharpe legs --------------------
    {"name": "tskew_news2_pv", "expression": f"{TSKEW} + 2 * ({NEWS}) + {PV}",
     "theme": "tz-skew + 2x news + PV.", "settings": _s(8)},
    {"name": "tskew2_news2_pv", "expression": f"2 * ({TSKEW}) + 2 * ({NEWS}) + {PV}",
     "theme": "2x tz-skew + 2x news + PV.", "settings": _s(8)},
    {"name": "tskew2_news_pv", "expression": f"2 * ({TSKEW}) + {NEWS} + {PV}",
     "theme": "2x tz-skew + news + PV.", "settings": _s(8)},

    # --- ts_rank variant of the three-leg blend ----------------------
    {"name": "tskewR_news_pv", "expression": f"{TSKEW_R} + {NEWS} + {PV}",
     "theme": "ts_rank skew + news + PV.", "settings": _s(8)},
]
