"""Round-32: test the best ORTHOGONAL blends at DELAY=1 (lower Sharpe bar).

Rounds 26-31 proved a fully-orthogonal-to-survivor blend caps at SH ~1.52
(base5_revrank), which FAILS the delay=0 LOW_SHARPE limit of 2.0. Adding skew
back would lift Sharpe but make the factor CORRELATED with the 3 skew-based
survivors -- defeating the user's "uncorrelated" goal.

But the delay=0 2.0 bar is specific to D0. At DELAY=1 the LOW_SHARPE limit is
typically 1.25. So the genuinely-orthogonal SH ~1.5 blend may pass ALL submit
checks at delay=1 while staying uncorrelated to the survivors AND keeping
self_corr < 0.70 to the submitted pool. This round re-runs the top orthogonal
blends at delay=1 to (a) confirm the delay=1 LOW_SHARPE limit and (b) find a
genuinely-uncorrelated submittable factor.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVM = "implied_volatility_mean_60"
IVC = "implied_volatility_call_60"

IVMOM = nf(gz(f"ts_delta({IVM}, 20)"))
CALLMOM = nf(gz(f"ts_delta({IVC}, 20)"))
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))

BASE5 = f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR} + {VWAPPOS}"


def _s(delay=1, decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": delay, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # the best orthogonal blends, now at delay=1
    {"name": "d1_base5_revrank", "expression": f"{BASE5} + {REVRANK}",
     "theme": "base5+revrank @ delay1.", "settings": _s(1, 8)},
    {"name": "d1_base5_callmom", "expression": f"{BASE5} + {CALLMOM}",
     "theme": "base5+callmom @ delay1.", "settings": _s(1, 8)},
    {"name": "d1_base5_callmom_revrank",
     "expression": f"{BASE5} + {CALLMOM} + {REVRANK}",
     "theme": "base5+callmom+revrank @ delay1.", "settings": _s(1, 8)},
    {"name": "d1_base5", "expression": BASE5,
     "theme": "base5 @ delay1.", "settings": _s(1, 8)},

    # delay=1 with decay variants (delay1 often likes more decay)
    {"name": "d1_base5_revrank_d12", "expression": f"{BASE5} + {REVRANK}",
     "theme": "base5+revrank @ delay1 decay12.", "settings": _s(1, 12)},
    {"name": "d1_base5_revrank_d4", "expression": f"{BASE5} + {REVRANK}",
     "theme": "base5+revrank @ delay1 decay4.", "settings": _s(1, 4)},

    # upweighted strong legs @ delay1
    {"name": "d1_base5_pv2iv2",
     "expression": f"2 * ({IVMOM}) + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {REVRANK}",
     "theme": "weighted base5+revrank @ delay1.", "settings": _s(1, 8)},

    # control: same at delay=0 to confirm the bar difference
    {"name": "d0_base5_revrank_control", "expression": f"{BASE5} + {REVRANK}",
     "theme": "control: base5+revrank @ delay0.", "settings": _s(0, 8)},
]
