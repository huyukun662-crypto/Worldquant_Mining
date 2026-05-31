"""Round-27 D0 candidates: ORTHOGONAL OPTION signals (NOT the put-call skew).

Round 26 verdict (verified from WQ_D0_CHECK_REPORT.json): NaN-fill makes every
non-option family concentration-safe (concW PASS x9), but fundamental / analyst
/ social / pure-PV signals are too WEAK standalone (best anl_fwd_eyield SH 0.77)
and several are crowded (self_corr 0.72-0.78). Static value/quality just doesn't
carry Sharpe on D0.

The survivors hit ~2.0 because OPTION data carries a real edge. Those use ONE
functional form: the put-call skew (iv_put_60 - iv_call_60). But the option
family has OTHER, functionally-distinct signals that should be only partially
correlated with the skew:

  1. VARIANCE RISK PREMIUM  = implied vol - historical (realized) vol.
     A documented premium (options overprice future variance). Uses the LEVEL
     of IV vs realized, not the put-vs-call asymmetry -> orthogonal to skew.
  2. IV TERM STRUCTURE      = IV_long - IV_short (e.g. mean_180 - mean_60).
     The slope of the vol curve, again independent of put/call asymmetry.
  3. IV MOMENTUM            = ts_delta(mean IV, 20).  Change in option-implied
     vol over time -> a dynamic signal, distinct from a static skew snapshot.
  4. CALL/PUT IV TERM SKEW combos that are NOT the 60d put-call skew.

All NaN-filled with if_else(is_nan(x),0,x) (the proven concentration fix) and
industry-neutralized. Probe standalone to find which carry SH, AND we will
later measure correlation-to-survivors; for now the design intent is a
different functional form so the resulting alpha is not a skew clone.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVM60 = "implied_volatility_mean_60"
IVM180 = "implied_volatility_mean_180"
HV60 = "historical_volatility_60"
HV120 = "historical_volatility_120"

# 1. variance risk premium: IV - HV  (sign: short vol when IV>>HV -> -(IV-HV))
VRP = nf(gz(f"-({IVM60} - {HV60})"))
VRP120 = nf(gz(f"-({IVM180} - {HV120})"))
# 2. term structure: long IV - short IV  (contango/backwardation)
TERM = nf(gz(f"{IVM180} - {IVM60}"))
# 3. IV momentum
IVMOM = nf(gz(f"ts_delta({IVM60}, 20)"))
IVMOM60 = nf(gz(f"ts_delta({IVM60}, 60)"))
# 4. IV level (rich/cheap vol) — pure level, not skew
IVLVL = nf(gz(f"-{IVM60}"))


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    {"name": "opt_vrp60", "expression": VRP,
     "theme": "variance risk premium IV60-HV60.", "settings": _s(8)},
    {"name": "opt_vrp120", "expression": VRP120,
     "theme": "variance risk premium IV180-HV120.", "settings": _s(8)},
    {"name": "opt_termstruct", "expression": TERM,
     "theme": "IV term structure mean180-mean60.", "settings": _s(8)},
    {"name": "opt_ivmom20", "expression": IVMOM,
     "theme": "IV momentum ts_delta(mean60,20).", "settings": _s(8)},
    {"name": "opt_ivmom60", "expression": IVMOM60,
     "theme": "IV momentum ts_delta(mean60,60).", "settings": _s(8)},
    {"name": "opt_ivlevel", "expression": IVLVL,
     "theme": "IV level (low-vol -> long).", "settings": _s(8)},

    # composites of the orthogonal option views
    {"name": "opt_vrp_term", "expression": f"{VRP} + {TERM}",
     "theme": "VRP + term structure.", "settings": _s(8)},
    {"name": "opt_vrp_term_mom", "expression": f"{VRP} + {TERM} + {IVMOM}",
     "theme": "VRP + term + momentum (option composite).", "settings": _s(8)},
]
