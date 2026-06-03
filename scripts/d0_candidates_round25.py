"""Round-25 D0 candidates: decorrelate the NaN-filled skew below self_corr 0.70.

BREAKTHROUGH (Round 24 probe, verified by direct /alphas/{id} reads):
filling the IV-skew's NaNs (the ~30% non-optionable names) BEFORE use makes it
pass CONCENTRATED_WEIGHT and EVERY other IS check:
    if_else(is_nan(skew), 0, skew) -> SH 2.15 FIT 1.83 TO 0.27, all IS PASS
    ts_backfill(skew, 60)          -> SH 2.12 FIT 1.83 TO 0.25, all IS PASS
The NaN dropout was the whole concentration problem.

REMAINING GATE: self-correlation to the user's already-submitted pool is 0.84
(if_else) / 0.82 (ts_backfill), both ABOVE the 0.70 submit limit. The skew is
too similar to an existing submitted alpha.

Fix: blend the NaN-filled skew with the orthogonal news + PV legs (the safe
base news2_pv_d8 has self_corr only 0.357). Diluting the skew component pulls
the blend's correlation-to-pool below 0.70, while both legs are
concentration-safe and the combined SH should stay > 2.0. Sweep the skew vs
base weighting to find the point where self_corr < 0.70 AND SH > 2.0.
"""

SKEW0 = ("if_else(is_nan(-group_zscore(implied_volatility_put_60 "
         "- implied_volatility_call_60, sector)), 0, "
         "-group_zscore(implied_volatility_put_60 - implied_volatility_call_60, "
         "sector))")
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # skew-dominant -> balanced -> base-dominant (find self_corr<0.70 crossing)
    {"name": "skew0_news_pv_s10", "expression": f"{SKEW0} + {NEWS} + {PV}",
     "theme": "skew0 + news + PV (equal).", "settings": _s(8)},
    {"name": "skew0_news2_pv", "expression": f"{SKEW0} + 2 * ({NEWS}) + {PV}",
     "theme": "skew0 + 2news + PV.", "settings": _s(8)},
    {"name": "skew0_news3_pv", "expression": f"{SKEW0} + 3 * ({NEWS}) + {PV}",
     "theme": "skew0 + 3news + PV (more decorrelation).", "settings": _s(8)},
    {"name": "skew0half_news2_pv",
     "expression": f"0.5 * ({SKEW0}) + 2 * ({NEWS}) + {PV}",
     "theme": "0.5skew0 + 2news + PV.", "settings": _s(8)},
    {"name": "skew0half_news2_pv2",
     "expression": f"0.5 * ({SKEW0}) + 2 * ({NEWS}) + 2 * ({PV})",
     "theme": "0.5skew0 + 2news + 2PV (most diluted).", "settings": _s(8)},

    # base-dominant: the proven safe base news2_pv_d8 + a small skew0 kick
    {"name": "news2_pv_skew0_03", "expression": f"2 * ({NEWS}) + {PV} + 0.3 * ({SKEW0})",
     "theme": "safe base + 0.3 skew0.", "settings": _s(8)},
    {"name": "news2_pv_skew0_05", "expression": f"2 * ({NEWS}) + {PV} + 0.5 * ({SKEW0})",
     "theme": "safe base + 0.5 skew0.", "settings": _s(8)},
    {"name": "news2_pv_skew0_07", "expression": f"2 * ({NEWS}) + {PV} + 0.7 * ({SKEW0})",
     "theme": "safe base + 0.7 skew0.", "settings": _s(8)},
]
