"""Round-31 D0 candidates: optimize the best orthogonal blend toward 2.0.

State after rounds 26-30 (verified): no single orthogonal-to-survivor leg
exceeds ~0.9; the best BLEND is base4_vwap SH 1.48 FIT 1.24, concW PASS,
self_corr 0.65. The strong D0 edge lives in the iv put-call skew the survivors
already use, so a fully-orthogonal alpha tops out lower. Round 31 squeezes the
orthogonal blend as high as it goes: assemble the strongest verified orthogonal
legs, add the MOST orthogonal new ones to hold self_corr down, and sweep
decay/truncation.

Verified orthogonal leg menu (standalone SH | self_corr):
    pvcorr   0.91 | 0.65      ivmom20  0.86 | 0.39      fwd_ey   0.77 | 0.68
    revrank  0.71 | 0.51      arghigh  0.63 | 0.60      callmom  0.64 | 0.39
    vwappos  (lifts base4 to 1.48)     ivmom10  0.53 | 0.26 (most orthogonal)
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVM = "implied_volatility_mean_60"
IVC = "implied_volatility_call_60"

IVMOM = nf(gz(f"ts_delta({IVM}, 20)"))
IVMOM10 = nf(gz(f"ts_delta({IVM}, 10)"))
CALLMOM = nf(gz(f"ts_delta({IVC}, 20)"))
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


# proven 1.48 base
BASE5 = f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR} + {VWAPPOS}"

CANDIDATES = [
    # base5 + most-orthogonal extra legs
    {"name": "base5_callmom", "expression": f"{BASE5} + {CALLMOM}",
     "theme": "base5 + call-mom (selfC0.39).", "settings": _s(8)},
    {"name": "base5_revrank", "expression": f"{BASE5} + {REVRANK}",
     "theme": "base5 + rev-rank.", "settings": _s(8)},
    {"name": "base5_callmom_revrank",
     "expression": f"{BASE5} + {CALLMOM} + {REVRANK}",
     "theme": "base5 + callmom + revrank (7-leg).", "settings": _s(8)},

    # upweight the two strongest legs (pvcorr 0.91, ivmom 0.86)
    {"name": "base5_pv2iv2",
     "expression": f"2 * ({IVMOM}) + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS}",
     "theme": "base5, 2x ivmom + 2x pvcorr.", "settings": _s(8)},
    {"name": "base5_pv2iv2_callmom",
     "expression": f"2 * ({IVMOM}) + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {CALLMOM}",
     "theme": "weighted base5 + callmom.", "settings": _s(8)},

    # decay / truncation sweep on the best structure
    {"name": "base5_callmom_d6", "expression": f"{BASE5} + {CALLMOM}",
     "theme": "base5+callmom decay6.", "settings": _s(6)},
    {"name": "base5_callmom_d12", "expression": f"{BASE5} + {CALLMOM}",
     "theme": "base5+callmom decay12.", "settings": _s(12)},
    {"name": "base5_callmom_t08", "expression": f"{BASE5} + {CALLMOM}",
     "theme": "base5+callmom trunc0.08.", "settings": _s(8, 0.08)},
]
