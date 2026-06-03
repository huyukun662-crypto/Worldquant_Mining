"""Round-41: op-efficient base6 -> pack more orthogonal legs under the 64 limit.

Round-40 hit the 64-operator wall (71-78 ops) because EVERY leg was wrapped in
if_else(is_nan(X),0,X), which duplicates X and ~doubles its op count. But only
the SPARSE legs actually need NaN-fill: option (implied_volatility_*) and
analyst (est_*) and social (snt_*) data cover <100% of TOP3000. The DENSE PV
legs -- ts_arg_max(close), ts_corr(close,volume), vwap reversion, ts_rank(returns)
-- have no NaN to fill, so their wrapper is pure wasted budget.

This round uses a LEAN base6 (NaN-fill only on the sparse option/analyst legs,
bare group_zscore on the dense PV legs), which frees ~20 operators -- enough to
add the orthogonal social + analyst legs that previously overflowed. Quadrature
predicts the fully-orthogonal d0 ceiling is ~1.8 even with every weak orthogonal
leg added, so this most likely CONFIRMS the ceiling rather than breaking 2.0 --
but it is the one untested lever, so we run it to close the question empirically.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


# ---- LEAN base6: NaN-fill ONLY the sparse option/analyst legs ----
IVMOM = nf(gz("ts_delta(implied_volatility_mean_60, 20)"))  # option: sparse
FEY = nf(gz("divide(est_epsr, close)"))                     # analyst: sparse
ARGHI = gz("ts_arg_max(close, 60)")                         # dense: bare
PVCORR = gz("-ts_corr(close, volume, 20)")                  # dense: bare
VWAPPOS = gz("-divide(subtract(close, vwap), vwap)")        # dense: bare
REVRANK = gz("-ts_rank(returns, 10)")                       # dense: bare
LEAN_BASE6 = f"{IVMOM} + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {REVRANK}"

# ---- orthogonal legs to pack in (sparse -> keep NaN-fill) ----
SOCVAL = nf(gz("ts_mean(snt_social_value, 5)"))   # +0.50, selfC 0.41 (best orth)
SENTVAL = nf(gz("ts_mean(snt_value, 5)"))         # +0.35, selfC 0.37
SCLSENT = nf(gz("-ts_mean(scl12_sentiment, 5)"))  # round39 raw -0.25 -> flip
EBREV = nf(gz("ts_delta(est_ebitda, 60)"))        # +0.30, selfC 0.41
FCFY = nf(gz("divide(est_fcf, close)"))           # +0.69, selfC 0.68 (value-corr)


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # all-orthogonal pack (no value-yield, self-corr should stay safe)
    {"name": "lean_soc3", "expression": f"{LEAN_BASE6} + 2 * ({SOCVAL}) + {SENTVAL} + {EBREV}",
     "theme": "lean base6 + 2x socval + sentval + ebitda-rev.", "settings": _s()},
    {"name": "lean_soc4", "expression": f"{LEAN_BASE6} + 2 * ({SOCVAL}) + {SENTVAL} + {SCLSENT} + {EBREV}",
     "theme": "lean base6 + all 3 social + ebitda-rev.", "settings": _s()},

    # add the strong value-yield leg now that budget allows (watch self_corr)
    {"name": "lean_socfcf", "expression": f"{LEAN_BASE6} + 2 * ({SOCVAL}) + {SENTVAL} + {FCFY}",
     "theme": "lean base6 + social + FCF yield.", "settings": _s()},
    {"name": "lean_max", "expression": f"{LEAN_BASE6} + 2 * ({SOCVAL}) + {SENTVAL} + {SCLSENT} + {EBREV} + {FCFY}",
     "theme": "lean base6 + everything orthogonal.", "settings": _s()},

    # decay sweep on the all-orthogonal pack
    {"name": "lean_soc3_d4", "expression": f"{LEAN_BASE6} + 2 * ({SOCVAL}) + {SENTVAL} + {EBREV}",
     "theme": "lean_soc3 decay4.", "settings": _s(decay=4)},
    {"name": "lean_soc3_d12", "expression": f"{LEAN_BASE6} + 2 * ({SOCVAL}) + {SENTVAL} + {EBREV}",
     "theme": "lean_soc3 decay12.", "settings": _s(decay=12)},
]
