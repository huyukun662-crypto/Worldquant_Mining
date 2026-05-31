"""Round-28 D0 candidates: BLEND the best orthogonal legs toward SH 2.0.

Verified leg strengths so far (all concentration-safe via NaN-fill, all
orthogonal to the 3 survivors' news+PVcov+iv-skew):
    opt_ivmom20   SH 0.86  self_corr 0.39   (option IV momentum)   <- strongest
    opt_ivmom60   SH 0.69  self_corr 0.43
    anl_fwd_eyield SH 0.77 self_corr 0.68   (forward earnings yield)
    fund_valq     SH 0.56  self_corr 0.77
None alone clears SH 2.0, exactly like news/PV/skew did individually. The
survivors reached 2.0 by BLENDING uncorrelated legs. Round 28 does the same
with these orthogonal families PLUS fresh price signals that are NOT the
survivors' ts_covariance(returns,volume)/ts_av_diff(close) reversal:

  MOM   = classic 12-1 price momentum: ts_delta(close skipping last 21d)
  ARGHI = ts_arg_max(close,60): days since 60d high (momentum/reversal)
  PRANK = -ts_rank(close,60): price-position reversal
  PVCORR= -ts_corr(close, volume, 20): price-volume corr (distinct from cov)

All legs group_zscore(industry)-neutralized + NaN-filled. Sweep blends of the
orthogonal winners; the design avoids every survivor signal source so a
2.0 blend here is a genuinely new, uncorrelated alpha.
"""


def nf(x):
    return f"if_else(is_nan({x}), 0, {x})"


def gz(x):
    return f"group_zscore({x}, industry)"


IVM60 = "implied_volatility_mean_60"

# orthogonal winners (option momentum + analyst)
IVMOM = nf(gz(f"ts_delta({IVM60}, 20)"))
IVMOM60 = nf(gz(f"ts_delta({IVM60}, 60)"))
FEY = nf(gz("divide(est_epsr, close)"))

# fresh price signals (NOT cov(ret,vol) / av_diff(close))
MOM = nf(gz("ts_delta(close, 105) - ts_delta(close, 21)"))   # ~12-1 momentum
ARGHI = nf(gz("ts_arg_max(close, 60)"))                       # days since 60d high
PRANK = nf(gz("-ts_rank(close, 60)"))                         # price-position reversal
PVCORR = nf(gz("-ts_corr(close, volume, 20)"))               # price-vol corr


def _s(decay=8, trunc=0.05, neut="INDUSTRY"):
    return {"universe": "TOP3000", "decay": decay, "neutralization": neut,
            "truncation": trunc}


CANDIDATES = [
    # fresh price signals standalone (do any carry edge?)
    {"name": "px_mom121", "expression": MOM,
     "theme": "12-1 price momentum.", "settings": _s(8)},
    {"name": "px_arghigh", "expression": ARGHI,
     "theme": "days since 60d high.", "settings": _s(8)},
    {"name": "px_pvcorr", "expression": PVCORR,
     "theme": "neg price-volume corr.", "settings": _s(8)},

    # blend the orthogonal winners (option mom + analyst + price)
    {"name": "ivmom_fey", "expression": f"{IVMOM} + {FEY}",
     "theme": "IV-mom + fwd earnings yield.", "settings": _s(8)},
    {"name": "ivmom_fey_mom", "expression": f"{IVMOM} + {FEY} + {MOM}",
     "theme": "IV-mom + fwd-EY + price-mom.", "settings": _s(8)},
    {"name": "ivmom2_fey_pvcorr", "expression": f"2 * ({IVMOM}) + {FEY} + {PVCORR}",
     "theme": "2x IV-mom + fwd-EY + pv-corr.", "settings": _s(8)},
    {"name": "ivmom_fey_argpx",
     "expression": f"{IVMOM} + {FEY} + {ARGHI} + {PVCORR}",
     "theme": "IV-mom + fwd-EY + arg-high + pv-corr (4-leg).", "settings": _s(8)},
    {"name": "ivmom2_fey_mom_pvcorr",
     "expression": f"2 * ({IVMOM}) + {FEY} + {MOM} + {PVCORR}",
     "theme": "2x IV-mom + fwd-EY + price-mom + pv-corr.", "settings": _s(8)},
]
