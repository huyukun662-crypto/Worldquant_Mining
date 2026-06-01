"""Round-37: maximize the ZERO-survivor d0 blend by leading with IV-momentum.

Reversal failed (Round 36). The cleanest strong orthogonal leg is IV-MOMENTUM
(opt_ivmom20 SH 0.86, self_corr 0.39) -- option-vol-LEVEL momentum, which uses
option data but NOT the put-call skew the survivors use, so it stays orthogonal.
This round builds a richer IV-momentum family (multiple horizons + acceleration)
as the CORE, supported by the other orthogonal legs (fwd-EY, days-since-high,
pvcorr, vwap, revrank), optimizing weights + decay at delay=0 to push the
zero-survivor blend past its SH 1.52 ceiling. NO skew / news / cov(ret,vol) /
av_diff anywhere -> genuinely uncorrelated to all 5 existing factors.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


M30 = "implied_volatility_mean_30"
M60 = "implied_volatility_mean_60"
M90 = "implied_volatility_mean_90"
M120 = "implied_volatility_mean_120"

# IV-momentum family (multiple horizons + acceleration) -- the orthogonal core
IVM20 = nf(gz(f"ts_delta({M60}, 20)"))
IVM10 = nf(gz(f"ts_delta({M60}, 10)"))
IVM_SHORT = nf(gz(f"ts_delta({M30}, 10)"))
IVM_ACCEL = nf(gz(f"ts_delta({M60}, 10) - ts_delta({M60}, 20)"))   # accel
IVCORE = f"{IVM20} + {IVM10} + {IVM_SHORT} + {IVM_ACCEL}"

# supporting orthogonal legs
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))
SUPPORT = f"{FEY} + {ARGHI} + {PVCORR} + {VWAPPOS} + {REVRANK}"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # IV-momentum core alone (does the richer family beat 0.86?)
    {"name": "ivcore", "expression": IVCORE,
     "theme": "IV-momentum family (4 horizons+accel).", "settings": _s(8)},

    # core + support, weight the IV core up
    {"name": "iv2_support", "expression": f"2 * ({IVCORE}) + {SUPPORT}",
     "theme": "2x IV-core + support.", "settings": _s(8)},
    {"name": "iv3_support", "expression": f"3 * ({IVCORE}) + {SUPPORT}",
     "theme": "3x IV-core + support.", "settings": _s(8)},
    {"name": "iv_support", "expression": f"{IVCORE} + {SUPPORT}",
     "theme": "IV-core + support equal.", "settings": _s(8)},

    # decay sweep on the best structure
    {"name": "iv2_support_d4", "expression": f"2 * ({IVCORE}) + {SUPPORT}",
     "theme": "2x IV-core + support, decay4.", "settings": _s(4)},
    {"name": "iv2_support_d12", "expression": f"2 * ({IVCORE}) + {SUPPORT}",
     "theme": "2x IV-core + support, decay12.", "settings": _s(12)},

    # upweight pvcorr too (strongest support leg)
    {"name": "iv2_pv2_support",
     "expression": f"2 * ({IVCORE}) + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {REVRANK}",
     "theme": "2x IV-core + 2x pvcorr + support.", "settings": _s(8)},

    # subindustry neut
    {"name": "iv2_support_subind", "expression": f"2 * ({IVCORE}) + {SUPPORT}",
     "theme": "2x IV-core + support, subindustry.", "settings": _s(8, 0.05, "SUBINDUSTRY")},
]
