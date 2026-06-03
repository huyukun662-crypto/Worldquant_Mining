"""Round-18 D0 candidates: find a 3rd concentration-SAFE orthogonal leg.

After 17 rounds the trade-off is pinned down:
  * IV-skew family: SH 2.5 on TOP3000 but CONCENTRATED_WEIGHT is unfixable
    (option ~70% coverage; shrinking the universe kills the Sharpe AND still
    concentrates). Dead end.
  * concentration-safe news+PV: caps at SH 1.75.

Route to >=2.0 that can actually pass concentration: add a THIRD broad-coverage,
dense, concentration-safe signal orthogonal to BOTH post-news drift and
price/volume reversal. Three uncorrelated ~1.4-SH legs blend to ~1.4*sqrt(3)
~= 2.4. Candidate 3rd legs (each economically distinct, all full/dense coverage):

  LOWVOL  = -group_zscore(ts_std_dev(returns, 60), industry)   low-vol premium
            (pure PV, coverage 1.0 -> certainly concentration-safe)
  EY      = group_zscore(divide(operating_income, enterprise_value), sector)  earnings yield (value)
  GP      = group_zscore(divide(ebitda, assets), sector)       gross profitability (quality)
  AG      = -group_zscore(ts_delta(assets, 60), sector)        asset-growth anomaly

This round probes each standalone (sign/strength/concentration unknown) AND the
most promising blends with the news+PV base, in one pass.
"""

NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")
LOWVOL = "-group_zscore(ts_std_dev(returns, 60), industry)"
EY = "group_zscore(divide(operating_income, enterprise_value), sector)"
GP = "group_zscore(divide(ebitda, assets), sector)"
AG = "-group_zscore(ts_delta(assets, 60), sector)"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- standalone probes of candidate 3rd legs ---------------------
    {"name": "lowvol60", "expression": LOWVOL,
     "theme": "low-vol premium standalone.", "settings": _s(8)},
    {"name": "value_ey", "expression": EY,
     "theme": "earnings yield (OI/EV) standalone.", "settings": _s(8)},
    {"name": "quality_gp", "expression": GP,
     "theme": "gross profitability (EBITDA/assets) standalone.", "settings": _s(8)},
    {"name": "asset_growth", "expression": AG,
     "theme": "asset-growth anomaly standalone.", "settings": _s(8)},

    # --- blends: news+PV base + 3rd leg ------------------------------
    {"name": "news2_pv_lowvol", "expression": f"2 * ({NEWS}) + {PV} + {LOWVOL}",
     "theme": "2x news + PV + low-vol.", "settings": _s(8)},
    {"name": "news2_pv_ey", "expression": f"2 * ({NEWS}) + {PV} + {EY}",
     "theme": "2x news + PV + earnings yield.", "settings": _s(8)},
    {"name": "news2_pv_lowvol_ey",
     "expression": f"2 * ({NEWS}) + {PV} + {LOWVOL} + {EY}",
     "theme": "2x news + PV + low-vol + earnings yield (4-leg).", "settings": _s(8)},
    {"name": "news2_pv_lowvol_gp",
     "expression": f"2 * ({NEWS}) + {PV} + {LOWVOL} + {GP}",
     "theme": "2x news + PV + low-vol + gross profit (4-leg).", "settings": _s(8)},
]
