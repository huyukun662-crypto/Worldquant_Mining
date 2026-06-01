"""Round-29 D0 candidates: push the orthogonal blend past SH 2.0.

Round 28 best (verified): ivmom_fey_argpx (IV-mom + fwd-EY + arg-high + pv-corr)
SH 1.41 FIT 1.30, only LOW_SHARPE failing, self_corr 0.63, concW PASS. The
diversification of orthogonal concentration-safe legs is working; we need ~0.6
more Sharpe. Verified standalone leg strengths (all NaN-filled, industry-neut):
    px_pvcorr   SH 0.91   (neg price-volume corr, 20d)   <- strongest fresh leg
    opt_ivmom20 SH 0.86   (IV momentum)
    anl_fwd_ey  SH 0.77   (forward earnings yield)
    px_arghigh  SH 0.63   (days since 60d high)

Round 29 (a) upweights the strongest legs (pvcorr, ivmom), (b) adds MORE fresh
orthogonal legs to deepen diversification, and (c) sweeps decay:
    PVCORR2 = -ts_corr(close, volume, 60)    longer-window price-vol corr
    VWAPpos = -(close - vwap)/vwap           intraday vwap reversion
    RNG     = ts_std_dev(returns, 20)        realized-vol (low-vol premium, neg)
    VOLTRD  = -ts_delta(ts_mean(volume,5), 20)  volume-trend reversal
Every leg avoids the survivors' news_pct/iv-skew/ts_cov(ret,vol)/ts_av_diff.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVM60 = "implied_volatility_mean_60"

IVMOM = nf(gz(f"ts_delta({IVM60}, 20)"))
FEY = nf(gz("divide(est_epsr, close)"))
ARGHI = nf(gz("ts_arg_max(close, 60)"))
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))
# new fresh orthogonal legs
PVCORR60 = nf(gz("-ts_corr(close, volume, 60)"))
VWAPPOS = nf(gz("-divide(subtract(close, vwap), vwap)"))
RNG = nf(gz("-ts_std_dev(returns, 20)"))            # low realized-vol premium
VOLTRD = nf(gz("-ts_delta(ts_mean(volume, 5), 20)"))


# the proven Round-28 4-leg base
BASE4 = f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR}"


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # upweight strongest legs in the proven base
    {"name": "base4_pvcorr2", "expression": f"{IVMOM} + {FEY} + {ARGHI} + 2 * ({PVCORR})",
     "theme": "base4, 2x pvcorr.", "settings": _s(8)},
    {"name": "base4_ivmom2", "expression": f"2 * ({IVMOM}) + {FEY} + {ARGHI} + {PVCORR}",
     "theme": "base4, 2x ivmom.", "settings": _s(8)},

    # add fresh legs (deepen diversification)
    {"name": "base4_vwap", "expression": f"{BASE4} + {VWAPPOS}",
     "theme": "base4 + vwap reversion.", "settings": _s(8)},
    {"name": "base4_rng", "expression": f"{BASE4} + {RNG}",
     "theme": "base4 + low-vol premium.", "settings": _s(8)},
    {"name": "base4_pvcorr60", "expression": f"{BASE4} + {PVCORR60}",
     "theme": "base4 + pvcorr60.", "settings": _s(8)},

    # big multi-leg blends
    {"name": "blend6", "expression": f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR} + {VWAPPOS} + {RNG}",
     "theme": "6-leg orthogonal blend.", "settings": _s(8)},
    {"name": "blend6_pvw",
     "expression": f"{IVMOM} + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {RNG}",
     "theme": "6-leg, 2x pvcorr.", "settings": _s(8)},

    # best blend at higher decay (smoother -> often lifts Sharpe)
    {"name": "blend6_d12",
     "expression": f"{IVMOM} + {FEY} + {ARGHI} + 2 * ({PVCORR}) + {VWAPPOS} + {RNG}",
     "theme": "6-leg 2x-pvcorr, decay 12.", "settings": _s(12)},
]
