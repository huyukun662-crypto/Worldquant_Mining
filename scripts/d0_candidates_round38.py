"""Round-38: final push on zero-survivor d0 base6 via settings optimization.

base6 (IV-mom+fwd-EY+arg-high+pvcorr+vwap+revrank, all NaN-filled) is the best
ZERO-survivor blend: SH 1.52 at d0 (decay8/INDUSTRY/trunc0.05). The expression
space is exhausted (reversal/IV-family/skew-dynamics all failed). The remaining
untried lever is the SETTINGS search space -- neutralization and truncation,
which are legitimately part of the optimization per project spec. This round
sweeps neutralization (SUBINDUSTRY/SECTOR/MARKET) x truncation (0.02-0.10) on
the proven base6 to find the configuration that maximizes d0 Sharpe. If nothing
clears 2.0, the honest ceiling for a fully-uncorrelated d0 factor is ~1.5-1.6.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVMOM = nf(gz("ts_delta(implied_volatility_mean_60, 20)"))
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
REVRANK = nf(gz("-ts_rank(returns, 10)"))
BASE6 = f"{IVMOM} + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {REVRANK}"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "delay": 0, "decay": decay,
            "neutralization": neut, "truncation": trunc}


CANDIDATES = [
    # neutralization sweep
    {"name": "b6_subind_t05", "expression": BASE6,
     "theme": "base6 subindustry trunc0.05.", "settings": _s(8, 0.05, "SUBINDUSTRY")},
    {"name": "b6_sector_t05", "expression": BASE6,
     "theme": "base6 sector trunc0.05.", "settings": _s(8, 0.05, "SECTOR")},
    {"name": "b6_market_t05", "expression": BASE6,
     "theme": "base6 market trunc0.05.", "settings": _s(8, 0.05, "MARKET")},

    # truncation sweep (industry)
    {"name": "b6_ind_t02", "expression": BASE6,
     "theme": "base6 industry trunc0.02.", "settings": _s(8, 0.02)},
    {"name": "b6_ind_t10", "expression": BASE6,
     "theme": "base6 industry trunc0.10.", "settings": _s(8, 0.10)},

    # best-guess combos
    {"name": "b6_subind_t02", "expression": BASE6,
     "theme": "base6 subindustry trunc0.02.", "settings": _s(8, 0.02, "SUBINDUSTRY")},
    {"name": "b6_subind_d12", "expression": BASE6,
     "theme": "base6 subindustry decay12.", "settings": _s(12, 0.05, "SUBINDUSTRY")},
    {"name": "b6_subind_d4", "expression": BASE6,
     "theme": "base6 subindustry decay4.", "settings": _s(4, 0.05, "SUBINDUSTRY")},
]
