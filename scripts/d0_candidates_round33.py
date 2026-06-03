"""Round-33: push the ORTHOGONAL blend to SH 2.0 at DELAY=0 (no skew).

d1_base5_revrank jumped 1.92 (decay8) -> 2.13 (decay4): LOW DECAY is the lever.
At delay=0 I only ever tested decay=8 (SH 1.52). d0 signals are fresher, so a
lower decay should help MORE. This round sweeps decay 2/4/6 on the best
orthogonal blend (base5 + revrank), plus truncation and a 7th leg, ALL at
delay=0 and using ZERO survivor signal source (no news/iv-skew/cov/av_diff) so
the result stays uncorrelated to the 3 d0 skew factors.

Orthogonal leg menu (NaN-filled, industry-neutral):
  IV-momentum, fwd-earnings-yield, days-since-high, -price-vol-corr,
  vwap-reversion, -return-rank, IV-call-momentum.
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

BASE6 = f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR} + {VWAPPOS} + {REVRANK}"


def _s(decay=4, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # decay sweep on the best orthogonal blend at delay=0
    {"name": "d0_base6_d2", "expression": BASE6,
     "theme": "base6 d0 decay2.", "settings": _s(2)},
    {"name": "d0_base6_d4", "expression": BASE6,
     "theme": "base6 d0 decay4.", "settings": _s(4)},
    {"name": "d0_base6_d6", "expression": BASE6,
     "theme": "base6 d0 decay6.", "settings": _s(6)},
    {"name": "d0_base6_d0", "expression": BASE6,
     "theme": "base6 d0 no-decay.", "settings": _s(0)},

    # upweight strongest legs (pvcorr, ivmom) at low decay
    {"name": "d0_base6w_d4",
     "expression": f"2 * ({IVMOM}) + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {REVRANK}",
     "theme": "weighted base6 d0 decay4.", "settings": _s(4)},

    # add 7th leg (callmom) at low decay
    {"name": "d0_base7_d4", "expression": f"{BASE6} + {CALLMOM}",
     "theme": "base6+callmom d0 decay4.", "settings": _s(4)},

    # tighter truncation insurance at decay4
    {"name": "d0_base6_d4_t03", "expression": BASE6,
     "theme": "base6 d0 decay4 trunc0.03.", "settings": _s(4, 0.03)},

    # subindustry neutralization (finer groups, may lift Sharpe)
    {"name": "d0_base6_d4_subind", "expression": BASE6,
     "theme": "base6 d0 decay4 subindustry.", "settings": _s(4, 0.05, "SUBINDUSTRY")},
]
