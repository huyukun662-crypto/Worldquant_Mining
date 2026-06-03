"""Round-35: d0 SH>=2.0 via skew + ORTHOGONAL base (different decorrelator).

Conclusively proven (rounds 26-34): the strong d0 edge is the static skew
LEVEL; a skew-free blend caps at SH 1.5. So a d0 factor reaching 2.0 MUST use
the skew. The 3 survivors decorrelate the skew with news+PV. This round
decorrelates it instead with the SH-1.5 ORTHOGONAL base6 (IV-mom + fwd-EY +
days-since-high + pvcorr + vwap + revrank) -- a completely different supporting
structure. The result shares ONLY the skew leg with the survivors, so it is a
structurally distinct d0 factor; we read its self_corr to gauge how decorrelated
it actually is. Sweep the skew weight to trade Sharpe vs self_corr.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVP = "implied_volatility_put_60"
IVC = "implied_volatility_call_60"
IVM = "implied_volatility_mean_60"

# the strong skew level, NaN-filled (concentration-safe), sector-neutral
SKEW = nf(f"-group_zscore({IVP} - {IVC}, sector)")

# orthogonal base6 (SH ~1.5, skew-free) as the decorrelator
IVMOM = nf(gz(f"ts_delta({IVM}, 20)"))
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))
BASE6 = f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR} + {VWAPPOS} + {REVRANK}"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # skew weight sweep on top of the orthogonal base (find SH>=2 with low selfC)
    {"name": "obase_skew05", "expression": f"{BASE6} + 0.5 * ({SKEW})",
     "theme": "orthog base6 + 0.5 skew.", "settings": _s(8)},
    {"name": "obase_skew10", "expression": f"{BASE6} + 1.0 * ({SKEW})",
     "theme": "orthog base6 + 1.0 skew.", "settings": _s(8)},
    {"name": "obase_skew15", "expression": f"{BASE6} + 1.5 * ({SKEW})",
     "theme": "orthog base6 + 1.5 skew.", "settings": _s(8)},
    {"name": "obase_skew20", "expression": f"{BASE6} + 2.0 * ({SKEW})",
     "theme": "orthog base6 + 2.0 skew.", "settings": _s(8)},
    {"name": "obase2_skew10", "expression": f"2 * ({BASE6}) + 1.0 * ({SKEW})",
     "theme": "2x orthog base6 + 1.0 skew (base-dominant).", "settings": _s(8)},
    {"name": "obase3_skew10", "expression": f"3 * ({BASE6}) + 1.0 * ({SKEW})",
     "theme": "3x orthog base6 + 1.0 skew (most decorrelated).", "settings": _s(8)},
    {"name": "obase_skew10_d6", "expression": f"{BASE6} + 1.0 * ({SKEW})",
     "theme": "orthog base6 + skew, decay6.", "settings": _s(6)},
    {"name": "obase2_skew15", "expression": f"2 * ({BASE6}) + 1.5 * ({SKEW})",
     "theme": "2x base6 + 1.5 skew.", "settings": _s(8)},
]
