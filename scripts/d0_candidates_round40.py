"""Round-40: empirical orthogonal-d0 ceiling -- base6 (X) new orthogonal legs.

Round-39 established each NEW orthogonal source's standalone d0 strength:
  soc_socval  SH 0.50  selfC 0.41   (snt_social_value, truly orthogonal)
  soc_sentval SH 0.35  selfC 0.37   (snt_value raw sign, truly orthogonal)
  an_fcfy     SH 0.69  selfC 0.68   (fwd FCF yield -- strong but value-correlated)
base6 is the proven zero-survivor orthogonal blend at SH 1.52.

Diversification of uncorrelated positive-SR legs adds in quadrature, so the
THEORETICAL ceiling of base6 (X) {socval, sentval} is sqrt(1.52^2+0.5^2+0.35^2)
~= 1.62, and adding fcfy ~1.78 -- both below the hard d0 LOW_SHARPE gate of 2.0.
This round tests that empirically: if the best fully-orthogonal d0 blend lands
~1.6-1.8, the orthogonal-d0 ceiling < 2.0 is confirmed across ALL families
(option/news/PV/earnings/social/analyst). fcfy variants also report self_corr so
we see whether including the value-yield leg breaches the 0.70 self-corr gate.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


# ---- base6: proven zero-survivor orthogonal blend (SH 1.52 at d0) ----
IVMOM = nf(gz("ts_delta(implied_volatility_mean_60, 20)"))
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))
BASE6 = f"{IVMOM} + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {REVRANK}"

# ---- new orthogonal legs, CORRECT signs from round-39 ----
SOCVAL = nf(gz("ts_mean(snt_social_value, 5)"))   # +0.50, selfC 0.41 (safe)
SENTVAL = nf(gz("ts_mean(snt_value, 5)"))         # +0.35, selfC 0.37 (safe)
FCFY = nf(gz("divide(est_fcf, close)"))           # +0.69, selfC 0.68 (risky)
EBREV = nf(gz("ts_delta(est_ebitda, 60)"))        # +0.30, selfC 0.41


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # base6 + truly-orthogonal social legs (self-corr stays safe)
    {"name": "b6_soc2", "expression": f"{BASE6} + {SOCVAL} + {SENTVAL}",
     "theme": "base6 + social (safe-orthogonal).", "settings": _s()},
    {"name": "b6_socval2", "expression": f"{BASE6} + 2 * ({SOCVAL})",
     "theme": "base6 + 2x strongest social leg.", "settings": _s()},

    # add the strong-but-value-correlated FCF yield (watch self_corr)
    {"name": "b6_soc_fcf", "expression": f"{BASE6} + {SOCVAL} + {SENTVAL} + {FCFY}",
     "theme": "base6 + social + FCF yield.", "settings": _s()},
    {"name": "b6_fcf2", "expression": f"{BASE6} + 2 * ({FCFY})",
     "theme": "base6 + 2x FCF yield.", "settings": _s()},

    # everything orthogonal, optimally co-weighted attempt
    {"name": "b6_all_new",
     "expression": f"{BASE6} + {SOCVAL} + {SENTVAL} + {FCFY} + {EBREV}",
     "theme": "base6 + all new orthogonal legs.", "settings": _s()},
    # same, lower decay to chase d0 Sharpe
    {"name": "b6_all_d4",
     "expression": f"{BASE6} + {SOCVAL} + {SENTVAL} + {FCFY} + {EBREV}",
     "theme": "base6 + all new, decay4.", "settings": _s(decay=4)},
]
