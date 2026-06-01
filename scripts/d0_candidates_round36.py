"""Round-36: STRONG pure-reversal at delay=0, low decay (zero survivor source).

Goal: a genuinely-uncorrelated (no skew/news/PV-cov/av_diff) submittable factor
at DELAY=0. Rounds 26-35 capped skew-free blends at SH 1.52 -- BUT every
reversal probe used decay=8, which smears a FAST signal (Round 30 rev5 SH 0.3).
Short-term reversal is the classic strong d0 edge and wants LOW decay. This
round tests pure price/volume reversal forms at delay=0 with decay 0-2 and
turnover control (hump / longer formation), all NaN-safe + industry-neutral.

Signal forms (none use options/news/cov(ret,vol)/av_diff):
  R5Z   = -ts_zscore(returns,5)              short-term return reversal
  RMEAN = -ts_mean(returns,5)                mean-reversion
  RANK  = -ts_rank(close,5)                  price-rank reversal
  VWREV = -(close-vwap)/vwap                 vwap reversion (intraday)
  HLREV = -(close - ts_mean(close,5))/close  distance-from-mean reversal
  hump() wraps to cut turnover while keeping the fast edge (the trick that
  worked for news drift).
"""


def gz(x):
    return f"group_zscore({x}, industry)"


R5Z = gz("-ts_zscore(returns, 5)")
RMEAN = gz("-ts_mean(returns, 5)")
RANK = gz("-ts_rank(close, 5)")
VWREV = gz("-divide(subtract(close, vwap), vwap)")
HLREV = gz("-divide(subtract(close, ts_mean(close, 5)), close)")
R10Z = gz("-ts_zscore(returns, 10)")


def _s(decay=2, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # pure reversal at LOW decay (the correct config for a fast signal)
    {"name": "rev5z_d0", "expression": R5Z,
     "theme": "5d return-zscore reversal, no decay.", "settings": _s(0)},
    {"name": "rev5z_d2", "expression": R5Z,
     "theme": "5d return-zscore reversal, decay2.", "settings": _s(2)},
    {"name": "revmean_d2", "expression": RMEAN,
     "theme": "5d mean-reversion, decay2.", "settings": _s(2)},
    {"name": "hlrev_d2", "expression": HLREV,
     "theme": "distance-from-5d-mean reversal, decay2.", "settings": _s(2)},
    {"name": "vwrev_d2", "expression": VWREV,
     "theme": "vwap reversion, decay2.", "settings": _s(2)},

    # turnover-controlled reversal (hump keeps the edge, cuts TO)
    {"name": "rev5z_hump_d2", "expression": f"hump({R5Z}, hump=0.01)",
     "theme": "5d reversal, hump 0.01, decay2.", "settings": _s(2)},
    {"name": "rev10z_d2", "expression": R10Z,
     "theme": "10d return-zscore reversal, decay2.", "settings": _s(2)},

    # blend the reversal forms (diversify the fast edge)
    {"name": "rev_blend_d2", "expression": f"{R5Z} + {VWREV} + {HLREV}",
     "theme": "reversal blend (return+vwap+distance), decay2.", "settings": _s(2)},
]
