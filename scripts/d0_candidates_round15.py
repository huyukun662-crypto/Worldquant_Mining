"""Round-15 D0 candidates: dilute the option cluster to break concW < 0.10.

Rounds 12-14 hit a hard floor: CONCENTRATED_WEIGHT bottoms at ~0.103 (limit
0.10) no matter how we coarsen the skew standardization or raise decay. The
floor is structural -- IV skew only covers ~70% of names, so the optionable
large-cap cluster holds >10% of the book even after every smoothing trick.
WQ now returns the check as a bare {"result":"FAIL"} (no value), confirming
it is a real fail, not a pending read.

Two un-tried levers attack the cluster directly:
  1. BREADTH DILUTION: add a full-coverage leg (PV core, coverage 1.0; news,
     0.91) with enough weight that the option cluster is ~1/3 of book risk,
     pushing its weight share under 10%. Round 13 showed 0.5x PV -> 0.1046;
     scale PV to 1.0-1.5x.
  2. AGGRESSIVE TRUNCATION: 0.05->0.04 barely moved it, but the relationship
     may be convex -- test 0.02/0.03 hard caps.
The tension is Sharpe: too much PV dilutes the skew edge (equal-weight skew+PV
was only 1.54). Keep skew at full weight, add breadth on top, decay ~18-20 for
fitness, and downweight-skew variants as fallback.
"""

SKEW_SEC = "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, sector)"
SKEW_MKT = "-zscore(implied_volatility_put_60 - implied_volatility_call_60)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=18, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- aggressive truncation on the best structure ------------------
    {"name": "sec_skew_news_d20_t03", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sector skew + news, d20, trunc0.03.", "settings": _s(20, 0.03)},
    {"name": "sec_skew_news_d20_t02", "expression": f"{SKEW_SEC} + {NEWS}",
     "theme": "sector skew + news, d20, trunc0.02.", "settings": _s(20, 0.02)},

    # --- breadth dilution: full-coverage PV scaled up ----------------
    {"name": "sec_skew_news_pv1_d18", "expression": f"{SKEW_SEC} + {NEWS} + {PV}",
     "theme": "sector skew + news + 1.0 PV breadth, d18.", "settings": _s(18, 0.05)},
    {"name": "sec_skew_news_pv15_d18", "expression": f"{SKEW_SEC} + {NEWS} + 1.5 * ({PV})",
     "theme": "sector skew + news + 1.5 PV, d18.", "settings": _s(18, 0.05)},
    {"name": "sec_skew_news15_pv1_d20", "expression": f"{SKEW_SEC} + 1.5 * ({NEWS}) + {PV}",
     "theme": "sector skew + 1.5 news + 1.0 PV, d20.", "settings": _s(20, 0.05)},

    # --- downweight skew so the cluster is a minority of book ---------
    {"name": "skew07_news_pv_d18", "expression": f"0.7 * ({SKEW_SEC}) + {NEWS} + 0.5 * ({PV})",
     "theme": "0.7 skew + news + 0.5 PV (skew minority), d18.", "settings": _s(18, 0.05)},

    # --- combine both levers: breadth + low truncation ----------------
    {"name": "sec_skew_news_pv1_d18_t03", "expression": f"{SKEW_SEC} + {NEWS} + {PV}",
     "theme": "skew + news + 1.0 PV, d18, trunc0.03.", "settings": _s(18, 0.03)},
    {"name": "mz_skew_news_pv1_d20_t03", "expression": f"{SKEW_MKT} + {NEWS} + {PV}",
     "theme": "market-z skew + news + 1.0 PV, d20, trunc0.03.", "settings": _s(20, 0.03)},
]
