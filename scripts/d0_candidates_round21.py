"""Round-21 D0 candidates: per-name TEMPORAL normalization of IV skew.

Every prior IV attempt used CROSS-SECTIONAL standardization (group_zscore /
zscore / rank / winsorize across names), and all hit a CONCENTRATED_WEIGHT
floor ~0.103 (limit 0.10) because the skew's edge lives in a few extreme
optionable large-caps that then dominate the book.

New, untried lever: normalize the skew over each name's OWN HISTORY
(ts_rank / ts_zscore) BEFORE the cross-sectional neutralization. This:
  * bounds each name's signal vs its own past (ts_rank -> [0,1];
    ts_zscore -> ~[-3,3]) so a name with structurally high skew no longer
    produces a cross-sectional outlier -> should cut concentration, and
  * keeps a real signal: "is this name's call-vs-put IV unusually high vs
    its own norm?" (option-positioning momentum), which the cross-sectional
    z-score throws away.

Profitable skew direction (verified from real Round-9 record): SH +2.17 came
from -group_zscore(put60 - call60) = group_zscore(call60 - put60). So the raw
edge variable is SKEW = call60 - put60 (no leading minus needed; ts_rank and
group_zscore are both monotonic so they preserve the sign).

Probe standalone first (cheap: tells us if temporal-norm passes concentration
at all), then stack with the proven concentration-safe news + PV legs.
"""

SKEW = "implied_volatility_call_60 - implied_volatility_put_60"
TSR60 = f"group_zscore(ts_rank({SKEW}, 60), industry)"
TSR120 = f"group_zscore(ts_rank({SKEW}, 120), industry)"
TSZ120 = f"group_zscore(ts_zscore({SKEW}, 120), industry)"
NEWS = "group_zscore(ts_mean(news_pct_120min, 5), industry)"
PV = ("-zscore(ts_covariance(returns, volume, 20)) "
      "- group_zscore(ts_av_diff(close, 5), industry)")


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # --- standalone temporal-norm skew (does it pass concentration?) --
    {"name": "tsr_skew60", "expression": TSR60,
     "theme": "ts_rank(call-put,60) per-name temporal skew.", "settings": _s(8)},
    {"name": "tsr_skew120", "expression": TSR120,
     "theme": "ts_rank(call-put,120).", "settings": _s(8)},
    {"name": "tsz_skew120", "expression": TSZ120,
     "theme": "ts_zscore(call-put,120) per-name.", "settings": _s(8)},

    # --- temporal-norm skew + news (concentration-safe partner) -------
    {"name": "tsr60_news", "expression": f"{TSR60} + {NEWS}",
     "theme": "tsr-skew60 + news.", "settings": _s(8)},
    {"name": "tsz120_news", "expression": f"{TSZ120} + {NEWS}",
     "theme": "tsz-skew120 + news.", "settings": _s(8)},

    # --- temporal-norm skew + news + PV (push to 2.0) -----------------
    {"name": "tsr60_news_pv", "expression": f"{TSR60} + {NEWS} + {PV}",
     "theme": "tsr-skew60 + news + PV.", "settings": _s(8)},
    {"name": "tsz120_news_pv", "expression": f"{TSZ120} + {NEWS} + {PV}",
     "theme": "tsz-skew120 + news + PV.", "settings": _s(8)},

    # --- upweight the temporal skew (it carries the Sharpe) -----------
    {"name": "tsr60x2_news_pv", "expression": f"2 * ({TSR60}) + {NEWS} + {PV}",
     "theme": "2x tsr-skew60 + news + PV.", "settings": _s(8)},
]
