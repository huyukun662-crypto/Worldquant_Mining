"""Round-34: strong d0 from skew DYNAMICS, vector-neutralized vs the survivors.

Proven over rounds 26-33: a skew-FREE orthogonal blend cannot reach SH 2.0 at
delay=0 -- the strong d0 edge is in the option skew. The 3 survivors use the
STATIC skew LEVEL: S = -group_zscore(iv_put_60 - iv_call_60, sector). A
different FUNCTION of the same option data can carry d0 Sharpe yet be only
partially correlated with the level:

  - SKEW INNOVATION:  the level minus its own recent mean (ts_zscore) -> the
    surprise/change in skew, not the level.
  - SKEW MOMENTUM:    ts_delta of the skew.
  - SKEW TERM CHANGE: 60d skew vs 120d skew.

To make it genuinely uncorrelated to the survivors, vector_neut(signal, S)
projects OUT the survivors' exact skew-level leg, leaving the orthogonal
residual. We then blend that residual with the SH-1.5 orthogonal base so the
resulting alpha (a) carries option Sharpe and (b) has self_corr < 0.70 to the
pool. All NaN-filled + industry-neutral.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVP = "implied_volatility_put_60"
IVC = "implied_volatility_call_60"
IVP120 = "implied_volatility_put_120"
IVC120 = "implied_volatility_call_120"
IVM = "implied_volatility_mean_60"

# the survivors' exact skew-level leg (what we want to be orthogonal TO)
SKEW_LEVEL = f"group_zscore({IVP} - {IVC}, sector)"

# skew dynamics (different function of the same data)
SKEW_INNOV = nf(gz(f"ts_zscore({IVP} - {IVC}, 60)"))         # innovation/surprise
SKEW_MOM = nf(gz(f"-ts_delta({IVP} - {IVC}, 20)"))           # skew momentum
SKEW_TERM = nf(gz(f"-(({IVP} - {IVC}) - ({IVP120} - {IVC120}))"))  # term change

# vector-neutralize the skew-momentum vs the survivors' level -> residual
SKEW_MOM_RESID = nf(f"vector_neut(gz_mom, gz_level)"
                    .replace("gz_mom", f"group_zscore(-ts_delta({IVP} - {IVC}, 20), industry)")
                    .replace("gz_level", f"group_zscore({IVP} - {IVC}, industry)"))

# orthogonal SH~1.5 base (skew-free) to blend with
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
    # standalone skew-dynamics probes (which carry d0 Sharpe?)
    {"name": "skew_innov", "expression": SKEW_INNOV,
     "theme": "skew innovation ts_zscore(put-call,60).", "settings": _s(8)},
    {"name": "skew_mom", "expression": SKEW_MOM,
     "theme": "skew momentum -ts_delta(put-call,20).", "settings": _s(8)},
    {"name": "skew_term", "expression": SKEW_TERM,
     "theme": "skew term change 60 vs 120.", "settings": _s(8)},
    {"name": "skew_mom_resid", "expression": SKEW_MOM_RESID,
     "theme": "skew-momentum vector-neut vs level.", "settings": _s(8)},

    # blend skew-dynamics with the orthogonal base (carry Sharpe, hold self_corr)
    {"name": "base6_skewinnov", "expression": f"{BASE6} + {SKEW_INNOV}",
     "theme": "base6 + skew innovation.", "settings": _s(8)},
    {"name": "base6_skewmom", "expression": f"{BASE6} + {SKEW_MOM}",
     "theme": "base6 + skew momentum.", "settings": _s(8)},
    {"name": "base6_skewmom2", "expression": f"{BASE6} + 2 * ({SKEW_MOM})",
     "theme": "base6 + 2x skew momentum.", "settings": _s(8)},
    {"name": "base6_skewmomresid", "expression": f"{BASE6} + 2 * ({SKEW_MOM_RESID})",
     "theme": "base6 + 2x vector-neut skew-mom.", "settings": _s(8)},
]
